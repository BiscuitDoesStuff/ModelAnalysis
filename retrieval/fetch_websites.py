"""1b. Website-native crawl — BenchLM / LLM Stats / Vals pages themselves.

Reads the explicit snapshot it is given (--input), builds a free-relevant allowlist
(verified-free + provisional + OCF stack candidates + BenchLM top), then fetches
per-model website pages (best-effort, keyless HTML/MD). Never aborts the run:
per-page failures are recorded, snapshot-level failures write {"error"}.

Output: <output>/<run_id>_websites.json, with the same run ID as the snapshot.
"""
import json
import os
import re
import sys
import datetime
from pathlib import Path
# Do this before urllib imports: retrieval/http.py must not shadow stdlib http.
if __package__ in (None, ""):
    sys.path[0] = str(Path(__file__).resolve().parents[1])
from pipeline_common import atomic_json, safe_error, utc_now, source_status, load_config, SCHEMA_VERSION
from analysis.common import TIERS, kebab, norm
from retrieval.http import SourceClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
class FetchContext:
    def __init__(self, source, config, cache_dir, error_log, client=None):
        self.source, self.config = source, config
        self.cache_dir, self.error_log = Path(cache_dir), Path(error_log)
        self.client = client or SourceClient(source, "website", log=self.log_err)

    def log_err(self, msg):
        self.error_log.parent.mkdir(parents=True, exist_ok=True)
        with self.error_log.open("a", encoding="utf-8") as f:
            f.write(f"{utc_now()} {safe_error(msg)}\n")


def _cache_path(ctx, slug):
    safe = re.sub(r"[^a-z0-9_-]", "_", slug.lower())[:120]
    return ctx.cache_dir / f"{ctx.source}__{safe}.json"


def cache_get(ctx, slug, max_days=None):
    """Slug-keyed cache: BenchLM md rarely changes; refresh after max_days."""
    try:
        p = _cache_path(ctx, slug)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            value = json.load(f)
        # Legacy caches have no trustworthy observation timestamp: refresh them.
        observed = datetime.datetime.fromisoformat(value["fetched_at"])
        if observed.tzinfo is None:
            return None
        age = datetime.datetime.now(datetime.timezone.utc) - observed
        if age.total_seconds() > (ctx.config["cache_days"] if max_days is None else max_days) * 86400:
            return None
        value["cache_hit"] = True
        ctx.client.cache_hits += 1
        return value
    except Exception:
        return None


def cache_put(ctx, slug, payload):
    try:
        payload["fetched_at"] = utc_now()
        payload["cache_hit"] = False
        atomic_json(_cache_path(ctx, slug), payload)
    except Exception as e:
        ctx.log_err(f"websites cache write failed {ctx.source}/{slug}: {e}")



def build_allowlist(snap):
    """Free-relevant allowlist as (norm_slug, display_name) pairs.

    Order: frontier (BenchLM top + AA-scored) first so the per-source page
    budget covers models with website pages; OR free routes after.
    """
    out, seen = [], set()

    def add(raw_id, name=""):
        key = norm(str(raw_id).split(":")[0].split("/")[-1])
        if key and key not in seen:
            seen.add(key)
            out.append({"slug": key, "name": name or str(raw_id)})

    bench = snap.get("benchlm", {}) if isinstance(snap.get("benchlm"), dict) else {}
    for m in (bench.get("leaderboard", []) if isinstance(bench.get("leaderboard"), list) else [])[:40]:
        if isinstance(m, dict) and m.get("model"):
            add(m["model"], m.get("model", ""))
    aa = snap.get("aa", {}) if isinstance(snap.get("aa"), dict) else {}
    scored = []
    for m in (aa.get("data", []) if isinstance(aa.get("data", []), list) else []):
        try:
            ev = (m.get("evaluations", {}) or {}).get("artificial_analysis_intelligence_index")
            score = float(ev) if ev is not None else None
        except Exception:
            score = None
        if score is not None and score >= TIERS["medium"]:
            scored.append((score, m))
    for score, m in sorted(scored, key=lambda t: t[0], reverse=True)[:60]:
        add(m.get("slug", "") or m.get("id", ""), m.get("name", ""))
    ors = snap.get("openrouter", []) if isinstance(snap.get("openrouter"), list) else []
    for m in ors:
        try:
            pricing = m.get("pricing", {}) or {}
            free = (float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0) \
                or str(m.get("id", "")).endswith(":free")
        except Exception:
            free = str(m.get("id", "")).endswith(":free")
        if free:
            add(m.get("id", ""), m.get("name", ""))
    return out[:150]


def fetch_benchlm_md(ctx, allowlist, leaderboard):
    """Per-model markdown mirrors: /md/models/<kebab>.md (static, reliable)."""
    lb_by_norm = {}
    for m in leaderboard:
        if isinstance(m, dict) and m.get("model"):
            lb_by_norm[norm(m["model"])] = m
    matched = [a for a in allowlist if a["slug"] in lb_by_norm]
    matched += [a for a in allowlist if a["slug"] not in lb_by_norm]
    pages, hits = {}, 0
    for item in matched[:ctx.config["website_max_pages"]]:
        target = lb_by_norm.get(item["slug"])
        if not target:
            continue
        slug = kebab(target.get("model", ""))
        if not slug:
            continue
        cached = cache_get(ctx, slug)
        if cached is not None:
            pages[item["slug"]] = cached
            hits += 1
            continue
        url = f"https://benchlm.ai/md/models/{slug}.md"
        try:
            md = ctx.client.get_text(url)
            pages[item["slug"]] = {"url": url, "benchlm_slug": slug,
                                   "model": target.get("model"), "md": md[:20000]}
            cache_put(ctx, slug, pages[item["slug"]])
        except Exception as e:
            pages[item["slug"]] = {"url": url, "error": str(e)[:300]}
    print(f"websites benchlm_md: {len(pages)} ({hits} cached)")
    return pages


def parse_llmstats_model(html):
    """Lightweight extraction from public /models/<slug> HTML (best-effort)."""
    def find(pat):
        m = re.search(pat, html, re.S)
        return m.group(1).strip() if m else ""
    text = re.sub(r"\s+", " ", html)
    out = {}
    # Pricing: $X.XX/M input/output patterns near pricing section.
    prices = re.findall(r"\$([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:/|per) ?M[^$]{0,40}?(input|output|cached)", text, re.I)
    if prices:
        out["price_hints"] = [{"value": p[0], "kind": p[1].lower()} for p in prices[:6]]
    m = re.search(r"(\d[\d,\.]*)\s*M(?:illion)?[ -]?token context", text, re.I)
    if m:
        out["context_hint"] = m.group(1)
    m = re.search(r"LLM Stats Score[^0-9]{0,80}?([0-9]+\.[0-9]+)", text)
    if m:
        try:
            out["llmstats_score_hint"] = float(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\d+)\s*evals", text, re.I)
    if m:
        try:
            out["evals_hint"] = int(m.group(1))
        except Exception:
            pass
    if "Proprietary" in html:
        out["license_hint"] = "Proprietary"
    elif "Open Source" in html or "Open Weight" in html:
        out["license_hint"] = "Open"
    return out


def fetch_llmstats_pages(ctx, allowlist):
    pages, hits = {}, 0
    for item in allowlist[:ctx.config["website_max_pages"]]:
        slug = kebab(item.get("name", "") or item["slug"])
        if not slug:
            continue
        cached = cache_get(ctx, slug)
        if cached is not None:
            pages[item["slug"]] = cached
            hits += 1
            continue
        url = f"https://llm-stats.com/models/{slug}"
        try:
            html = ctx.client.get_text(url)
            if "Could not find" in html[:5000] or len(html) < 5000:
                pages[item["slug"]] = {"url": url, "error": "not-found-or-thin"}
                continue
            parsed = parse_llmstats_model(html)
            parsed["url"] = url
            parsed["llmstats_slug"] = slug
            pages[item["slug"]] = parsed
            cache_put(ctx, slug, parsed)
        except Exception as e:
            pages[item["slug"]] = {"url": url, "error": str(e)[:300]}
    print(f"websites llmstats: {len(pages)} ({hits} cached)")
    return pages


def fetch_vals_pages(ctx, snap, allowlist):
    """Vals model pages via index hrefs matched by normalized name."""
    vals = snap.get("vals", {}) if isinstance(snap.get("vals"), dict) else {}
    hrefs = [r.get("href", "") for r in (vals.get("models", []) if isinstance(vals.get("models"), list) else [])
             if isinstance(r, dict) and r.get("href")]
    pages, hits = {}, 0
    allow_norms = {a["slug"]: a for a in allowlist}
    fetched = 0
    for href in hrefs:
        if fetched >= ctx.config["website_max_pages"]:
            break
        tail = href.split("/models/", 1)[-1] if "/models/" in href else href
        key = norm(tail.replace("_", " ").replace("-", " "))
        match = None
        for slug in allow_norms:
            if slug and (slug in key or key in slug):
                match = slug
                break
        if not match:
            continue
        cached = cache_get(ctx, tail)
        if cached is not None:
            pages[match] = cached
            hits += 1
            fetched += 1
            continue
        url = f"https://www.vals.ai{href}"
        try:
            html = ctx.client.get_text(url)
            acc = re.findall(r"(\d{1,2}\.\d{1,2})\s*%", html)
            cost = re.search(r"\$\s*([0-9]+\.[0-9]+)\s*(?:per test|/ ?test)", html, re.I)
            lat = re.search(r"(\d+\s*min\s*\d+\s*s|\d+\s*s)\s*(?:latency)?", html, re.I)
            pages[match] = {"url": url, "vals_href": href,
                            "accuracy_hints": acc[:8],
                            "cost_per_test_hint": cost.group(1) if cost else "",
                            "latency_hint": lat.group(1) if lat else "",
                            "html_len": len(html)}
            cache_put(ctx, tail, pages[match])
            fetched += 1
        except Exception as e:
            pages[match] = {"url": url, "error": str(e)[:300]}
            fetched += 1
    print(f"websites vals: {len(pages)} ({hits} cached)")
    return pages


def main(input_path=None, output_dir=None, cache_dir=None, config=None):
    cfg = config or load_config()
    if input_path is None:
        raise ValueError("websites requires an explicit input snapshot")
    raw = Path(output_dir) if output_dir is not None else Path(ROOT) / "raw"
    cache = Path(cache_dir) if cache_dir is not None else Path(ROOT) / "raw" / "cache_websites"
    raw.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    with open(input_path, encoding="utf-8") as f:
        snap = json.load(f)
    stamp = str(snap.get("retrieved_at", datetime.datetime.now().strftime("%Y-%m-%d_%H%M")))
    allowlist = build_allowlist(snap)
    print(f"websites {stamp}: allowlist {len(allowlist)}")
    leaderboard = []
    bench = snap.get("benchlm", {}) if isinstance(snap.get("benchlm"), dict) else {}
    if isinstance(bench.get("leaderboard"), list):
        leaderboard = bench["leaderboard"]
    out = {"retrieved_at": stamp, "run_id": snap.get("run_id", stamp), "schema_version": SCHEMA_VERSION,
           "allowlist": allowlist}
    fetchers = {"benchlm_md": lambda ctx: fetch_benchlm_md(ctx, allowlist, leaderboard),
                "llmstats": lambda ctx: fetch_llmstats_pages(ctx, allowlist),
                "vals": lambda ctx: fetch_vals_pages(ctx, snap, allowlist)}
    out["source_health"] = {}
    for src in ("benchlm_md", "llmstats", "vals"):
        source = "benchlm" if src == "benchlm_md" else src
        ctx = FetchContext(source, cfg, cache, raw / "_errors.log")
        disabled = source in cfg["disabled_sources"]
        pages = out[src] = {} if disabled else fetchers[src](ctx)
        failed = sum("error" in v for v in pages.values())
        cached = sum(bool(v.get("cache_hit")) for v in pages.values())
        out["source_health"][src] = source_status("skipped" if disabled else "partial" if failed else "complete",
                                                  len(pages) - failed, scope="selected-pages", complete=False,
                                                  attempted_count=len(pages), failed_count=failed, cache_hits=cached,
                                                  oldest_data_at=min((v["fetched_at"] for v in pages.values() if v.get("fetched_at")), default=None),
                                                  retrieval=ctx.client.snapshot())
    path = str(raw / f"{stamp}_websites.json")
    atomic_json(path, out)
    print(f"wrote {path} | benchlm_md={len(out['benchlm_md'])} "
           f"llmstats={len(out['llmstats'])} vals={len(out['vals'])}")
    return path


if __name__ == "__main__":
    from pipeline_common import stage_cli
    stage_cli(main, __doc__)
