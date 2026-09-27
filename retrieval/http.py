"""Source-bound HTTP measurements, not quota accounting or wire-level telemetry.

requests counts urlopen attempts (including failures/retries; redirects inside
urllib are not separate attempts). retries counts attempts after the first of
each call. response_bytes counts body bytes read, including HTTP error bodies,
before UTF-8 decoding; headers/TLS and unread bodies are excluded. request_seconds
times transport + body reading, including failures, but not parsing/backoff.
elapsed_seconds spans the source operation, including parsing, cache and backoff.
hosts attributes attempts to the requested hostname, never URLs or credentials.
not_modified counts 304 revalidation answers (their error body stays 0 bytes);
backoff sleeps are jittered, and a 429/503 Retry-After (integer seconds, capped)
replaces the jittered backoff for that attempt. Snapshots are detached copies;
absent historical measurements remain unknown.
"""
from copy import deepcopy
import json
import random
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from pipeline_common import safe_error

RETRY_AFTER_CAP = 60  # seconds: longest server-requested pause honoured before a retry
JITTER = 0.5  # backoff sleeps scale within [0.75, 1.25] x the base delay
# One shared _errors.log per run: concurrent sources must never interleave their lines.
_ERROR_LOG_LOCK = threading.Lock()


def retry_after_seconds(error):
    """Integer-seconds Retry-After on 429/503, capped; anything else means no hint."""
    if getattr(error, "code", None) not in (429, 503):
        return None
    headers = getattr(error, "headers", None) or getattr(error, "hdrs", None)
    try:
        raw = headers.get("Retry-After") if headers is not None else None
        if raw is None:
            raw = headers.get("retry-after")
    except Exception:
        raw = None
    try:
        seconds = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return min(seconds, RETRY_AFTER_CAP) if seconds >= 0 else None


def _header_dict(response):
    """Lower-cased response headers for validator capture; unusable headers are empty."""
    try:
        return {str(key).lower(): str(value) for key, value in response.headers.items()}
    except Exception:
        return {}


class SourceClient:
    def __init__(self, source, kind, *, log=None, transport=None, clock=None, sleeper=None, rand=None):
        self.source, self.kind = source, kind
        self.log = log or (lambda message: None)
        self.transport = transport or urllib.request.urlopen
        self.clock = clock or time.perf_counter
        self.sleep = sleeper or time.sleep
        self.rand = rand or random.random
        self.started = self.clock()
        self.hosts = {}
        self.cache_hits = 0
        self.not_modified = 0
        self.last_response_headers = {}
        self.quota = None

    def snapshot(self):
        totals = {key: sum(h[key] for h in self.hosts.values())
                  for key in ("requests", "response_bytes", "request_seconds", "retries")}
        return deepcopy({"source": self.source, "kind": self.kind, **totals,
                         "elapsed_seconds": self.clock() - self.started,
                         "cache_hits": self.cache_hits, "not_modified": self.not_modified,
                         "hosts": self.hosts,
                         **({"quota": self.quota} if self.quota is not None else {})})

    def get(self, url, headers=None, timeout=60, retries=3):
        return self._get(url, headers, timeout, retries, json.loads, website=False)

    def get_text(self, url, headers=None, timeout=None, retries=None):
        website = self.kind == "website"
        return self._get(url, headers, timeout if timeout is not None else (25 if website else 60),
                         retries if retries is not None else (2 if website else 3),
                         lambda text: text, website=website)

    def _get(self, url, headers, timeout, retries, parse, *, website):
        host = urlsplit(url).hostname or "unknown"
        counters = self.hosts.setdefault(host, {"requests": 0, "response_bytes": 0,
                                                "request_seconds": 0.0, "retries": 0})
        last = None
        for i in range(retries):
            pause = None
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "model-watch/1", **(headers or {})})
                counters["requests"] += 1
                counters["retries"] += int(i > 0)
                start = self.clock()
                try:
                    with self.transport(req, timeout=timeout) as response:
                        body = response.read()
                        counters["response_bytes"] += len(body)
                        captured = _header_dict(response)
                except urllib.error.HTTPError as exc:
                    # Counting error bodies must not change the original retry decision.
                    try:
                        counters["response_bytes"] += len(exc.read())
                    except Exception:
                        pass
                    finally:
                        try:
                            exc.close()
                        except Exception:
                            pass
                    raise
                finally:
                    counters["request_seconds"] += self.clock() - start
                self.last_response_headers = captured
                return parse(body.decode("utf-8", "replace"))
            except urllib.error.HTTPError as exc:
                if exc.code == 304:
                    # A revalidation answer, not a failure: callers reuse their stored body.
                    self.not_modified += 1
                    raise
                if 400 <= exc.code < 500 and exc.code != 429:
                    self.log(safe_error(f"FAILED {host}: {exc}"))
                    raise
                last = exc
                pause = retry_after_seconds(exc)
            except Exception as exc:
                if not website and not isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, ValueError)):
                    raise
                last = exc
            self.log(safe_error(f"retry {i+1}/{retries} {host}: {last}"))
            if i < retries - 1:
                if pause is None:
                    base = 1 if website else 2 ** i
                    pause = base * (1 + JITTER * (self.rand() - 0.5))
                self.sleep(pause)
        self.log(safe_error(f"FAILED {host}: {last}"))
        raise last
