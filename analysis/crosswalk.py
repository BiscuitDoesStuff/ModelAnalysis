"""Entity resolution — canonical slug crosswalk across providers + benchmark sources.

Providers remain the source of truth for existence. Benchmark sources
(BenchLM / LLM Stats / Vals / AA) join by normalized name/slug, never by guess:
exact norm equality only. Unmapped rows stay unjoined.
"""
import re


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def kebab(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def base_slug(mid):
    return norm(str(mid).split(":")[0].split("/")[-1])


def benchlm_indexes(snap):
    bench = snap.get("benchlm", {}) if isinstance(snap.get("benchlm"), dict) else {}
    lb = bench.get("leaderboard", []) if isinstance(bench.get("leaderboard"), list) else []
    pr = bench.get("pricing", []) if isinstance(bench.get("pricing"), list) else []
    by_norm, pr_by_norm = {}, {}
    for m in lb:
        if isinstance(m, dict) and m.get("model"):
            by_norm[norm(m["model"])] = m
    for m in pr:
        if isinstance(m, dict) and m.get("model"):
            pr_by_norm[norm(m["model"])] = m
    meta = bench.get("meta", {}) if isinstance(bench.get("meta"), dict) else {}
    return by_norm, pr_by_norm, meta


def llmstats_indexes(snap):
    llm = snap.get("llmstats", {}) if isinstance(snap.get("llmstats"), dict) else {}
    out = {}
    raw_models = llm.get("models", [])
    models = raw_models if isinstance(raw_models, list) else []
    if not models and isinstance(raw_models, dict):
        # Legacy shape: {"models": {"models": [...]}} (pre-paged fetcher).
        models = (raw_models.get("models", []) if isinstance(raw_models.get("models"), dict)
                  else raw_models.get("models", [])) or []
        if not isinstance(models, list):
            models = []
    for m in models:
        if isinstance(m, dict) and (m.get("id") or m.get("name")):
            out[norm(m.get("id", "") or m.get("name", ""))] = m
            if m.get("name"):
                out.setdefault(norm(m["name"]), m)
    ranks = {}
    for cat, rows in ((llm.get("rankings", {}) or {}).items() if isinstance(llm.get("rankings"), dict) else []):
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and r.get("model_id"):
                ranks.setdefault(norm(r["model_id"]), {})[cat] = r
    details = {}
    for lid, d in ((llm.get("details", {}) or {}).items() if isinstance(llm.get("details"), dict) else []):
        details[norm(lid)] = d
        if isinstance(d, dict) and d.get("name"):
            details.setdefault(norm(d["name"]), d)
    return out, ranks, details


def vals_indexes(snap):
    vals = snap.get("vals", {}) if isinstance(snap.get("vals"), dict) else {}
    rows = vals.get("models", []) if isinstance(vals.get("models"), list) else []
    out = {}
    for r in rows:
        if isinstance(r, dict) and r.get("name"):
            out[norm(r["name"])] = r
    return out


def attach_crosswalk(models, snap, websites=None):
    """Mutate canonical rows with benchlm/llmstats/vals join metadata."""
    bench_by, bench_pr, bench_meta = benchlm_indexes(snap)
    llm_by, llm_ranks, llm_details = llmstats_indexes(snap)
    vals_by = vals_indexes(snap)
    web = websites or {}
    bench_md = web.get("benchlm_md", {}) if isinstance(web, dict) else {}
    llm_web = web.get("llmstats", {}) if isinstance(web, dict) else {}
    vals_web = web.get("vals", {}) if isinstance(web, dict) else {}
    for m in models:
        slug = m.get("slug", "")
        name_n = norm(m.get("name", ""))
        cand = [slug, name_n, norm(m.get("aa_id", "")), norm(m.get("or_id", "").split("/")[-1])]
        found = None
        for c in cand:
            if c and c in bench_by:
                found = bench_by[c]
                break
        m["benchlm"] = ({"model": found.get("model"), "creator": found.get("creator"),
                         "overall": found.get("overallScore"),
                         "evidence": found.get("evidenceStatus"),
                         "categories": found.get("categoryScores") or {},
                         "in_price": found.get("inputPrice"), "out_price": found.get("outputPrice")}
                        if found else None)
        pr = None
        for c in cand:
            if c and c in bench_pr:
                pr = bench_pr[c]
                break
        m["benchlm_pricing"] = ({"context": pr.get("contextWindow"), "type": pr.get("sourceType"),
                                 "in_price": pr.get("inputPrice"), "out_price": pr.get("outputPrice")}
                                if pr else None)
        llm = None
        for c in cand:
            if c and c in llm_by:
                llm = llm_by[c]
                break
        m["llmstats_api"] = llm
        rank = None
        for c in cand:
            if c and c in llm_ranks:
                rank = llm_ranks[c]
                break
        m["llmstats_rank"] = rank
        det = None
        for c in cand:
            if c and c in llm_details:
                det = llm_details[c]
                break
        m["llmstats_detail"] = det
        val = None
        for c in cand:
            if c and c in vals_by:
                val = vals_by[c]
                break
        m["vals_index"] = val
        m["website"] = {"benchlm_md": bench_md.get(slug), "llmstats": llm_web.get(slug),
                        "vals": vals_web.get(slug)}
    return {"methodology": bench_meta.get("methodologyVersion", ""),
            "lastUpdated": bench_meta.get("lastUpdated", "")}
