"""Synthetic transport/clock checks. Never contacts a provider or reads credentials."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

from pipeline_common import ROOT, SOURCES, atomic_json, load_config
from reports.build_report import reliability_tables, reliability_html
from retrieval.http import SourceClient, JITTER, RETRY_AFTER_CAP
from retrieval import fetch_models as fm, fetch_websites as fw


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Transport:
    def __init__(self, clock, *responses):
        self.clock, self.responses = clock, iter(responses)
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        self.clock.now += 0.25
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(response)


class Response(io.BytesIO):
    def __init__(self, body, headers):
        super().__init__(body)
        self.headers = headers


class HeaderedTransport:
    """Serves (body, headers) tuples or exceptions, recording every request."""
    def __init__(self, clock, *responses):
        self.clock, self.responses = clock, iter(responses)
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        self.clock.now += 0.25
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        body, headers = item if isinstance(item, tuple) else (item, {})
        return Response(body, headers)


def client(source, kind, *responses, rand=None):
    clock = Clock()
    transport = Transport(clock, *responses)
    # rand=0.5 keeps sleeps at the exact base delay; jitter tests inject other draws.
    return SourceClient(source, kind, transport=transport, clock=clock, sleeper=clock.sleep,
                        rand=rand or (lambda: 0.5)), transport, clock


def headered_client(source, kind, *responses):
    clock = Clock()
    transport = HeaderedTransport(clock, *responses)
    return (SourceClient(source, kind, transport=transport, clock=clock, sleeper=clock.sleep,
                         rand=lambda: 0.5), transport, clock)


def if_headers(request):
    """Conditional request headers as sent (Request capitalizes stored keys)."""
    return {key.lower(): value for key, value in request.headers.items() if key.lower().startswith("if-")}


def not_modified(url):
    return urllib.error.HTTPError(url, 304, "Not Modified", {}, io.BytesIO(b""))


class HttpMetricsTests(unittest.TestCase):
    def test_bytes_failures_retries_timing_and_redaction(self):
        url = "https://user:password@fixture.invalid/private?token=secret"
        error = urllib.error.HTTPError(url, 503, "unavailable", {}, io.BytesIO(b"error"))
        body = '{"text":"é"}'.encode()
        http, transport, clock = client("benchlm", "api", error, TimeoutError("token=secret"), body)
        self.assertEqual(http.get(url, {"Authorization": "Bearer private"}), {"text": "é"})
        metrics = http.snapshot()
        self.assertEqual(metrics["requests"], 3)
        self.assertEqual(metrics["retries"], 2)
        self.assertEqual(metrics["response_bytes"], 5 + len(body))
        self.assertEqual(metrics["request_seconds"], 0.75)
        self.assertEqual(metrics["elapsed_seconds"], 3.75)
        self.assertEqual(clock.sleeps, [1, 2])
        self.assertEqual([timeout for _, timeout in transport.calls], [60] * 3)
        self.assertEqual(list(metrics["hosts"]), ["fixture.invalid"])
        for secret in ("password", "private", "token", "secret", "Authorization", "Bearer", "https://", "error"):
            self.assertNotIn(secret, json.dumps(metrics))
        metrics["hosts"]["fixture.invalid"]["requests"] = 999
        self.assertEqual(http.snapshot()["requests"], 3)

    def test_4xx_fails_fast_except_quota_429_which_waits_and_retries(self):
        # Deliberate Phase 6 revision: the pre-optimisation baseline treated 429
        # like any other 4xx; Retry-After support makes 429 wait and retry now.
        for kind in ("api", "website"):
            for code in (401, 404):
                with self.subTest(kind=kind, code=code):
                    error = urllib.error.HTTPError("https://fixture.invalid", code, "failed", {}, io.BytesIO(b"denied"))
                    http, _, clock = client("test", kind, error)
                    with self.assertRaises(urllib.error.HTTPError):
                        http.get_text("https://fixture.invalid")
                    self.assertEqual(http.snapshot()["response_bytes"], 6)
                    self.assertEqual(http.snapshot()["requests"], 1)
                    self.assertEqual(clock.sleeps, [])
            with self.subTest(kind=kind, code="429 honours Retry-After"):
                waited = urllib.error.HTTPError("https://fixture.invalid", 429, "slow",
                                                {"Retry-After": "3"}, io.BytesIO(b"slow"))
                http, _, clock = client("test", kind, waited, b"recovered")
                self.assertEqual(http.get_text("https://fixture.invalid"), "recovered")
                self.assertEqual(clock.sleeps, [3])
                self.assertEqual((http.snapshot()["requests"], http.snapshot()["retries"]), (2, 1))
            with self.subTest(kind=kind, code="429 caps Retry-After"):
                capped = urllib.error.HTTPError("https://fixture.invalid", 429, "slow",
                                                {"Retry-After": "600"}, io.BytesIO(b"slow"))
                http, _, clock = client("test", kind, capped, b"recovered")
                self.assertEqual(http.get_text("https://fixture.invalid"), "recovered")
                self.assertEqual(clock.sleeps, [RETRY_AFTER_CAP])

    def test_503_honours_retry_after_and_invalid_or_missing_header_falls_back(self):
        busy = urllib.error.HTTPError("https://fixture.invalid", 503, "unavailable",
                                      {"Retry-After": "4"}, io.BytesIO(b"busy"))
        http, _, clock = client("test", "api", busy, b"ok")
        self.assertEqual(http.get_text("https://fixture.invalid"), "ok")
        self.assertEqual(clock.sleeps, [4])
        for kind in ("api", "website"):
            for hint in (None, "soon", "Wed, 21 Oct 2026 07:28:00 GMT", "-5"):
                with self.subTest(kind=kind, retry_after=hint):
                    headers = {} if hint is None else {"Retry-After": hint}
                    error = urllib.error.HTTPError("https://fixture.invalid", 429, "slow", headers, io.BytesIO(b""))
                    http, _, clock = client("test", kind, error, b"ok")
                    self.assertEqual(http.get_text("https://fixture.invalid"), "ok")
                    self.assertEqual(clock.sleeps, [1])  # today's backoff, jitter-neutral helper

    def test_backoff_jitter_is_bounded_and_attempt_counts_unchanged(self):
        draws = iter([0.0, 1.0])
        http, _, clock = client("benchlm", "api", TimeoutError("offline"), TimeoutError("offline"), b"{}",
                                rand=lambda: next(draws))
        self.assertEqual(http.get("https://fixture.invalid"), {})
        self.assertEqual((http.snapshot()["requests"], http.snapshot()["retries"]), (3, 2))
        self.assertEqual(clock.sleeps, [1 - JITTER / 2, 2 * (1 + JITTER / 2)])
        for base, slept in zip((1, 2), clock.sleeps):
            self.assertGreaterEqual(slept, base * (1 - JITTER / 2))
            self.assertLessEqual(slept, base * (1 + JITTER / 2))
        web_draws = iter([0.0])
        web, _, web_clock = client("test", "website", TimeoutError("offline"), b"ok",
                                   rand=lambda: next(web_draws))
        self.assertEqual(web.get_text("https://fixture.invalid"), "ok")
        self.assertEqual(web_clock.sleeps, [1 - JITTER / 2])
        self.assertEqual((web.snapshot()["requests"], web.snapshot()["retries"]), (2, 1))

    def test_parse_failure_retries_but_http_clock_excludes_parsing_and_backoff(self):
        http, _, clock = client("test", "api", b"bad json", b"{}")
        self.assertEqual(http.get("https://fixture.invalid"), {})
        clock.now += 7  # source parsing / projection outside the transport
        self.assertEqual(http.snapshot()["response_bytes"], 10)
        self.assertEqual(http.snapshot()["request_seconds"], 0.5)
        self.assertEqual(http.snapshot()["elapsed_seconds"], 8.5)
        self.assertEqual(http.snapshot()["retries"], 1)

    def test_exhaustion_and_original_exception_policy(self):
        for kind, attempts, sleeps in (("api", 3, [1, 2]), ("website", 2, [1])):
            http, transport, clock = client("test", kind, *[TimeoutError("offline") for _ in range(attempts)])
            with self.assertRaises(TimeoutError):
                http.get_text("https://fixture.invalid")
            self.assertEqual(http.snapshot()["requests"], attempts)
            self.assertEqual(http.snapshot()["response_bytes"], 0)
            self.assertEqual(http.snapshot()["retries"], attempts - 1)
            self.assertEqual(clock.sleeps, sleeps)
            self.assertEqual(transport.calls[0][1], 25 if kind == "website" else 60)
        http, _, clock = client("test", "api", RuntimeError("not a retryable API failure"))
        with self.assertRaises(RuntimeError):
            http.get("https://fixture.invalid")
        self.assertEqual(clock.sleeps, [])
        http, _, clock = client("test", "website", RuntimeError("website retries any exception"), b"ok")
        self.assertEqual(http.get_text("https://fixture.invalid"), "ok")
        self.assertEqual(clock.sleeps, [1])

    def test_source_kind_and_host_isolation(self):
        api, _, _ = client("benchlm", "api", b"{}", b"[]")
        web, _, _ = client("benchlm", "website", b"text")
        api.get("https://same.invalid/a")
        api.get("https://other.invalid/a")
        web.get_text("https://same.invalid/b")
        self.assertEqual(api.snapshot()["requests"], 2)
        self.assertEqual(web.snapshot()["requests"], 1)
        self.assertEqual(api.snapshot()["hosts"]["same.invalid"]["response_bytes"], 2)
        self.assertEqual(web.snapshot()["hosts"]["same.invalid"]["response_bytes"], 4)
        self.assertNotEqual(api.snapshot()["kind"], web.snapshot()["kind"])

    def test_body_read_time_and_explicit_timeout(self):
        clock = Clock()
        class Response(io.BytesIO):
            def read(self):
                clock.now += 2
                return super().read()
        def transport(request, timeout):
            self.assertEqual(timeout, 90)
            clock.now += 1
            return Response(b"{}")
        http = SourceClient("modelsdev", "api", transport=transport, clock=clock)
        self.assertEqual(http.get("https://fixture.invalid", timeout=90), {})
        self.assertEqual(http.snapshot()["request_seconds"], 3)
        self.assertEqual(http.snapshot()["elapsed_seconds"], 3)


class InvocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("unexpected live HTTP"))
        self.blocked = self.network.start()
        self.addCleanup(self.network.stop)

    def test_repeat_api_main_paths_config_failures_zero_and_skips(self):
        cfg = load_config()
        cfg["disabled_sources"] = [s for s in SOURCES if s not in ("openrouter", "nvidia")]
        clients = []
        def factory(source, kind, **kwargs):
            http, _, _ = client(source, kind, b'{"data":[]}' if source == "openrouter" else TimeoutError("offline"))
            if source == "nvidia":
                http.transport.responses = iter([TimeoutError("offline")] * 3)
            clients.append(http)
            return http
        with patch.object(fm, "apply_credentials"), patch.object(fm, "SourceClient", side_effect=factory), \
             patch.dict(os.environ, {}, clear=True), patch.object(fm, "ROOT", str(self.root)), \
             contextlib.redirect_stdout(io.StringIO()):
            first = fm.main(self.root / "first", "one", config=cfg)
            cfg["disabled_sources"] = list(SOURCES)
            second = fm.main(self.root / "second", "two", config=cfg)
            default = fm.main(run_id="three", config=cfg)
        a, b = [json.loads(Path(p).read_text(encoding="utf-8")) for p in (first, second)]
        # Contexts start inside pool workers, so creation order is scheduling
        # order; each run still creates exactly one client per source, and the
        # published snap/health keys keep SOURCES order from the main thread.
        groups = [clients[i * len(SOURCES):(i + 1) * len(SOURCES)] for i in range(3)]
        self.assertEqual(len(clients), len(SOURCES) * 3)
        for group in groups:
            self.assertEqual(sorted(c.source for c in group), sorted(SOURCES))
        self.assertEqual(list(a["source_health"]), list(SOURCES))
        self.assertEqual(list(a)[4:4 + len(SOURCES)], list(SOURCES))
        self.assertEqual(a["source_health"]["openrouter"]["count"], 0)
        self.assertEqual(a["source_health"]["openrouter"]["retrieval"]["requests"], 1)
        self.assertEqual(a["source_health"]["nvidia"]["status"], "failed")
        self.assertEqual(a["source_health"]["nvidia"]["retrieval"]["requests"], 3)
        self.assertTrue(all(h["retrieval"]["requests"] == 0 and h["status"] == "skipped" for h in b["source_health"].values()))
        self.assertNotEqual(Path(first).parent, Path(second).parent)
        self.assertEqual(Path(default).parent, self.root / "raw")
        self.assertEqual((self.root / "second" / "_errors.log").read_text(), "")
        self.blocked.assert_not_called()

    def test_parallel_fetch_bounded_ordered_llmstats_after_catalogs(self):
        cfg = load_config()
        main_ident = threading.get_ident()
        guard, active, peak, idents = threading.Lock(), [0], [0], []
        account = lambda remaining: json.dumps(
            {"usage": {"remaining": remaining, "quota_day": "2026-09-27"}}).encode()
        llmstats_script = [account(250),
                           b'{"models":[{"id":"m1","name":"M One"}]}',
                           b'{"benchmarks":[]}',
                           b'{"models":[]}', b'{"models":[]}', b'{"models":[]}', b'{"models":[]}',
                           b'{"name":"M One","scores":[]}', account(240)]
        def factory(source, kind, **kwargs):
            idents.append((source, threading.get_ident()))
            if source == "llmstats":
                responses = list(llmstats_script)
            elif source == "openrouter":
                responses = [json.dumps({"data": [{"id": "acme/m1",
                                                   "pricing": {"prompt": 0, "completion": 0}}]}).encode()]
            elif source == "modelsdev":
                responses = [b'{}']
            elif source == "benchlm":
                responses = [b'{"models":[]}', b'{"models":[]}']
            elif source == "vals":
                responses = [b"<html><body>none</body></html>"]
            else:
                responses = [b'{"data":[]}']
            http, transport, _ = client(source, kind, *responses)
            http.log = kwargs.get("log", http.log)
            return http
        orig_call = Transport.__call__
        def tracked(self, request, timeout):
            with guard:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            try:
                time.sleep(0.02)
                return orig_call(self, request, timeout)
            finally:
                with guard:
                    active[0] -= 1
        buf = io.StringIO()
        with patch.object(fm, "apply_credentials"), patch.object(fm, "SourceClient", side_effect=factory), \
             patch.object(Transport, "__call__", tracked), \
             patch.dict(os.environ, {"LLM_STATS_API_KEY": "fixture", "OPENAI_API_KEY": "fixture",
                                     "ANTHROPIC_API_KEY": "fixture"}), \
             contextlib.redirect_stdout(buf):
            out = fm.main(self.root / "run", "parallel", config=cfg)
        snap = json.loads(Path(out).read_text(encoding="utf-8"))
        printed = [line.split("source ")[1].split(":")[0] for line in buf.getvalue().splitlines()
                   if line.startswith("source ")]
        self.assertEqual(printed, list(SOURCES))
        self.assertEqual(list(snap["source_health"]), list(SOURCES))
        self.assertEqual(list(snap)[4:4 + len(SOURCES)], list(SOURCES))
        self.assertGreater(peak[0], 1)
        self.assertLessEqual(peak[0], 4)
        by_source = dict(idents)
        self.assertEqual(len(by_source), len(SOURCES))
        self.assertEqual(by_source["llmstats"], main_ident)
        self.assertGreater(len({ident for _, ident in idents}), 1)
        self.assertEqual(snap["llmstats"]["model_count"], 1)
        self.assertIn("m1", snap["llmstats"]["details"])
        self.assertEqual((self.root / "run" / "_errors.log").read_text(), "")
        self.blocked.assert_not_called()

    def test_parallel_failure_isolated_and_error_log_serialized(self):
        cfg = load_config()
        cfg["disabled_sources"] = [s for s in SOURCES if s not in ("openrouter", "nvidia", "zen")]
        def factory(source, kind, **kwargs):
            if source == "openrouter":
                http, _, _ = client(source, kind, b'{"data":[]}')
            else:
                http, _, _ = client(source, kind, *[TimeoutError("offline")] * 3)
            http.log = kwargs.get("log", http.log)
            return http
        buf = io.StringIO()
        with patch.object(fm, "apply_credentials"), patch.object(fm, "SourceClient", side_effect=factory), \
             patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(buf):
            out = fm.main(self.root / "fail", "isolated", config=cfg)
        snap = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(snap["source_health"]["openrouter"]["status"], "complete")
        self.assertEqual(snap["source_health"]["nvidia"]["status"], "failed")
        self.assertEqual(snap["source_health"]["zen"]["status"], "failed")
        lines = (self.root / "fail" / "_errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 8)
        for line in lines:
            self.assertRegex(line, r"^\S+ (retry [123]/3|FAILED) ")
        self.blocked.assert_not_called()

    def test_llmstats_daily_budget_cuts_details_first(self):
        script = lambda: [json.dumps({"usage": {"remaining": 250, "quota_day": "2026-09-27"}}).encode(),
                          b'{"models":[{"id":"m1","name":"M One"}]}',
                          b'{"benchmarks":[]}',
                          b'{"models":[]}', b'{"models":[]}', b'{"models":[]}', b'{"models":[]}',
                          b'{"name":"M One","scores":[]}',
                          json.dumps({"usage": {"remaining": 240, "quota_day": "2026-09-27"}}).encode()]
        snap_so_far = {"openrouter": [{"id": "acme/m1", "pricing": {"prompt": 0, "completion": 0}}],
                       "aa": {"data": []}, "benchlm": {"leaderboard": []}}
        def run_with(budget):
            cfg = load_config()
            cfg["llmstats_daily_budget"] = budget
            http, transport, _ = client("llmstats", "api", *script())
            ctx = fm.FetchContext("llmstats", cfg, self.root / "errors", client=http)
            with patch.dict(os.environ, {"LLM_STATS_API_KEY": "fixture"}):
                result = fm.fetch_llmstats(ctx, snap_so_far)
            data = [c for c in transport.calls if not c[0].full_url.endswith("/account")]
            return result, ctx, data
        result, ctx, data = run_with(0)
        self.assertIn("m1", result["details"])
        self.assertEqual(len(data), 7)
        self.assertEqual(ctx.health["components"]["details"]["budget"], 12)
        self.assertNotIn("daily_budget", ctx.health["components"]["details"])
        result, ctx, data = run_with(1000)
        self.assertIn("m1", result["details"])
        self.assertEqual(len(data), 7)
        result, ctx, data = run_with(6)
        self.assertEqual(result["details"], {})
        self.assertEqual(len(data), 6)
        details = ctx.health["components"]["details"]
        self.assertEqual(details["status"], "skipped")
        self.assertEqual(details["daily_budget"], 6)
        self.assertIn("llmstats_daily_budget", details["reason"])
        result, ctx, data = run_with(3)
        self.assertEqual(result["details"], {})
        self.assertLessEqual(len(data), 3)
        self.assertEqual(ctx.health["components"]["rankings.reasoning"]["status"], "skipped")
        self.blocked.assert_not_called()

    def test_llmstats_daily_budget_config_validation_and_refusal_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "config.json"
            atomic_json(p, {"llmstats_daily_budget": -1})
            with self.assertRaises(ValueError):
                load_config(p)
            atomic_json(p, {"llmstats_daily_budget": "12"})
            with self.assertRaises(ValueError):
                load_config(p)
        cfg = load_config()
        cfg["llmstats_daily_budget"] = 100
        low = json.dumps({"usage": {"remaining": 4, "quota_day": "2026-09-27"}}).encode()
        http, transport, _ = client("llmstats", "api", low)
        ctx = fm.FetchContext("llmstats", cfg, self.root / "errors", client=http)
        with patch.dict(os.environ, {"LLM_STATS_API_KEY": "fixture"}):
            result = fm.fetch_llmstats(ctx, {})
        self.assertIn("quota too low", result["error"])
        self.assertIsNone(ctx.client.quota["after"]["remaining"])
        self.assertEqual(len(transport.calls), 1)
        self.blocked.assert_not_called()

    def test_repeat_website_main_cache_timestamp_and_paths(self):
        snap = self.root / "snapshot.json"
        atomic_json(snap, {"retrieved_at": "fixture", "benchlm": {"leaderboard": [{"model": "One"}, {"model": "Two"}]}})
        cfg = load_config()
        cfg.update(disabled_sources=["llmstats", "vals"], website_max_pages=1)
        clients = []
        def factory(source, kind, **kwargs):
            http, _, _ = client(source, kind, b"# one", b"# two")
            clients.append(http)
            return http
        with patch.object(fw, "SourceClient", side_effect=factory), patch.object(fw, "ROOT", str(self.root)), \
             contextlib.redirect_stdout(io.StringIO()):
            first = fw.main(snap, self.root / "first", self.root / "cache1", cfg)
            second = fw.main(snap, self.root / "second", self.root / "cache1", cfg)
            cfg["website_max_pages"] = 2
            third = fw.main(snap, self.root / "third", self.root / "cache2", cfg)
            default = fw.main(snap, config=cfg)
        a, b, c = [json.loads(Path(p).read_text(encoding="utf-8")) for p in (first, second, third)]
        self.assertEqual(a["benchlm_md"]["one"]["fetched_at"], b["benchlm_md"]["one"]["fetched_at"])
        self.assertTrue(b["benchlm_md"]["one"]["cache_hit"])
        self.assertEqual(b["source_health"]["benchlm_md"]["retrieval"]["cache_hits"], 1)
        self.assertEqual(b["source_health"]["benchlm_md"]["retrieval"]["requests"], 0)
        self.assertEqual(c["source_health"]["benchlm_md"]["retrieval"]["requests"], 2)
        self.assertEqual(len(c["benchlm_md"]), 2)
        self.assertEqual([x.source for x in clients], ["benchlm", "llmstats", "vals"] * 4)
        self.assertEqual(Path(default).parent, self.root / "raw")
        self.assertTrue((self.root / "raw" / "cache_websites" / "benchlm__one.json").exists())
        for src in ("llmstats", "vals"):
            self.assertEqual(a["source_health"][src]["retrieval"]["requests"], 0)
        self.blocked.assert_not_called()

    def test_website_failures_and_empty_allowlist_are_measured(self):
        snap = self.root / "snapshot.json"
        atomic_json(snap, {"retrieved_at": "fixture", "benchlm": {"leaderboard": [{"model": "One"}]}})
        cfg = load_config()
        cfg["disabled_sources"] = ["llmstats", "vals"]
        def factory(source, kind, **kwargs):
            return client(source, kind, TimeoutError("offline"), TimeoutError("offline"))[0]
        with patch.object(fw, "SourceClient", side_effect=factory), contextlib.redirect_stdout(io.StringIO()):
            first = fw.main(snap, self.root / "first", self.root / "cache", cfg)
            atomic_json(snap, {"retrieved_at": "fixture"})
            second = fw.main(snap, self.root / "second", self.root / "cache", cfg)
        a, b = [json.loads(Path(p).read_text(encoding="utf-8"))["source_health"]["benchlm_md"] for p in (first, second)]
        self.assertEqual((a["status"], a["failed_count"], a["retrieval"]["requests"]), ("partial", 1, 2))
        self.assertEqual((b["status"], b["retrieval"]["requests"]), ("complete", 0))

    def test_direct_script_and_module_help(self):
        for module in ("fetch_models", "fetch_websites"):
            for command in ([f"retrieval/{module}.py"], ["-m", f"retrieval.{module}"]):
                result = subprocess.run([sys.executable, "-B", *command, "--help"], cwd=ROOT,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)


class QuotaTests(unittest.TestCase):
    def run_fetch(self, before, after=None):
        responses = [before]
        if after is not None:
            responses += [b'{"models":[]}', b'{"benchmarks":[]}', *([b'{"models":[]}'] * 4), after]
        http, transport, _ = client("llmstats", "api", *responses)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"LLM_STATS_API_KEY": "synthetic-secret", "LLM_STATS_DETAIL_MAX": "0"}):
            ctx = fm.FetchContext("llmstats", load_config(), Path(tmp) / "errors", client=http)
            result = fm.fetch_llmstats(ctx)
        return result, http.snapshot(), transport

    def test_before_after_from_only_existing_calls(self):
        def account(remaining):
            return json.dumps({"usage": {"remaining": remaining, "quota_day": "2026-09-27", "private": "secret"},
                               "email": "private", "token": "secret"}).encode()
        result, metrics, transport = self.run_fetch(account(100), account(94))
        self.assertEqual(len(transport.calls), 8)
        self.assertEqual(sum(req.full_url.endswith("/account") for req, _ in transport.calls), 2)
        self.assertEqual(metrics["quota"], {"before": {"remaining": 100, "day": "2026-09-27"},
                                            "after": {"remaining": 94, "day": "2026-09-27"}})
        self.assertEqual(result["meta"]["quota_remaining"], 94)
        self.assertNotIn("secret", json.dumps([metrics, result]))

    def test_refusal_does_not_add_after_call(self):
        result, metrics, transport = self.run_fetch(b'{"usage":{"remaining":0,"quota_day":"2026-09-27"}}')
        self.assertIn("quota too low", result["error"])
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(metrics["quota"]["before"]["remaining"], 0)
        self.assertEqual(metrics["quota"]["after"], {"remaining": None, "day": None})

    def test_unavailable_account_unknown_without_added_calls(self):
        error = lambda: urllib.error.HTTPError("https://fixture.invalid", 403, "no account", {}, io.BytesIO(b"no"))
        _, metrics, transport = self.run_fetch(error(), error())
        self.assertEqual(len(transport.calls), 8)
        self.assertEqual(metrics["quota"], {k: {"remaining": None, "day": None} for k in ("before", "after")})

    def test_sanitizes_non_numeric_remaining_and_non_day(self):
        for remaining in (True, "123", {"token": "secret"}, float("inf"), float("nan")):
            self.assertEqual(fm.quota_sample({"usage": {"remaining": remaining, "quota_day": "secret"}}),
                             {"remaining": None, "day": None})
        self.assertEqual(fm.quota_sample({"usage": "secret"}), {"remaining": None, "day": None})

    def test_missing_key_no_requests_and_quota_unknown(self):
        http, transport, _ = client("llmstats", "api")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            ctx = fm.FetchContext("llmstats", load_config(), Path(tmp) / "errors", client=http)
            self.assertIn("skipped", fm.fetch_llmstats(ctx))
        self.assertEqual(transport.calls, [])
        self.assertEqual(http.snapshot()["requests"], 0)
        self.assertIsNone(http.snapshot()["quota"]["before"]["remaining"])

    def test_existing_detail_cap_respects_remaining_quota(self):
        responses = [b'{"usage":{"remaining":9}}', b'{"models":[{"id":"one"},{"id":"two"}]}',
                     b'{"benchmarks":[]}', *([b'{"models":[]}'] * 4), b'{"name":"One","scores":[]}',
                     b'{"usage":{"remaining":2}}']
        http, transport, _ = client("llmstats", "api", *responses)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"LLM_STATS_API_KEY": "fixture", "LLM_STATS_DETAIL_MAX": "12"}):
            ctx = fm.FetchContext("llmstats", load_config(), Path(tmp) / "errors", client=http)
            result = fm.fetch_llmstats(ctx, {"openrouter": [{"id": "one:free"}, {"id": "two:free"}]})
        self.assertEqual(list(result["details"]), ["one"])
        self.assertEqual(ctx.health["components"]["details"]["budget"], 1)
        self.assertEqual(len(transport.calls), 9)

    def test_interrupted_catalog_keeps_partial_rows_and_attempt_metrics(self):
        first = b'{"data":[{"id":"one"}],"has_more":true,"last_id":"one"}'
        http, transport, _ = client("anthropic", "api", first, *([TimeoutError("offline")] * 3))
        with tempfile.TemporaryDirectory() as tmp:
            ctx = fm.FetchContext("anthropic", load_config(), Path(tmp) / "errors", client=http)
            self.assertEqual(fm.catalog(ctx, "https://fixture.invalid/models", paginate=True), [{"id": "one"}])
        self.assertEqual(ctx.health["status"], "partial")
        self.assertFalse(ctx.health["complete"])
        self.assertIn("after_id=one", transport.calls[1][0].full_url)
        self.assertEqual(http.snapshot()["requests"], 4)
        self.assertEqual(http.snapshot()["retries"], 2)
        self.assertEqual(http.snapshot()["response_bytes"], len(first))


class ConditionalRevalidationTests(unittest.TestCase):
    """304 revalidation for catalogs and BenchLM JSON: scripted transport, no network."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("unexpected live HTTP"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def fetch(self, scripts, run_id, enabled, cache_dir=None, env=None):
        """One fetch_models.main invocation; returns (snapshot dict, transports by source)."""
        cfg = load_config()
        cfg["disabled_sources"] = [s for s in SOURCES if s not in enabled]
        transports = {}

        def factory(source, kind, **kwargs):
            http, transport, _ = headered_client(source, kind, *scripts.get(source, []))
            transports[source] = transport
            return http
        with patch.object(fm, "apply_credentials"), patch.object(fm, "SourceClient", side_effect=factory), \
             patch.dict(os.environ, env or {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            path = fm.main(self.root / f"out-{run_id}", run_id, config=cfg, cache_dir=cache_dir)
        return json.loads(Path(path).read_text(encoding="utf-8")), transports

    def test_conditional_round_trip_reuses_304_body_with_original_time_and_metrics(self):
        cache = self.root / "cache"
        body = json.dumps({"data": [{"id": "one"}]}).encode()
        first, t1 = self.fetch({"openrouter": [(body, {"ETag": 'W/"v1"'})]}, "one", ("openrouter",), cache)
        h1 = first["source_health"]["openrouter"]
        self.assertEqual((h1["status"], h1["count"]), ("complete", 1))
        self.assertEqual((h1["retrieval"]["requests"], h1["retrieval"]["not_modified"]), (1, 0))
        self.assertEqual(if_headers(t1["openrouter"].calls[0][0]), {})
        (entry_path,) = (cache / "validators").glob("openrouter_*.json")
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        self.assertEqual((entry["etag"], entry["fetched_at"]), ('W/"v1"', h1["fetched_at"]))

        second, t2 = self.fetch({"openrouter": [not_modified("https://openrouter.ai/api/v1/models")]},
                                "two", ("openrouter",), cache)
        h2 = second["source_health"]["openrouter"]
        self.assertEqual(second["openrouter"], first["openrouter"])  # stored body reused
        self.assertEqual(h2["fetched_at"], h1["fetched_at"])         # original stored time kept
        self.assertEqual(if_headers(t2["openrouter"].calls[0][0]), {"if-none-match": 'W/"v1"'})
        self.assertEqual((h2["retrieval"]["requests"], h2["retrieval"]["retries"],
                          h2["retrieval"]["response_bytes"], h2["retrieval"]["not_modified"]),
                         (1, 0, 0, 1))

    def test_benchlm_revalidates_each_json_url_with_if_modified_since(self):
        cache = self.root / "cache"
        lb = json.dumps({"models": [{"model": "One"}], "lastUpdated": "2026-09-01"}).encode()
        pr = json.dumps({"models": [{"model": "One"}]}).encode()
        headers = {"Last-Modified": "Tue, 01 Sep 2026 00:00:00 GMT"}
        first, _ = self.fetch({"benchlm": [(lb, dict(headers)), (pr, dict(headers))]},
                              "one", ("benchlm",), cache)
        h1 = first["source_health"]["benchlm"]
        self.assertEqual((h1["status"], h1["retrieval"]["requests"], h1["retrieval"]["not_modified"]),
                         ("complete", 2, 0))
        self.assertEqual(len(list((cache / "validators").glob("benchlm_*.json"))), 2)

        second, t2 = self.fetch({"benchlm": [not_modified("https://benchlm.ai/api/data/leaderboard?limit=1000"),
                                             not_modified("https://benchlm.ai/api/data/pricing?limit=5000")]},
                                "two", ("benchlm",), cache)
        h2 = second["source_health"]["benchlm"]
        self.assertEqual(second["benchlm"], first["benchlm"])
        self.assertEqual(h2["fetched_at"], h1["fetched_at"])
        self.assertEqual(len(t2["benchlm"].calls), 2)
        for request, _ in t2["benchlm"].calls:
            self.assertEqual(if_headers(request), {"if-modified-since": headers["Last-Modified"]})
        self.assertEqual((h2["status"], h2["retrieval"]["requests"], h2["retrieval"]["response_bytes"],
                          h2["retrieval"]["not_modified"]), ("complete", 2, 0, 2))

    def test_reused_partial_pagination_stays_partial_with_original_time(self):
        cache = self.root / "cache"
        env = {"ANTHROPIC_API_KEY": "fixture"}
        page1 = json.dumps({"data": [{"id": "one"}], "has_more": True, "last_id": "one"}).encode()
        offline = [TimeoutError("offline")] * 3
        first, _ = self.fetch({"anthropic": [(page1, {"ETag": '"p1"'}), *offline]},
                              "one", ("anthropic",), cache, env)
        h1 = first["source_health"]["anthropic"]
        self.assertEqual((h1["status"], h1["complete"], h1["count"]), ("partial", False, 1))
        self.assertEqual(first["anthropic"], [{"id": "one"}])
        self.assertEqual((h1["retrieval"]["requests"], h1["retrieval"]["not_modified"]), (4, 0))
        self.assertEqual(len(list((cache / "validators").glob("anthropic_*.json"))), 1)

        second, t2 = self.fetch({"anthropic": [not_modified("https://api.anthropic.com/v1/models?limit=1000"),
                                               *offline]},
                                "two", ("anthropic",), cache, env)
        h2 = second["source_health"]["anthropic"]
        self.assertEqual((h2["status"], h2["complete"]), ("partial", False))  # reuse never completes
        self.assertEqual(second["anthropic"], first["anthropic"])
        self.assertEqual(h2["fetched_at"], h1["fetched_at"])
        self.assertEqual(if_headers(t2["anthropic"].calls[0][0]), {"if-none-match": '"p1"'})
        self.assertEqual((h2["retrieval"]["requests"], h2["retrieval"]["not_modified"]), (4, 1))

    def test_standalone_fetcher_without_cache_dir_sends_no_conditional_requests(self):
        body = json.dumps({"data": [{"id": "one"}]}).encode()
        first, t1 = self.fetch({"openrouter": [(body, {"ETag": '"v1"'})]}, "one", ("openrouter",))
        second, t2 = self.fetch({"openrouter": [(body, {"ETag": '"v1"'})]}, "two", ("openrouter",))
        for run, transports in (("one", t1), ("two", t2)):
            for request, _ in transports["openrouter"].calls:
                self.assertEqual(if_headers(request), {}, run)
        self.assertEqual(list(self.root.rglob("validators")), [])  # no validator writes either
        self.assertEqual(second["source_health"]["openrouter"]["status"], "complete")

    def test_response_without_validators_stores_nothing_and_fetches_plain_again(self):
        cache = self.root / "cache"
        body = json.dumps({"data": [{"id": "one"}]}).encode()
        self.fetch({"openrouter": [(body, {})]}, "one", ("openrouter",), cache)
        self.assertFalse((cache / "validators").exists())
        second, t2 = self.fetch({"openrouter": [(body, {})]}, "two", ("openrouter",), cache)
        self.assertEqual(if_headers(t2["openrouter"].calls[0][0]), {})
        metrics = second["source_health"]["openrouter"]["retrieval"]
        self.assertEqual((metrics["requests"], metrics["response_bytes"], metrics["not_modified"]),
                         (1, len(body), 0))

    def test_llmstats_and_vals_never_send_or_read_conditional_validators(self):
        cache = self.root / "cache"
        account = json.dumps({"usage": {"remaining": 100, "quota_day": "2026-09-27"}}).encode()
        script = [(account, {}), (b'{"models":[{"id":"one","name":"One"}]}', {}),
                  (b'{"benchmarks":[]}', {}), *[(b'{"models":[]}', {})] * 4, (account, {})]
        stored = {"etag": '"stored"', "last_modified": "",
                  "fetched_at": "2026-09-01T00:00:00+00:00", "body": "{}"}
        llm_url = "https://api.zeroeval.com/stats/v1/models?limit=200"
        http, transport, _ = headered_client("llmstats", "api", *script)
        ctx = fm.FetchContext("llmstats", load_config(), self.root / "errors",
                              client=http, cache_dir=cache)
        atomic_json(fm._validator_path(ctx, llm_url), {"url": llm_url, **stored})
        self.assertIsNotNone(fm._validator_get(ctx, llm_url))  # an entry a conditional path would use
        with patch.dict(os.environ, {"LLM_STATS_API_KEY": "fixture", "LLM_STATS_DETAIL_MAX": "0"}):
            fm.fetch_llmstats(ctx)
        for request, _ in transport.calls:
            self.assertEqual(if_headers(request), {})

        vals_url = "https://www.vals.ai/benchmarks/vals_index"
        vhttp, vtransport, _ = headered_client("vals", "api",
                                               (b'<a href="/models/x_one">One model</a>', {}))
        vctx = fm.FetchContext("vals", load_config(), self.root / "errors",
                               client=vhttp, cache_dir=cache)
        entry_path = fm._validator_path(vctx, vals_url)
        atomic_json(entry_path, {"url": vals_url, **stored})
        before = entry_path.read_text(encoding="utf-8")
        fm.fetch_vals_index(vctx)
        for request, _ in vtransport.calls:
            self.assertEqual(if_headers(request), {})
        self.assertEqual(entry_path.read_text(encoding="utf-8"), before)  # never consulted or rewritten

    def test_website_time_cache_sends_no_conditional_headers(self):
        snap = self.root / "snapshot.json"
        atomic_json(snap, {"retrieved_at": "fixture", "benchlm": {"leaderboard": [{"model": "One"}]}})
        cfg = load_config()
        cfg["disabled_sources"] = ["llmstats", "vals"]
        transports = []

        def factory(source, kind, **kwargs):
            http, transport, _ = client(source, kind, b"# one")
            transports.append(transport)
            return http
        with patch.object(fw, "SourceClient", side_effect=factory), contextlib.redirect_stdout(io.StringIO()):
            first = fw.main(snap, self.root / "first", self.root / "cache", cfg)
            second = fw.main(snap, self.root / "second", self.root / "cache", cfg)
        a, b = [json.loads(Path(p).read_text(encoding="utf-8")) for p in (first, second)]
        for transport in transports:
            for request, _ in transport.calls:
                self.assertEqual(if_headers(request), {})
        self.assertEqual(b["benchlm_md"]["one"]["fetched_at"], a["benchlm_md"]["one"]["fetched_at"])
        self.assertTrue(b["benchlm_md"]["one"]["cache_hit"])
        self.assertEqual(b["source_health"]["benchlm_md"]["retrieval"]["requests"], 0)


class RetrievalTableTests(unittest.TestCase):
    def test_legacy_unknown_versus_recorded_zero_and_no_quota_delta(self):
        zero, _, _ = client("disabled", "api")
        zero.quota = {"before": {"remaining": 5, "day": "2026-09-27"},
                      "after": {"remaining": 250, "day": "2026-09-28"}}
        a = {"source_health": {"old": {"status": "complete"}, "disabled": {"retrieval": zero.snapshot()}}}
        title, headers, rows = next(t for t in reliability_tables(a) if t[0].startswith("Retrieval"))
        self.assertIn("retained on replay, not new activity", title)
        self.assertIn("HTTP seconds", headers)
        self.assertEqual(rows[0][1:7], ["unknown"] * 6)
        self.assertEqual(rows[1][1:7], [0] * 6)
        html = reliability_html(a)
        self.assertIn("<caption", html)
        self.assertIn("scope='col'", html)
        self.assertNotIn("-245", html)  # different quota days must never imply a delta


if __name__ == "__main__":
    unittest.main()
