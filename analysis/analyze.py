"""2. Data Analysis — normalize all providers, free-classify, diff vs sqlite, combined rank."""
import json, os, glob, sqlite3, datetime, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
DB = os.path.join(ROOT, "analysis", "store.sqlite")
os.makedirs(os.path.dirname(DB), exist_ok=True)

def is_free_or(pricing):
    try:
        return float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0
    except Exception:
        return False

def aa_score(ev):
    try:
        return float((ev or {}).get("artificial_analysis_intelligence_index", 0) or 0)
    except Exception:
        return 0

def aa_creator(m):
    c = m.get("model_creator", "")
    return c.get("name", "") if isinstance(c, dict) else str(c)

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def main():
    raw_files = glob.glob(os.path.join(RAW, "*_models.json"))
    if not raw_files:
        print("no snapshots in raw/")
        return
    files = sorted(raw_files, key=os.path.getmtime)
    with open(files[-1], encoding="utf-8") as f:
        snap = json.load(f)
    stamp = str(snap.get("retrieved_at", datetime.datetime.now().strftime("%Y-%m-%d_%H%M")))
    day = stamp[:10]

    ors = snap.get("openrouter", []) if isinstance(snap.get("openrouter"), list) else []
    oai = snap.get("openai", []) if isinstance(snap.get("openai"), list) else []
    ant = snap.get("anthropic", []) if isinstance(snap.get("anthropic"), list) else []
    aa_raw = snap.get("aa", {})
    aa = aa_raw.get("data", []) if isinstance(aa_raw, dict) else []

    or_rows = [{"id": m.get("id", ""), "name": m.get("name", ""), "context": m.get("context_length"),
                "free": (is_free_or(m.get("pricing", {})) or str(m.get("id", "")).endswith(":free"))
                        and (m.get("architecture") or {}).get("output_modalities") == ["text"]
                        and not str(m.get("id", "")).startswith("openrouter/")}
               for m in ors]
    free_ids = sorted([r["id"] for r in or_rows if r["free"]])

    oai_rows = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", ""), "shutdown": m.get("shutdown_date", "")} for m in oai]
    ant_rows = [{"id": m.get("id", ""), "name": m.get("display_name", ""),
                 "ctx_in": m.get("max_input_tokens"), "ctx_out": m.get("max_tokens")} for m in ant]

    aa_rows = []
    for m in aa:
        p = m.get("pricing", {}) or {}
        try:
            zero = float(p.get("price_1m_input_tokens", 1)) == 0 and float(p.get("price_1m_output_tokens", 1)) == 0
        except Exception:
            zero = False
        aa_rows.append({"id": m.get("slug", "") or m.get("id", ""), "name": m.get("name", ""),
                        "creator": aa_creator(m), "score": aa_score(m.get("evaluations")),
                        "cost_blended": p.get("price_1m_blended_3_to_1"), "zero_price": zero})
    aa_top = sorted(aa_rows, key=lambda r: r["score"], reverse=True)[:15]
    aa_free_unverified = sorted([r["id"] for r in aa_rows if r["zero_price"]])

    # Combined free+score rank: OR free matched to AA by exact normalized slug (no match = unscored)
    aa_by_slug = {norm(r["id"]): r for r in aa_rows}
    combined = []
    for r in or_rows:
        if not r["free"]:
            continue
        best = aa_by_slug.get(norm(r["id"].split(":")[0].split("/")[-1]))
        combined.append({"id": r["id"], "aa_score": best["score"] if best else 0,
                         "aa_match": best["id"] if best else "", "context": r["context"]})
    combined = sorted(combined, key=lambda r: r["aa_score"], reverse=True)[:30]

    con = sqlite3.connect(DB)
    cols = [r[1] for r in con.execute("PRAGMA table_info(models)")]
    if cols and "source" not in cols:
        con.execute(f"ALTER TABLE models RENAME TO models_old_{stamp.replace('-', '')}")
    con.execute("CREATE TABLE IF NOT EXISTS models(id TEXT, source TEXT, day TEXT, free INT, PRIMARY KEY(id, source, day))")
    prev_or = {r[0] for r in con.execute(
        "SELECT id FROM models WHERE source='openrouter' AND day="
        "(SELECT MAX(day) FROM models WHERE source='openrouter' AND day<?)", (day,))}
    for r in or_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "openrouter", day, int(r["free"])))
    for r in oai_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "openai", day, 0))
    for r in ant_rows:
        con.execute("INSERT OR REPLACE INTO models VALUES(?,?,?,?)", (r["id"], "anthropic", day, 0))
    con.commit()
    cur_or = {r["id"] for r in or_rows}
    new_or = sorted(cur_or - prev_or) if prev_or else []
    removed_or = sorted(prev_or - cur_or) if prev_or else []
    hist_days = [r[0] for r in con.execute("SELECT DISTINCT day FROM models ORDER BY day")]

    out = {"stamp": stamp, "day": day, "total_openrouter": len(or_rows), "free_count": len(free_ids), "free_ids": free_ids[:300],
           "new_ids_vs_history": new_or[:50], "new_total": len(new_or),
           "removed_ids_vs_history": removed_or[:50], "removed_total": len(removed_or), "history_days": hist_days,
           "total_openai": len(oai_rows), "openai_ids": sorted([r["id"] for r in oai_rows]),
           "openai_retired": sorted([r["id"] for r in oai_rows if r["shutdown"]])[:50],
           "total_anthropic": len(ant_rows), "anthropic_ids": sorted([r["id"] for r in ant_rows]),
           "total_aa": len(aa_rows), "aa_top15": aa_top,
           "aa_free_unverified": aa_free_unverified[:100], "aa_free_count": len(aa_free_unverified),
           "combined_free_rank": combined}
    ap = os.path.join(ROOT, "analysis", f"{stamp}_analysis.json")
    with open(ap, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    afiles = sorted(glob.glob(os.path.join(ROOT, "analysis", "*_analysis.json")), key=os.path.getmtime)
    for old in afiles[:-1]:
        os.remove(old)
        print(f"pruned analysis {os.path.basename(old)}")
    print(f"{stamp}: OR={len(or_rows)} free={len(free_ids)} OAI={len(oai_rows)} ANT={len(ant_rows)} AA={len(aa_rows)} new={len(new_or)} removed={len(removed_or)} days={len(hist_days)} -> {ap}")
    con.close()

if __name__ == "__main__":
    main()
