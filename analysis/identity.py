"""Provider identity: which catalog routes and AA rows are one model. Pure functions.

Rules (strict by default):
- A route's vendor is its namespace (first ID segment) through the alias table in
  identity.json; OpenAI/Anthropic native catalogs imply their vendor; Zen has none.
- Same tail + same vendor -> one entity. Same tail + different known vendors ->
  separate entities, recorded as a `vendor-collision`.
- A vendor-unknown route joins only when exactly one entity has its tail;
  otherwise it stays alone and is recorded as `ambiguous-tail`.
- An AA row joins the entity with its tail and creator vendor. If that creator
  is not aliased to the route vendor, it still joins when it is the only AA row
  for the tail and one entity has the tail (`aa-creator-unaliased`, so the alias
  can be added). Two AA rows with the same tail and vendor are an `aa-duplicate`:
  the first by slug is kept, never silently overwritten.
- identity.json `joins` merge and `splits` separate listed routes explicitly.
Entities that do not collide keep their tail as slug; colliding ones get
`<tail>.<vendor>` (norm never yields '.', so no clash with plain slugs).
"""
import datetime
import json
import os
import re

try:
    from .common import base_slug, norm
except ImportError:
    from common import base_slug, norm

PROVIDERS = ("openrouter", "openai", "anthropic", "nvidia", "zenmux", "zen")
IMPLIED_VENDOR = {"openai": "openai", "anthropic": "anthropic"}
NO_VENDOR = {"zen"}
BASIS_ORDER = ("exact", "alias", "unique-tail", "explicit")
_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+\S*$")
DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "identity.json")


def validate_overrides(data):
    """Problems in identity.json; empty when valid (same spirit as research.json checks)."""
    problems = []
    if not isinstance(data.get("vendor_aliases", {}), dict):
        problems.append("vendor_aliases must be an object")
    for kind, minimum in (("joins", 2), ("splits", 1)):
        entries = data.get(kind, [])
        if not isinstance(entries, list):
            problems.append(f"{kind} must be a list")
            continue
        for i, entry in enumerate(entries):
            where = f"{kind}[{i}]"
            routes = entry.get("routes") if isinstance(entry, dict) else None
            if not isinstance(routes, list) or len(routes) < minimum or not all(
                    isinstance(r, dict) and r.get("provider") in PROVIDERS + ("aa",)
                    and isinstance(r.get("id"), str) and r["id"] for r in routes):
                problems.append(f"{where}: routes needs >= {minimum} {{provider, id}} entries")
            urls = entry.get("evidence_urls") if isinstance(entry, dict) else None
            if not isinstance(urls, list) or not urls or not all(isinstance(u, str) and _URL.match(u) for u in urls):
                problems.append(f"{where}: evidence_urls needs well-formed http(s) URLs")
            try:
                datetime.date.fromisoformat(entry.get("checked_at", ""))
            except (TypeError, ValueError, AttributeError):
                problems.append(f"{where}: checked_at must be YYYY-MM-DD")
            if not (isinstance(entry, dict) and str(entry.get("rationale", "")).strip()):
                problems.append(f"{where}: rationale is required")
    return problems


def load_overrides(path=None):
    with open(path or DEFAULT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    problems = validate_overrides(data)
    if problems:
        raise ValueError("identity.json invalid: " + "; ".join(problems))
    return data


def vendor_of(raw, aliases):
    key = norm(raw)
    return aliases.get(key, key)


def route_record(provider, route_id, aliases):
    rid = str(route_id).lstrip("~")
    namespace = rid.split("/", 1)[0] if "/" in rid else ""
    raw = IMPLIED_VENDOR.get(provider, "" if provider in NO_VENDOR else namespace)
    return {"provider": provider, "id": route_id, "vendor_raw": norm(raw),
            "vendor": vendor_of(raw, aliases) if raw else "", "tail": base_slug(route_id),
            "free_suffix": (provider == "zen" and str(route_id).endswith("-free")) or str(route_id).endswith(":free")}


def resolve(routes, aa_rows=(), overrides=None):
    """routes: {provider: [route_id]}; aa_rows: [{slug, creator}].

    Returns {"entities": {slug: entity}, "route_entity": {(provider, id): slug},
    "aa_entity": {aa_slug: slug}, "conflicts": [...]}. Output is independent of input order.
    """
    overrides = overrides or {}
    aliases = {k: v for k, v in (overrides.get("vendor_aliases") or {}).items() if not k.startswith("_")}
    nodes = {}  # (provider, id) -> record; AA rows use provider "aa"
    for provider in PROVIDERS:
        for rid in sorted(set(routes.get(provider) or [])):
            if rid:
                nodes[(provider, rid)] = route_record(provider, rid, aliases)
    aa_list = sorted({(str(r.get("slug") or ""), str(r.get("creator") or "")) for r in aa_rows if r.get("slug")})
    for slug, creator in aa_list:
        nodes[("aa", slug)] = {"provider": "aa", "id": slug, "vendor_raw": norm(creator),
                               "vendor": vendor_of(creator, aliases) if creator else "",
                               "tail": base_slug(slug), "free_suffix": False}
    conflicts, group, basis = [], {}, {}

    # Explicit splits first: listed nodes leave their natural group.
    for i, entry in enumerate(overrides.get("splits") or []):
        for ref in entry["routes"]:
            node = (ref["provider"], ref["id"])
            if node in nodes:
                group[node] = ("split", i, nodes[node]["tail"], nodes[node]["vendor"])
                basis[node] = "explicit"
            else:
                conflicts.append({"kind": "explicit-missing-route", "route": f"{node[0]}:{node[1]}",
                                  "reason": f"splits[{i}] names a route absent from this snapshot"})

    # Provider routes with a known vendor group by (tail, vendor).
    for node, rec in nodes.items():
        if node in group or node[0] == "aa" or not rec["vendor"]:
            continue
        group[node] = ("v", rec["tail"], rec["vendor"])
        basis[node] = "exact" if rec["vendor"] == rec["vendor_raw"] else "alias"

    def tail_groups(tail):
        return sorted({g for n, g in group.items() if g[0] == "v" and g[1] == tail})

    # AA rows: exact vendor match, else the only AA candidate for a single-entity tail.
    aa_by_tail = {}
    for slug, _ in aa_list:
        aa_by_tail.setdefault(nodes[("aa", slug)]["tail"], []).append(("aa", slug))
    claimed = {}
    for tail in sorted(aa_by_tail):
        for node in aa_by_tail[tail]:
            if node in group:
                continue
            rec = nodes[node]
            key = ("v", tail, rec["vendor"])
            existing = tail_groups(tail)
            if rec["vendor"] and key in existing:
                target, how = key, "exact" if rec["vendor"] == rec["vendor_raw"] else "alias"
            elif len(aa_by_tail[tail]) == 1 and len(existing) == 1:
                target, how = existing[0], "unique-tail"
                conflicts.append({"kind": "aa-creator-unaliased", "tail": tail, "aa_slug": node[1],
                                  "aa_vendor": rec["vendor"], "route_vendor": existing[0][2],
                                  "reason": "joined as the only AA row for this tail; add a vendor alias to confirm"})
            else:
                target, how = key, "exact"
            if target in claimed:
                conflicts.append({"kind": "aa-duplicate", "tail": tail, "vendor": target[2],
                                  "aa_slugs": [claimed[target][1], node[1]], "kept": claimed[target][1],
                                  "reason": "two AA rows normalise to one entity; the first by slug is kept"})
                continue
            claimed[target] = node
            group[node], basis[node] = target, how

    # Vendor-unknown routes (Zen): join only a unique entity for their tail.
    for node, rec in sorted(nodes.items()):
        if node in group or node[0] == "aa":  # unattached AA rows are recorded duplicates
            continue
        existing = tail_groups(rec["tail"])
        if len(existing) == 1:
            group[node], basis[node] = existing[0], "unique-tail"
        else:
            group[node], basis[node] = ("u", rec["tail"], node[0]), "exact"
            if len(existing) > 1:
                conflicts.append({"kind": "ambiguous-tail", "tail": rec["tail"],
                                  "route": f"{node[0]}:{node[1]}", "candidates": [f"{g[2]}/{g[1]}" for g in existing],
                                  "reason": "vendor-unknown route matches several vendors; kept separate"})

    # Explicit joins merge whole groups (union-find over group keys).
    parent = {}

    def find(g):
        parent.setdefault(g, g)
        while parent[g] != g:
            parent[g] = parent[parent[g]]
            g = parent[g]
        return g
    explicit_groups = set()
    for i, entry in enumerate(overrides.get("joins") or []):
        present = [(r["provider"], r["id"]) for r in entry["routes"] if (r["provider"], r["id"]) in group]
        for ref in entry["routes"]:
            if (ref["provider"], ref["id"]) not in group:
                conflicts.append({"kind": "explicit-missing-route", "route": f"{ref['provider']}:{ref['id']}",
                                  "reason": f"joins[{i}] names a route absent from this snapshot"})
        roots = sorted({find(group[n]) for n in present})
        for other in roots[1:]:
            parent[other] = roots[0]
        if roots:
            explicit_groups.add(roots[0])
    members = {}
    for node, g in group.items():
        members.setdefault(find(g), []).append(node)

    # One entity per final group; slugs stay plain unless the tail is shared.
    entities = []
    for g, nodes_in in members.items():
        nodes_in.sort()
        provider_nodes = [n for n in nodes_in if n[0] != "aa"]
        head = nodes[(sorted(provider_nodes, key=lambda n: (nodes[n]["free_suffix"], n)) or nodes_in)[0]]
        vendor = g[2] if g[0] in ("v", "split") else ""
        how = "explicit" if g in explicit_groups or g[0] == "split" else max(
            (basis[n] for n in nodes_in), key=BASIS_ORDER.index)
        entities.append({"tail": head["tail"], "vendor": vendor, "group": g, "nodes": nodes_in,
                         "basis": how, "label": vendor or (head["provider"] if g[0] == "u" else "")})
    by_tail = {}
    for e in entities:
        by_tail.setdefault(e["tail"], []).append(e)
    taken, out, route_entity, aa_entity = set(), {}, {}, {}
    for tail in sorted(by_tail):
        group_list = sorted(by_tail[tail], key=lambda e: (e["label"], e["nodes"]))
        for e in group_list:
            slug = tail if len(group_list) == 1 else f"{tail}.{e['label'] or 'unknown'}"
            n = 2
            while slug in taken:
                slug, n = f"{tail}.{e['label'] or 'unknown'}.{n}", n + 1
            taken.add(slug)
            e["slug"] = slug
        if len(group_list) > 1 and any(e["vendor"] for e in group_list):
            known = [e for e in group_list if e["group"][0] != "u"]
            if len({e["vendor"] for e in known}) > 1:
                conflicts.append({"kind": "vendor-collision", "tail": tail,
                                  "entities": [e["slug"] for e in known],
                                  "routes": {e["slug"]: [f"{p}:{i}" for p, i in e["nodes"]] for e in known},
                                  "reason": "same tail from different vendors; kept separate"})
    for e in entities:
        routes_by_provider = {}
        for provider, rid in e["nodes"]:
            if provider == "aa":
                aa_entity[rid] = e["slug"]
            else:
                routes_by_provider.setdefault(provider, []).append(rid)
                route_entity[(provider, rid)] = e["slug"]
        out[e["slug"]] = {"slug": e["slug"], "tail": e["tail"], "vendor": e["vendor"],
                          "key": f"{e['vendor'] or '?'}/{e['tail']}", "basis": e["basis"],
                          "routes": routes_by_provider,
                          "aa": next((rid for p, rid in e["nodes"] if p == "aa"), None),
                          "free_only_zen": bool(e["nodes"]) and all(p == "zen" and nodes[(p, i)]["free_suffix"]
                                                                    for p, i in e["nodes"])}
    # Churn groups free-only Zen routes with their paid counterpart for alternatives.
    tails = {}
    for slug, e in out.items():
        tails.setdefault(e["tail"], []).append(slug)
    for slug, e in out.items():
        e["canonical_id"] = slug
        if e["free_only_zen"]:
            base = tails.get(base_slug(e["routes"]["zen"][0][:-len("-free")]), [])
            if len(base) == 1:
                e["canonical_id"] = base[0]
    for c in conflicts:
        c["entities"] = sorted(set(c.get("entities") or []) | {
            s for key in ("route",) if c.get(key) for s in [route_entity.get(tuple(c[key].split(":", 1)))] if s} | {
            aa_entity[x] for x in c.get("aa_slugs", []) + ([c["aa_slug"]] if c.get("aa_slug") else []) if x in aa_entity})
    conflicts.sort(key=lambda c: (c["kind"], c.get("tail", ""), json.dumps(c, sort_keys=True)))
    for e in out.values():
        e["conflicts"] = [c for c in conflicts if e["slug"] in c["entities"]]
    return {"entities": out, "route_entity": route_entity, "aa_entity": aa_entity, "conflicts": conflicts}
