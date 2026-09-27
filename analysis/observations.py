"""Observations fact table — one row per (entity, source, field).

Never mixes benchmark scales. Every observation carries provenance: the real
source, a unit from scales.UNITS, benchmark/version, evidence type (common.EVIDENCE),
url or url_unavailable_reason, observed_at (the source's fetch time, or a cached
page's original fetch time) and expires_at for registry evidence. Each has an
obs_id (hash of entity, source, field, version) that displayed cells reference.
"""
import hashlib
import json

try:
    from .common import score_evidence_type
except ImportError:
    from common import score_evidence_type


def obs(entity, source, field, value, unit="", benchmark="", version="",
        evidence="", url="", observed_at="", expires_at="", **extra):
    row = {"entity": entity, "source": source, "field": field, "value": value,
           "unit": unit, "benchmark": benchmark, "version": version,
           "evidence": evidence, "url": url,
           "observed_at": observed_at, "expires_at": expires_at, **extra}
    if not url and "url_unavailable_reason" not in row:
        row["url_unavailable_reason"] = "source row has no URL"
    return row


def obs_id(entity, source, field, version):
    return hashlib.sha1(json.dumps([entity, source, field, version]).encode("utf-8")).hexdigest()[:16]


def summary(o):
    """What a displayed cell carries about its observation (full row stays in the analysis)."""
    return {k: o.get(k, "") for k in ("obs_id", "source", "version", "observed_at", "evidence")}


def build_observations(models, day, source_health=None):
    """Observations for every model; also sets models[].provenance for displayed score/price."""
    health = source_health or {}

    def fetched(source):
        return (health.get(source) or {}).get("fetched_at") or day

    observations = []
    for m in models:
        slug = m.get("slug", "")
        start = len(observations)
        prov = {}
        # AA ranking score (primary, versioned): API, registry score, or inherited estimate.
        ss = m.get("score_source") or {}
        if m.get("score") is not None:
            kind = ss.get("kind", "")
            if kind == "aa-api":
                row = obs(slug, "aa", "score", m["score"], "aa-index", ss.get("benchmark", "aa-intelligence-index"),
                          ss.get("version") or "", "measured", ss.get("url", ""), fetched("aa"))
            else:
                up = ss.get("upstream") or {}
                row = obs(slug, "registry", "score", m["score"], "aa-index",
                          ss.get("benchmark") or up.get("benchmark", "aa-intelligence-index"),
                          ss.get("version") or up.get("version") or "", score_evidence_type(m),
                          ss.get("url") or next(iter(ss.get("equivalence_urls") or []), ""),
                          ss.get("checked_at") or day, ss.get("expires_at", ""), detail=kind)
            if not row["version"]:
                row["version_unavailable_reason"] = "no AA index version pinned for this day"
            observations.append(row)
            prov["score"] = row
        if m.get("cost_blended") is not None:
            cs = m.get("cost_source", "")
            evidence = ("provisional" if str(m.get("free_status", "")).startswith("provisional")
                        else "inherited-estimate" if cs == "inherited" else "measured")
            if cs == "aa":
                row = obs(slug, "aa", "price_blended", m["cost_blended"], "usd-per-1m-blended-3to1", "", "",
                          evidence, "https://artificialanalysis.ai/models/" + m.get("aa_id", "") if m.get("aa_id") else "",
                          fetched("aa"), detail=cs)
            elif cs == "or-derived":
                row = obs(slug, "openrouter", "price_blended", m["cost_blended"], "usd-per-1m-blended-3to1", "", "",
                          evidence, "https://openrouter.ai/" + m["or_id"] if m.get("or_id") else "",
                          fetched("openrouter"), detail=cs)
            else:  # inherited: the destination route's price from the registry record
                row = obs(slug, "registry", "price_blended", m["cost_blended"], "usd-per-1m-blended-3to1", "", "",
                          evidence, ss.get("capability_url", ""), ss.get("checked_at") or day,
                          ss.get("expires_at", ""), detail=cs or "inherited")
            observations.append(row)
            prov["price"] = row
        # BenchLM website + JSON.
        b = m.get("benchlm") or {}
        b_url = f"https://benchlm.ai/models/{(b.get('model','') or '').lower().replace(' ','-')}" if b.get("model") else ""
        if b.get("overall") is not None:
            observations.append(obs(slug, "benchlm", "score", b["overall"], "benchlm-100", "benchlm-overall", "",
                                    "external-reference", b_url, fetched("benchlm"), detail=b.get("evidence", "")))
        for cat, val in (b.get("categories") or {}).items():
            if isinstance(val, (int, float)):
                observations.append(obs(slug, "benchlm", f"score.{cat}", val, "benchlm-100", f"benchlm-{cat}", "",
                                        "external-reference", b_url, fetched("benchlm"), detail=b.get("evidence", "")))
        bp = m.get("benchlm_pricing") or {}
        if bp.get("context"):
            observations.append(obs(slug, "benchlm", "context", bp["context"], "tokens", "", "",
                                    "external-reference", "", fetched("benchlm")))
        if bp.get("type"):
            observations.append(obs(slug, "benchlm", "license_type", bp["type"], "label", "", "",
                                    "external-reference", "", fetched("benchlm")))
        # LLM Stats API (when key present) — category scores kept separate.
        api = m.get("llmstats_api") or {}
        top = api.get("top_scores") or {}
        if isinstance(top, dict):
            for cat, val in top.items():
                if isinstance(val, (int, float)):
                    observations.append(obs(slug, "llmstats", f"score.{cat}", val, "llmstats-trueskill",
                                            f"llmstats-{cat}", "", "external-reference", api.get("url") or "",
                                            fetched("llmstats")))
        for cat, r in ((m.get("llmstats_rank") or {}).items() if isinstance(m.get("llmstats_rank"), dict) else []):
            if isinstance(r, dict) and r.get("rating") is not None:
                observations.append(obs(slug, "llmstats", f"rank.{cat}", r.get("rank"), "llmstats-rank",
                                        f"llmstats-{cat}", "", "external-reference", r.get("url") or "",
                                        fetched("llmstats")))
                observations.append(obs(slug, "llmstats", f"rating.{cat}", r.get("rating"),
                                        "llmstats-conservative", f"llmstats-{cat}", "", "external-reference",
                                        r.get("url") or "", fetched("llmstats")))
        det = m.get("llmstats_detail") or {}
        for s in (det.get("scores", []) if isinstance(det, dict) else []):
            if isinstance(s, dict) and isinstance(s.get("score"), (int, float)):
                observations.append(obs(slug, "llmstats", f"bench.{s.get('bench', '')}", s["score"],
                                        "benchmark-native", str(s.get("bench", "")), "", "external-reference",
                                        s.get("url") or "", fetched("llmstats"),
                                        detail="verified" if s.get("verified") else (
                                            "self-reported" if s.get("self_reported") else "third-party")))
        # Website-native hints: observed when the page was fetched (cache keeps the original time).
        web = m.get("website") or {}
        lw = web.get("llmstats") or {}
        if isinstance(lw, dict):
            seen = lw.get("fetched_at") or day
            if lw.get("llmstats_score_hint") is not None:
                observations.append(obs(slug, "llmstats-web", "score_hint", lw["llmstats_score_hint"],
                                        "llmstats-trueskill", "llmstats-overall", "", "hint", lw.get("url", ""), seen))
            if lw.get("context_hint"):
                observations.append(obs(slug, "llmstats-web", "context_hint", lw["context_hint"], "tokens",
                                        "", "", "hint", lw.get("url", ""), seen))
            if lw.get("license_hint"):
                observations.append(obs(slug, "llmstats-web", "license_hint", lw["license_hint"], "label",
                                        "", "", "hint", lw.get("url", ""), seen))
            for ph in (lw.get("price_hints") or []):
                observations.append(obs(slug, "llmstats-web", f"price_hint.{ph.get('kind','')}", ph.get("value"),
                                        "usd-per-1m", "", "", "hint", lw.get("url", ""), seen))
        vw = web.get("vals") or {}
        if isinstance(vw, dict):
            seen = vw.get("fetched_at") or day
            for acc in (vw.get("accuracy_hints") or [])[:4]:
                try:
                    observations.append(obs(slug, "vals-web", "score.accuracy_hint", float(acc), "percent",
                                            "vals-index", "", "hint", vw.get("url", ""), seen))
                    break
                except Exception:
                    continue
            if vw.get("cost_per_test_hint"):
                observations.append(obs(slug, "vals-web", "cost_per_test_hint", vw["cost_per_test_hint"],
                                        "usd-per-test", "vals-index", "", "hint", vw.get("url", ""), seen))
            if vw.get("latency_hint"):
                observations.append(obs(slug, "vals-web", "latency_hint", vw["latency_hint"], "duration",
                                        "vals-index", "", "hint", vw.get("url", ""), seen))
        # Capabilities already on the row (models.dev / OR).
        if m.get("context") is not None:
            observations.append(obs(slug, "openrouter", "context", m["context"], "tokens", "", "", "measured",
                                    "https://openrouter.ai/" + m["or_id"] if m.get("or_id") else "",
                                    fetched("openrouter")))
        if m.get("modelsdev_efforts"):
            observations.append(obs(slug, "modelsdev", "reasoning_efforts", list(m["modelsdev_efforts"]),
                                    "effort-list", "", "", "measured", "https://models.dev/api.json",
                                    fetched("modelsdev")))
        # Stable IDs; repeated (entity, source, field, version) rows get an ordinal.
        taken = set()
        for row in observations[start:]:
            key = (row["entity"], row["source"], row["field"], row["version"])
            n = sum(1 for k in taken if k[:4] == key)
            row["obs_id"] = obs_id(*key) if not n else obs_id(*key[:3], f"{row['version']}#{n}")
            taken.add(key + (n,))
        if prov:
            m["provenance"] = {k: summary(v) for k, v in prov.items()}
        else:
            m.pop("provenance", None)
    return observations
