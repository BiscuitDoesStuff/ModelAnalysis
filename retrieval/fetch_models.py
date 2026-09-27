"""1. Data Retrieval Process — hybrid (public first, authed where keys exist). On-use.
Benchmark sources: AA (keyed API) + BenchLM (keyless JSON) + LLM Stats (keyed API,
public website fallback via fetch_websites.py) + Vals (public website, best-effort).
"""
import json, os, sys, datetime, time, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import (apply_credentials, atomic_json, new_run_id, utc_now, safe_error,
                             source_status, load_config, SOURCES, PROVIDERS, SCHEMA_VERSION)
from analysis.common import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")  # default only; pipeline.py passes the staging dir
ERRLOG = os.path.join(RAW, "_errors.log")
FETCH_HEALTH = {}
CONFIG = load_config()

def log_err(msg):
    os.makedirs(os.path.dirname(ERRLOG), exist_ok=True)
    with open(ERRLOG, "a", encoding="utf-8") as f:
        f.write(f"{utc_now()} {safe_error(msg)}\n")

def get(url, headers=None, timeout=60, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "model-watch/1", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                log_err(f"FAILED {url}: {e}")
                raise
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
            last = e
        log_err(f"retry {i+1}/{retries} {url}: {last}")
        if i < retries - 1:
            time.sleep(2 ** i)
    log_err(f"FAILED {url}: {last}")
    raise last

def get_text(url, headers=None, timeout=60, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "model-watch/1", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                log_err(f"FAILED {url}: {e}")
                raise
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
            last = e
        log_err(f"retry {i+1}/{retries} {url}: {last}")
        if i < retries - 1:
            time.sleep(2 ** i)
    log_err(f"FAILED {url}: {last}")
    raise last


def catalog(source, url, headers=None, paginate=False):
    from urllib.parse import urlencode
    rows, seen = [], set()
    while True:
        try:
            data = get(url, headers)
            batch = data.get("data") if isinstance(data, dict) else None
            if not isinstance(batch, list) or any(not isinstance(m, dict) or not m.get("id") for m in batch):
                raise ValueError(f"{source}: malformed catalog data")
            rows.extend(batch)
            if not data.get("has_more"):
                FETCH_HEALTH[source] = source_status("complete", len(rows))
                return rows
            cursor = data.get("last_id") or (batch[-1]["id"] if batch else None)
            if not paginate or not cursor or cursor in seen:
                raise ValueError(f"{source}: unresolved pagination")
            seen.add(cursor)
            url = url.split("?", 1)[0] + "?" + urlencode({"after_id": cursor, "limit": 1000})
        except Exception as exc:
            FETCH_HEALTH[source] = source_status("partial" if rows else "failed", len(rows), reason=safe_error(exc))
            if rows:
                return rows
            raise


def fetch_openrouter():
    key = os.getenv("OPENROUTER_API_KEY")
    return catalog("openrouter", "https://openrouter.ai/api/v1/models",
                   {"Authorization": f"Bearer {key}"} if key else None)

def fetch_openai():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"skipped": "no OPENAI_API_KEY"}
    return catalog("openai", "https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})

def fetch_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return {"skipped": "no ANTHROPIC_API_KEY"}
    return catalog("anthropic", "https://api.anthropic.com/v1/models?limit=1000", {
        "x-api-key": key, "anthropic-version": "2023-06-01"}, paginate=True)

def fetch_aa():
    key = os.getenv("AA_API_KEY")
    if not key:
        return {"skipped": "no AA_API_KEY"}
    data = get("https://artificialanalysis.ai/api/v2/data/llms/models", {"x-api-key": key})
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("AA: malformed data")
    return data

def fetch_nvidia():
    return catalog("nvidia", "https://integrate.api.nvidia.com/v1/models")

def fetch_zenmux():
    return catalog("zenmux", "https://zenmux.ai/api/v1/models")

def fetch_zen():
    return catalog("zen", "https://opencode.ai/zen/v1/models")


def fetch_benchlm():
    """BenchLM benchmark aggregator (public, keyless). Leaderboard + pricing JSON."""
    components = {}
    def component(name, url, cap):
        try:
            data = get(url, timeout=60)
            if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                raise ValueError("missing models list")
            limited = len(data["models"]) >= cap or bool(data.get("next_cursor") or data.get("has_more"))
            components[name] = source_status("partial" if limited else "complete", len(data["models"]), scope="bounded-reference")
            return data
        except Exception as exc:
            components[name] = source_status("failed", reason=safe_error(exc), scope="bounded-reference")
            return {}
    lb = component("leaderboard", "https://benchlm.ai/api/data/leaderboard?limit=1000", 1000)
    pr = component("pricing", "https://benchlm.ai/api/data/pricing?limit=5000", 5000)
    FETCH_HEALTH["benchlm"] = source_status("complete" if all(c["complete"] for c in components.values()) else "partial",
                                            len(lb.get("models", [])), scope="bounded-reference", components=components)
    lb_models = lb.get("models", []) if isinstance(lb, dict) else []
    pr_models = pr.get("models", []) if isinstance(pr, dict) else []
    return {"leaderboard": lb_models if isinstance(lb_models, list) else [],
            "pricing": pr_models if isinstance(pr_models, list) else [],
            "meta": {"lastUpdated": (lb.get("lastUpdated") if isinstance(lb, dict) else None),
                     "methodologyVersion": (lb.get("methodologyVersion") if isinstance(lb, dict) else None),
                     "mode": (lb.get("mode") if isinstance(lb, dict) else None)}}


def _llmstats_project_model(m):
    """Minimal projection: capabilities + prices + TrueSkill, no description text."""
    if not isinstance(m, dict):
        return {}
    org = m.get("organization", {}) or {}
    lic = m.get("license", {}) or {}
    provs = []
    for p in (m.get("providers", []) or []):
        if isinstance(p, dict):
            provs.append({"provider_id": p.get("provider_id"), "provider_name": p.get("provider_name"),
                          "in_per_m": p.get("input_price_per_m"), "out_per_m": p.get("output_price_per_m"),
                          "tps": p.get("throughput_tps"), "latency_s": p.get("latency_s"),
                          "status": p.get("status")})
    inf = m.get("inference", {}) or {}
    return {"id": m.get("id"), "name": m.get("name"),
            "org": org.get("id") or org.get("name"), "family": m.get("family"),
            "license": lic.get("id") or lic.get("name"), "open_weight": bool(m.get("open_weight")),
            "model_type": m.get("model_type"), "modalities": m.get("modalities") or [],
            "context_window": m.get("context_window"), "params": m.get("param_count"),
            "cutoff": m.get("knowledge_cutoff"), "released": m.get("release_date"),
            "providers": provs, "top_scores": m.get("top_scores") or {},
            "supports_tools": bool(inf.get("supports_tools")),
            "supports_vision": bool(inf.get("supports_vision")),
            "supports_streaming": bool(inf.get("supports_streaming")),
            "openai_compatible": bool(inf.get("openai_compatible")),
            "url": m.get("url"), "updated": m.get("updated_at")}


def fetch_llmstats(snap_so_far=None):
    """LLM Stats / ZeroEval API (keyed). Skipped gracefully when no key.

    Quota budget ~19 data responses/run (Community: 250/day): models p1-2,
    benchmarks, 4 category rankings, ~12 model details for the free-relevant
    priority list. Public website pages are crawled separately by
    retrieval/fetch_websites.py so a keyless run still gains pricing/context
    hints. Community plan requires 'Data by LLM Stats' attribution (see site
    footer/methodology) and forbids bulk redistribution — snapshots stay local.
    """
    key = os.getenv("LLM_STATS_API_KEY")
    if not key:
        return {"skipped": "no LLM_STATS_API_KEY"}
    headers = {"Authorization": f"Bearer {key}"}
    snap_so_far = snap_so_far or {}

    # Quota pre-check (free call): fit details budget to remaining balance.
    try:
        _detail_max = int(os.getenv("LLM_STATS_DETAIL_MAX") or CONFIG["llmstats_detail_max"])
    except Exception:
        _detail_max = 12
    try:
        _acct = get("https://api.zeroeval.com/stats/v1/account", headers, timeout=30)
        _remaining = ((_acct.get("usage", {}) or {}).get("remaining") if isinstance(_acct, dict) else None)
    except Exception as e:
        log_err(f"llmstats account pre-check failed (continuing blind): {e}")
        _remaining = None
    if isinstance(_remaining, (int, float)) and _remaining < 8:
        return {"error": f"quota too low ({_remaining} remaining), need ~8 for base calls; wait for UTC reset"}
    if isinstance(_remaining, (int, float)):
        _detail_max = max(0, min(_detail_max, int(_remaining) - 8))
        if _detail_max < 12:
            log_err(f"llmstats details capped to {_detail_max} (quota remaining {_remaining})")

    components = {}
    def pages(name, path, field, cap):
        from urllib.parse import quote
        rows, cursor, seen = [], None, set()
        try:
            for _ in range(cap):
                url = "https://api.zeroeval.com/stats/v1/" + path
                if cursor:
                    url += "&cursor=" + quote(str(cursor), safe="")
                data = get(url, headers, timeout=60)
                batch = data.get(field) if isinstance(data, dict) else None
                if not isinstance(batch, list) or any(not isinstance(x, dict) for x in batch):
                    raise ValueError(f"{name}: malformed {field}")
                rows.extend(batch)
                cursor = data.get("next_cursor")
                if not cursor:
                    components[name] = source_status("complete", len(rows), scope="reference")
                    return rows
                if cursor in seen:
                    raise ValueError("repeated pagination cursor")
                seen.add(cursor)
            components[name] = source_status("partial", len(rows), scope="reference", reason="page budget reached")
        except Exception as exc:
            components[name] = source_status("partial" if rows else "failed", len(rows), scope="reference", reason=safe_error(exc))
        return rows
    models = [_llmstats_project_model(m) for m in pages("models", "models?limit=200", "models", 5)]
    bench_rows = pages("benchmarks", "benchmarks?limit=500", "benchmarks", 5)
    benchmarks = [{"id": b.get("id"), "name": b.get("name"),
                   "categories": b.get("categories") or [],
                   "verified": bool(b.get("verified")),
                   "model_count": b.get("model_count")}
                   for b in bench_rows
                  if isinstance(b, dict)]
    rankings = {}
    for cat in ("general", "reasoning", "code", "agents"):
        batch = pages("rankings." + cat, f"rankings?category={cat}&limit=50", "models", 4)
        rankings[cat] = [{"model_id": x.get("model_id"), "model_name": x.get("model_name"),
                              "org": x.get("organization"), "rank": x.get("rank"),
                              "rating": x.get("conservative_rating"),
                              "evals": x.get("benchmarks_evaluated"),
                              "min_in": x.get("min_input_price"),
                              "url": x.get("url")} for x in batch]
    # Detail priority: OR free routes, then AA-scored, then BenchLM top.
    priority, seen = [], set()

    def add(raw_id):
        k = norm(str(raw_id).split(":")[0].split("/")[-1])
        if k and k not in seen:
            seen.add(k)
            priority.append(k)

    for m in (snap_so_far.get("openrouter", []) if isinstance(snap_so_far.get("openrouter"), list) else []):
        try:
            free = (float((m.get("pricing", {}) or {}).get("prompt", 1)) == 0
                    and float((m.get("pricing", {}) or {}).get("completion", 1)) == 0) \
                or str(m.get("id", "")).endswith(":free")
        except Exception:
            free = str(m.get("id", "")).endswith(":free")
        if free:
            add(m.get("id", ""))
    aa = snap_so_far.get("aa", {}) if isinstance(snap_so_far.get("aa"), dict) else {}
    scored = []
    for m in (aa.get("data", []) if isinstance(aa.get("data"), list) else []):
        try:
            s = float((m.get("evaluations", {}) or {}).get("artificial_analysis_intelligence_index"))
        except Exception:
            continue
        if s is not None:
            scored.append((s, m.get("slug", "") or m.get("id", "")))
    for _, mid in sorted(scored, key=lambda t: t[0], reverse=True)[:40]:
        add(mid)
    bench = snap_so_far.get("benchlm", {}) if isinstance(snap_so_far.get("benchlm"), dict) else {}
    for m in (bench.get("leaderboard", []) if isinstance(bench.get("leaderboard"), list) else [])[:30]:
        if isinstance(m, dict) and m.get("model"):
            add(m["model"])
    by_norm = {norm(m.get("id", "")): m.get("id", "") for m in models if m.get("id")}
    for m in models:
        if m.get("name"):
            by_norm.setdefault(norm(m["name"]), m["id"])
    try:
        detail_max = _detail_max
    except Exception:
        detail_max = 12
    details, fetched, detail_failed = {}, 0, 0
    for slug in priority:
        if fetched + detail_failed >= max(detail_max, 0):
            break
        lid = by_norm.get(slug)
        if not lid or lid in details:
            continue
        try:
            d = get(f"https://api.zeroeval.com/stats/v1/models/{lid}", headers, timeout=60)
            scores = [ {"bench": s.get("benchmark_id"), "name": s.get("benchmark_name"),
                        "cat": s.get("category"), "score": s.get("score"),
                        "norm": s.get("normalized_score"), "max": s.get("max_score"),
                        "self_reported": bool(s.get("is_self_reported")),
                        "verified": bool(s.get("verified_by_llmstats")),
                        "rank": s.get("rank"), "url": s.get("source_url")}
                       for s in (d.get("scores", []) if isinstance(d, dict) else []) if isinstance(s, dict)]
            details[lid] = {"name": d.get("name"), "scores": scores,
                            "n_benchmarks": len(scores)}
            fetched += 1
        except Exception as e:
            detail_failed += 1
            log_err(f"llmstats detail {lid} failed: {e}")
    try:
        acct = get("https://api.zeroeval.com/stats/v1/account", headers, timeout=30)
        usage = (acct.get("usage", {}) if isinstance(acct, dict) else {})
    except Exception:
        usage = {}
    components["details"] = source_status("partial" if detail_failed else "complete", len(details),
                                          scope="selected-details", attempted_count=fetched + detail_failed,
                                          failed_count=detail_failed, budget=detail_max)
    FETCH_HEALTH["llmstats"] = source_status("complete" if all(c["complete"] for c in components.values()) else "partial",
                                             len(models), scope="reference", components=components)
    return {"models": models, "model_count": len(models),
            "benchmarks": benchmarks, "benchmark_count": len(benchmarks),
            "rankings": rankings, "details": details,
            "meta": {"quota_remaining": usage.get("remaining"), "quota_day": usage.get("quota_day", "")}}


def fetch_vals_index():
    """Vals AI public index (keyless HTML, best-effort).

    No public JSON API exists; the website itself is the source. We fetch the
    benchmarks directory + Vals Index page HTML and extract the model table
    with lightweight regex. Fragile by design — failures return {"error"} via
    safe() and never abort the run. Detailed per-model pages are crawled by
    retrieval/fetch_websites.py for the free-relevant allowlist.
    """
    import re as _re
    html = get_text("https://www.vals.ai/benchmarks/vals_index", timeout=60)
    rows = []
    # Best-effort: model links look like /models/<provider>_<slug>
    for m in _re.finditer(r'href="(/models/[^"]+)"[^>]*>([^<]{2,80})<', html):
        href, name = m.group(1), m.group(2).strip()
        if href.startswith("/models/") and name and len(name) > 1:
            rows.append({"href": href, "name": name})
    # De-duplicate preserving order.
    seen, uniq = set(), []
    for r in rows:
        if r["href"] not in seen:
            seen.add(r["href"])
            uniq.append(r)
    return {"models": uniq[:200], "source": "html:vals_index"}

def fetch_modelsdev():
    """Tier 1: models.dev capabilities catalog (public, keyless). Minimal projection only."""
    data = get("https://models.dev/api.json", timeout=90)
    routes = []
    if not isinstance(data, dict):
        raise ValueError("models.dev: expected provider object")
    for provider_id, pdata in data.items():
        if not isinstance(pdata, dict):
            continue
        models = pdata.get("models", {})
        if not isinstance(models, dict):
            continue
        for model_key, m in models.items():
            if not isinstance(m, dict):
                continue
            cost = m.get("cost", {}) or {}
            modalities = m.get("modalities", {}) or {}
            reasoning_options = m.get("reasoning_options", []) or []
            efforts = []
            for opt in reasoning_options:
                if isinstance(opt, dict) and opt.get("type") == "effort":
                    vals = opt.get("values", [])
                    if isinstance(vals, list):
                        efforts = [str(v) for v in vals]
                    break
            limit = m.get("limit", {}) or {}
            routes.append({
                "provider": str(provider_id),
                "id": str(m.get("id", model_key)),
                "cost": {"input": cost.get("input"), "output": cost.get("output"),
                         "cache_read": cost.get("cache_read")},
                "modalities": {"input": list(modalities.get("input", []) or []),
                               "output": list(modalities.get("output", []) or [])},
                "reasoning": bool(m.get("reasoning", False)),
                "reasoning_efforts": efforts,
                "deprecated": str(m.get("status", "")).lower() == "deprecated",
                "limit": {"context": limit.get("context"), "output": limit.get("output")},
                "last_updated": m.get("last_updated", ""),
            })
    return routes

def safe(fn):
    try:
        return fn()
    except Exception as e:
        return {"error": safe_error(e)}

def main(output_dir=None, run_id=None, started_at=None, config=None):
    global RAW, ERRLOG, CONFIG
    apply_credentials()
    CONFIG = config or load_config()
    if output_dir is not None:
        RAW = str(output_dir)
    os.makedirs(RAW, exist_ok=True)
    ERRLOG = os.path.join(RAW, "_errors.log")
    FETCH_HEALTH.clear()
    open(ERRLOG, "w").close()
    stamp = run_id or new_run_id()
    snap = {"retrieved_at": stamp, "run_id": stamp, "schema_version": SCHEMA_VERSION,
            "started_at": started_at or utc_now()}
    fetchers = {"openrouter": fetch_openrouter, "openai": fetch_openai, "anthropic": fetch_anthropic,
                "nvidia": fetch_nvidia, "zenmux": fetch_zenmux, "zen": fetch_zen,
                "modelsdev": fetch_modelsdev, "aa": fetch_aa, "benchlm": fetch_benchlm,
                "llmstats": lambda: fetch_llmstats(snap), "vals": fetch_vals_index}
    for source in SOURCES:
        value = {"skipped": "disabled in configuration"} if source in CONFIG["disabled_sources"] else safe(fetchers[source])
        snap[source] = value
        scope = "catalog" if source in PROVIDERS else "best-effort" if source == "vals" else "reference"
        if isinstance(value, dict) and ("error" in value or "skipped" in value):
            status = "failed" if "error" in value else "skipped"
            FETCH_HEALTH[source] = source_status(status, scope=scope, reason=value.get("error", value.get("skipped", "")))
        elif source not in FETCH_HEALTH:
            count = len(value) if isinstance(value, list) else len(value.get("data", value.get("models", [])))
            FETCH_HEALTH[source] = source_status("complete", count, scope=scope, complete=source != "vals")
        print(f"source {source}: {FETCH_HEALTH[source]['status']} ({FETCH_HEALTH[source]['count']})")
    snap["source_health"] = dict(FETCH_HEALTH)
    out = os.path.join(RAW, f"{stamp}_models.json")
    atomic_json(out, snap)
    print(f"wrote {out}")
    return out

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch a uniquely identified snapshot (does not publish)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config")
    args = parser.parse_args()
    main(output_dir=args.output, config=load_config(args.config))
