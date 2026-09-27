"""Maintain analysis/research.json evidence. Nothing is marked verified without `confirm`.

    python tools/refresh_evidence.py list [--days 7]
    python tools/refresh_evidence.py confirm <key> --checked YYYY-MM-DD [--expires YYYY-MM-DD] [--value N] [--note TEXT]
    python tools/refresh_evidence.py retire <key> [--note TEXT]
    python tools/refresh_evidence.py version-confirm --checked YYYY-MM-DD
    python tools/refresh_evidence.py version-new <version> --from YYYY-MM-DD --url URL [--checked YYYY-MM-DD]

Keys come from `list`: scores:<target_slug>:<benchmark> or inheritance:<target_slug>.
Every change is validated, written in the file's existing layout, and logged as a
dated line in docs/run-notes.md.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.registry import aa_version, entries, evidence_status, validate  # noqa: E402

REGISTRY = ROOT / "analysis" / "research.json"
NOTES = ROOT / "docs" / "run-notes.md"
DEFAULT_WINDOW = 7  # days of validity a confirmation grants (the current practice)


def dumps(registry):
    """research.json layout: one line per version range and score, inheritance entries expanded."""
    line = lambda value: json.dumps(value, ensure_ascii=False)  # noqa: E731
    parts = []
    for key, value in registry.items():
        if key in ("aa_index_versions", "scores") and isinstance(value, list):
            body = ",\n".join("    " + line(v) for v in value)
            parts.append(f"  {line(key)}: [\n{body}\n  ]" if value else f"  {line(key)}: []")
        elif key == "inheritance" and isinstance(value, list):
            items = [",\n".join(f"      {line(k)}: {line(v)}" for k, v in rec.items()) for rec in value]
            body = ",\n".join("    {\n" + item + "\n    }" for item in items)
            parts.append(f"  {line(key)}: [\n{body}\n  ]" if value else f"  {line(key)}: []")
        else:
            parts.append(f"  {line(key)}: {line(value)}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, registry):
    errors, _ = validate(registry)
    if errors:
        raise SystemExit("refusing to write an invalid registry: " + "; ".join(errors))
    Path(path).write_text(dumps(registry), encoding="utf-8", newline="\n")


def log(notes, day, text):
    notes = Path(notes)
    content = notes.read_text(encoding="utf-8")
    head = "# Run notes\n\n"
    if not content.startswith(head):
        raise SystemExit(f"{notes} does not start with '# Run notes'")
    notes.write_text(head + f"- {day} (evidence): {text}\n" + content[len(head):], encoding="utf-8", newline="\n")


def find(registry, key):
    for section, k, rec in entries(registry):
        if k == key:
            return section, rec
    raise SystemExit(f"unknown key {key!r}; run `list` for keys")


def urls(section, rec):
    if section == "scores":
        return [rec.get("url")]
    return list(rec.get("equivalence_urls") or []) + [rec.get("capability_url")]


def iso(value):
    datetime.date.fromisoformat(value)
    return value


def cmd_list(registry, days, today):
    status = evidence_status(registry, today, within=days)
    print(f"as of {today}: AA Intelligence Index {status['aa_index_version']}"
          + (f" (confirmed {status['aa_version_checked_at']})" if status["aa_version_checked_at"] else "")
          + (" — RE-CHECK DUE" if status["aa_version_recheck_due"] or status["aa_version_note"] else ""))
    for r in registry.get("aa_index_versions") or []:
        print(f"  version {r['version']}: {r['valid_from']} .. {r.get('valid_to') or 'open'}, checked {r['checked_at']}, {r['source_url']}")
    due = {i["key"] for i in status["expiring"]} | set(status["expired"])
    print(f"entries expiring within {days} days or expired ({len(due)}):")
    for section, key, rec in entries(registry):
        if key in due:
            state = "EXPIRED" if key in status["expired"] else "expires"
            print(f"  {key}  {state} {rec['expires_at']} (checked {rec['checked_at']})")
            for url in urls(section, rec):
                print(f"      re-check: {url}")
    others = [key for _, key, _ in entries(registry) if key not in due]
    if others:
        print("other entries: " + ", ".join(others))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--registry", default=str(REGISTRY))
    p.add_argument("--notes", default=str(NOTES))
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list")
    s.add_argument("--days", type=int, default=DEFAULT_WINDOW)
    s.add_argument("--today", type=iso, default=datetime.datetime.now(datetime.timezone.utc).date().isoformat())
    s = sub.add_parser("confirm")
    s.add_argument("key")
    s.add_argument("--checked", type=iso, required=True)
    s.add_argument("--expires", type=iso)
    s.add_argument("--value", type=float)
    s.add_argument("--note", default="")
    s = sub.add_parser("retire")
    s.add_argument("key")
    s.add_argument("--note", default="")
    s = sub.add_parser("version-confirm")
    s.add_argument("--checked", type=iso, required=True)
    s = sub.add_parser("version-new")
    s.add_argument("version")
    s.add_argument("--from", dest="start", type=iso, required=True)
    s.add_argument("--url", required=True)
    s.add_argument("--checked", type=iso)
    args = p.parse_args(argv)
    registry = load(args.registry)

    if args.cmd == "list":
        return cmd_list(registry, args.days, args.today)
    if args.cmd == "confirm":
        section, rec = find(registry, args.key)
        expires = args.expires or (datetime.date.fromisoformat(args.checked)
                                   + datetime.timedelta(days=DEFAULT_WINDOW)).isoformat()
        rec.update(checked_at=args.checked, expires_at=expires)
        change = f"checked {args.checked}, expires {expires}"
        if args.value is not None:
            if section != "scores":
                raise SystemExit("--value applies to scores entries only")
            old, rec["value"] = rec["value"], int(args.value) if args.value.is_integer() else args.value
            change += f", value {old} -> {rec['value']}"
        save(args.registry, registry)
        log(args.notes, args.checked, f"confirmed `{args.key}` ({change})." + (f" {args.note}" if args.note else ""))
    elif args.cmd == "retire":
        section, rec = find(registry, args.key)
        registry[section].remove(rec)
        save(args.registry, registry)
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        log(args.notes, today, f"retired `{args.key}`." + (f" {args.note}" if args.note else ""))
    elif args.cmd == "version-confirm":
        version, rng, note = aa_version(registry, args.checked)
        if rng is None or note:
            raise SystemExit(f"no aa_index_versions range covers {args.checked}; use version-new")
        rng["checked_at"] = args.checked
        save(args.registry, registry)
        log(args.notes, args.checked, f"AA Intelligence Index v{version} still current (range from {rng['valid_from']}).")
    elif args.cmd == "version-new":
        ranges = registry.setdefault("aa_index_versions", [])
        start = datetime.date.fromisoformat(args.start)
        for r in ranges:
            if r.get("valid_to") is None and r["valid_from"] < args.start:
                r["valid_to"] = (start - datetime.timedelta(days=1)).isoformat()
        ranges.append({"version": args.version, "valid_from": args.start, "valid_to": None,
                       "source_url": args.url, "checked_at": args.checked or args.start})
        save(args.registry, registry)
        stale = [key for _, key, rec in entries(registry) if rec.get("version") not in (args.version, None)
                 and rec.get("benchmark", "aa-intelligence-index") == "aa-intelligence-index"]
        log(args.notes, args.checked or args.start,
            f"AA Intelligence Index v{args.version} from {args.start} ({args.url}); entries on older versions stop applying"
            + (f": {', '.join(stale)}" if stale else "") + ".")
        if stale:
            print("now ineligible (old AA version): " + ", ".join(stale))
    print(f"updated {args.registry}; logged in {args.notes}")


if __name__ == "__main__":
    main()
