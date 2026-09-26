"""1. Data Retrieval Process — hybrid (public first, authed where keys exist). On-use."""
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

def fetch_groq():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return {"skipped": "no GROQ_API_KEY"}
    return get("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"}).get("data", [])

def fetch_cerebras():
    key = os.getenv("CEREBRAS_API_KEY")
    if not key:
        return {"skipped": "no CEREBRAS_API_KEY"}
    return get("https://api.cerebras.ai/v1/models", {"Authorization": f"Bearer {key}"}).get("data", [])

def fetch_nvidia():
    return get("https://integrate.api.nvidia.com/v1/models").get("data", [])

def fetch_zenmux():
    return get("https://zenmux.ai/api/v1/models").get("data", [])

def fetch_zen():
    return get("https://opencode.ai/zen/v1/models").get("data", [])

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
            "groq": safe(fetch_groq),
            "cerebras": safe(fetch_cerebras),
            "nvidia": safe(fetch_nvidia),
            "zenmux": safe(fetch_zenmux),
            "zen": safe(fetch_zen),
            "modelsdev": safe(fetch_modelsdev),
            "aa": safe(fetch_aa)}
    out = os.path.join(RAW, f"{stamp}_models.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1)
    prune(1)
    print(f"wrote {out} | openrouter={len(ors) if isinstance(ors, list) else ors} "
          f"| openai={len(snap['openai']) if isinstance(snap['openai'], list) else snap['openai']} "
          f"| anthropic={len(snap['anthropic']) if isinstance(snap['anthropic'], list) else snap['anthropic']} "
          f"| groq={len(snap['groq']) if isinstance(snap['groq'], list) else snap['groq']} "
          f"| cerebras={len(snap['cerebras']) if isinstance(snap['cerebras'], list) else snap['cerebras']} "
          f"| nvidia={len(snap['nvidia']) if isinstance(snap['nvidia'], list) else snap['nvidia']} "
          f"| zenmux={len(snap['zenmux']) if isinstance(snap['zenmux'], list) else snap['zenmux']} "
          f"| zen={len(snap['zen']) if isinstance(snap['zen'], list) else snap['zen']} "
          f"| modelsdev={len(snap['modelsdev']) if isinstance(snap['modelsdev'], list) else snap['modelsdev']}")

if __name__ == "__main__":
    main()
