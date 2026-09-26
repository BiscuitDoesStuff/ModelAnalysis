"""3. Report — 9-section OCF views: MD + XLSX + JSON per run. On-use. Keeps latest only."""
import json, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REP = os.path.join(ROOT, "reports")
os.makedirs(REP, exist_ok=True)

MD_CAP = 20
TIERS = ["max", "high", "medium"]
TIER_LABEL = {"max": "Max (50+)", "high": "High (40+)", "medium": "Medium/General (30+)"}
VARIANTS = {"OCF": set(), "OF": {"C"}, "CF": {"O"}, "F": {"O", "C"}}
OCF = {"O", "C", "F"}


def opencode_ids(or_id):
    if not or_id:
        return ""
    return or_id if or_id.startswith("openrouter/") else f"openrouter/{or_id}"


def hier_key(r):
    s = r.get("score")
    x = r.get("ratio")
    return (-(s if s is not None else -1), -(x if x is not None else -1))


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def prune_reports(keep_stamps):
    for f in glob.glob(os.path.join(REP, "*_summary.md")) + glob.glob(os.path.join(REP, "*_models.json")) + glob.glob(os.path.join(REP, "*_models.xlsx")):
        bn = os.path.basename(f)
        if not any(bn.startswith(s) for s in keep_stamps):
            os.remove(f)
            print(f"pruned report {os.path.basename(f)}")


def build_sections(a):
    models = a.get("models", [])
    routers = [m["id"] for m in models if m.get("router")]
    models = [m for m in models if not m.get("router")]
    ocf = [m for m in models if set(m.get("groups", [])) & OCF]

    all_intel = sorted(models, key=lambda r: (-(r["score"] if r["score"] is not None else -1)))
    costed = sorted([m for m in models if m.get("cost_blended") is not None],
                    key=lambda r: r["cost_blended"])
    uncosted = [m for m in models if m.get("cost_blended") is None]
    paid_ratio = sorted([m for m in models if not m.get("free") and m.get("ratio") is not None],
                        key=lambda r: -r["ratio"])
    free_block = sorted([m for m in models if m.get("free") and m.get("score") is not None],
                        key=lambda r: -r["score"])
    free_unscored = [m for m in models if m.get("free") and m.get("score") is None]
    unratable = [m for m in models if not m.get("free") and m.get("ratio") is None]

    ocf_intel = [m for m in all_intel if m in ocf]
    ocf_costed = [m for m in costed if m in ocf]
    ocf_uncosted = [m for m in uncosted if m in ocf]
    ocf_ratio = [m for m in paid_ratio if m in ocf]
    ocf_free = [m for m in free_block if m in ocf]
    ocf_free_unscored = [m for m in free_unscored if m in ocf]
    ocf_unratable = [m for m in unratable if m in ocf]

    stack = {}
    for t in TIERS:
        rows = sorted([m for m in ocf if m.get("tier") == t], key=hier_key)
        present = set().union(*[set(m.get("groups", [])) for m in rows]) if rows else set()
        stack[t] = {"rows": rows, "gaps": sorted(OCF - present)}

    practical = []
    for t in TIERS:
        for v, off in VARIANTS.items():
            rows = sorted([m for m in stack[t]["rows"] if not (set(m.get("groups", [])) & off)],
                          key=hier_key)
            practical.append({"tier": t, "variant": v,
                              "winner": rows[0] if rows else None,
                              "runner_up": rows[1] if len(rows) > 1 else None})

    elig = [m for m in ocf if not m.get("free") and m.get("score") is not None
            and m.get("cost_blended") is not None]
    q = {"score_q1": pct([m["score"] for m in elig], 0.25),
         "score_q3": pct([m["score"] for m in elig], 0.75),
         "cost_q1": pct([m["cost_blended"] for m in elig], 0.25),
         "cost_q3": pct([m["cost_blended"] for m in elig], 0.75)}
    outliers = {"bargains": [], "overpriced": [], "free_gems": []}
    if elig and q["score_q3"] is not None:
        outliers["bargains"] = [m for m in elig
                                if m["score"] >= q["score_q3"] and m["cost_blended"] <= q["cost_q1"]]
        outliers["overpriced"] = [m for m in elig
                                  if m["score"] <= q["score_q1"] and m["cost_blended"] >= q["cost_q3"]]
    outliers["free_gems"] = [m for m in ocf if m.get("free") and (m.get("score") or 0) >= 40]

    return {"all_intel": all_intel, "costed": costed, "uncosted": uncosted,
            "paid_ratio": paid_ratio, "free_block": free_block,
            "free_unscored": free_unscored, "unratable": unratable,
            "ocf_intel": ocf_intel, "ocf_costed": ocf_costed, "ocf_uncosted": ocf_uncosted,
            "ocf_ratio": ocf_ratio, "ocf_free": ocf_free,
            "ocf_free_unscored": ocf_free_unscored, "ocf_unratable": ocf_unratable,
            "stack": stack, "practical": practical, "outliers": outliers,
            "quartiles": q, "ocf_count": len(ocf), "model_count": len(models),
            "routers": routers}


def row_md(m):
    g = "".join(m.get("groups", [])) or "-"
    s = m["score"] if m.get("score") is not None else "unscored"
    c = m["cost_blended"] if m.get("cost_blended") is not None else "cost-unknown"
    r = m["ratio"] if m.get("ratio") is not None else "-"
    oc = f" → `{opencode_ids(m['or_id'])}`" if m.get("or_id") else ""
    return f"- `{m['id']}` [{g}] — score {s} — ${c}/1M — ratio {r}{oc}\n"


def main():
    afiles = sorted(glob.glob(os.path.join(ROOT, "analysis", "*_analysis.json")), key=os.path.getmtime)
    if not afiles:
        print("run analysis first")
        return
    with open(afiles[-1], encoding="utf-8") as f:
        a = json.load(f)
    stamp = a.get("stamp", a.get("day", "unknown"))
    th = a.get("thresholds", {"max": 50, "high": 40, "medium": 30})
    s = build_sections(a)

    L = [f"# ModelAnalysis — {stamp} (on-use)\n",
         f"Models {s['model_count']} | OCF {s['ocf_count']} | "
         f"Scored {sum(1 for m in a.get('models', []) if m.get('score') is not None)} | "
         f"Costed {sum(1 for m in a.get('models', []) if m.get('cost_blended') is not None)} | "
         f"Tiers Max {len(s['stack']['max']['rows'])} / High {len(s['stack']['high']['rows'])} / "
         f"Medium {len(s['stack']['medium']['rows'])} | "
         f"Thresholds {th['max']}/{th['high']}/{th['medium']} | <30 excluded from stack only | "
         f"Routers {len(s['routers'])} excluded\n",
         "\n## 1. All Data — Intelligence\n"]
    L += [row_md(m) for m in s["all_intel"][:MD_CAP]]
    if len(s["all_intel"]) > MD_CAP:
        L.append(f"_…and {len(s['all_intel']) - MD_CAP} more (see XLSX/JSON)_\n")
    L += ["\n## 2. All Data — Cost\n"]
    L += [row_md(m) for m in s["costed"][:MD_CAP]]
    if s["uncosted"]:
        L.append(f"\n_cost-unknown ({len(s['uncosted'])}), e.g: " +
                 ", ".join(f"`{m['id']}`" for m in s["uncosted"][:MD_CAP]) + "_\n")
    L += ["\n## 3. All Data — Intelligence/Cost Ratio (paid only; free ranked by score below)\n"]
    L += [row_md(m) for m in s["paid_ratio"][:MD_CAP]]
    L += ["\n_Free by score_\n"]
    L += [row_md(m) for m in s["free_block"][:MD_CAP]]
    if s["free_unscored"]:
        L.append(f"_Free unscored ({len(s['free_unscored'])}): " +
                 ", ".join(f"`{m['id']}`" for m in s["free_unscored"][:MD_CAP]) + "_\n")
    L += ["\n## 4. OCF — Intelligence\n"]
    L += [row_md(m) for m in s["ocf_intel"][:MD_CAP]]
    L += ["\n## 5. OCF — Cost\n"]
    L += [row_md(m) for m in s["ocf_costed"][:MD_CAP]]
    if s["ocf_uncosted"]:
        L.append(f"\n_cost-unknown ({len(s['ocf_uncosted'])})_\n")
    L += ["\n## 6. OCF — Intelligence/Cost Ratio\n"]
    L += [row_md(m) for m in s["ocf_ratio"][:MD_CAP]]
    L += ["\n_Free by score_\n"]
    L += [row_md(m) for m in s["ocf_free"][:MD_CAP]]
    L += ["\n## 7. OCF — Optimized stack\n"]
    for t in TIERS:
        gaps = f" — gaps: {','.join(s['stack'][t]['gaps'])}" if s["stack"][t]["gaps"] else ""
        L.append(f"\n### {TIER_LABEL[t]}{gaps}\n")
        L += [row_md(m) for m in s["stack"][t]["rows"][:MD_CAP]]
    L += ["\n## 8. OCF — Practical picks (winner + runner-up per tier × variant)\n",
          "| Tier | Variant | Winner | Runner-up |\n|---|---|---|---|\n"]
    for p in s["practical"]:
        w = f"`{p['winner']['id']}` ({p['winner']['score']}/{p['winner']['ratio']})" if p["winner"] else "— (gap)"
        u = f"`{p['runner_up']['id']}`" if p["runner_up"] else "—"
        L.append(f"| {TIER_LABEL[p['tier']]} | {p['variant']} | {w} | {u} |\n")
    L += ["\n## 9. OCF — Outliers\n"]
    for cls, title in [("bargains", "Bargains (top-quartile score, bottom-quartile cost)"),
                       ("overpriced", "Overpriced (bottom-quartile score, top-quartile cost)"),
                       ("free_gems", "Free gems (free, score 40+)")]:
        L.append(f"\n### {title}\n")
        L += [row_md(m) for m in s["outliers"][cls][:MD_CAP]] or ["_(none)_\n"]
    L.append("\n_Free excluded from ratio (infinite); ratios use " +
             f"{a.get('cost_method', 'blended $/1M')}. OCF = OpenAI + Claude + strict-free. " +
             "Per-model OpenCode compat not verified._\n")
    with open(os.path.join(REP, f"{stamp}_summary.md"), "w", encoding="utf-8") as f:
        f.write("".join(L))

    slim = lambda m: [m["id"], "".join(m["groups"]), m["score"], m["cost_blended"],
                      m["ratio"], opencode_ids(m["or_id"]), ",".join(m["providers"])]
    scored = sorted(m["score"] for m in a.get("models", []) if m.get("score") is not None)
    dist = {"scored": len(scored)}
    if scored:
        dist.update({"p10": round(pct(scored, 0.10), 2), "p50": round(pct(scored, 0.50), 2),
                     "p90": round(pct(scored, 0.90), 2), "max": max(scored)})
    full = {"stamp": stamp, "day": a.get("day", stamp[:10]), "thresholds": th,
            "cost_method": a.get("cost_method", ""), "quartiles": s["quartiles"],
            "score_dist": dist, "routers_excluded": s["routers"],
            "collisions": a.get("collisions", []),
            "all_intel": s["all_intel"], "all_cost": s["costed"], "all_cost_unknown": s["uncosted"],
            "all_ratio_paid": s["paid_ratio"], "all_ratio_free_by_score": s["free_block"],
            "all_ratio_unratable": s["unratable"] + s["free_unscored"],
            "ocf_intel": s["ocf_intel"], "ocf_cost": s["ocf_costed"],
            "ocf_cost_unknown": s["ocf_uncosted"], "ocf_ratio_paid": s["ocf_ratio"],
            "ocf_ratio_free_by_score": s["ocf_free"],
            "ocf_stack": {t: {"rows": s["stack"][t]["rows"], "gaps": s["stack"][t]["gaps"]} for t in TIERS},
            "ocf_practical": s["practical"], "ocf_outliers": s["outliers"]}
    with open(os.path.join(REP, f"{stamp}_models.json"), "w", encoding="utf-8") as f:
        json.dump(full, f, indent=1)

    try:
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "summary"
        ws.append(["stamp", stamp])
        ws.append(["models", s["model_count"]])
        ws.append(["ocf", s["ocf_count"]])
        for t in TIERS:
            ws.append([f"stack_{t}", len(s["stack"][t]["rows"])])
            ws.append([f"gaps_{t}", ",".join(s["stack"][t]["gaps"])])
        H = ["id", "groups", "score", "cost_per_1M", "ratio", "opencode_id", "providers"]
        tabs = {"All_Intel": s["all_intel"], "All_Cost": s["costed"] + s["uncosted"],
                "All_Ratio": s["paid_ratio"] + s["free_block"] + s["unratable"] + s["free_unscored"],
                "OCF_Intel": s["ocf_intel"], "OCF_Cost": s["ocf_costed"] + s["ocf_uncosted"],
                "OCF_Ratio": s["ocf_ratio"] + s["ocf_free"] + s["ocf_unratable"] + s["ocf_free_unscored"],
                "OCF_Outliers": s["outliers"]["bargains"] + s["outliers"]["overpriced"] + s["outliers"]["free_gems"]}
        for name, rows in tabs.items():
            w = wb.create_sheet(name); w.append(H)
            for m in rows:
                w.append(slim(m))
        w = wb.create_sheet("OCF_Stack"); w.append(["tier"] + H + ["gap"])
        for t in TIERS:
            for m in s["stack"][t]["rows"]:
                w.append([t] + slim(m) + [""])
            for g in s["stack"][t]["gaps"]:
                w.append([t, f"GAP:{g}", "", "", "", "", "", "", "gap"])
        w = wb.create_sheet("OCF_Practical")
        w.append(["tier", "variant", "winner", "winner_score", "winner_ratio", "runner_up"])
        for p in s["practical"]:
            w.append([p["tier"], p["variant"],
                      p["winner"]["id"] if p["winner"] else "GAP",
                      p["winner"]["score"] if p["winner"] else None,
                      p["winner"]["ratio"] if p["winner"] else None,
                      p["runner_up"]["id"] if p["runner_up"] else None])
        wb.save(os.path.join(REP, f"{stamp}_models.xlsx"))
        x = "xlsx ok"
    except Exception as e:
        x = f"xlsx skipped: {e}"
    prune_reports([os.path.basename(f).replace("_analysis.json", "") for f in afiles[-1:]])
    print(f"report {stamp} written ({x})")


if __name__ == "__main__":
    main()
