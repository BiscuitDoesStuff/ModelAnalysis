"""research.json contract: validation, AA index version by date range, expiry summary.

Entries are addressed as `scores:<target_slug>:<benchmark>` and
`inheritance:<target_slug>` (tools/refresh_evidence.py uses the same keys).
"""
import datetime
import math
import re

try:
    from .common import EFFORTS
    from .scales import BENCHMARKS
except ImportError:
    from common import EFFORTS
    from scales import BENCHMARKS

PROVIDERS = ("openrouter", "openai", "anthropic", "nvidia", "zenmux", "zen")
URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+\S*$")
WARN_DAYS = 3          # warn when evidence expires within this many days
VERSION_RECHECK_DAYS = 7  # an open AA version range should be re-confirmed this often
REQUIRED = {
    "scores": ("target_slug", "variant", "benchmark", "version", "value", "source", "url",
               "checked_at", "expires_at"),
    "inheritance": ("target_slug", "source_slug", "variant", "version", "provider", "route_id", "selector",
                    "supported_efforts", "cost_blended", "checked_at", "expires_at",
                    "equivalence_urls", "capability_url", "rationale"),
}


def date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def entry_key(section, rec):
    if section == "scores":
        return f"scores:{rec.get('target_slug')}:{rec.get('benchmark')}"
    return f"inheritance:{rec.get('target_slug')}"


def entries(registry):
    for section in ("scores", "inheritance"):
        for rec in registry.get(section, []):
            yield section, entry_key(section, rec), rec


def validate(registry, model_slugs=None):
    """(errors, warnings). Errors break the contract; warnings need a human."""
    errors, warnings = [], []
    ranges = registry.get("aa_index_versions")
    if ranges is None:
        if registry.get("snapshot_benchmarks"):
            warnings.append("legacy per-day snapshot_benchmarks; migrate to aa_index_versions")
        else:
            errors.append("aa_index_versions is required")
    else:
        spans = []
        for i, r in enumerate(ranges):
            where = f"aa_index_versions[{i}]"
            start, end = date(r.get("valid_from")), date(r.get("valid_to")) if r.get("valid_to") is not None else None
            if not r.get("version"):
                errors.append(f"{where}: version is required")
            if start is None or (r.get("valid_to") is not None and end is None):
                errors.append(f"{where}: valid_from/valid_to must be YYYY-MM-DD (valid_to may be null)")
            elif end is not None and end < start:
                errors.append(f"{where}: valid_to is before valid_from")
            if not URL.match(str(r.get("source_url", ""))):
                errors.append(f"{where}: source_url must be an http(s) URL")
            if date(r.get("checked_at")) is None:
                errors.append(f"{where}: checked_at must be YYYY-MM-DD")
            if start:
                spans.append((start, end or datetime.date.max, where))
        spans.sort()
        for (s1, e1, w1), (s2, e2, w2) in zip(spans, spans[1:]):
            if s2 <= e1:
                errors.append(f"{w1} and {w2} overlap")
    seen = set()
    for section, key, rec in entries(registry):
        missing = [f for f in REQUIRED[section] if f not in rec]
        if missing:
            errors.append(f"{key}: missing {', '.join(missing)}")
            continue
        if key in seen:
            errors.append(f"{key}: duplicate entry")
        seen.add(key)
        checked, expires = date(rec["checked_at"]), date(rec["expires_at"])
        if checked is None or expires is None:
            errors.append(f"{key}: checked_at/expires_at must be YYYY-MM-DD")
        elif checked > expires:
            errors.append(f"{key}: checked_at is after expires_at")
        if section == "scores":
            if rec["benchmark"] not in BENCHMARKS:
                errors.append(f"{key}: benchmark {rec['benchmark']!r} not in scales.BENCHMARKS")
            if not URL.match(str(rec["url"])):
                errors.append(f"{key}: url must be an http(s) URL")
            if not (isinstance(rec["value"], (int, float)) and not isinstance(rec["value"], bool)
                    and math.isfinite(rec["value"])):
                errors.append(f"{key}: value must be a finite number")
            if rec["variant"] not in EFFORTS + ("", "unspecified"):
                errors.append(f"{key}: variant {rec['variant']!r} unknown")
        else:
            efforts = rec["supported_efforts"]
            if not isinstance(efforts, list) or not set(efforts) <= set(EFFORTS):
                errors.append(f"{key}: supported_efforts must list known efforts")
            elif rec["variant"] not in efforts:
                errors.append(f"{key}: variant {rec['variant']!r} not in supported_efforts")
            if rec["provider"] not in PROVIDERS:
                errors.append(f"{key}: provider {rec['provider']!r} unknown")
            urls = rec["equivalence_urls"]
            if not isinstance(urls, list) or not urls or not all(URL.match(str(u)) for u in urls):
                errors.append(f"{key}: equivalence_urls must be http(s) URLs")
            if not URL.match(str(rec["capability_url"])):
                errors.append(f"{key}: capability_url must be an http(s) URL")
            if not str(rec["rationale"]).strip():
                errors.append(f"{key}: rationale is required")
        if model_slugs is not None:
            for field in ("target_slug", "source_slug"):
                if rec.get(field) and rec[field] not in model_slugs:
                    warnings.append(f"{key}: {field} {rec[field]!r} matches no model")
    return errors, warnings


def aa_version(registry, day):
    """(version, range or None, note). note is a warning when the day is not covered."""
    for r in registry.get("aa_index_versions") or []:
        if r["valid_from"] <= day and (r.get("valid_to") is None or day <= r["valid_to"]):
            return r["version"], r, ""
    pins = registry.get("snapshot_benchmarks") or {}
    if day in pins:
        return pins[day], None, ""
    ranges = registry.get("aa_index_versions") or []
    if ranges:
        latest = max(ranges, key=lambda r: r["valid_from"])
        return latest["version"], latest, (f"no AA index version range covers {day}; using latest "
                                           f"{latest['version']} from {latest['valid_from']}")
    if pins:
        latest = max(pins)
        return pins[latest], None, f"no AA benchmark pinned for day {day}; defaulting to latest known {pins[latest]} from {latest}"
    return None, None, "no AA index versions at all; external AA-version scores stay reference-only"


def evidence_status(registry, day, within=WARN_DAYS):
    """What expires soon, what has expired, and how fresh the AA version check is."""
    today = datetime.date.fromisoformat(day)
    expiring, expired, soonest = [], [], None
    for _, key, rec in entries(registry):
        end = date(rec.get("expires_at"))
        if end is None:
            continue
        left = (end - today).days
        if left < 0:
            expired.append(key)
        else:
            soonest = min(soonest, end) if soonest else end
            if left <= within:
                expiring.append({"key": key, "expires_at": rec["expires_at"], "days_left": left})
    version, rng, note = aa_version(registry, day)
    checked = date((rng or {}).get("checked_at"))
    stale_version = bool(rng and rng.get("valid_to") is None and checked
                         and (today - checked).days > VERSION_RECHECK_DAYS)
    return {"day": day, "soonest_expiry": soonest.isoformat() if soonest else None,
            "days_left": (soonest - today).days if soonest else None,
            "expiring": expiring, "expired": sorted(expired),
            "aa_index_version": version, "aa_version_checked_at": (rng or {}).get("checked_at"),
            "aa_version_recheck_due": stale_version, "aa_version_note": note}
