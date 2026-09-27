"""Views over observations — per-source leaderboards + merged capabilities/pricing.

Ranking stays AA-only. BenchLM / LLM Stats / Vals are parallel views with
their own scales, evidence tiers, and provenance. Reports read views.
"""


def _score(m, key="score"):
    v = m.get(key)
    return v if isinstance(v, (int, float)) else -1


def build_views(models):
    bench_rows = [m for m in models if (m.get("benchlm") or {}).get("overall") is not None]
    bench_rows = sorted(bench_rows, key=lambda m: -_score(m["benchlm"], "overall"))
    llm_rows = []
    for m in models:
        rk = m.get("llmstats_rank") or {}
        g = rk.get("general") or {}
        api = m.get("llmstats_api") or {}
        web = ((m.get("website") or {}).get("llmstats")) or {}
        rating, rank, evals, url = g.get("rating"), g.get("rank"), g.get("evals"), g.get("url", "")
        if rating is None:
            top = api.get("top_scores") or {}
            vals = [v for v in top.values() if isinstance(v, (int, float))]
            rating = max(vals) if vals else web.get("llmstats_score_hint")
        if rating is not None:
            llm_rows.append({"id": m["id"], "slug": m["slug"], "score": rating,
                             "rank": rank, "evals": evals if evals is not None else web.get("evals_hint"),
                             "url": url or web.get("url", "") or api.get("url", "")})
    llm_rows = sorted(llm_rows, key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 0,
                                               -(r["score"] if isinstance(r["score"], (int, float)) else -1)))
    vals_rows = []
    for m in models:
        web = ((m.get("website") or {}).get("vals")) or {}
        accs = web.get("accuracy_hints") or []
        if accs:
            try:
                vals_rows.append({"id": m["id"], "slug": m["slug"],
                                  "accuracy": float(accs[0]),
                                  "cost_per_test": web.get("cost_per_test_hint", ""),
                                  "latency": web.get("latency_hint", ""),
                                  "url": web.get("url", "")})
            except Exception:
                continue
    vals_rows = sorted(vals_rows, key=lambda r: -r["accuracy"])

    capabilities, pricing = [], []
    for m in models:
        web = m.get("website") or {}
        lw, vw = web.get("llmstats") or {}, web.get("vals") or {}
        b, bp = m.get("benchlm") or {}, m.get("benchlm_pricing") or {}
        api = m.get("llmstats_api") or {}
        api_provs = api.get("providers") or []
        best_prov = min(api_provs, key=lambda p: (p.get("in_per_m") if isinstance(p.get("in_per_m"), (int, float)) else 1e18)) if api_provs else {}
        capabilities.append({
            "id": m["id"], "slug": m["slug"], "name": m.get("name", ""),
            "groups": m.get("groups", []), "providers": m.get("providers", []),
            "variant": m.get("variant", ""), "efforts": m.get("efforts", []),
            "efforts_hint": m.get("efforts_hint", []),
            "context_or": m.get("context"), "context_benchlm": bp.get("context"),
            "context_llmstats": api.get("context_window") or (lw.get("context_hint") if isinstance(lw, dict) else ""),
            "license_benchlm": bp.get("type"),
            "license_llmstats": api.get("license") or (lw.get("license_hint") if isinstance(lw, dict) else ""),
            "modalities_llmstats": api.get("modalities") or [],
            "params": api.get("params"), "cutoff": api.get("cutoff"), "released": api.get("released"),
            "supports_tools": api.get("supports_tools"), "supports_vision": api.get("supports_vision"),
            "modalities": {"zenmux_output": m.get("zenmux_output", []),
                           "modality_status": m.get("modality_status", "")},
            "deprecated_upstream": bool(m.get("deprecated_upstream")),
            "free_status": m.get("free_status", "none"),
            "copy_id": (m.get("selector") or (f"openrouter/{m['or_id']}" if m.get("or_id") and not str(m['or_id']).startswith("openrouter/") else m.get("or_id", "")) or m.get("fallback_id", "")),
        })
        pricing.append({
            "id": m["id"], "slug": m["slug"],
            "aa_blended": m.get("cost_blended"), "cost_source": m.get("cost_source", ""),
            "benchlm_in": b.get("in_price"), "benchlm_out": b.get("out_price"),
            "llmstats_provider": best_prov.get("provider_name", "") if isinstance(best_prov, dict) else "",
            "llmstats_in": (best_prov.get("in_per_m") if isinstance(best_prov, dict) else None),
            "llmstats_out": (best_prov.get("out_per_m") if isinstance(best_prov, dict) else None),
            "llmstats_hints": (lw.get("price_hints", []) if isinstance(lw, dict) else []),
            "vals_cost_per_test": (vw.get("cost_per_test_hint", "") if isinstance(vw, dict) else ""),
            "free_status": m.get("free_status", "none"),
        })

    ev_counts = {"supported": 0, "estimated": 0, "other": 0}
    for m in models:
        ev = ((m.get("benchlm") or {}).get("evidence") or "").lower()
        if ev == "supported":
            ev_counts["supported"] += 1
        elif ev == "estimated":
            ev_counts["estimated"] += 1
        elif ev:
            ev_counts["other"] += 1
    # L0 triage: provisional-l0 rows ranked by AA score with corroboration flags.
    # Qualifier = score>=40 AND callable route (or_id/fallback) → verify-billing
    # candidate for verified-free promotion; everything else stays watch-list.
    # (2026-09-27 audit: 234 L0, top 33.6, zero qualifiers — pool is sub-threshold.)
    triage = []
    for m in models:
        if m.get("free_status") != "provisional-l1" and m.get("free_status") != "provisional-l0":
            continue
        route = m.get("or_id") or m.get("fallback_id", "")
        qualifier = (m.get("score") or 0) >= 40 and bool(route)
        triage.append({"id": m["id"], "slug": m["slug"], "score": m.get("score"),
                       "free_status": m.get("free_status"), "route": route or "",
                       "provider": m.get("fallback_provider", "") if not m.get("or_id") else "openrouter",
                       "benchlm": (m.get("benchlm") or {}).get("overall"),
                       "ranked": bool(m.get("llmstats_rank")),
                       "qualifier": qualifier})
    triage = sorted(triage, key=lambda r: (-(r["score"] if isinstance(r.get("score"), (int, float)) else -1)))
    return {"benchlm_leaderboard": [{"id": m["id"], "slug": m["slug"], "model": m["benchlm"]["model"],
                                     "creator": m["benchlm"].get("creator", ""),
                                     "overall": m["benchlm"]["overall"],
                                     "evidence": m["benchlm"].get("evidence", ""),
                                     "categories": m["benchlm"].get("categories", {})} for m in bench_rows],
            "llmstats_leaderboard": llm_rows,
            "vals_leaderboard": vals_rows,
            "capabilities": capabilities,
            "pricing": pricing,
            "provisional_triage": triage,
            "confidence": ev_counts}
