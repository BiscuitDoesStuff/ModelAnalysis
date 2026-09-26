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
            "aa": safe(fetch_aa)}
    out = os.path.join(RAW, f"{stamp}_models.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1)
    prune(1)
    print(f"wrote {out} | openrouter={len(ors) if isinstance(ors, list) else ors} "
          f"| openai={len(snap['openai']) if isinstance(snap['openai'], list) else snap['openai']} "
          f"| anthropic={len(snap['anthropic']) if isinstance(snap['anthropic'], list) else snap['anthropic']} "
          f"| groq={len(snap['groq']) if isinstance(snap['groq'], list) else snap['groq']} "
          f"| cerebras={len(snap['cerebras']) if isinstance(snap['cerebras'], list) else snap['cerebras']}")

if __name__ == "__main__":
    main()
