"""Offline source-completeness, credential and cache regressions."""
import datetime as dt
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
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
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ctx = fm.FetchContext("fixture", load_config(), Path(self.temp.name) / "errors")

    def test_catalog_empty_is_distinct_from_missing_field(self):
        with patch.object(self.ctx.client, "get", return_value={"data": []}):
            self.assertEqual(fm.catalog(self.ctx, "https://fixture"), [])
            self.assertTrue(self.ctx.health["complete"])
        with patch.object(self.ctx.client, "get", return_value={}):
            with self.assertRaises(ValueError):
                fm.catalog(self.ctx, "https://fixture")
            self.assertFalse(self.ctx.health["complete"])

    def test_complete_and_interrupted_pagination(self):
        first = {"data": [{"id": "one"}], "has_more": True, "last_id": "one"}
        with patch.object(self.ctx.client, "get", side_effect=[first, {"data": [{"id": "two"}]}]) as get:
            rows = fm.catalog(self.ctx, "https://fixture/models", paginate=True)
            self.assertEqual([x["id"] for x in rows], ["one", "two"])
            self.assertIn("after_id=one", get.call_args.args[0])
            self.assertTrue(self.ctx.health["complete"])
        with patch.object(self.ctx.client, "get", side_effect=[first, TimeoutError("offline")]):
            self.assertEqual(fm.catalog(self.ctx, "https://fixture", paginate=True), [{"id": "one"}])
            self.assertEqual(self.ctx.health["status"], "partial")

    def test_unhandled_pagination_cannot_claim_complete(self):
        with patch.object(self.ctx.client, "get", return_value={"data": [{"id": "one"}], "has_more": True}):
            fm.catalog(self.ctx, "https://fixture")
            self.assertFalse(self.ctx.health["complete"])

    def test_benchmark_component_survives_other_failure(self):
        with patch.object(self.ctx.client, "get", side_effect=[{"models": [{"model": "one"}]}, TimeoutError("offline")]):
            result = fm.fetch_benchlm(self.ctx)
            self.assertEqual(len(result["leaderboard"]), 1)
            self.assertEqual(result["pricing"], [])
            self.assertEqual(self.ctx.health["components"]["pricing"]["status"], "failed")

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
             patch.object(self.ctx.client, "get", side_effect=response), patch.object(self.ctx, "log_err"):
            result = fm.fetch_llmstats(self.ctx)
        self.assertEqual(result["model_count"], 1)
        status = self.ctx.health
        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["components"]["models"]["status"], "partial")
        self.assertEqual(status["components"]["rankings.general"]["status"], "complete")
        self.assertEqual(status["components"]["rankings.reasoning"]["status"], "failed")

    def test_validator_stage_flush_and_304_reuse_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            ctx = fm.FetchContext("fixture", load_config(), Path(tmp) / "errors", cache_dir=cache)
            ctx.client.last_response_headers = {"etag": '"v1"'}
            with patch.object(ctx.client, "get", return_value={"data": [{"id": "one"}]}):
                self.assertEqual(fm.catalog(ctx, "https://fixture/models"), [{"id": "one"}])
            self.assertEqual(len(ctx.pending), 1)
            self.assertFalse(cache.exists())  # writes wait for the source's final health
            with patch.object(ctx.client, "get", return_value={}):
                with self.assertRaises(ValueError):
                    fm.catalog(ctx, "https://fixture/bad")
            self.assertEqual(len(ctx.pending), 1)  # a malformed body stages nothing

            fm._validator_flush(ctx, "2026-09-01T00:00:00+00:00")
            self.assertEqual(ctx.pending, [])
            entry = fm._validator_get(ctx, "https://fixture/models")
            self.assertEqual((entry["etag"], entry["fetched_at"], entry["data"]),
                             ('"v1"', "2026-09-01T00:00:00+00:00", {"data": [{"id": "one"}]}))
            error = urllib.error.HTTPError("https://fixture/models", 304, "Not Modified", {}, io.BytesIO(b""))
            with patch.object(ctx.client, "get", side_effect=error):
                self.assertEqual(fm.catalog(ctx, "https://fixture/models"), [{"id": "one"}])
            self.assertEqual(ctx.reused_at, "2026-09-01T00:00:00+00:00")  # main keeps this time
            self.assertTrue(ctx.health["complete"])
            # A stored entry for a plain (no cache dir) context is never consulted.
            plain = fm.FetchContext("fixture", load_config(), Path(tmp) / "errors")
            with patch.object(plain.client, "get", return_value={"data": [{"id": "two"}]}) as get:
                self.assertEqual(fm.catalog(plain, "https://fixture/models"), [{"id": "two"}])
            passed = get.call_args.args[1] or {}
            self.assertFalse(any(str(key).lower().startswith("if-") for key in passed))
            self.assertIsNone(plain.reused_at)

    def test_windows_fallback_applied_before_fetch_and_disable_wins(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(fm, "apply_credentials") as creds:
            config = load_config()
            config["disabled_sources"] = list(fm.SOURCES)
            with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network")):
                output = fm.main(tmp, "fixture", "2026-09-26T00:00:00+00:00", config)
                data = json.loads(Path(output).read_text(encoding="utf-8"))
            creds.assert_called_once()
            self.assertTrue(all(v["status"] == "skipped" for v in data["source_health"].values()))


class CacheTests(unittest.TestCase):
    def test_cache_age_uses_observation_time_not_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = fw.FetchContext("fixture", load_config(), Path(tmp) / "errors", cache_dir=tmp)
            data = {"url": "https://fixture", "value": 10}
            fw.cache_put(ctx, "one", data)
            read = fw.cache_get(ctx, "one")
            self.assertTrue(read["cache_hit"])
            self.assertEqual(read["fetched_at"], data["fetched_at"])
            data["fetched_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).isoformat()
            atomic_json(fw._cache_path(ctx, "one"), data)
            self.assertIsNone(fw.cache_get(ctx, "one"))
            atomic_json(fw._cache_path(ctx, "legacy"), {"url": "old"})
            self.assertIsNone(fw.cache_get(ctx, "legacy"))

    def test_vals_pages_match_exact_or_longest_model_key(self):
        # Allowlist order must not decide the match: opus-5 sorts first but is only a prefix of opus-5-5.
        allowlist = [{"slug": "claudeopus5"}, {"slug": "claudeopus55"}]
        hrefs = ["/models/anthropic_claude-opus-5-5", "/models/anthropic_claude-opus-5", "/models/"]
        snap = {"vals": {"models": [{"href": h} for h in hrefs]}}
        with tempfile.TemporaryDirectory() as tmp:
            ctx = fw.FetchContext("vals", load_config(), Path(tmp) / "errors", cache_dir=tmp)
            with patch.object(ctx.client, "get_text", side_effect=lambda url, **kw: url), \
                 patch("sys.stdout", io.StringIO()):
                pages = fw.fetch_vals_pages(ctx, snap, allowlist)
        self.assertEqual({k: v["vals_href"] for k, v in pages.items()},
                         {"claudeopus55": hrefs[0], "claudeopus5": hrefs[1]})


if __name__ == "__main__":
    unittest.main()
