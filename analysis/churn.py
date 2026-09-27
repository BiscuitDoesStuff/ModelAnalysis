"""Pure route evidence and comparison rules; catalog identity is (provider, id)."""
import hashlib
import json
import math
import re

RULE_VERSION = 2
PROVIDERS = ("openrouter", "openai", "anthropic", "nvidia", "zenmux", "zen")
LOSS_TYPES = frozenset(("verified_free_paid", "verified_free_removed"))
EVENT_TYPES = ("verified_free_paid", "verified_free_removed", "verification_unknown",
               "free_added", "free_restored", "catalog_added", "catalog_removed", "catalog_changed")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def canonical_id(provider, route_id):
    tail = route_id.rsplit("/", 1)[-1].split(":", 1)[0].lower()
    if provider == "zen" and tail.endswith("-free"):
        tail = tail[:-5]
    return re.sub(r"[^a-z0-9]", "", tail)


def _prices(row):
    pricing = row.get("pricing")
    if not isinstance(pricing, dict):
        return None
    try:
        values = [float(pricing[k]) for k in ("prompt", "completion")
                  if not isinstance(pricing.get(k), bool)]
        if len(values) == 2 and all(math.isfinite(v) and v >= 0 for v in values):
            return values
    except (KeyError, ValueError, TypeError, OverflowError):
        pass
    return None


def route_evidence(provider, row):
    """Never infer paid from absent price/modality, or free from canonical models."""
    mid = row["id"]
    if provider == "zen" and mid.endswith("-free"):
        return "verified_free", ["zen:free-route"]
    if provider != "openrouter":
        prices = _prices(row)
        return ("paid", ["explicit-positive-price"]) if prices and any(prices) else (
            "unknown", ["no-verified-route-evidence"])
    if mid.lower().lstrip("~").startswith("openrouter/"):
        return "ineligible", ["router"]
    architecture = row.get("architecture")
    modalities = architecture.get("output_modalities") if isinstance(architecture, dict) else None
    if not isinstance(modalities, list) or not modalities:
        return "unknown", ["modality-missing"]
    if modalities != ["text"]:
        return "ineligible", ["not-text-only"]
    prices = _prices(row)
    if mid.endswith(":free") or prices == [0.0, 0.0]:
        return "verified_free", ["or:strict-free"]
    if prices is None:
        return "unknown", ["pricing-missing"]
    return "paid", ["explicit-positive-price"]


def build_routes(snapshot, models):
    """Return per-source exact routes and sources with malformed catalog entries.

    Optional explicit mappings: models=[{slug, routes:[{provider,id}]}] or
    [{slug, route_ids:{provider:[id]}}]. Display-only/benchmark rows confer no evidence.
    String entries are exact IDs with no implied pricing/modality. Invalid IDs and
    any duplicate (even identical) downgrade the whole source's completeness.
    """
    mappings = {}
    for model in (models.values() if isinstance(models, dict) else models or []):
        if not isinstance(model, dict) or model.get("history_excluded"):
            continue
        group = model.get("canonical_id") or model.get("slug")
        if not group:
            continue
        refs = list(model.get("routes") or [])
        for provider, ids in (model.get("route_ids") or {}).items():
            for mid in ([ids] if isinstance(ids, str) else ids):
                refs.append({"provider": provider, "id": mid})
        for ref in refs:
            if isinstance(ref, dict) and ref.get("provider") in PROVIDERS and ref.get("id"):
                key = (ref["provider"], ref["id"])
                # Conflicting mappings must not manufacture alternative access.
                mappings[key] = str(group) if key not in mappings or mappings[key] == str(group) else None
    routes, malformed = {}, set()
    for provider in PROVIDERS:
        routes[provider] = {}
        rows = snapshot.get(provider)
        if not isinstance(rows, list):
            malformed.add(provider)
            continue
        for row in rows:
            if isinstance(row, str):
                row = {"id": row}
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                    or not row["id"] or row["id"] != row["id"].strip()):
                malformed.add(provider)
                continue
            mid = row["id"]
            if mid in routes[provider]:
                malformed.add(provider)
                continue
            state, evidence = route_evidence(provider, row)
            mapped = mappings.get((provider, mid))
            routes[provider][mid] = {
                "provider": provider, "id": mid,
                "canonical_id": mapped or canonical_id(provider, mid),
                "canonical_explicit": bool(mapped),
                "namespace": mid.rsplit("/", 1)[0].lower() if "/" in mid else "",
                "state": state, "verified_free": state == "verified_free",
                "evidence": evidence, "catalog_hash": digest(row),
            }
    return routes, malformed


def retain_decisive(routes, before, run_id, observed_at):
    """Carry historical evidence, never current verification, through unknowns.

    Only called for a complete catalog against its same-rule published baseline.
    The self-contained decisive observation survives retention of the original run.
    Removed IDs are not carried forward as present routes.
    """
    for mid, route in routes.items():
        route.update(observed_run_id=run_id, observed_at=observed_at, rule_version=RULE_VERSION)
        if route["state"] in ("verified_free", "paid"):
            route["last_decisive"] = dict(route)
        elif mid in before and before[mid].get("last_decisive"):
            route["last_decisive"] = before[mid]["last_decisive"]


def same_model(left, right):
    if not left["canonical_id"] or left["canonical_id"] != right["canonical_id"]:
        return False
    if left.get("canonical_explicit") and right.get("canonical_explicit"):
        return True
    return not (left.get("namespace") and right.get("namespace")
                and left["namespace"] != right["namespace"])


def compare_routes(before, after, known_free=()):
    """Compare complete catalogs only (the caller enforces coverage/version gates)."""
    changes = []
    known_free = set(known_free)
    for mid in sorted(set(before) | set(after)):
        old, new = before.get(mid), after.get(mid)
        kinds = []
        if old is None:
            kinds.append("catalog_added")
        elif new is None:
            kinds.append("catalog_removed")
        elif old["catalog_hash"] != new["catalog_hash"]:
            kinds.append("catalog_changed")
        decisive = (old.get("last_decisive") or old) if old else None
        if decisive and decisive["verified_free"]:
            if new is None:
                kinds.append("verified_free_removed")
            elif new["state"] == "paid":
                kinds.append("verified_free_paid")
            elif not new["verified_free"] and old["verified_free"]:
                kinds.append("verification_unknown")
        elif new and new["verified_free"]:
            kinds.append("free_restored" if mid in known_free else "free_added")
        for kind in kinds:
            route = new or old
            changes.append({"type": kind, "kind": kind,
                            "provider": route["provider"], "source": route["provider"],
                            "id": mid, "route_id": mid,
                            "canonical_id": route["canonical_id"], "model": route["canonical_id"],
                            "before": decisive if kind in LOSS_TYPES else old,
                            "baseline_before": old, "after": new,
                            "alert": kind in LOSS_TYPES})
    return changes


def event_details(change, run_id, baseline_run_id, routes, health):
    event = dict(change, run_id=run_id, baseline_run_id=baseline_run_id, rule_version=RULE_VERSION)
    event["event_id"] = digest([RULE_VERSION, run_id, change["provider"], change["id"], change["type"]])
    source_health = health[change["provider"]]
    baseline = source_health.get("baseline") or {}
    event.update(baseline_observed_at=baseline.get("fetched_at") or baseline.get("started_at"),
                 current_observed_at=source_health.get("fetched_at"),
                 before_observed_at=(change.get("before") or {}).get("observed_at"),
                 before_run_id=(change.get("before") or {}).get("observed_run_id"))
    if change["type"] in LOSS_TYPES:
        lost = change["before"]
        alternatives = [route for provider in PROVIDERS if health[provider]["complete"]
                        for route in routes[provider].values()
                        if (provider, route["id"]) != (lost["provider"], lost["id"])
                        and route["verified_free"] and same_model(lost, route)]
        unknown_sources = [provider for provider in PROVIDERS if not health[provider]["complete"]]
        unknown_routes = [route for provider in PROVIDERS if health[provider]["complete"]
                          for route in routes[provider].values()
                          if route["state"] == "unknown" and same_model(lost, route)]
        unknown = bool(unknown_sources or unknown_routes)
        event.update(alternatives=sorted(alternatives, key=lambda r: (r["provider"], r["id"])),
                     unknown_coverage=unknown, unknown_sources=unknown_sources,
                     unknown_routes=unknown_routes,
                     access_status="verified_alternative" if alternatives else (
                         "unknown" if unknown else "no_verified_route"))
    return event
