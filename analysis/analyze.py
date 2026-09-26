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
    aa_by_slug = {norm(r["id"]): r for r in aa_rows}

    # Canonical deduped models (reports-layer union; raw snapshots untouched).
    TIER_MAX, TIER_HIGH, TIER_MED = 50, 40, 30

    def tier_of(score):
        if score is None:
            return ""
        if score >= TIER_MAX:
            return "max"
        if score >= TIER_HIGH:
            return "high"
        if score >= TIER_MED:
            return "medium"
        return "below"

    def or_cost_per_1m(pricing):
        try:
            p = float((pricing or {}).get("prompt", -1))
            c = float((pricing or {}).get("completion", -1))
            if p < 0 or c < 0:
                return None
            return round((3 * p + c) / 4 * 1e6, 4)
        except Exception:
            return None

    def aa_cost(value):
        try:
            return None if value is None else round(float(value), 4)
        except Exception:
            return None

    def base_slug(mid):
        return norm(str(mid).split(":")[0].split("/")[-1])

    or_free = {r["id"] for r in or_rows if r["free"]}
    or_ctx = {r["id"]: r["context"] for r in or_rows}
    or_name = {m.get("id", ""): m.get("name", "") for m in ors}
    or_price = {m.get("id", ""): m.get("pricing", {}) for m in ors}
    ant_name = {m.get("id", ""): m.get("display_name", "") for m in ant}
    aa_by_base = {base_slug(k): v for k, v in aa_by_slug.items()}

    union = {}
    for m in ors:
        mid = m.get("id", "")
        union.setdefault(base_slug(mid), {"or": [], "oai": [], "ant": [], "aa": None})
        union[base_slug(mid)]["or"].append(mid)
    for m in oai:
        union.setdefault(base_slug(m.get("id", "")), {"or": [], "oai": [], "ant": [], "aa": None})
        union[base_slug(m.get("id", ""))]["oai"].append(m.get("id", ""))
    for m in ant:
        union.setdefault(base_slug(m.get("id", "")), {"or": [], "oai": [], "ant": [], "aa": None})
        union[base_slug(m.get("id", ""))]["ant"].append(m.get("id", ""))
    for m in aa:
        key = base_slug(m.get("slug", "") or m.get("id", ""))
        union.setdefault(key, {"or": [], "oai": [], "ant": [], "aa": None})
        union[key]["aa"] = m

    collisions = []
    for key, entry in union.items():
        bases = {i.split(":")[0] for i in entry["or"]}
        if len(bases) > 1:
            collisions.append({"slug": key, "ids": sorted(entry["or"])})
    if collisions:
        print(f"note: {len(collisions)} slug-collision merges (same tail slug, kept merged): " +
              ", ".join(c["slug"] for c in collisions[:10]))

    models = []
    for key in sorted(union):
        u = union[key]
        free = any(i in or_free for i in u["or"])
        groups = []
        if u["oai"] or any(i.lstrip("~").split("/")[0].lower() == "openai" for i in u["or"] if "/" in i.lstrip("~")):
            groups.append("O")
        if u["ant"] or any(i.lstrip("~").split("/")[0].lower() == "anthropic" for i in u["or"] if "/" in i.lstrip("~")):
            groups.append("C")
        if free:
            groups.append("F")
        providers = []
        if u["or"]:
            providers.append("openrouter")
        if u["oai"]:
            providers.append("openai")
        if u["ant"]:
            providers.append("anthropic")
        aa_match = aa_by_base.get(key)
        score = aa_match["score"] if aa_match else None
        cost = aa_cost(aa_match["cost_blended"]) if aa_match else None
        if cost is None:
            for i in u["or"]:
                cost = or_cost_per_1m(or_price.get(i))
                if cost is not None:
                    break
        ratio = round(score / cost, 4) if score is not None and cost and cost > 0 else None
        or_ids = sorted(u["or"])
        disp_or = next((i for i in or_ids if i in or_free), or_ids[0] if or_ids else "")
        disp = (u["oai"] or u["ant"] or ([disp_or] if disp_or else []) or
                ([aa_match.get("slug", "") or aa_match.get("id", "")] if aa_match else [""]))[0]
        name = (next((or_name.get(i, "") for i in or_ids if or_name.get(i)), "") or
                next((ant_name.get(i, "") for i in u["ant"] if ant_name.get(i)), "") or
                ((aa_match or {}).get("name", "")))
        router = disp_or.lower().lstrip("~").startswith("openrouter/")
        models.append({"id": disp, "or_id": disp_or, "name": name, "groups": groups,
                       "providers": providers, "score": score, "cost_blended": cost,
                       "ratio": ratio, "context": or_ctx.get(disp_or),
                       "free": free, "router": router, "tier": tier_of(score)})

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

    out = {"stamp": stamp, "day": day, "total_openrouter": len(or_rows), "free_count": len(free_ids),
           "new_ids_vs_history": new_or[:50], "new_total": len(new_or),
           "removed_ids_vs_history": removed_or[:50], "removed_total": len(removed_or), "history_days": hist_days,
           "total_openai": len(oai_rows), "openai_ids": sorted([r["id"] for r in oai_rows]),
           "openai_retired": sorted([r["id"] for r in oai_rows if r["shutdown"]])[:50],
           "total_anthropic": len(ant_rows), "anthropic_ids": sorted([r["id"] for r in ant_rows]),
           "total_aa": len(aa_rows),
           "models": models, "collisions": collisions,
           "thresholds": {"max": TIER_MAX, "high": TIER_HIGH, "medium": TIER_MED},
           "cost_method": "aa_blended_primary_or_derived_fallback_per_1M"}
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
