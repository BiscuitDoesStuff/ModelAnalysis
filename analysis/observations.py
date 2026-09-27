"""Observations fact table — one row per (entity, source, field).

Never mixes benchmark scales. Every observation carries provenance
(source, benchmark/version, evidence tier, url, observed_at/expires_at).
Views (views.py) read observations; reports read views.
"""


def obs(entity, source, field, value, unit="", benchmark="", version="",
        evidence="", url="", observed_at="", expires_at=""):
    return {"entity": entity, "source": source, "field": field, "value": value,
            "unit": unit, "benchmark": benchmark, "version": version,
            "evidence": evidence, "url": url,
            "observed_at": observed_at, "expires_at": expires_at}


def build_observations(models, day):
    observations = []
    for m in models:
        slug = m.get("slug", "")
        # AA ranking score (primary, versioned).
        ss = m.get("score_source") or {}
        if m.get("score") is not None:
            observations.append(obs(slug, "aa", "score", m["score"], "index-100",
                                    ss.get("benchmark", "aa-intelligence-index"),
                                    ss.get("version", ""), ss.get("kind", ""),
                                    ss.get("url", ""), day, ""))
        if m.get("cost_blended") is not None:
            observations.append(obs(slug, m.get("cost_source", "unknown") or "unknown",
                                    "price_blended", m["cost_blended"], "$/1M", "", "", "",
                                    "", day, ""))
        # BenchLM website + JSON.
        b = m.get("benchlm") or {}
        if b.get("overall") is not None:
            observations.append(obs(slug, "benchlm", "score", b["overall"], "benchlm-100",
                                    "benchlm-overall", "", b.get("evidence", ""),
                                    f"https://benchlm.ai/models/{(b.get('model','') or '').lower().replace(' ','-')}",
                                    day, ""))
        for cat, val in (b.get("categories") or {}).items():
            if isinstance(val, (int, float)):
                observations.append(obs(slug, "benchlm", f"score.{cat}", val, "benchlm-100",
                                        f"benchlm-{cat}", "", b.get("evidence", ""), "", day, ""))
        bp = m.get("benchlm_pricing") or {}
        if bp.get("context"):
            observations.append(obs(slug, "benchlm", "context", bp["context"], "tokens",
                                    "", "", "", "", day, ""))
        if bp.get("type"):
            observations.append(obs(slug, "benchlm", "license_type", bp["type"], "", "", "", "", "", day, ""))
        # LLM Stats API (when key present) — category scores kept separate.
        api = m.get("llmstats_api") or {}
        top = api.get("top_scores") or {}
        if isinstance(top, dict):
            for cat, val in top.items():
                if isinstance(val, (int, float)):
                    observations.append(obs(slug, "llmstats", f"score.{cat}", val, "llmstats-trueskill-raw",
                                            f"llmstats-{cat}", "", "api", api.get("url", ""), day, ""))
        for cat, r in ((m.get("llmstats_rank") or {}).items() if isinstance(m.get("llmstats_rank"), dict) else []):
            if isinstance(r, dict) and r.get("rating") is not None:
                observations.append(obs(slug, "llmstats", f"rank.{cat}", r.get("rank"), "rank",
                                        f"llmstats-{cat}", "", "api", r.get("url", ""), day, ""))
                observations.append(obs(slug, "llmstats", f"rating.{cat}", r.get("rating"),
                                        "llmstats-conservative", f"llmstats-{cat}", "", "api",
                                        r.get("url", ""), day, ""))
        det = m.get("llmstats_detail") or {}
        for s in (det.get("scores", []) if isinstance(det, dict) else []):
            if isinstance(s, dict) and isinstance(s.get("score"), (int, float)):
                observations.append(obs(slug, "llmstats", f"bench.{s.get('bench', '')}",
                                        s["score"], "benchmark-native",
                                        str(s.get("bench", "")), "",
                                        "verified" if s.get("verified") else ("self-reported" if s.get("self_reported") else "third-party"),
                                        s.get("url", ""), day, ""))
        # Website-native hints (best-effort, labelled as hints).
        web = m.get("website") or {}
        lw = web.get("llmstats") or {}
        if isinstance(lw, dict):
            if lw.get("llmstats_score_hint") is not None:
                observations.append(obs(slug, "llmstats-web", "score_hint",
                                        lw["llmstats_score_hint"], "llmstats-trueskill",
                                        "llmstats-overall", "", "hint",
                                        lw.get("url", ""), day, ""))
            if lw.get("context_hint"):
                observations.append(obs(slug, "llmstats-web", "context_hint",
                                        lw["context_hint"], "tokens", "", "", "hint",
                                        lw.get("url", ""), day, ""))
            if lw.get("license_hint"):
                observations.append(obs(slug, "llmstats-web", "license_hint",
                                        lw["license_hint"], "", "", "", "hint",
                                        lw.get("url", ""), day, ""))
            for ph in (lw.get("price_hints") or []):
                observations.append(obs(slug, "llmstats-web", f"price_hint.{ph.get('kind','')}",
                                        ph.get("value"), "$/M", "", "", "hint",
                                        lw.get("url", ""), day, ""))
        vw = web.get("vals") or {}
        if isinstance(vw, dict):
            for acc in (vw.get("accuracy_hints") or [])[:4]:
                try:
                    observations.append(obs(slug, "vals-web", "accuracy_hint", float(acc), "%",
                                            "vals-index", "", "hint", vw.get("url", ""), day, ""))
                    break
                except Exception:
                    continue
            if vw.get("cost_per_test_hint"):
                observations.append(obs(slug, "vals-web", "cost_per_test_hint",
                                        vw["cost_per_test_hint"], "$/test", "vals-index",
                                        "", "hint", vw.get("url", ""), day, ""))
            if vw.get("latency_hint"):
                observations.append(obs(slug, "vals-web", "latency_hint",
                                        vw["latency_hint"], "duration", "vals-index",
                                        "", "hint", vw.get("url", ""), day, ""))
        # Capabilities already on the row (models.dev / ZenMux / OR).
        if m.get("context") is not None:
            observations.append(obs(slug, "openrouter", "context", m["context"], "tokens",
                                    "", "", "", "", day, ""))
        if m.get("modelsdev_efforts"):
            observations.append(obs(slug, "modelsdev", "reasoning_efforts",
                                    list(m["modelsdev_efforts"]), "effort-list", "", "", "",
                                    "https://models.dev/api.json", day, ""))
    return observations
