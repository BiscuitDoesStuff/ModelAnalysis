"""Record a trimmed, key-free test fixture from a real published bundle.

    python tools/record_fixture.py                 # from runs/current.json
    python tools/record_fixture.py --bundle runs/bundles/<run_id>

Writes tests/fixtures/recorded_snapshot.json, recorded_websites.json and
recorded_research.json (a copy of analysis/research.json). The snapshot pins
the bundle's evidence day, so CI replays stay stable when the registry changes.

Only rows for a selected set of models are kept (registry targets, free-status
samples, stack and practical picks, effort variants, benchmark joins,
bench-only rows, a router). Nothing is written unless the source bundle has
complete coverage, the secret scan is clean, and a replay of the trimmed
fixture passes smoke and the golden coverage check.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from analysis.common import base_slug, norm  # noqa: E402
from pipeline_common import PROVIDERS, SOURCES, resolve_credentials  # noqa: E402
import audit_provenance  # noqa: E402
import ci  # noqa: E402

PREFIX = "recorded"
MD_EXCERPT = 1500  # BenchLM page text kept per model; enough to render, far from the full page
SECRET_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9])nvapi-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|x-api-key|token)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{16,}"),
]
QUERY_SECRET = re.compile(r"(?i)(authorization|api[_-]?key|token|cursor)=([^\s&\"]+)")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def top(rows, n, key=lambda m: m.get("score") if m.get("score") is not None else -1):
    return sorted(rows, key=lambda m: (-key(m), m.get("slug", "")))[:n]


def select_slugs(models, report, registry):
    """Canonical slugs the fixture keeps: enough to give every smoke check content."""
    by_slug = {m["slug"]: m for m in models}
    keep = set()
    for rec in registry.get("scores", []):
        keep.add(rec["target_slug"])
    for rec in registry.get("inheritance", []):
        keep.update((rec["target_slug"], rec["source_slug"]))

    def status(s):
        return [m for m in models if m.get("free_status") == s and "__" not in m["slug"]]
    verified = status("verified")
    zen_free = [m for m in verified if m.get("fallback_provider") == "zen" and "free" in m.get("fallback_id", "")]
    keep.update(m["slug"] for m in top(zen_free, 6))
    keep.update(m["slug"] for m in top([m for m in verified if "or:strict-free" in m.get("free_evidence", [])], 6))
    keep.update(m["slug"] for m in top(status("provisional-l1"), 4))
    keep.update(m["slug"] for m in top(status("provisional-l0"), 4))
    if "claudeopus5medium" in by_slug:
        keep.add("claudeopus5medium")
    for tier in (report.get("ocf_stack") or {}).values():
        keep.update(s for s in tier.get("rows", []) if isinstance(s, str))
    for pick in report.get("ocf_practical") or []:
        keep.update(pick.get(f) for f in ("winner", "runner_up") if isinstance(pick.get(f), str))
    keep.update(m["slug"] for m in top([m for m in models if m.get("variant")], 10))
    keep.update(m["slug"] for m in top([m for m in models if m.get("benchlm")], 5))
    keep.update(m["slug"] for m in top([m for m in models if m.get("llmstats_api") or m.get("llmstats_rank")], 5))
    keep.update(m["slug"] for m in [m for m in models if m.get("bench_only") and m.get("benchlm")][:2])
    keep.update(m["slug"] for m in [m for m in models if m.get("bench_only") and not m.get("benchlm")][:2])
    keep.update(m["slug"] for m in [m for m in models if m.get("router")][:1])
    keep.update(m["slug"] for m in [m for m in models if m.get("deprecated_upstream")][:2])
    keep.update(m["slug"] for m in [m for m in models if m.get("modality_status") == "modality-unverified"][:1])
    # Derived estimate rows (`<target>__<variant>`) come from their base entity.
    return {s.split("__")[0] for s in keep if s}


def tails_of(models, keys):
    """Raw rows are found by tail; split entities have `<tail>.<vendor>` slugs."""
    return {(m.get("identity") or {}).get("tail") or m["slug"].split(".")[0]
            for m in models if m["slug"].split("__")[0] in keys}


def join_keys(models, keys):
    """Every name a benchmark row may join on for a kept model (mirrors crosswalk candidates)."""
    out = set(keys) | tails_of(models, keys)
    for m in models:
        if m["slug"].split("__")[0] in keys:
            out.update(norm(x) for x in (m.get("name"), m.get("aa_id"), (m.get("or_id") or "").split("/")[-1]))
    out.discard("")
    return out


def trim_snapshot(snap, keys, joins):
    out = {k: snap[k] for k in ("retrieved_at", "run_id", "started_at", "schema_version") if k in snap}
    kept = lambda mid: base_slug(mid) in keys  # noqa: E731
    for src in PROVIDERS:
        value = snap.get(src)
        # Long catalog descriptions are read by no stage; leave them out of a public fixture.
        out[src] = ([{k: v for k, v in m.items() if k != "description"} for m in value if kept(m.get("id", ""))]
                    if isinstance(value, list) else value)
    md = snap.get("modelsdev")
    out["modelsdev"] = [m for m in md if kept(m.get("id", ""))] if isinstance(md, list) else md
    aa = snap.get("aa")
    if isinstance(aa, dict):
        out["aa"] = {k: v for k, v in aa.items() if k != "data" and len(json.dumps(v)) < 4096}
        out["aa"]["data"] = [m for m in aa.get("data", []) if kept(m.get("slug") or m.get("id", ""))]
    else:
        out["aa"] = aa
    bench = snap.get("benchlm")
    if isinstance(bench, dict):
        hit = lambda m: isinstance(m, dict) and (norm(m.get("model")) in joins or kept(m.get("model", "")))  # noqa: E731
        out["benchlm"] = {"leaderboard": [m for m in bench.get("leaderboard", []) if hit(m)],
                          "pricing": [m for m in bench.get("pricing", []) if hit(m)],
                          "meta": bench.get("meta", {})}
    else:
        out["benchlm"] = bench
    llm = snap.get("llmstats")
    if isinstance(llm, dict) and isinstance(llm.get("models"), list):
        models = [m for m in llm["models"] if norm(m.get("id")) in joins or norm(m.get("name")) in joins
                  or kept(m.get("id") or "")]
        rankings = {cat: [r for r in rows if kept(r.get("model_id") or r.get("model_name") or "")
                          or norm(r.get("model_id")) in joins]
                    for cat, rows in (llm.get("rankings") or {}).items()}
        details = {lid: d for lid, d in (llm.get("details") or {}).items()
                   if norm(lid) in joins or norm((d or {}).get("name")) in joins}
        used = {s.get("bench") for d in details.values() for s in (d or {}).get("scores", [])}
        benchmarks = [b for b in llm.get("benchmarks", []) if b.get("id") in used] or llm.get("benchmarks", [])[:5]
        out["llmstats"] = {"models": models, "model_count": len(models), "benchmarks": benchmarks,
                           "benchmark_count": len(benchmarks), "rankings": rankings, "details": details,
                           "meta": llm.get("meta", {})}
    else:
        out["llmstats"] = llm
    vals = snap.get("vals")
    if isinstance(vals, dict) and isinstance(vals.get("models"), list):
        out["vals"] = dict(vals, models=[m for m in vals["models"] if norm(m.get("name")) in joins][:10])
    else:
        out["vals"] = vals
    health = json.loads(json.dumps(snap.get("source_health", {})))
    for src, h in health.items():
        value = out.get(src)
        count = (len(value) if isinstance(value, list) else len(value.get("data", [])) if src == "aa"
                 else len(value.get("leaderboard", [])) if src == "benchlm"
                 else len(value.get("models", [])) if isinstance(value, dict) and isinstance(value.get("models"), list)
                 else h.get("count", 0))
        h["count"] = count
    out["source_health"] = health
    return out


def trim_websites(web, keys):
    out = {k: web[k] for k in ("retrieved_at", "run_id", "schema_version", "source_health") if k in web}
    out["allowlist"] = [a for a in web.get("allowlist", []) if a.get("slug") in keys]
    for src in ("benchlm_md", "llmstats", "vals"):
        pages = {k: dict(v) for k, v in (web.get(src) or {}).items() if k in keys}
        for page in pages.values():
            if isinstance(page.get("md"), str):
                page["md"] = page["md"][:MD_EXCERPT]
        out[src] = pages
    return out


def scrub(value, secrets):
    """Redact credential values and key-like query parameters in every string."""
    if isinstance(value, dict):
        return {k: scrub(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secrets) for v in value]
    if isinstance(value, str):
        for s in secrets:
            value = value.replace(s, "[redacted]")
        return QUERY_SECRET.sub(r"\1=[redacted]", value)
    return value


def secret_scan(value, secrets, path="$"):
    """JSON paths whose strings still look like credentials (values never printed)."""
    hits = []
    if isinstance(value, dict):
        for k, v in value.items():
            hits += secret_scan(v, secrets, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            hits += secret_scan(v, secrets, f"{path}[{i}]")
    elif isinstance(value, str):
        if any(s in value for s in secrets) or any(p.search(value) for p in SECRET_PATTERNS):
            hits.append(path)
    return hits


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                          encoding="utf-8", newline="\n")


def record(bundle, out_dir, registry_path=None, secrets=None):
    """Build, scan and verify the fixture in a temp dir, then copy it to out_dir. Returns 0 on success."""
    bundle = Path(bundle)
    manifest = load(bundle / "manifest.json")
    run_id = manifest["run_id"]
    snap = load(bundle / "raw" / f"{run_id}_models.json")
    web_path = bundle / "raw" / f"{run_id}_websites.json"
    web = load(web_path) if web_path.exists() else None
    analysis = load(bundle / "analysis" / f"{run_id}_analysis.json")
    report = load(bundle / "reports" / f"{run_id}_models.json")
    registry = load(registry_path or ROOT / "analysis" / "research.json")

    bad = {s: h.get("status") for s, h in snap.get("source_health", {}).items() if h.get("status") != "complete"}
    missing = set(SOURCES) - set(snap.get("source_health", {}))
    if bad or missing:
        print(f"refusing: bundle {run_id} is not complete coverage "
              f"({', '.join(f'{s}={v}' for s, v in sorted(bad.items())) or 'missing ' + ', '.join(sorted(missing))}). "
              "Record from a run where every source is complete (LLM Stats needs quota).")
        return 1

    keys = select_slugs(analysis["models"], report, registry)
    joins = join_keys(analysis["models"], keys)
    fixture = {"kind": "recorded", "recorded_from": run_id, "as_of": analysis["day"],
               "registry": f"{PREFIX}_research.json"}
    trimmed = trim_snapshot(snap, tails_of(analysis["models"], keys), joins)
    trimmed["fixture"] = fixture
    trimmed_web = None
    if web is not None:
        trimmed_web = trim_websites(web, keys)
        fixture["websites"] = f"{PREFIX}_websites.json"

    if secrets is None:
        secrets = [v for v in resolve_credentials().values() if v and len(v) >= 8]
    files = {f"{PREFIX}_snapshot.json": scrub(trimmed, secrets), f"{PREFIX}_research.json": registry}
    if trimmed_web is not None:
        files[f"{PREFIX}_websites.json"] = scrub(trimmed_web, secrets)
    hits = [f"{name}: {p}" for name, value in files.items() for p in secret_scan(value, secrets)]
    if hits:
        print("secret scan: FOUND key-like strings, nothing written:\n  " + "\n  ".join(hits[:20]))
        return 1
    print("secret scan: clean")

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "fixture"
        stage.mkdir()
        for name, value in files.items():
            write_json(stage / name, value)
        print(f"kept {len(keys)} models from {len(analysis['models'])}; replaying the trimmed fixture...")
        try:
            replayed = ci.replay(stage / f"{PREFIX}_snapshot.json", Path(tmp) / "state", quiet=True)
            smoke = subprocess.run(ci.PY + ["tests/smoke.py", "--bundle", str(replayed)], cwd=ROOT, env=ci.ENV,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
        except subprocess.CalledProcessError as exc:
            print(f"replay failed (exit {exc.returncode}); nothing written")
            return 1
        failures = [line for line in smoke.stdout.splitlines() if line.startswith("FAIL")]
        if smoke.returncode or failures:
            print("smoke failed on the trimmed fixture; nothing written:\n  " + "\n  ".join(failures or [smoke.stdout[-2000:]]))
            return 1
        gaps = ci.golden_coverage(replayed, recorded=True)
        if gaps:
            print("trimmed fixture lacks: " + ", ".join(gaps) + "; nothing written")
            return 1
        trace = audit_provenance.audit(replayed, 0)
        if trace["orphans"] or trace["mismatches"] or trace["wrong_scale"]:
            print("provenance audit failed on the trimmed fixture; nothing written: "
                  + "; ".join((trace["orphans"] + trace["mismatches"] + trace["wrong_scale"])[:5]))
            return 1
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copyfile(stage / name, out_dir / name)
    for name in files:
        print(f"wrote {out_dir / name} ({(out_dir / name).stat().st_size / 1024:.0f} KB)")
    print(f"fixture verified: smoke 0 failures, coverage OK (as of {fixture['as_of']}, from {run_id})")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bundle", help="Published bundle directory (default: runs/current.json)")
    p.add_argument("--out", default=str(ROOT / "tests" / "fixtures"), help="Output directory")
    args = p.parse_args()
    bundle = args.bundle
    if not bundle:
        current = load(ROOT / "runs" / "current.json")
        bundle = ROOT / "runs" / current["bundle"]
    return record(bundle, args.out)


if __name__ == "__main__":
    sys.exit(main())
