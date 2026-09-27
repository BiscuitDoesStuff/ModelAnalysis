"""1. Data Retrieval Process — hybrid (public first, authed where keys exist). On-use.
Benchmark sources: AA (keyed API) + BenchLM (keyless JSON) + LLM Stats (keyed API,
public website fallback via fetch_websites.py) + Vals (public website, best-effort).
"""
import json, os, sys, datetime, time, urllib.request, urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
os.makedirs(RAW, exist_ok=True)
ERRLOG = os.path.join(RAW, "_errors.log")

def log_err(msg):
    with open(ERRLOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")

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


def fetch_openrouter():
    return get("https://openrouter.ai/api/v1/models").get("data", [])

def fetch_openai():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"skipped": "no OPENAI_API_KEY"}
    return get("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"}).get("data", [])

def fetch_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return {"skipped": "no ANTHROPIC_API_KEY"}
    return get("https://api.anthropic.com/v1/models", {
        "x-api-key": key, "anthropic-version": "2023-06-01"}).get("data", [])

def fetch_aa():
    key = os.getenv("AA_API_KEY")
    if not key:
        return {"skipped": "no AA_API_KEY"}
    return get("https://artificialanalysis.ai/api/v2/data/llms/models", {"x-api-key": key})

def fetch_nvidia():
    return get("https://integrate.api.nvidia.com/v1/models").get("data", [])

def fetch_zenmux():
    return get("https://zenmux.ai/api/v1/models").get("data", [])

def fetch_zen():
    return get("https://opencode.ai/zen/v1/models").get("data", [])


def fetch_benchlm():
    """BenchLM benchmark aggregator (public, keyless). Leaderboard + pricing JSON."""
    lb = get("https://benchlm.ai/api/data/leaderboard?limit=1000", timeout=60)
    pr = get("https://benchlm.ai/api/data/pricing?limit=5000", timeout=60)
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
    import re as _re
    key = os.getenv("LLM_STATS_API_KEY")
    if not key:
        return {"skipped": "no LLM_STATS_API_KEY"}
    headers = {"Authorization": f"Bearer {key}"}
    snap_so_far = snap_so_far or {}

    def norm(s):
        return _re.sub(r"[^a-z0-9]", "", str(s or "").lower())

    # Quota pre-check (free call): fit details budget to remaining balance.
    try:
        _detail_max = int(os.getenv("LLM_STATS_DETAIL_MAX", "12"))
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

    models, cursor, pages = [], None, 0
    while True:
        url = "https://api.zeroeval.com/stats/v1/models?limit=200" + (f"&cursor={cursor}" if cursor else "")
        try:
            data = get(url, headers, timeout=60)
        except Exception as e:
            if models:
                log_err(f"llmstats models page {pages+1} failed, keeping {len(models)}: {e}")
                break
            raise
        batch = data.get("models", []) if isinstance(data, dict) else []
        models.extend(_llmstats_project_model(m) for m in batch)
        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        pages += 1
        if not cursor or pages >= 5:
            break
    bench_raw = get("https://api.zeroeval.com/stats/v1/benchmarks?limit=500", headers, timeout=60)
    benchmarks = [{"id": b.get("id"), "name": b.get("name"),
                   "categories": b.get("categories") or [],
                   "verified": bool(b.get("verified")),
                   "model_count": b.get("model_count")}
                  for b in (bench_raw.get("benchmarks", []) if isinstance(bench_raw, dict) else [])
                  if isinstance(b, dict)]
    rankings = {}
    for cat in ("general", "reasoning", "code", "agents"):
        try:
            rows, _cur, _pg = [], None, 0
            while True:
                rurl = (f"https://api.zeroeval.com/stats/v1/rankings?category={cat}&limit=50"
                        + (f"&cursor={_cur}" if _cur else ""))
                r = get(rurl, headers, timeout=60)
                batch = r.get("models", []) if isinstance(r, dict) else []
                rows.extend({"model_id": x.get("model_id"), "model_name": x.get("model_name"),
                             "org": x.get("organization"), "rank": x.get("rank"),
                             "rating": x.get("conservative_rating"),
                             "evals": x.get("benchmarks_evaluated"),
                             "min_in": x.get("min_input_price"),
                             "url": x.get("url")} for x in batch if isinstance(x, dict))
                _cur = r.get("next_cursor") if isinstance(r, dict) else None
                _pg += 1
                if not _cur or _pg >= 4:
                    break
            rankings[cat] = rows
        except Exception as e:
            log_err(f"llmstats rankings {cat} failed: {e}")
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
    details, fetched = {}, 0
    for slug in priority:
        if fetched >= max(detail_max, 0):
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
            log_err(f"llmstats detail {lid} failed: {e}")
    try:
        acct = get("https://api.zeroeval.com/stats/v1/account", headers, timeout=30)
        usage = (acct.get("usage", {}) if isinstance(acct, dict) else {})
    except Exception:
        usage = {}
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
        return routes
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

def prune(keep=1):
    import glob as g
    files = sorted(g.glob(os.path.join(RAW, "*_models.json")), key=os.path.getmtime)
    for old in files[:-keep]:
        os.remove(old)
        print(f"pruned {os.path.basename(old)}")

def safe(fn):
    try:
        return fn()
    except Exception as e:
        return {"error": str(e)}

def main():
    open(ERRLOG, "w").close()
    try:
        ors = fetch_openrouter()
    except Exception as e:
        print(f"openrouter failed, keeping previous snapshot: {e}")
        sys.exit(1)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    snap = {"retrieved_at": stamp,
            "openrouter": ors,
            "openai": safe(fetch_openai),
            "anthropic": safe(fetch_anthropic),
            "nvidia": safe(fetch_nvidia),
            "zenmux": safe(fetch_zenmux),
            "zen": safe(fetch_zen),
            "modelsdev": safe(fetch_modelsdev),
            "aa": safe(fetch_aa),
            "benchlm": safe(fetch_benchlm)}
    snap["llmstats"] = safe(lambda: fetch_llmstats(snap))
    snap["vals"] = safe(fetch_vals_index)
    out = os.path.join(RAW, f"{stamp}_models.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1)
    prune(1)
    print(f"wrote {out} | openrouter={len(ors) if isinstance(ors, list) else ors} "
          f"| openai={len(snap['openai']) if isinstance(snap['openai'], list) else snap['openai']} "
          f"| anthropic={len(snap['anthropic']) if isinstance(snap['anthropic'], list) else snap['anthropic']} "
          f"| nvidia={len(snap['nvidia']) if isinstance(snap['nvidia'], list) else snap['nvidia']} "
          f"| zenmux={len(snap['zenmux']) if isinstance(snap['zenmux'], list) else snap['zenmux']} "
          f"| zen={len(snap['zen']) if isinstance(snap['zen'], list) else snap['zen']} "
          f"| modelsdev={len(snap['modelsdev']) if isinstance(snap['modelsdev'], list) else snap['modelsdev']} "
          f"| benchlm={len((snap['benchlm'].get('leaderboard', []) if isinstance(snap['benchlm'], dict) else []))} "
          f"| llmstats={snap['llmstats'].get('model_count', snap['llmstats']) if isinstance(snap['llmstats'], dict) else snap['llmstats']} "
          f"| vals={len((snap['vals'].get('models', []) if isinstance(snap['vals'], dict) else []))}")

if __name__ == "__main__":
    main()
