"""Small shared contracts for local configuration, run identity and atomic files."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = 3
PROVIDERS = ("openrouter", "openai", "anthropic", "nvidia", "zenmux", "zen")
SOURCES = PROVIDERS + ("modelsdev", "aa", "benchlm", "llmstats", "vals")
KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "AA_API_KEY",
        "LLM_STATS_API_KEY", "LLM_STATS_DETAIL_MAX")
DEFAULTS = {"disabled_sources": [], "run_days": 90, "daily_days": 365,
            "artifact_bundles": 2, "failed_days": 7, "website_max_pages": 40,
            "cache_days": 7, "llmstats_detail_max": 12, "llmstats_daily_budget": 0}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def new_run_id():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d_%H%M%S") + "_" + uuid.uuid4().hex[:12]


def validate_run_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("Invalid run ID")
    return value


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=1, ensure_ascii=False, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_config(path=None):
    cfg = dict(DEFAULTS)
    if path:
        supplied = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        unknown = set(supplied) - set(DEFAULTS)
        if unknown:
            raise ValueError("Unknown configuration keys: " + ", ".join(sorted(unknown)))
        cfg.update(supplied)
    if not isinstance(cfg["disabled_sources"], list) or set(cfg["disabled_sources"]) - set(SOURCES):
        raise ValueError("disabled_sources must list known source names")
    for key in set(DEFAULTS) - {"disabled_sources"}:
        if type(cfg[key]) is not int or cfg[key] < (2 if key == "artifact_bundles" else 0):
            raise ValueError(f"Invalid nonnegative integer configuration: {key}")
    return cfg


def windows_user_value(name):
    if os.name != "nt":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None


def resolve_credentials(environ=None, dotenv=None, user_reader=None):
    """Return resolved values; callers must never log the returned mapping."""
    env = os.environ if environ is None else environ
    if dotenv is None:
        from dotenv import dotenv_values
        dotenv = dotenv_values(ROOT / ".env", interpolate=False)
    reader = windows_user_value if user_reader is None else user_reader
    return {name: str(env.get(name) or dotenv.get(name) or reader(name) or "") for name in KEYS}


def apply_credentials():
    for name, value in resolve_credentials().items():
        if value:
            os.environ[name] = value


def safe_error(exc):
    """Sanitize URLs and environment secrets in provider/network diagnostics."""
    text = str(exc)
    for name in KEYS:
        value = os.getenv(name)
        if value and len(value) >= 4:
            text = text.replace(value, "[redacted]")
    text = re.sub(r"(?i)(authorization|api[_-]?key|token|cursor)=([^\s&]+)", r"\1=[redacted]", text)
    return text[:500]


def source_status(status, count=0, *, scope="catalog", reason="", complete=None, **extra):
    return {"status": status, "complete": status == "complete" if complete is None else complete,
            "scope": scope, "count": count, "fetched_at": utc_now(), "reason": reason,
            "enabled": status != "skipped", "attempted": status != "skipped", **extra}


def check_identity(data, run_id, label):
    actual = data.get("run_id") or data.get("stamp") or data.get("retrieved_at")
    if actual != run_id:
        raise ValueError(f"Mixed-run {label}: expected {run_id}, got {actual}")


def stage_cli(main, description):
    import argparse
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--input", required=True, help="Exact input artifact; no newest-file selection")
    p.add_argument("--output", required=True, help="Scratch output directory (not a published bundle)")
    args = p.parse_args()
    output = Path(args.output).resolve()
    if any((parent / "manifest.json").exists() for parent in (output, *output.parents)):
        p.error("Published/run bundles are immutable; choose a scratch output directory")
    main(input_path=args.input, output_dir=args.output)
