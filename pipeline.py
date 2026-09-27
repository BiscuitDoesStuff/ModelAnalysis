"""Run the six stages with pinned inputs and publish a validated local bundle."""
import argparse
from contextlib import contextmanager
import datetime as dt
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import time
from urllib.parse import unquote, urlsplit

from pipeline_common import (ROOT, SCHEMA_VERSION, PROVIDERS, SOURCES, atomic_json,
                             check_identity, load_config, new_run_id, safe_error,
                             source_status, utc_now, validate_run_id)


@contextmanager
def writer_lock(state_dir):
    """OS-owned lock: a crashed process cannot leave a stale logical lock."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_dir / "writer.lock", "a+b") as f:
        f.seek(0, 2)
        if not f.tell():
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another pipeline writer is running") from exc
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            if attrs["id"] in self.ids:
                raise ValueError("Duplicate HTML id: " + attrs["id"])
            self.ids.add(attrs["id"])
        if tag in ("a", "link", "script", "img"):
            value = attrs.get("href") if tag in ("a", "link") else attrs.get("src")
            if value:
                self.links.append(value)


def validate_bundle(bundle, run_id):
    bundle = Path(bundle)
    raw = bundle / "raw" / f"{run_id}_models.json"
    analysis = bundle / "analysis" / f"{run_id}_analysis.json"
    report = bundle / "reports" / f"{run_id}_models.json"
    site = bundle / "reports" / f"{run_id}_site"
    for label, path in (("snapshot", raw), ("analysis", analysis), ("report", report), ("site", site / "data.json")):
        check_identity(json.loads(path.read_text(encoding="utf-8")), run_id, label)
    for suffix in ("summary.md", "models.xlsx", "report.html"):
        p = bundle / "reports" / f"{run_id}_{suffix}"
        if not p.is_file() or not p.stat().st_size:
            raise ValueError("Missing report artifact: " + p.name)
    a = json.loads(analysis.read_text(encoding="utf-8"))
    from reports.build_site import model_filename
    wanted = {model_filename(m["slug"]) for m in a["models"] if not m.get("router")}
    actual = {p.name for p in (site / "models").glob("*.html")}
    if wanted != actual:
        raise ValueError("Model-page coverage mismatch")
    parsed = {}
    for p in site.rglob("*.html"):
        parser = Links()
        parser.feed(p.read_text(encoding="utf-8"))
        parsed[p.resolve()] = parser
    for p, parser in parsed.items():
        for href in parser.links:
            url = urlsplit(href)
            if url.scheme or url.netloc:
                continue
            target = (p.parent / unquote(url.path)).resolve() if url.path else p
            if not target.is_relative_to(site.resolve()) or not target.is_file():
                raise ValueError(f"Broken internal link in {p.name}: {href}")
            if url.fragment and target in parsed and unquote(url.fragment) not in parsed[target].ids:
                raise ValueError(f"Broken fragment in {p.name}: {href}")
    return {"model_pages": len(actual), "html_pages": len(parsed), "validated_at": utc_now()}


def _hook(callback, point):
    if callback:
        callback(point)


def publish_bundle(state_dir, staging, manifest, db_path, failpoint=None):
    from analysis.history import publish_run
    state_dir, staging = Path(state_dir), Path(staging)
    destination = state_dir / "bundles" / manifest["run_id"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = dict(manifest, state="validated", commit_requested=True)
    atomic_json(staging / "manifest.json", manifest)
    _hook(failpoint, "before_finalize")
    os.replace(staging, destination)
    _hook(failpoint, "after_finalize")
    # Pointer is the filesystem commit record; pending DB state is reconciled
    # before any subsequent run may calculate a baseline.
    pointer = {"schema_version": SCHEMA_VERSION, "run_id": manifest["run_id"],
               "bundle": "bundles/" + manifest["run_id"], "started_at": manifest["started_at"],
               "published_at": utc_now()}
    atomic_json(state_dir / "current.json", pointer)
    _hook(failpoint, "after_pointer")
    publish_run(str(db_path), manifest["run_id"])
    _hook(failpoint, "after_history")
    manifest.update(state="published", published_at=pointer["published_at"])
    atomic_json(destination / "manifest.json", manifest)
    return destination


def recover_publication(state_dir, db_path):
    """Finish only validated, explicitly committed bundles after interruption."""
    from analysis.history import publish_run
    state_dir = Path(state_dir)
    current = json.loads((state_dir / "current.json").read_text(encoding="utf-8")) if (state_dir / "current.json").exists() else {}
    manifests = [(json.loads(path.read_text(encoding="utf-8")), path)
                 for path in (state_dir / "bundles").glob("*/manifest.json")]
    for manifest, path in sorted(manifests, key=lambda item: (item[0]["started_at"], item[0]["run_id"])):
        if manifest.get("state") != "validated" or not manifest.get("commit_requested"):
            continue
        run_id = validate_run_id(manifest["run_id"])
        validate_bundle(path.parent, run_id)
        if not current or (current.get("started_at", ""), current["run_id"]) <= (manifest["started_at"], run_id):
            current = {"schema_version": SCHEMA_VERSION, "run_id": run_id,
                       "bundle": "bundles/" + run_id, "started_at": manifest["started_at"],
                       "published_at": utc_now()}
            atomic_json(state_dir / "current.json", current)
        publish_run(str(db_path), run_id)
        manifest.update(state="published", published_at=utc_now())
        atomic_json(path, manifest)


def prune_artifacts(state_dir, config):
    """Delete only manifested generated bundles; never legacy/user files."""
    state_dir = Path(state_dir)
    pointer = json.loads((state_dir / "current.json").read_text(encoding="utf-8"))
    published = []
    for p in (state_dir / "bundles").glob("*/manifest.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        if m.get("state") == "published" and p.parent.name == m.get("run_id"):
            published.append((m.get("published_at", ""), p.parent))
    protected = {p for _, p in sorted(published, reverse=True)[:config["artifact_bundles"]]}
    protected.add((state_dir / pointer["bundle"]))
    for _, path in published:
        if path not in protected:
            shutil.rmtree(path)
    # Under the writer lock no staging run is in progress, so an old `pending`
    # manifest is a hard-killed run that never reached its failure handler.
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=config["failed_days"])
    for p in (state_dir / "staging").glob("*/manifest.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        if m.get("state") in ("failed", "pending") and dt.datetime.fromisoformat(m["started_at"]) < cutoff:
            shutil.rmtree(p.parent)


def _legacy_health(snapshot):
    # Lists prove some usable data, not that a historical endpoint was fully
    # paginated. Imported legacy snapshots never establish loss baselines.
    result = {}
    for src in SOURCES:
        value = snapshot.get(src)
        if isinstance(value, dict) and ("skipped" in value or "error" in value):
            result[src] = source_status("skipped" if "skipped" in value else "failed", scope="legacy-unverified",
                                        reason="Imported source was unavailable")
        else:
            result[src] = source_status("partial", len(value) if isinstance(value, list) else 0,
                                        scope="legacy-unverified", reason="Imported snapshot has no completeness evidence")
    return result


def run(*, state_dir=None, db_path=None, config=None, snapshot_path=None, websites_path=None, failpoint=None):
    from analysis import analyze
    from analysis.history import prepare_run, prune_history
    from reports import build_report, build_site
    from alerts import check_churn
    from retrieval import fetch_models, fetch_websites
    cfg = config or load_config()
    state_dir = Path(state_dir or ROOT / "runs").resolve()
    db_path = Path(db_path or ROOT / "analysis" / "store.sqlite").resolve()
    with writer_lock(state_dir):
        recover_publication(state_dir, db_path)
        run_id, started_at = new_run_id(), utc_now()
        staging = state_dir / "staging" / run_id
        for part in ("raw", "analysis", "reports"):
            (staging / part).mkdir(parents=True, exist_ok=True)
        manifest = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "started_at": started_at,
                    "day": started_at[:10], "state": "pending", "stages": {},
                    "artifacts": {"snapshot": f"raw/{run_id}_models.json",
                                  "analysis": f"analysis/{run_id}_analysis.json",
                                  "report": f"reports/{run_id}_models.json",
                                  "site": f"reports/{run_id}_site/index.html"}}
        atomic_json(staging / "manifest.json", manifest)

        def stage(name, job):
            begin = time.monotonic()
            print(f"[{name}] start {utc_now()}")
            _hook(failpoint, name)
            result = job()
            manifest["stages"][name] = {"status": "complete", "seconds": round(time.monotonic() - begin, 3)}
            atomic_json(staging / "manifest.json", manifest)
            print(f"[{name}] done in {manifest['stages'][name]['seconds']}s")
            return result

        try:
            raw = staging / "raw" / f"{run_id}_models.json"
            if snapshot_path:
                snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
                origin_id = snap.get("run_id") or snap.get("retrieved_at")
                snap.update(run_id=run_id, retrieved_at=run_id, started_at=started_at,
                            schema_version=SCHEMA_VERSION, imported_from=origin_id)
                snap.setdefault("source_health", _legacy_health(snap))
                stage("fetch", lambda: atomic_json(raw, snap))
            else:
                stage("fetch", lambda: fetch_models.main(staging / "raw", run_id, started_at, cfg))
                snap = json.loads(raw.read_text(encoding="utf-8"))
                origin_id = run_id
            check_identity(snap, run_id, "snapshot")
            if not any(isinstance(snap.get(s), list) and snap[s] and
                       snap["source_health"].get(s, {}).get("status") in ("complete", "partial") for s in PROVIDERS):
                raise ValueError("No usable provider catalog; keeping the current report")
            web = staging / "raw" / f"{run_id}_websites.json"
            if snapshot_path:
                if websites_path:
                    w = json.loads(Path(websites_path).read_text(encoding="utf-8"))
                    check_identity(w, origin_id, "imported websites")
                    w.update(run_id=run_id, retrieved_at=run_id)
                else:
                    w = {"run_id": run_id, "retrieved_at": run_id, "source_health": {},
                         "allowlist": [], "benchlm_md": {}, "llmstats": {}, "vals": {}}
                stage("websites", lambda: atomic_json(web, w))
            else:
                stage("websites", lambda: fetch_websites.main(raw, staging / "raw", state_dir / "cache", cfg))
            analysis_path = stage("analyze", lambda: analyze.main(raw, staging / "analysis", web))
            a = json.loads(Path(analysis_path).read_text(encoding="utf-8"))
            churn = prepare_run(str(db_path), snap, a["models"], run_id, started_at, snap["source_health"])
            a["churn"] = churn
            a["source_health"] = {**snap["source_health"], **churn.get("source_health", {})}
            for src, baseline in churn.get("baselines", {}).items():
                if src in a["source_health"]:
                    a["source_health"][src]["baseline"] = baseline
            # Legacy broad disappeared fields remain empty; schema v3 churn
            # carries route-level classifications and cannot be mistaken for v2.
            a["history_semantics"] = "published-route-snapshots-v1"
            atomic_json(analysis_path, a)
            manifest["coverage"] = "partial" if any(h.get("status") in ("partial", "failed") for h in a["source_health"].values()) else "complete"
            stage("report", lambda: build_report.main(analysis_path, staging / "reports"))
            stage("site", lambda: build_site.main(analysis_path, staging / "reports"))
            report_path = staging / "reports" / f"{run_id}_models.json"
            stage("alerts", lambda: check_churn.main(report_path, staging / "reports"))
            manifest["validation"] = stage("validate", lambda: validate_bundle(staging, run_id))
            destination = publish_bundle(state_dir, staging, manifest, db_path, failpoint)
        except BaseException as exc:
            # BaseException: Ctrl+C is a failure too, so its staging ages out.
            if staging.exists():
                manifest.update(state="failed", error=safe_error(exc) or type(exc).__name__)
                atomic_json(staging / "manifest.json", manifest)
            raise
        # Cleanup failures must not roll back an already published run.
        try:
            _hook(failpoint, "cleanup")
            prune_history(str(db_path), started_at, cfg["run_days"], cfg["daily_days"])
            prune_artifacts(state_dir, cfg)
        except Exception as exc:
            print("Published successfully; cleanup deferred: " + safe_error(exc))
        print(f"Published {run_id} ({manifest['coverage']} coverage): {destination}")
        return destination


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", help="Optional JSON configuration")
    p.add_argument("--state-dir", help="Bundles, current manifest, cache and staging location")
    p.add_argument("--db", help="History database (default analysis/store.sqlite)")
    p.add_argument("--snapshot", help="Offline replay of an existing snapshot; performs no network calls")
    p.add_argument("--websites", help="Matching website snapshot for offline replay")
    p.add_argument("--recover", action="store_true", help="Finish interrupted publication without fetching")
    args = p.parse_args()
    if args.websites and not args.snapshot:
        p.error("--websites requires --snapshot")
    if args.recover:
        state = Path(args.state_dir or ROOT / "runs")
        with writer_lock(state):
            recover_publication(state, args.db or ROOT / "analysis" / "store.sqlite")
        return
    run(state_dir=args.state_dir, db_path=args.db, config=load_config(args.config),
        snapshot_path=args.snapshot, websites_path=args.websites)


if __name__ == "__main__":
    main()
