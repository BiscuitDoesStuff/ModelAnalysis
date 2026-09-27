"""Unit tests for join/observation/report-contract helpers. No network, no snapshot needed.
Run: python tests/test_units.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
sys.path.insert(0, os.path.join(ROOT, "retrieval"))

fails = []


def check(cond, msg):
    print(("ok  " if cond else "FAIL") + f" {msg}")
    if not cond:
        fails.append(msg)


from crosswalk import norm, kebab, base_slug, benchlm_indexes, llmstats_indexes
from observations import obs, build_observations
from views import build_views
from enrichment import current, finite

check(norm("Claude Opus 5 (medium)") == "claudeopus5medium", "norm strips punctuation")
check(norm("openrouter/x:y/z") == "openrouterxyz", "norm alnum only (base_slug strips provider)")
check(kebab("Muse Spark 1.3") == "muse-spark-1-3", "kebab model name")
check(base_slug("openai/gpt-5:free") == "gpt5", "base_slug strips provider+tag")
check(base_slug("x/y/z") == "z", "base_slug tail segment")

sys.path.insert(0, ROOT)
import importlib.util
spec = importlib.util.spec_from_file_location("analyze_mod", os.path.join(ROOT, "analysis", "analyze.py"))
analyze_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze_mod)
check(analyze_mod.parse_variant("Muse Spark 1.3 (max)", "") == "max", "variant parens form")
check(analyze_mod.parse_variant("Claude Opus 5 Max Effort", "") == "max", "variant long form")
check(analyze_mod.parse_variant("", "muse-spark-1-3-xhigh") == "xhigh", "variant slug suffix")
check(analyze_mod.parse_variant("Plain Model", "plain-model") == "", "variant none")
check(analyze_mod.is_free_or({"prompt": "0", "completion": "0"}), "free zero strings")
check(not analyze_mod.is_free_or({"prompt": "1", "completion": "0"}), "non-free nonzero")

check(current({"checked_at": "2026-09-26", "expires_at": "2026-10-03"}, "2026-09-27"), "registry current")
check(not current({"checked_at": "2026-09-26", "expires_at": "2026-10-03"}, "2026-10-04"), "registry expired")
check(finite(48.1) and not finite(float("inf")) and not finite(True) and not finite(None), "finite guard")

o = obs("slug1", "benchlm", "score", 71.8, "benchlm-100", "benchlm-overall", "", "supported", "https://x", "2026-09-27", "")
check(set(o) == {"entity", "source", "field", "value", "unit", "benchmark", "version",
                 "evidence", "url", "observed_at", "expires_at"}, "observation schema")

snap = {"benchlm": {"leaderboard": [{"model": "Qwen3.8 Max", "overallScore": 71.8,
                                     "evidenceStatus": "supported", "categoryScores": {"coding": 80}}],
                     "pricing": [], "meta": {}},
        "llmstats": {"models": [{"id": "qwen3-8-max", "name": "Qwen3.8 Max",
                                 "top_scores": {"general": 1500}}],
                     "rankings": {"general": [{"model_id": "qwen3-8-max", "model_name": "Qwen3.8 Max",
                                               "rank": 12, "rating": 51.5, "evals": 9, "url": "https://u"}]},
                     "details": {}},
        "vals": {"models": []}}
by, pr, meta = benchlm_indexes(snap)
check("qwen38max" in by and by["qwen38max"]["overallScore"] == 71.8, "benchlm index by norm")
lb, rk, dt = llmstats_indexes(snap)
check("qwen38max" in lb, "llmstats model index by norm")
check(rk.get("qwen38max", {}).get("general", {}).get("rank") == 12, "llmstats rank index")

import copy
sys.path.insert(0, os.path.join(ROOT, "retrieval"))
from fetch_models import _llmstats_project_model
proj = _llmstats_project_model({"id": "m", "name": "M", "description": "LONG " * 500,
                                "organization": {"id": "o"}, "license": {"id": "mit"},
                                "providers": [{"provider_id": "p", "input_price_per_m": 1}],
                                "top_scores": {"general": 1}, "inference": {},
                                "unknown_future_field": True})
check("description" not in proj and "unknown_future_field" not in proj, "projection drops text/unknown")
check(proj["providers"][0]["in_per_m"] == 1, "projection provider prices")

models = [{"id": "Qwen3.8 Max", "slug": "qwen38max", "or_id": "", "name": "Qwen3.8 Max",
           "groups": [], "providers": [], "score": None, "cost_blended": None, "cost_source": "none",
           "free": False, "router": False, "free_status": "none", "variant": "",
           "efforts": [], "efforts_hint": [], "fallback_id": "", "fallback_provider": "",
           "benchlm": {"model": "Qwen3.8 Max", "overall": 71.8, "evidence": "supported",
                       "categories": {"coding": 80}, "in_price": 1, "out_price": 2},
           "benchlm_pricing": {"context": "1M", "type": "Open Weight"},
           "llmstats_api": {"id": "qwen3-8-max", "providers": [], "top_scores": {"general": 1500}},
           "llmstats_rank": {"general": {"rank": 12, "rating": 51.5, "evals": 9, "url": "https://u"}},
           "llmstats_detail": {"scores": []}, "vals_index": None,
           "website": {}}]
from crosswalk import attach_crosswalk
attach_crosswalk(copy.deepcopy(models), snap, {})
check(models[0].get("benchlm", {}).get("overall") == 71.8, "crosswalk preserves benchlm join")
obsv = build_observations(models, "2026-09-27")
check(any(x["field"] == "score" and x["source"] == "benchlm" for x in obsv), "benchlm score observation")
check(any(x["field"] == "rating.general" for x in obsv), "llmstats rating observation")
check(all(x["observed_at"] == "2026-09-27" for x in obsv), "observations stamped")
views = build_views(models)
check(len(views["benchlm_leaderboard"]) == 1, "benchlm view row")
check(views["benchlm_leaderboard"][0]["overall"] == 71.8, "benchlm view value, AA score untouched")
check(views["llmstats_leaderboard"][0]["rank"] == 12, "llmstats view rank-first order")
check(views["confidence"] == {"supported": 1, "estimated": 0, "other": 0}, "confidence counts")
check(all(v is None or isinstance(v, (int, float)) for v in [views["benchlm_leaderboard"][0]["overall"]]), "no mixed scales")

print(f"{len(fails)} failures")
sys.exit(1 if fails else 0)
