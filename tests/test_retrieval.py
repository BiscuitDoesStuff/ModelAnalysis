"""Offline source-completeness, credential and cache regressions."""
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline_common import resolve_credentials, load_config, atomic_json, check_identity, new_run_id
from retrieval import fetch_models as fm, fetch_websites as fw


class ConfigurationTests(unittest.TestCase):
    def test_credential_precedence_and_empty_values(self):
        resolved = resolve_credentials(
            {"OPENAI_API_KEY": "process", "ANTHROPIC_API_KEY": ""},
            {"OPENAI_API_KEY": "file", "ANTHROPIC_API_KEY": "file"}, lambda _: "user")
        self.assertEqual(resolved["OPENAI_API_KEY"], "process")
        self.assertEqual(resolved["ANTHROPIC_API_KEY"], "file")
        self.assertEqual(resolved["AA_API_KEY"], "user")

    def test_configuration_and_unique_identity(self):
        self.assertEqual(load_config()["run_days"], 90)
        self.assertEqual(len({new_run_id() for _ in range(1000)}), 1000)
        with self.assertRaises(ValueError):
            check_identity({"run_id": "other"}, "wanted", "fixture")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "config.json"
            atomic_json(p, {"disabled_sources": ["unknown"]})
            with self.assertRaises(ValueError):
                load_config(p)


class FetchTests(unittest.TestCase):
    def setUp(self):
        fm.FETCH_HEALTH.clear()

    def test_catalog_empty_is_distinct_from_missing_field(self):
        with patch.object(fm, "get", return_value={"data": []}):
            self.assertEqual(fm.catalog("openrouter", "https://fixture"), [])
            self.assertTrue(fm.FETCH_HEALTH["openrouter"]["complete"])
        with patch.object(fm, "get", return_value={}):
            with self.assertRaises(ValueError):
                fm.catalog("openrouter", "https://fixture")
            self.assertFalse(fm.FETCH_HEALTH["openrouter"]["complete"])

    def test_complete_and_interrupted_pagination(self):
        first = {"data": [{"id": "one"}], "has_more": True, "last_id": "one"}
        with patch.object(fm, "get", side_effect=[first, {"data": [{"id": "two"}]}]) as get:
            rows = fm.catalog("anthropic", "https://fixture/models", paginate=True)
            self.assertEqual([x["id"] for x in rows], ["one", "two"])
            self.assertIn("after_id=one", get.call_args.args[0])
            self.assertTrue(fm.FETCH_HEALTH["anthropic"]["complete"])
        with patch.object(fm, "get", side_effect=[first, TimeoutError("offline")]):
            self.assertEqual(fm.catalog("anthropic", "https://fixture", paginate=True), [{"id": "one"}])
            self.assertEqual(fm.FETCH_HEALTH["anthropic"]["status"], "partial")

    def test_unhandled_pagination_cannot_claim_complete(self):
        with patch.object(fm, "get", return_value={"data": [{"id": "one"}], "has_more": True}):
            fm.catalog("openai", "https://fixture")
            self.assertFalse(fm.FETCH_HEALTH["openai"]["complete"])

    def test_benchmark_component_survives_other_failure(self):
        with patch.object(fm, "get", side_effect=[{"models": [{"model": "one"}]}, TimeoutError("offline")]):
            result = fm.fetch_benchlm()
            self.assertEqual(len(result["leaderboard"]), 1)
            self.assertEqual(result["pricing"], [])
            self.assertEqual(fm.FETCH_HEALTH["benchlm"]["components"]["pricing"]["status"], "failed")

    def test_llmstats_partial_models_and_independent_rankings(self):
        def response(url, *args, **kwargs):
            if url.endswith("/account"):
                return {"usage": {"remaining": 100}}
            if "cursor=" in url:
                raise TimeoutError("page unavailable")
            if "/models?" in url:
                return {"models": [{"id": "one", "name": "One"}], "next_cursor": "second"}
            if "/benchmarks?" in url:
                return {"benchmarks": [{"id": "bench"}]}
            if "category=reasoning" in url:
                raise TimeoutError("ranking unavailable")
            return {"models": []}
        with patch.dict(os.environ, {"LLM_STATS_API_KEY": "fixture", "LLM_STATS_DETAIL_MAX": "0"}), \
             patch.object(fm, "get", side_effect=response), patch.object(fm, "log_err"):
            result = fm.fetch_llmstats()
        self.assertEqual(result["model_count"], 1)
        status = fm.FETCH_HEALTH["llmstats"]
        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["components"]["models"]["status"], "partial")
        self.assertEqual(status["components"]["rankings.general"]["status"], "complete")
        self.assertEqual(status["components"]["rankings.reasoning"]["status"], "failed")

    def test_windows_fallback_applied_before_fetch_and_disable_wins(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(fm, "apply_credentials") as creds:
            config = load_config()
            config["disabled_sources"] = list(fm.SOURCES)
            with patch.object(fm, "get", side_effect=AssertionError("unexpected network")), \
                 patch.object(fm, "RAW", tmp), patch.object(fm, "ERRLOG", str(Path(tmp) / "errors")), \
                 patch.object(fm, "CONFIG", config):
                output = fm.main(tmp, "fixture", "2026-09-26T00:00:00+00:00", config)
                data = json.loads(Path(output).read_text(encoding="utf-8"))
            creds.assert_called_once()
            self.assertTrue(all(v["status"] == "skipped" for v in data["source_health"].values()))


class CacheTests(unittest.TestCase):
    def test_cache_age_uses_observation_time_not_mtime(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(fw, "CACHE", tmp):
            data = {"url": "https://fixture", "value": 10}
            fw.cache_put("fixture", "one", data)
            read = fw.cache_get("fixture", "one")
            self.assertTrue(read["cache_hit"])
            self.assertEqual(read["fetched_at"], data["fetched_at"])
            data["fetched_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).isoformat()
            atomic_json(fw._cache_path("fixture", "one"), data)
            self.assertIsNone(fw.cache_get("fixture", "one"))
            atomic_json(fw._cache_path("fixture", "legacy"), {"url": "old"})
            self.assertIsNone(fw.cache_get("fixture", "legacy"))


if __name__ == "__main__":
    unittest.main()
