"""Compare two published runs: identity splits/merges, ranks, free status, stack and picks.

    python tools/compare_bundles.py OLD NEW

OLD and NEW are bundle folders or state folders (a state folder's current.json
selects its bundle). Bundles from before provider identity have no per-model
routes; their route ownership is rebuilt with the old rule (tail slug only).
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.common import base_slug  # noqa: E402
from pipeline_common import PROVIDERS  # noqa: E402

TOP = 50


def resolve_bundle(path):
    path = Path(path)
    if (path / "current.json").exists():
        current = json.loads((path / "current.json").read_text(encoding="utf-8"))
        return path / current["bundle"]
    return path


def load(path):
    bundle = resolve_bundle(path)
    run_id = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["run_id"]
    read = lambda rel: json.loads((bundle / rel).read_text(encoding="utf-8"))  # noqa: E731
    a = read(f"analysis/{run_id}_analysis.json")
    r = read(f"reports/{run_id}_models.json")
    snap = read(f"raw/{run_id}_models.json")
    models = [m for m in a["models"] if not m.get("history_excluded")]
    owner = {}
    if any("routes" in m for m in models):
        for m in models:
            for route in m.get("routes", []):
                owner[(route["provider"], route["id"])] = m["slug"]
    else:  # pre-identity bundle: every route belonged to its tail slug
        slugs = {m["slug"] for m in models}
        for provider in PROVIDERS:
            for row in snap.get(provider) or []:
                rid = row.get("id") if isinstance(row, dict) else row
                if rid and base_slug(rid) in slugs:
                    owner[(provider, rid)] = base_slug(rid)
    for m in models:
        if m.get("aa_id"):
            owner[("aa", m["aa_id"])] = m["slug"]
    return {"run_id": run_id, "a": a, "r": r, "models": {m["slug"]: m for m in models}, "owner": owner}


def compare(old_path, new_path):
    old, new = load(old_path), load(new_path)
    shared = set(old["owner"]) & set(new["owner"])
    old_to_new, new_from_old = {}, {}
    for node in shared:
        old_to_new.setdefault(old["owner"][node], set()).add(new["owner"][node])
        new_from_old.setdefault(new["owner"][node], set()).add(old["owner"][node])
    splits = {o: sorted(n) for o, n in old_to_new.items() if len(n) > 1}
    merges = {n: sorted(o) for n, o in new_from_old.items() if len(o) > 1}
    renamed = {o: next(iter(n)) for o, n in old_to_new.items()
               if len(n) == 1 and next(iter(n)) != o and len(new_from_old[next(iter(n))]) == 1}

    def follow(slug):
        """Old slug -> new slug when the mapping is one-to-one, else the same slug."""
        targets = old_to_new.get(slug)
        return next(iter(targets)) if targets and len(targets) == 1 else slug
    ranks_old = {s: i for i, s in enumerate(old["r"].get("all_intel", []), 1)}
    ranks_new = {s: i for i, s in enumerate(new["r"].get("all_intel", []), 1)}
    rank_changes = []
    for slug, rank in sorted(ranks_old.items(), key=lambda kv: kv[1]):
        now = ranks_new.get(follow(slug))
        if rank <= TOP or (now or TOP + 1) <= TOP:
            if now != rank:
                rank_changes.append((slug, follow(slug), rank, now))
    for slug, rank in sorted(ranks_new.items(), key=lambda kv: kv[1]):
        if rank <= TOP and slug not in {follow(s) for s in ranks_old}:
            rank_changes.append((None, slug, None, rank))
    score_changes = []
    for slug, m in sorted(old["models"].items()):
        target = new["models"].get(follow(slug))
        if m.get("score") is not None and (target is None or target.get("score") != m["score"]):
            score_changes.append((slug, follow(slug), m["score"], target.get("score") if target else "entity gone"))

    def picks(side):
        stack = {t: v.get("rows", []) for t, v in (side["r"].get("ocf_stack") or {}).items()}
        practical = {f"{p['tier']}/{p['variant']}": (p.get("winner"), p.get("runner_up"))
                     for p in side["r"].get("ocf_practical") or []}
        return stack, practical
    stack_old, prac_old = picks(old)
    stack_new, prac_new = picks(new)
    return {
        "old": old["run_id"], "new": new["run_id"],
        "entities": (len(old["models"]), len(new["models"])),
        "added": sorted(set(new["models"]) - set(new_from_old) - set(old["models"])),
        "removed": sorted(set(old["models"]) - set(old_to_new) - set(new["models"])),
        "splits": splits, "merges": merges, "renamed": renamed,
        "ambiguous": [c for c in new["a"].get("identity_conflicts", []) if c.get("kind") == "ambiguous-tail"],
        "conflicts": new["a"].get("identity_conflicts", []),
        "rank_changes": rank_changes, "score_changes": score_changes,
        "free_status": (old["a"].get("free_status_counts", {}), new["a"].get("free_status_counts", {})),
        "stack": {t: ([follow(s) for s in stack_old.get(t, [])], stack_new.get(t, []))
                  for t in sorted(set(stack_old) | set(stack_new))},
        "practical": {k: (tuple(follow(s) if s else s for s in prac_old.get(k, (None, None))), prac_new.get(k))
                      for k in sorted(set(prac_old) | set(prac_new))},
    }


def format_report(d):
    out = [f"Compare {d['old']} -> {d['new']}", f"Entities: {d['entities'][0]} -> {d['entities'][1]}", ""]

    def section(title, rows):
        out.append(f"== {title} ({len(rows)})")
        out.extend(f"  {row}" for row in rows)
        if not rows:
            out.append("  none")
        out.append("")
    section("Splits (old entity -> new entities): reply 'keep split' or 'join' + evidence URL for each",
            [f"{o} -> {', '.join(n)}" for o, n in sorted(d["splits"].items())])
    section("Merges (old entities -> new entity)", [f"{', '.join(o)} -> {n}" for n, o in sorted(d["merges"].items())])
    section("Renamed", [f"{o} -> {n}" for o, n in sorted(d["renamed"].items())])
    section("Became ambiguous", [f"{c['route']} (candidates {', '.join(c['candidates'])})" for c in d["ambiguous"]])
    section("All identity conflicts", [f"{c['kind']}: {c.get('tail', '')} {', '.join(c.get('entities', []))}"
                                       + (f" (AA creator '{c.get('aa_vendor')}' vs route vendor '{c.get('route_vendor')}')"
                                          if c.get("kind") == "aa-creator-unaliased" else "")
                                       for c in d["conflicts"]])
    section("Added entities", d["added"])
    section("Removed entities", d["removed"])
    section(f"Rank changes in the top {TOP} (AA intelligence order)",
            [f"{o or '(new)'} -> {n}: {r0 or '-'} -> {r1 or 'out'}" for o, n, r0, r1 in d["rank_changes"]])
    section("Score changes", [f"{o} -> {n}: {s0} -> {s1}" for o, n, s0, s1 in d["score_changes"]])
    old_fs, new_fs = d["free_status"]
    section("Free-status counts", [f"{k}: {old_fs.get(k, 0)} -> {new_fs.get(k, 0)}" for k in sorted(set(old_fs) | set(new_fs))
                                   if old_fs.get(k, 0) != new_fs.get(k, 0)])
    section("Stack changes", [f"{t}: -{sorted(set(o) - set(n))} +{sorted(set(n) - set(o))}"
                              for t, (o, n) in d["stack"].items() if set(o) != set(n)])
    section("Practical pick changes", [f"{k}: {o} -> {n}" for k, (o, n) in d["practical"].items() if tuple(o or ()) != tuple(n or ())])
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("old")
    p.add_argument("new")
    args = p.parse_args()
    print(format_report(compare(args.old, args.new)))


if __name__ == "__main__":
    main()
