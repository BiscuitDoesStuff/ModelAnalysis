"""3. Report — dated MD + XLSX + JSON per run (all providers). On-use. Keeps latest only."""
import json, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REP = os.path.join(ROOT, "reports")
os.makedirs(REP, exist_ok=True)

LIMITS = [
    ("NVIDIA", "~40 req/min per model, no daily cap (best for agents)", "Trial/prototyping"),
    ("Google AI Studio", "Flash ~20/day; Flash-Lite ~500/day; Pro needs billing", "May train on prompts"),
    ("OpenCode Zen", "Free models limited time", "Muse Spark: Meta trains; check terms"),
    ("ZenMux", "Select models free, rate-limited, limited time", "Standard terms"),
    ("OpenRouter", "~50 req/day free (~1,000/day after $10 credits)", "Some hosts may log"),
]

def opencode_ids(or_id):
    return f"openrouter/{or_id}"

def prune_reports(keep_stamps):
    for f in glob.glob(os.path.join(REP, "*_summary.md")) + glob.glob(os.path.join(REP, "*_models.json")) + glob.glob(os.path.join(REP, "*_models.xlsx")):
        bn = os.path.basename(f)
        if not any(bn.startswith(s) for s in keep_stamps):
            os.remove(f)
            print(f"pruned report {os.path.basename(f)}")

def main():
    afiles = sorted(glob.glob(os.path.join(ROOT, "analysis", "*_analysis.json")), key=os.path.getmtime)
    if not afiles:
        print("run analysis first")
        return
    with open(afiles[-1], encoding="utf-8") as f:
        a = json.load(f)
    stamp = a.get("stamp", a.get("day", "unknown"))
    day = a.get("day", stamp[:10])
    L = [f"# Model Watch — {stamp} (on-use)\n",
         f"OR {a['total_openrouter']} | OR free strict {a['free_count']} | OAI {a['total_openai']} | ANT {a['total_anthropic']} | AA {a['total_aa']} | AA $0 unverified {a['aa_free_count']} | New {a['new_total']} | Removed {a['removed_total']} | History days {len(a.get('history_days', []))}\n",
         "\n## Combined free rank (OR strict-$0 x AA score)\n"]
    for r in a.get("combined_free_rank", [])[:20]:
        L.append(f"- `{r['id']}` — AA {r['aa_score']} ({r['aa_match'] or 'unscored'}) — ctx {r['context']}\n")
    L += ["\n## Free — OpenRouter strict $0 (+ OpenCode ID)\n"]
    for i in a["free_ids"][:100]:
        L.append(f"- `{i}` → `{opencode_ids(i)}`\n")
    L += ["\n## AA Top 15 by Intelligence Index (cost blended $/1M)\n"]
    for r in a["aa_top15"]:
        L.append(f"- {r['name']} (`{r['id']}`) — {r['score']} — {r['creator']} — blended {r.get('cost_blended')}\n")
    L += ["\n## Anthropic native IDs\n"] + [f"- `{i}`\n" for i in a["anthropic_ids"]]
    L += ["\n## OpenAI retired (shutdown_date set)\n"] + [f"- `{i}`\n" for i in a["openai_retired"][:30]]
    L += ["\n## Diff vs history\nNew:\n"] + [f"- `{i}`\n" for i in a["new_ids_vs_history"]]
    L += ["Removed:\n"] + [f"- `{i}`\n" for i in a.get("removed_ids_vs_history", [])]
    L += ["\n## Free verification tiers\n- `free_ids`: OR $0 prompt+completion or `:free`, text-only output, routers (`openrouter/*`) excluded.\n- `aa_free_unverified`: AA $0 pricing — billing/account NOT checked.\n"]
    L += ["\n## Provider limits (hand-maintained, last checked 2026-09-25 — verify in docs)\n| Provider | Limits | Data use |\n|---|---|---|\n"]
    for p, lim, d in LIMITS:
        L.append(f"| {p} | {lim} | {d} |\n")
    L += ["\n_Source: on-use snapshot. OpenCode per-model compat not verified (`opencode` not on PATH)._ \n"]
    with open(os.path.join(REP, f"{stamp}_summary.md"), "w", encoding="utf-8") as f:
        f.write("".join(L))
    with open(os.path.join(REP, f"{stamp}_models.json"), "w", encoding="utf-8") as f:
        json.dump(a, f, indent=1)
    try:
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "summary"
        for k in ["stamp", "day", "total_openrouter", "free_count", "total_openai", "total_anthropic", "total_aa", "aa_free_count", "new_total", "removed_total"]:
            ws.append([k, a.get(k)])
        w2 = wb.create_sheet("free_rank"); w2.append(["or_id", "opencode_id", "aa_score", "aa_match", "context"])
        for r in a.get("combined_free_rank", []):
            w2.append([r["id"], opencode_ids(r["id"]), r["aa_score"], r["aa_match"], r["context"]])
        w3 = wb.create_sheet("aa_top15"); w3.append(["id", "name", "score", "creator", "cost_blended"])
        for r in a["aa_top15"]:
            w3.append([r["id"], r["name"], r["score"], r["creator"], r.get("cost_blended")])
        w4 = wb.create_sheet("diff"); w4.append(["direction", "id"])
        for i in a["new_ids_vs_history"]:
            w4.append(["added", i])
        for i in a.get("removed_ids_vs_history", []):
            w4.append(["removed", i])
        wb.save(os.path.join(REP, f"{stamp}_models.xlsx"))
        x = "xlsx ok"
    except Exception as e:
        x = f"xlsx skipped: {e}"
    prune_reports([os.path.basename(f).replace("_analysis.json", "") for f in afiles[-1:]])
    print(f"report {stamp} written ({x})")

if __name__ == "__main__":
    main()
