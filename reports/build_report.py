"""Build MD/XLSX/JSON and an offline HTML dashboard from an explicit analysis artifact."""
import json, os, sys, html as _html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from analysis.common import EFFORTS as EFFORT_TOKENS, EVIDENCE, TIERS as TIER_FLOORS, evidence_label, score_evidence_type

MD_CAP = 20
TIERS = ["max", "high", "medium"]
TIER_LABEL = {"max": "Max (50+)", "high": "High (40+)", "medium": "Medium/General (30+)"}
VARIANTS = {"OCF": set(), "OF": {"C"}, "CF": {"O"}, "F": {"O", "C"}}
OCF = {"O", "C", "F"}
VALUE_BAND = 1.5


def opencode_ids(or_id):
    if not or_id:
        return ""
    return or_id if or_id.startswith("openrouter/") else f"openrouter/{or_id}"


def copy_id(m):
    """Preferred copy ID: openrouter/<or_id>, else native fallback ID."""
    if m.get('selector'):
        return m['selector']
    oc = opencode_ids(m.get("or_id", ""))
    if oc:
        return oc
    fb = m.get("fallback_id", "")
    return str(fb) if fb and m.get('fallback_provider') not in (None, '', 'aa') else ""


def reliability_data(a):
    """Preserve optional run/history fields without reinterpreting source evidence."""
    return {k: a[k] for k in ("run_id", "schema_version", "started_at", "source_health", "website_health", "churn") if k in a}


def metadata_text(value):
    """Readable nested source components and baseline references, without schema guesses."""
    if isinstance(value, dict):
        return "; ".join(f"{k}: {metadata_text(v)}" for k, v in value.items()) or "—"
    if isinstance(value, list):
        return "; ".join(metadata_text(v) for v in value) or "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "—" if value is None or value == "" else str(value)


def health_entries(a):
    churn = a.get("churn") or {}
    sources = dict(a.get("source_health") or {})
    for source, health in (churn.get("source_health") or {}).items():
        sources[source] = {**(sources.get(source) or {}), **health}
    for group, values in (("", sources), ("website / ", a.get("website_health") or {})):
        for source, value in values.items():
            health = value if isinstance(value, dict) else {"status": value}
            yield group + source, health, (health.get("baseline") or (churn.get("baselines") or {}).get(source))


def partial_health(health):
    return (health.get("complete") is False or health.get("status") not in ("complete", "fresh")
            or health.get("scope", "catalog") != "catalog")


def source_summary(a):
    entries = list(health_entries(a))
    if not entries:
        return "Source coverage unknown — no health metadata."
    partial = sum(partial_health(health) for _, health, _ in entries)
    label = f"Partial coverage ({partial}/{len(entries)} sources limited or unavailable)" if partial else "Complete source coverage"
    return label + " · " + " · ".join(f"{name}: {metadata_text(health.get('status'))}" for name, health, _ in entries)


def baseline_message(a):
    churn = a.get("churn") or {}
    baselines = list((churn.get("baselines") or {}).values()) + [ref for _, _, ref in health_entries(a)]
    if not churn or not any(baselines) or churn.get("trusted_route_history") is False:
        return "No trusted baseline — route churn cannot be determined."
    if not churn.get("events"):
        return "No route events recorded; comparisons apply only to sources with trusted, complete coverage."
    return "Route events use per-source trusted baselines; incomplete coverage is not evidence of route loss."


def reliability_tables(a):
    churn = a.get("churn") or {}
    health_rows = []
    for name, health, baseline in health_entries(a):
        coverage = {k: health[k] for k in ("scope", "complete", "compared", "coverage", "components",
                    "attempted_count", "failed_count", "cache_hits", "oldest_data_at") if k in health}
        health_rows.append([name, health.get("status"), health.get("count"), health.get("fetched_at"),
                            health.get("reason") or health.get("error") or health.get("coverage_reason"),
                            baseline or "No trusted baseline", ("Partial coverage; " if partial_health(health) else "") + metadata_text(coverage)])
    yield "Source health", ["Source", "Status", "Count", "Fetched at", "Reason", "Baseline", "Coverage / components"], health_rows
    events = []
    for event in churn.get("events") or []:
        coverage = {k: event[k] for k in ("coverage", "unknown_coverage", "unknown_sources", "unknown_routes", "access_status") if k in event}
        kind = event.get("kind") or event.get("type")
        events.append([kind, event.get("source") or event.get("provider"), event.get("route_id") or event.get("id"),
                       event.get("model") or event.get("canonical_id"),
                       event.get("loss_reason") or event.get("reason") or kind,
                       event.get("alternatives") or "None recorded", coverage or churn.get("coverage") or "Unknown"])
    yield "Churn events", ["Event", "Source", "Route", "Model", "Loss reason / change", "Alternatives", "Coverage"], events
    daily = churn.get("daily") or {}
    if isinstance(daily.get("sources"), dict):
        rows = []
        for source, summary in daily["sources"].items():
            def counts(events):
                result = {}
                for event in events or []:
                    kind = event.get("kind") or event.get("type") or "unknown"
                    result[kind] = result.get(kind, 0) + 1
                return result or "No events"
            rows.append([daily.get("day"), source, counts(summary.get("net_events")), counts(summary.get("observed_events")),
                         summary.get("latest_complete"), summary.get("baseline") or "No trusted baseline",
                         [{k: h[k] for k in ("run_id", "status", "complete", "reason") if k in h} for h in summary.get("coverage") or []]])
        yield "Daily summary", ["Day", "Source", "Net events", "Observed events", "Latest complete", "Baseline", "Coverage"], rows
    else:
        yield "Daily summary", ["Day / field", "Summary"], list(daily.items())


def reliability_markdown(a):
    lines = ["\n## Reliability\n", source_summary(a) + "\n", baseline_message(a) + "\n"]
    for title, headers, rows in reliability_tables(a):
        lines.append(f"\n### {title}\n")
        lines.append("| " + " | ".join(headers) + " |\n|" + "---|" * len(headers) + "\n")
        for row in rows:
            lines.append("| " + " | ".join(esc(metadata_text(v)).replace("|", "&#124;").replace("\n", "<br>") for v in row) + " |\n")
        if not rows:
            lines.append("\nNo records available.\n")
    return "".join(lines)


def reliability_html(a):
    body = ["<section id='reliability'><h2>Reliability</h2>",
            f"<p><strong>{esc(source_summary(a))}</strong></p>",
            f"<p>{esc(baseline_message(a))}</p>"]
    identity = {k: a[k] for k in ("run_id", "started_at", "schema_version") if k in a}
    if identity:
        body.append(f"<p>{esc(metadata_text(identity))}</p>")
    for title, headers, rows in reliability_tables(a):
        body.append(f"<h3>{title}</h3><div class='twrap'><table><thead><tr>" +
                    "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead><tbody>")
        for row in rows:
            body.append("<tr>" + "".join(f"<td>{esc(metadata_text(v))}</td>" for v in row) + "</tr>")
        if not rows:
            body.append(f"<tr><td colspan='{len(headers)}'>No records available.</td></tr>")
        body.append("</tbody></table></div>")
    body.extend(f"<details><summary>Raw {esc(k)}</summary><pre>{esc(json.dumps(v, ensure_ascii=False, indent=2))}</pre></details>"
                for k, v in reliability_data(a).items())
    return "".join(body) + "</section>"


IDENTITY_HEADERS = ["Kind", "Tail", "Entities", "Routes", "Reason"]


def identity_rows(a):
    """One row per identity conflict: which routes sit on each side, and why."""
    for c in a.get("identity_conflicts") or []:
        if c.get("routes"):
            routes = "; ".join(f"{slug}: {', '.join(ids)}" for slug, ids in c["routes"].items())
        else:
            routes = ", ".join(filter(None, [c.get("route"), c.get("aa_slug") and f"aa:{c['aa_slug']}"]
                                      + [f"aa:{x}" for x in c.get("aa_slugs", [])]))
            if c.get("candidates"):
                routes += " vs " + ", ".join(c["candidates"])
        yield [c.get("kind", ""), c.get("tail", ""), ", ".join(c.get("entities", [])), routes, c.get("reason", "")]


def metadata_rows(value, path=""):
    """Lossless leaf paths for nested metadata in the spreadsheet."""
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from metadata_rows(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            yield from metadata_rows(item, f"{path}[{index}]")
    else:
        yield [path, json.dumps(value, ensure_ascii=False)]


def provenance_text(m, field):
    """One line naming where a displayed score/price came from: source, version, time, evidence, obs_id."""
    p = (m.get("provenance") or {}).get(field)
    if not p:
        return ""
    return (f"{p['source']} · {p.get('version') or 'version unknown'} · observed {p.get('observed_at') or 'unknown'}"
            f" · {evidence_label(p.get('evidence'))} · {p['obs_id']}")


def prov_attrs(m, field):
    """Attributes for a score (sc) or price (cc) cell; audit_provenance traces data-obs."""
    cls = "sc" if field == "score" else "cc"
    p = (m.get("provenance") or {}).get(field)
    if not p:
        return f" class='{cls}'"
    return f" class='{cls}' data-obs='{esc(p['obs_id'])}' title='{esc(provenance_text(m, field))}'"


def score_evidence(m):
    source = m.get('score_source') or {}
    text = evidence_label(score_evidence_type(m)) if source else 'unscored'
    if source.get('kind') == 'aa-api':
        text += ' (AA API)'
    elif source.get('kind') == 'external':
        text += ' (registry)'
    if source.get('source_slug'):
        text += ' from ' + source['source_slug']
    if source.get('version'):
        text += ' / ' + source['version']
    urls = ([source['url']] if source.get('url') else []) + source.get('equivalence_urls', [])
    if source.get('capability_url'):
        urls.append(source['capability_url'])
    upstream = source.get('upstream') or {}
    if upstream.get('url'):
        urls.append(upstream['url'])
    return text + ('; checked ' + source['checked_at'] if source.get('checked_at') else ''), urls


def evidence_html(m):
    text, urls = score_evidence(m)
    result = esc(text)
    for url in urls:
        if url.startswith(('https://', 'http://')):
            result += ' <a href="' + esc(url) + '">source</a>'
    for row in m.get('external_scores', []):
        result += '<br>' + esc(f"{row['benchmark']}: {row['value']} ({row['version']}; {row['variant']})")
        result += ' <a href="' + esc(row['url']) + '">reference</a>'
    return result


def copy_hint(m):
    fb = m.get("fallback_provider", "")
    if m.get("or_id"):
        return ""
    return f" ({fb})" if fb else ""


def variant_display(m):
    v = m.get("variant", "")
    if v:
        base = f" ({v})"
    elif m.get("variant_ambiguous"):
        base = " (ambiguous-effort)"
    elif m.get("variant_label") == "base (unspecified effort)":
        base = " (base, unspecified effort)"
    else:
        base = ""
    if m.get("deprecated_upstream"):
        base += " [deprecated-upstream]"
    if m.get("modality_status") == "modality-unverified":
        base += " [modality-unverified]"
    return base


def efforts_display(m):
    eff = m.get("efforts") or []
    if eff:
        d = m.get("default_effort", "")
        if d and d in eff:
            star = f" *{d}"
        elif d:
            star = f" *{d}"
        else:
            star = " (default unspecified)"
        return "/".join(eff) + star
    hint = m.get("efforts_hint") or []
    if hint:
        return "/".join(hint) + " (hint, sibling)"
    ors = m.get("or_reasoning_status", "")
    if ors in ("non-reasoning", "metadata-missing") and m.get("or_id"):
        return f"[{ors}]"
    return ""


def hier_key(r):
    s = r.get("score")
    x = r.get("ratio")
    return (-(s if s is not None else -1), -(x if x is not None else -1))


def free_status_of(m):
    fs = m.get("free_status")
    if fs in ("verified", "provisional-l1", "provisional-l0", "none"):
        return fs
    return "verified" if m.get("free") else "none"


def is_provisional(m):
    return free_status_of(m) in ("provisional-l1", "provisional-l0")


def has_callable(m):
    if m.get("or_id"):
        return True
    provs = set(m.get("providers", []))
    return bool(provs & {"openai", "anthropic", "openrouter",
                         "nvidia", "zenmux", "zen"})


def groups_display(m):
    g = "".join(m.get("groups", [])) or ""
    if is_provisional(m):
        g = (g + "F?") if g else "F?"
    return g or "–"


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def family_key_of(slug, variant):
    s = str(slug or "")
    if "__" in s:
        s = s.split("__")[0]
    v = str(variant or "")
    if v and s.endswith(v):
        base = s[: -len(v)]
        return base or s
    for eff in EFFORT_TOKENS:
        if eff and s.endswith(eff) and len(s) > len(eff):
            return s[: -len(eff)]
    return s or str(slug or "")


def build_value_bands(paid_rows, width=VALUE_BAND, floor=30.0, max_bands=20):
    """Group paid scored+costed rows into score bands; cheapest-first within band. Skips single-row bands."""
    scored = [m for m in paid_rows
              if m.get("score") is not None and m.get("cost_blended") not in (None, 0)]
    scored = sorted(scored, key=lambda r: (-r["score"], r["cost_blended"]))
    bands = []
    i = 0
    while i < len(scored) and len(bands) < max_bands:
        top = scored[i]["score"]
        if top < floor:
            break
        members = []
        j = i
        while j < len(scored) and scored[j]["score"] >= top - width:
            members.append(scored[j])
            j += 1
        if len(members) < 2:
            i = j
            continue
        by_cost = sorted(members, key=lambda r: (r["cost_blended"], -r["score"]))
        costs = [m["cost_blended"] for m in members if m.get("cost_blended")]
        top_cost = max(costs) if costs else None
        winner = by_cost[0] if by_cost else None
        saving = None
        if winner and top_cost and top_cost > 0 and winner["cost_blended"] is not None:
            saving = round((top_cost - winner["cost_blended"]) / top_cost * 100, 1)
        bands.append({"top": top, "bottom": min(m["score"] for m in members),
                      "rows": by_cost, "winner": winner,
                      "top_cost": top_cost, "saving_pct": saving})
        i = j
    return bands


def build_family_full(all_rows):
    """Full per-family table: every multi-variant family, all rows, no floor/cap."""
    fams = {}
    for m in all_rows:
        if m.get("router"):
            continue
        fams.setdefault(family_key_of(m.get("slug", ""), m.get("variant", "")), []).append(m)
    out = []
    for fam, members in fams.items():
        variants = {x.get("variant", "") for x in members if x.get("variant")}
        if len(members) < 2 or len(variants) < 1:
            continue
        scored = [x["score"] for x in members if x.get("score") is not None]
        peak = max(scored) if scored else None
        out.append({"family": fam, "peak": peak,
                    "rows": sorted(members, key=lambda r: (-(r.get("score") if r.get("score") is not None else -1)))})
    return sorted(out, key=lambda f: (-(f["peak"] if f["peak"] is not None else -1)))


def build_sections(a):
    models = a.get("models", [])
    routers = [m["id"] for m in models if m.get("router")]
    models = [m for m in models if not m.get("router")]
    ocf = [m for m in models
           if set(m.get("groups", [])) & OCF or is_provisional(m)]

    all_intel = sorted(models, key=lambda r: (-(r["score"] if r["score"] is not None else -1)))
    costed = sorted([m for m in models if m.get("cost_blended") is not None],
                    key=lambda r: r["cost_blended"])
    uncosted = [m for m in models if m.get("cost_blended") is None]
    paid_ratio = sorted([m for m in models
                         if free_status_of(m) == "none" and m.get("ratio") is not None],
                        key=lambda r: -r["ratio"])
    free_block = sorted([m for m in models
                         if free_status_of(m) == "verified" and m.get("score") is not None],
                        key=lambda r: -r["score"])
    provisional_block = sorted([m for m in models
                                if is_provisional(m) and m.get("score") is not None],
                               key=lambda r: -r["score"])
    free_unscored = [m for m in models
                     if free_status_of(m) == "verified" and m.get("score") is None]
    provisional_unscored = [m for m in models
                            if is_provisional(m) and m.get("score") is None]
    unratable = [m for m in models
                 if free_status_of(m) == "none" and m.get("ratio") is None]

    ocf_intel = [m for m in all_intel if m in ocf]
    ocf_costed = [m for m in costed if m in ocf]
    ocf_uncosted = [m for m in uncosted if m in ocf]
    ocf_ratio = [m for m in paid_ratio if m in ocf]
    ocf_free = [m for m in free_block if m in ocf]
    ocf_provisional = [m for m in provisional_block if m in ocf]
    ocf_free_unscored = [m for m in free_unscored if m in ocf]
    ocf_provisional_unscored = [m for m in provisional_unscored if m in ocf]
    ocf_unratable = [m for m in unratable if m in ocf]

    stack = {}
    for t in TIERS:
        rows = sorted([m for m in ocf if m.get("tier") == t and has_callable(m)],
                      key=hier_key)
        present = set().union(*[set(m.get("groups", [])) for m in rows]) if rows else set()
        stack[t] = {"rows": rows, "gaps": sorted(OCF - present)}

    practical = []
    for t in TIERS:
        for v, off in VARIANTS.items():
            rows = sorted([m for m in stack[t]["rows"] if not (set(m.get("groups", [])) & off)],
                          key=hier_key)
            practical.append({"tier": t, "variant": v,
                              "winner": rows[0] if rows else None,
                              "runner_up": rows[1] if len(rows) > 1 else None})

    elig = [m for m in ocf if free_status_of(m) == "none" and m.get("score") is not None
            and m.get("cost_blended") is not None]
    q = {"score_q1": pct([m["score"] for m in elig], 0.25),
         "score_q3": pct([m["score"] for m in elig], 0.75),
         "cost_q1": pct([m["cost_blended"] for m in elig], 0.25),
         "cost_q3": pct([m["cost_blended"] for m in elig], 0.75)}
    outliers = {"bargains": [], "overpriced": [], "free_gems": []}
    if elig and q["score_q3"] is not None:
        outliers["bargains"] = [m for m in elig
                                if m["score"] >= q["score_q3"] and m["cost_blended"] <= q["cost_q1"]]
        outliers["overpriced"] = [m for m in elig
                                  if m["score"] <= q["score_q1"] and m["cost_blended"] >= q["cost_q3"]]
    outliers["free_gems"] = [m for m in ocf
                             if (free_status_of(m) in ("verified", "provisional-l1", "provisional-l0"))
                             and (m.get("score") or 0) >= TIER_FLOORS["high"] and has_callable(m)]

    return {"all_intel": all_intel, "costed": costed, "uncosted": uncosted,
            "paid_ratio": paid_ratio, "free_block": free_block,
            "provisional_block": provisional_block,
            "free_unscored": free_unscored,
            "provisional_unscored": provisional_unscored, "unratable": unratable,
            "ocf_intel": ocf_intel, "ocf_costed": ocf_costed, "ocf_uncosted": ocf_uncosted,
            "ocf_ratio": ocf_ratio, "ocf_free": ocf_free,
            "ocf_provisional": ocf_provisional,
            "ocf_free_unscored": ocf_free_unscored,
            "ocf_provisional_unscored": ocf_provisional_unscored,
            "ocf_unratable": ocf_unratable,
            "stack": stack, "practical": practical, "outliers": outliers,
            "family_variants": build_family_full(all_intel),
            "quartiles": q, "ocf_count": len(ocf), "model_count": len(models),
            "routers": routers}


def row_md(m):
    g = groups_display(m) if groups_display(m) != "–" else "-"
    s = m["score"] if m.get("score") is not None else "unscored"
    c = m["cost_blended"] if m.get("cost_blended") is not None else "cost-unknown"
    cs = m.get("cost_source", "")
    cs_tag = f" [{cs}]" if cs in ("aa", "or-derived", "inherited") else ""
    r = m["ratio"] if m.get("ratio") is not None else "-"
    v = variant_display(m)
    eff = efforts_display(m)
    eff_s = f" — efforts {eff}" if eff else ""
    cp = copy_id(m)
    if m.get("or_id"):
        oc = f" → `{cp}`"
    elif cp:
        oc = f" → `{cp}`{copy_hint(m)} (native, no OR)"
    else:
        nc = m.get("nearest_callable", "")
        oc = " (AA-only, no callable ID" + (f"; nearest {nc} display-only" if nc else "") + ")"
    evidence, urls = score_evidence(m)
    refs = ' '.join(f'[source]({u})' for u in urls)
    return f"- `{m['id']}`{v} [{g}] — score {s} — ${c}/1M{cs_tag} — ratio {r}{eff_s}{oc} — {evidence} {refs}\n"


def esc(v):
    return _html.escape("" if v is None else str(v))


def fmt_cost(m):
    return "unknown" if m.get("cost_blended") is None else f"${m['cost_blended']}/1M"


def fmt_score(m):
    suffix = ' (estimate)' if (m.get('score_source') or {}).get('kind') == 'inherited-estimate' else ''
    return "unscored" if m.get("score") is None else str(m["score"]) + suffix


def html_table(rows, note=""):
    h = ['<input class="search" placeholder="Filter…" oninput="filterRows(this)">']
    if note:
        h.append(f'<p class="note">{esc(note)}</p>')
    h.append('<div class="twrap"><table><thead><tr><th>Model</th><th>Groups</th>'
             '<th>Score</th><th>Cost</th><th>Ratio</th><th>Variant</th><th>Efforts</th>'
             '<th>Route ID / selector <span class="hint">(click to copy)</span></th>'
             '<th>Sources</th><th>Score evidence / external metrics</th></tr></thead><tbody>')
    for m in rows:
        oc = copy_id(m)
        hint = copy_hint(m)
        var_cell = esc(m.get("variant", "") or "–")
        if m.get("variant_ambiguous"):
            var_cell += "<br><span class='gap'>ambiguous-effort</span>"
        elif not m.get("variant") and m.get("variant_label") == "base (unspecified effort)":
            var_cell += "<br><span class='hint'>base, unspecified</span>"
        if m.get("deprecated_upstream"):
            var_cell += "<br><span class='gap'>deprecated-upstream</span>"
        if m.get("modality_status") == "modality-unverified":
            var_cell += "<br><span class='gap'>modality-unverified</span>"
        eff_cell = esc(efforts_display(m) or "–")
        cost_cell = esc(fmt_cost(m))
        if m.get("cost_source") in ("aa", "or-derived", "inherited"):
            cost_cell += f"<br><span class='hint'>{esc(m['cost_source'])}</span>"
        route_cell = (f"<code class='copy' onclick=\"copyId(this)\" title='click to copy'>{esc(oc)}</code><span class='hint'>{esc(hint)}</span>" if oc
                      else "AA-only / no callable ID" + (f"<br><span class='hint'>nearest {esc(m.get('nearest_callable',''))} display-only</span>" if m.get("nearest_callable") else ""))
        h.append("<tr><td><code>" + esc(m["id"]) + "</code>" +
                 (f"<br><span class='nm'>{esc(m.get('name', ''))}</span>" if m.get("name") else "") +
                 "</td><td>" + esc(groups_display(m)) + "</td><td" + prov_attrs(m, "score") + ">" + esc(fmt_score(m)) +
                 "</td><td" + prov_attrs(m, "price") + ">" + cost_cell + "</td><td>" +
                 esc(m["ratio"] if m.get("ratio") is not None else "–") + "</td><td>" +
                 var_cell + "</td><td>" +
                 eff_cell + "</td><td>" +
                 route_cell +
                 "</td><td>" + esc(",".join(m.get("providers", []))) + "</td><td>" + evidence_html(m) + "</td></tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def explore_table(rows):
    h = ['<div class="filters">'
         '<input class="search" id="xq" placeholder="Filter text…" oninput="filterExplore()">'
         '<select id="xgrp" onchange="filterExplore()"><option value="">Groups: all</option>'
         '<option value="O">O only</option><option value="C">C only</option>'
         '<option value="F">F verified</option><option value="F?">F? provisional</option></select>'
         '<select id="xcost" onchange="filterExplore()"><option value="">Cost source: all</option>'
         '<option>aa</option><option>or-derived</option><option>inherited</option><option>none</option></select>'
         '<select id="xfree" onchange="filterExplore()"><option value="">Free: all</option>'
         '<option>verified</option><option>provisional-l1</option><option>provisional-l0</option><option>none</option></select>'
         '</div><div class="twrap"><table id="xtab"><thead><tr><th>Model</th><th>Groups</th>'
         '<th>Score</th><th>Cost</th><th>Ratio</th><th>Variant</th><th>Efforts</th>'
         '<th>Route ID / selector <span class="hint">(click to copy)</span></th>'
         '<th>Sources</th><th>Score evidence</th></tr></thead><tbody>']
    for m in rows:
        oc = copy_id(m)
        hint = copy_hint(m)
        var_cell = esc(m.get("variant", "") or "–")
        if m.get("variant_ambiguous"):
            var_cell += "<br><span class='gap'>ambiguous-effort</span>"
        if m.get("deprecated_upstream"):
            var_cell += "<br><span class='gap'>deprecated-upstream</span>"
        if m.get("modality_status") == "modality-unverified":
            var_cell += "<br><span class='gap'>modality-unverified</span>"
        cost_cell = esc(fmt_cost(m))
        if m.get("cost_source") in ("aa", "or-derived", "inherited"):
            cost_cell += f"<br><span class='hint'>{esc(m['cost_source'])}</span>"
        route_cell = (f"<code class='copy' onclick=\"copyId(this)\" title='click to copy'>{esc(oc)}</code><span class='hint'>{esc(hint)}</span>" if oc
                      else "AA-only / no callable ID" + (f"<br><span class='hint'>nearest {esc(m.get('nearest_callable',''))} display-only</span>" if m.get("nearest_callable") else ""))
        h.append(f"<tr data-groups=\"{esc(groups_display(m))}\" data-cost=\"{esc(m.get('cost_source',''))}\" data-free=\"{esc(free_status_of(m))}\">"
                 "<td><code>" + esc(m["id"]) + "</code></td><td>" + esc(groups_display(m)) + "</td><td" + prov_attrs(m, "score") + ">" + esc(fmt_score(m)) +
                 "</td><td" + prov_attrs(m, "price") + ">" + cost_cell + "</td><td>" + esc(m["ratio"] if m.get("ratio") is not None else "–") + "</td><td>" +
                 var_cell + "</td><td>" + esc(efforts_display(m) or "–") + "</td><td>" + route_cell +
                 "</td><td>" + esc(",".join(m.get("providers", []))) + "</td><td>" + evidence_html(m) + "</td></tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def graph_data(rows):
    """Minimal, non-router comparison data for the offline Graph page."""
    return [{"slug": m["slug"], "id": m["id"], "name": m.get("name") or "",
             "variant": m.get("variant") or "", "ambiguous": bool(m.get("variant_ambiguous")),
             "score": m.get("score"), "estimate": (m.get("score_source") or {}).get("kind") == "inherited-estimate",
             "cost": m.get("cost_blended"), "cost_source": m.get("cost_source") or "none",
             "free_status": free_status_of(m), "route": copy_id(m),
             "deprecated": bool(m.get("deprecated_upstream")),
             "modality_unverified": m.get("modality_status") == "modality-unverified"}
            for m in rows]


def build_html(a, s, stamp):
    th = a.get("thresholds", {"max": 50, "high": 40, "medium": 30})
    fsc = a.get("free_status_counts", {})
    chips = (f"<span class='chip'>Models {s['model_count']}</span>"
             f"<span class='chip'>OCF {s['ocf_count']}</span>"
             f"<span class='chip'>Scored {sum(1 for m in a.get('models', []) if m.get('score') is not None)}</span>"
             f"<span class='chip'>Max {len(s['stack']['max']['rows'])}</span>"
             f"<span class='chip'>High {len(s['stack']['high']['rows'])}</span>"
             f"<span class='chip'>Medium {len(s['stack']['medium']['rows'])}</span>"
             f"<span class='chip'>F verified {fsc.get('verified', sum(1 for m in a.get('models', []) if free_status_of(m) == 'verified'))}</span>"
             f"<span class='chip'>F? prov {fsc.get('provisional-l1', 0) + fsc.get('provisional-l0', 0)}</span>"
             f"<span class='chip dim'>Routers {len(s['routers'])} excluded</span>")

    def sec(tid, title, body):
        return f"<section id='t-{tid}' class='tab'><h2>{esc(title)}</h2>{body}</section>"

    tabs = [("start", "Start here"), ("value", "Best value"),
            ("stack", "Stack"), ("compare", "Variants"),
            ("free", "Free"), ("graph", "Graph"), ("explore", "Explore")]
    nav = "".join(f"<button data-t='t-{tid}' onclick='showTab(this)'>{t}</button>" for tid, t in tabs)

    ov = f"<p>Snapshot <b>{esc(stamp)}</b> · thresholds {th['max']}/{th['high']}/{th['medium']} " \
         "· free models never enter ratios, ranked by score instead. " \
         "[F?] = provisional free (AA $0, billing unverified; exact level in JSON/XLSX). " \
         "Variants (max/xhigh/high/medium/…) are separate ranked rows from AA; " \
         "Select an available <code>provider/model#variant</code> in OpenCode V2 (OR efforts shown per row, *=default). " \
         "Inherited scores are estimates from a matched effort, not measurements of the destination route. External metrics retain their own scale. " \
         "L0 = AA $0 only, intel-only unless a native fallback ID is shown.</p>"
    # Start-here top picks: quality / value / free, all copy-ready.
    value_bands = build_value_bands(s["ocf_ratio"])
    top_quality = s["stack"]["max"]["rows"][0] if s["stack"]["max"]["rows"] else None
    top_value = value_bands[0]["winner"] if value_bands else None
    top_free = (s["ocf_free"] + s["ocf_provisional"][:1])[:1]
    top_free = top_free[0] if top_free else None

    def _pick_card(title, m, extra=""):
        if not m:
            return f"<div class='card'><h3>{esc(title)}</h3><p>— (gap)</p></div>"
        cp = copy_id(m)
        route = (f"<code class='copy' onclick=\"copyId(this)\" title='click to copy'>{esc(cp)}</code>"
                 if cp else "AA-only / no callable ID")
        return (f"<div class='card'><h3>{esc(title)}</h3>"
                f"<p><code>{esc(m['id'])}</code> ({esc(fmt_score(m))}, {esc(fmt_cost(m))})</p>"
                f"<p>Route: {route}</p>"
                + (f"<p class='note'>{extra}</p>" if extra else "") + "</div>")

    v_extra = ""
    if value_bands:
        b0 = value_bands[0]
        v_extra = (f"Band {b0['top']:.1f}–{b0['bottom']:.1f}: saves {b0['saving_pct']}% vs priciest in band.")
    ov += "<div class='cards'>"
    ov += _pick_card("Top quality", top_quality)
    ov += _pick_card("Best value", top_value, v_extra)
    ov += _pick_card("Top free", top_free, "Verified/provisional free, score-ranked.")
    ov += "</div>"
    ov += reliability_html(a)
    ov += "<div class='cards'>"
    for t in TIERS:
        rows = s["stack"][t]["rows"]
        top = rows[0] if rows else None
        gaps = f"<span class='gap'>gaps: {','.join(s['stack'][t]['gaps'])}</span>" if s["stack"][t]["gaps"] else ""
        ov += (f"<div class='card'><h3>{TIER_LABEL[t]}</h3>"
               f"<p class='bign'>{len(rows)} models {gaps}</p>" +
               (f"<p>Top: <code>{esc(top['id'])}</code> ({fmt_score(top)}, {fmt_cost(top)})</p>" if top else "<p>—</p>") +
               "</div>")
    ov += "</div><h3>Practical winners</h3><table><thead><tr><th>Tier</th><th>OCF</th><th>OF</th><th>CF</th><th>F-only</th></tr></thead><tbody>"
    for t in TIERS:
        cells = []
        for v in ("OCF", "OF", "CF", "F"):
            p = next(x for x in s["practical"] if x["tier"] == t and x["variant"] == v)
            if p["winner"]:
                wv = f" ({esc(p['winner'].get('variant', ''))})" if p["winner"].get("variant") else ""
                cells.append(f"<code>{esc(p['winner']['id'])}</code>{wv}")
            else:
                cells.append("<span class='gap'>gap</span>")
        ov += f"<tr><td>{TIER_LABEL[t]}</td><td>{cells[0]}</td><td>{cells[1]}</td><td>{cells[2]}</td><td>{cells[3]}</td></tr>"
    ov += "</tbody></table>"
    ov += ("<p class='note'>Full 9-section data (All/OCF Intel/Cost/Ratio, stack, practical, outliers) "
           "stays in MD/JSON/XLSX. HTML is the 7-page user view: Start here · Best value · Stack · Variants · Free · Graph · Explore.</p>")

    def prac_winner_cell(p):
        w = p["winner"]
        if not w:
            return "<span class=gap>gap</span>"
        vid = esc(w["id"])
        vv = w.get("variant", "") or ""
        vtag = " (" + esc(vv) + ")" if vv else ""
        sc = esc(fmt_score(w))
        rt = esc(w["ratio"] if w.get("ratio") is not None else "–")
        cp = esc(copy_id(w))
        return f"<code>{vid}</code>{vtag} {sc} / {rt} {cp}"

    def prac_runner_cell(p):
        u = p["runner_up"]
        if not u:
            return "–"
        return "<code>" + esc(u["id"]) + "</code>"

    # Best value bands: close score (±band), cheapest-first.
    value_html = ("<p>Paid OCF models grouped by score bands "
                  f"(width ±{VALUE_BAND}). Within each band cheapest-first; winner saves vs priciest in band. "
                  "Free never enters ratios — see Free page. "
                  "Note: AA $/1M is variant-blind within a family (same price across efforts); "
                  "true task cost falls with lower effort via fewer reasoning tokens.</p>")
    if not value_bands:
        value_html += "<p class='note'>No scored+costed paid OCF rows for banding.</p>"
    for b in value_bands:
        w = b["winner"]
        note = (f"Winner <code>{esc(w['id'])}</code> saves {b['saving_pct']}% vs priciest "
                f"(${esc(str(b['top_cost']))}/1M) in band." if w and b["saving_pct"] is not None else "")
        value_html += f"<h3>Score {b['top']:.1f}–{b['bottom']:.1f}</h3><p class='note'>{note}</p>" + html_table(b["rows"])

    stack_html = ("<p class='note'>AA $/1M is variant-blind within a family — same price across max/xhigh/high/medium/low; "
                  "Stack ranks max first on score, but lower effort is cheaper per-task via fewer reasoning tokens. "
                  "Check Variants family table before locking max.</p>")
    for t in TIERS:
        rows = s["stack"][t]["rows"]
        gaps = f" <span class='gap'>gaps: {','.join(s['stack'][t]['gaps'])}</span>" if s["stack"][t]["gaps"] else ""
        # Per-tier value note: cheapest within 1.5pts of tier top.
        vnote = ""
        if rows:
            top_score = rows[0].get("score")
            near = [m for m in rows if m.get("score") is not None and top_score - m["score"] <= VALUE_BAND
                    and m.get("cost_blended") not in (None, 0)]
            if near:
                cheap = min(near, key=lambda m: m["cost_blended"])
                pricey = max(near, key=lambda m: m["cost_blended"])
                if pricey["cost_blended"] and cheap["cost_blended"] is not None and pricey["cost_blended"] > cheap["cost_blended"]:
                    save = round((pricey["cost_blended"] - cheap["cost_blended"]) / pricey["cost_blended"] * 100, 1)
                    vnote = (f"<p class='note'>Value in tier: <code>{esc(cheap['id'])}</code> "
                             f"({cheap['score']}, ${cheap['cost_blended']}/1M) saves {save}% vs "
                             f"<code>{esc(pricey['id'])}</code> within {VALUE_BAND}pts of top.</p>")
        stack_html += f"<h3>{TIER_LABEL[t]}{gaps}</h3>" + vnote + html_table(rows)
    prac_rows = ""
    for p in s["practical"]:
        prac_rows += ("<tr><td>" + TIER_LABEL[p["tier"]] + "</td><td>" + p["variant"] + "</td>"
                      "<td>" + prac_winner_cell(p) + "</td>"
                      "<td>" + prac_runner_cell(p) + "</td></tr>")
    prac = ("<p>Winner + runner-up per tier × access variant. Copy the winner ID; AA-only rows never copy.</p>"
            "<table><thead><tr><th>Tier</th><th>Variant</th><th>Winner</th><th>Runner-up</th></tr></thead><tbody>" +
            prac_rows + "</tbody></table>")
    stack_html += "<h3>Practical picks</h3>" + prac

    # Variant compare: top-30 at 30+ in HTML for readability; full 42-family export in JSON/XLSX.
    fams = [f for f in s.get("family_variants", []) if (f.get("peak") or 0) >= TIER_FLOORS["medium"]][:30]
    compare_html = ("<p>Top multi-variant families at 30+ in HTML for readability; full per-family table uncapped in "
                    "JSON <code>family_variants</code> + XLSX <code>Family_Variants</code>. "
                    "AA-only rows (no callable ID) are intel-only — "
                    "use the callable sibling base with <code>provider/model#variant</code>. "
                    "Same data uncapped in JSON <code>family_variants</code> + XLSX <code>Family_Variants</code>.</p>")
    if not fams:
        compare_html += "<p class='note'>No multi-variant families at 30+.</p>"
    for f in fams:
        callable_ids = [m["id"] for m in f["rows"] if copy_id(m)]
        hint = ("Callable via: " + esc(", ".join(callable_ids[:3]))) if callable_ids else "No callable route in family."
        compare_html += f"<h3>{esc(f['family'])} (peak {f['peak']})</h3><p class='note'>{hint}</p>" + html_table(f["rows"])

    free_html = ("<p>Verified free ranked by score, then provisional [F?] (AA $0, billing unverified). "
                 "Check <span class='gap'>deprecated-upstream</span> / <span class='gap'>modality-unverified</span> before trusting.</p>"
                 "<h3>Verified free by score [F? no — verified only]</h3>" + html_table(s["ocf_free"]) +
                 "<h3>Provisional free [F?] by score</h3>" + html_table(s["ocf_provisional"]))
    if s["ocf_free_unscored"] or s["ocf_provisional_unscored"]:
        free_html += ("<p class='note'>Unscored free: verified "
                      + esc(", ".join(m["id"] for m in s["ocf_free_unscored"][:20])) +
                      " | provisional " + esc(", ".join(m["id"] for m in s["ocf_provisional_unscored"][:20])) + "</p>")

    explore_html = ("<p>All non-router models in one filterable table. Replaces the old All/OCF Intel/Cost/Ratio duplicates. "
                     "Full uncapped lists stay in JSON/XLSX.</p>" + explore_table(s["all_intel"]))

    graph_html = ("<p>Select up to 12 models or effort variants from this snapshot. The scatter plot shows "
                  "AA Intelligence Index score (right = higher) versus blended token price (down = cheaper). "
                  "$/1M is a price proxy, <b>not measured cost per task</b>; AA prices can be identical across "
                  "effort variants despite different reasoning-token use. Estimated scores are labelled; "
                  "[F?] is not verified free. Missing scores/prices stay in the selection list but cannot be plotted.</p>"
                  "<div class='g-controls'><label for='g-search'>Find models</label> "
                  "<input id='g-search' class='search' type='search' placeholder='Search ID, name or effort…' autocomplete='off'> "
                  "<label for='g-scale'>Price scale</label> <select id='g-scale'><option value='linear'>Linear</option>"
                  "<option value='compressed'>Compressed (log1p)</option></select> "
                  "<button id='g-clear' type='button'>Clear selection</button> "
                  "<span id='g-count' aria-live='polite'></span></div>"
                  "<p class='note'>Search all non-router models; results show the first 60 matches. "
                  "Each variant is selectable separately.</p>"
                  "<div id='g-results' class='g-results' aria-label='Model search results'></div>"
                  "<p id='g-message' class='note' role='status' aria-live='polite'></p>"
                  "<div class='g-chart'><svg id='g-plot' viewBox='0 0 840 460' role='img' "
                  "aria-label='Selected model score versus blended price, higher quality to the right, cheaper toward the bottom'></svg></div>"
                  "<div id='g-legend' class='g-legend'></div>"
                  "<div id='g-bars' class='g-bars'></div>"
                  "<h3>Selected models</h3><div id='g-details' class='twrap'></div>")

    body = (sec("start", "Start here", ov) +
            sec("value", "Best value — close score, big cost gap", value_html) +
            sec("stack", "Stack — tiered callable picks", stack_html) +
            sec("compare", "Variants — family compare", compare_html) +
            sec("free", "Free — verified + provisional [F?]", free_html) +
            sec("graph", "Graph — compare selected models", graph_html) +
            sec("explore", "Explore — all models", explore_html))

    # Inline the script so the dated HTML works offline (including file:// URLs).
    with open(os.path.join(ROOT, "reports", "graph.js"), encoding="utf-8") as f:
        graph_script = f.read()
    graph_rows = json.dumps(graph_data(s["all_intel"]), ensure_ascii=True, separators=(",", ":"))
    graph_rows = graph_rows.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ModelAnalysis — {esc(stamp)}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#020617;color:#e2e8f0;margin:0;padding:24px;max-width:1200px}}
h1{{font-size:24px}}h2{{color:#7dd3fc}}h3{{color:#bae6fd}}
.chip{{display:inline-block;background:#082f49;border:1px solid #38bdf8;border-radius:12px;padding:3px 12px;margin:2px;font-size:13px}}
.dim{{opacity:.6}}nav{{position:sticky;top:0;background:#020617;padding:10px 0;z-index:5}}
nav button{{background:#1e293b;color:#e2e8f0;border:1px solid #38bdf8;border-radius:8px;padding:6px 12px;margin:2px;cursor:pointer}}
nav button.on{{background:#0369a1}}.tab{{display:none}}.tab.on{{display:block}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #334155;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#0f172a}}tr:nth-child(even){{background:#0b1220}}code{{color:#7dd3fc}}
.copy{{cursor:pointer;border-bottom:1px dotted #38bdf8}}.nm{{color:#94a3b8;font-size:12px}}
.gap{{color:#fbbf24;font-weight:700}}.note{{color:#94a3b8}}.hint{{font-weight:400;font-size:11px;color:#94a3b8}}
.search{{width:280px;padding:6px 10px;margin:8px 0;background:#0f172a;color:#e2e8f0;border:1px solid #38bdf8;border-radius:8px}}
.filters select{{padding:6px 10px;margin:8px 4px;background:#0f172a;color:#e2e8f0;border:1px solid #38bdf8;border-radius:8px}}
.twrap{{overflow-x:auto}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card{{background:#0f172a;border:1px solid #38bdf8;border-radius:10px;padding:12px 16px;min-width:200px}}
.bign{{font-size:15px}}
.g-controls button,.g-controls select,.g-results button,.g-details button{{background:#1e293b;color:#e2e8f0;border:1px solid #38bdf8;border-radius:7px;padding:6px 10px;cursor:pointer}}
.g-controls label{{font-weight:600}}.g-results{{display:flex;gap:6px;flex-wrap:wrap;max-height:210px;overflow-y:auto;padding:8px;background:#0f172a;border:1px solid #334155;border-radius:8px}}
.g-results button{{text-align:left;max-width:100%}}.g-results button[aria-pressed='true']{{background:#0369a1}}.g-results button:disabled{{opacity:.5;cursor:not-allowed}}
.g-chart{{max-width:100%;overflow-x:auto}}#g-plot{{display:block;width:100%;min-width:480px;background:#0f172a;border:1px solid #334155;border-radius:8px}}
.g-legend{{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}}.g-legend span{{padding:3px 8px;border:1px solid #334155;border-radius:6px}}
.g-bars{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,350px),1fr));gap:12px}}.g-bars>div{{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px}}
.g-bar-row{{display:grid;grid-template-columns: minmax(100px,1fr) 2fr auto;align-items:center;gap:6px;margin:6px 0;font-size:12px}}
.g-bar-track{{height:12px;background:#1e293b;border-radius:6px}}.g-bar-fill{{height:12px;border-radius:6px}}
.g-details button{{margin-right:5px}}#g-message{{min-height:1.5em}}
@media(max-width:600px){{body{{padding:12px}}.g-bar-row{{grid-template-columns:1fr 2fr auto}}}}
</style></head><body>
<h1>ModelAnalysis — {esc(stamp)}</h1>
<div>{chips}</div><nav>{nav}</nav>{body}
<script>
function showTab(b){{document.querySelectorAll('nav button').forEach(x=>x.classList.remove('on'));
document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
b.classList.add('on');document.getElementById(b.dataset.t).classList.add('on');}}
function filterRows(inp){{const q=inp.value.toLowerCase();
inp.parentElement.querySelectorAll('tbody tr').forEach(tr=>{{
tr.style.display=tr.textContent.toLowerCase().includes(q)?'':'none';}});}}
function filterExplore(){{const q=(document.getElementById('xq').value||'').toLowerCase();
const g=document.getElementById('xgrp').value;const c=document.getElementById('xcost').value;const f=document.getElementById('xfree').value;
document.querySelectorAll('#xtab tbody tr').forEach(tr=>{{
let ok=tr.textContent.toLowerCase().includes(q);
if(g){{const gg=tr.getAttribute('data-groups')||'';if(g==='F?'){{ok=ok&&gg.includes('F?');}}else if(g==='F'){{ok=ok&&gg.includes('F')&&!gg.includes('F?');}}else{{ok=ok&&gg.includes(g);}}}}
if(c){{ok=ok&&(tr.getAttribute('data-cost')||'')===c;}}
if(f){{ok=ok&&(tr.getAttribute('data-free')||'')===f;}}
tr.style.display=ok?'':'none';}});}}
function copyId(el){{navigator.clipboard.writeText(el.textContent).then(()=>{{
el.style.color='#4ade80';setTimeout(()=>el.style.color='',800);}});}}
document.querySelector('nav button').classList.add('on');
document.querySelector('.tab').classList.add('on');
</script><script>const graphModels = {graph_rows};
{graph_script}
</script></body></html>"""


def main(input_path=None, output_dir=None):
    """Write required report artifacts; retention belongs to the coordinator."""
    if input_path is None or output_dir is None:
        raise ValueError("input_path and output_dir are required")
    rep = os.fspath(output_dir)
    with open(input_path, encoding="utf-8") as f:
        a = json.load(f)
    from pipeline_common import validate_run_id
    stamp = validate_run_id(a.get("stamp"))
    if "run_id" in a:
        validate_run_id(a["run_id"])
    os.makedirs(rep, exist_ok=True)
    th = a.get("thresholds", {"max": 50, "high": 40, "medium": 30})
    s = build_sections(a)

    L = [f"# ModelAnalysis — {stamp} (on-use)\n",
         f"Models {s['model_count']} | OCF {s['ocf_count']} | "
         f"Scored {sum(1 for m in a.get('models', []) if m.get('score') is not None)} | "
         f"Costed {sum(1 for m in a.get('models', []) if m.get('cost_blended') is not None)} | "
         f"Tiers Max {len(s['stack']['max']['rows'])} / High {len(s['stack']['high']['rows'])} / "
         f"Medium {len(s['stack']['medium']['rows'])} | "
         f"Thresholds {th['max']}/{th['high']}/{th['medium']} | <30 excluded from stack only | "
         f"F verified {sum(1 for m in a.get('models', []) if free_status_of(m) == 'verified')} | "
         f"F? provisional L1/L0 "
         f"{sum(1 for m in a.get('models', []) if free_status_of(m) == 'provisional-l1')}/"
         f"{sum(1 for m in a.get('models', []) if free_status_of(m) == 'provisional-l0')} | "
         f"Routers {len(s['routers'])} excluded"
         + (f" | Identity conflicts {len(a['identity_conflicts'])} (XLSX Identity sheet, site Confidence page)"
            if "identity_conflicts" in a else "") + "\n",
         "\n## 1. All Data — Intelligence\n"]
    L += [row_md(m) for m in s["all_intel"][:MD_CAP]]
    if len(s["all_intel"]) > MD_CAP:
        L.append(f"_…and {len(s['all_intel']) - MD_CAP} more (see XLSX/JSON)_\n")
    L += ["\n## 2. All Data — Cost\n"]
    L += [row_md(m) for m in s["costed"][:MD_CAP]]
    if s["uncosted"]:
        L.append(f"\n_cost-unknown ({len(s['uncosted'])}), e.g: " +
                 ", ".join(f"`{m['id']}`" for m in s["uncosted"][:MD_CAP]) + "_\n")
    L += ["\n## 3. All Data — Intelligence/Cost Ratio (paid; verified-free by score; provisional [F?] by score)\n"]
    L += [row_md(m) for m in s["paid_ratio"][:MD_CAP]]
    L += ["\n_Verified free by score_\n"]
    L += [row_md(m) for m in s["free_block"][:MD_CAP]]
    L += ["\n_Provisional free [F?] by score (AA $0, billing unverified)_\n"]
    L += [row_md(m) for m in s["provisional_block"][:MD_CAP]]
    if s["free_unscored"] or s["provisional_unscored"]:
        L.append(f"_Free unscored verified ({len(s['free_unscored'])})"
                 + (", ".join(f"`{m['id']}`" for m in s["free_unscored"][:MD_CAP]) if s["free_unscored"] else "—") +
                 f" | provisional unscored ({len(s['provisional_unscored'])})_\n")
    L += ["\n## 4. OCF — Intelligence\n"]
    L += [row_md(m) for m in s["ocf_intel"][:MD_CAP]]
    L += ["\n## 5. OCF — Cost\n"]
    L += [row_md(m) for m in s["ocf_costed"][:MD_CAP]]
    if s["ocf_uncosted"]:
        L.append(f"\n_cost-unknown ({len(s['ocf_uncosted'])})_\n")
    L += ["\n## 6. OCF — Intelligence/Cost Ratio\n"]
    L += [row_md(m) for m in s["ocf_ratio"][:MD_CAP]]
    L += ["\n_Verified free by score_\n"]
    L += [row_md(m) for m in s["ocf_free"][:MD_CAP]]
    L += ["\n_Provisional free [F?] by score_\n"]
    L += [row_md(m) for m in s["ocf_provisional"][:MD_CAP]]
    L += ["\n## 7. OCF — Optimized stack\n"]
    for t in TIERS:
        gaps = f" — gaps: {','.join(s['stack'][t]['gaps'])}" if s["stack"][t]["gaps"] else ""
        L.append(f"\n### {TIER_LABEL[t]}{gaps}\n")
        L += [row_md(m) for m in s["stack"][t]["rows"][:MD_CAP]]
    L += ["\n## 8. OCF — Practical picks (winner + runner-up per tier × variant)\n",
          "| Tier | Variant | Winner | Runner-up |\n|---|---|---|---|\n"]
    for p in s["practical"]:
        if p["winner"]:
            wv = f" ({p['winner'].get('variant', '')})" if p["winner"].get("variant") else ""
            w = f"`{p['winner']['id']}`{wv} ({fmt_score(p['winner'])}/{p['winner']['ratio']}) → `{copy_id(p['winner'])}`"
        else:
            w = "— (gap)"
        u = f"`{p['runner_up']['id']}`" if p["runner_up"] else "—"
        L.append(f"| {TIER_LABEL[p['tier']]} | {p['variant']} | {w} | {u} |\n")
    L += ["\n## 9. OCF — Outliers\n"]
    for cls, title in [("bargains", "Bargains (top-quartile score, bottom-quartile cost)"),
                       ("overpriced", "Overpriced (bottom-quartile score, top-quartile cost)"),
                       ("free_gems", "Free gems (verified/provisional free, score 40+)")]:
        L.append(f"\n### {title}\n")
        L += [row_md(m) for m in s["outliers"][cls][:MD_CAP]] or ["_(none)_\n"]
    L.append("\n_Free excluded from ratio (infinite); ratios use " +
             f"{a.get('cost_method', 'blended $/1M')}. OCF = OpenAI + Claude + strict-free + provisional [F?] " +
             "(AA $0, billing unverified; AA-only variant rows included in Intel/Cost/Ratio via creator mapping, " +
             "stack/practical need a callable or_id/native ID; tier filled only by provisional still flags gap F(verified)). " +
             "Variants are separate AA rows; OpenCode V2 uses available provider/model#variant selectors. Inherited scores are estimates, not destination measurements. " +
             "L0 = AA $0 only, intel-only unless a native fallback ID is shown (e.g. zen). Zen *-free routes count as verified free. " +
             "Per-model OpenCode compat not verified._\n")
    L.append("\n_Provenance legend: every score is the AA Intelligence Index (`aa-index`), from the AA API "
             "(measured) or `research.json` (external reference / inherited estimate); every price is USD per 1M tokens, "
             "3:1 blend, from the tagged source (`aa`, `or-derived` = OpenRouter, `inherited` = registry). Each value's "
             "source, version, observation time and `obs_id` are in the XLSX `*_provenance` columns, the dashboard/site "
             "cell tooltips, and the analysis JSON `observations`. Evidence labels: "
             + ", ".join(f"{k} = {v}" for k, v in EVIDENCE.items()) + "._\n")
    L.insert(2, reliability_markdown(a))
    for key, value in reliability_data(a).items():
        L.append(f"\n## {key}\n\n```json\n{json.dumps(value, ensure_ascii=False, indent=2)}\n```\n")
    with open(os.path.join(rep, f"{stamp}_summary.md"), "w", encoding="utf-8") as f:
        f.write("".join(L))

    slim = lambda m: [m["id"], groups_display(m), m["score"], provenance_text(m, "score"),
                      m["cost_blended"], provenance_text(m, "price"),
                      m.get("cost_source", ""), m["ratio"], copy_id(m), ",".join(m["providers"]),
                      free_status_of(m), m.get("variant", ""), bool(m.get("variant_ambiguous", False)),
                      m.get("variant_label", ""),
                      "/".join(m.get("efforts") or []), m.get("default_effort", ""),
                      m.get("default_effort_source", ""), m.get("efforts_source", ""),
                      "/".join(m.get("efforts_hint") or []), m.get("efforts_hint_source", ""),
                      m.get("or_reasoning_status", ""),
                      m.get("fallback_id", ""), m.get("fallback_provider", ""),
                      m.get("nearest_callable", ""),
                      bool(m.get("deprecated_upstream", False)), ",".join(m.get("deprecated_sources", []) or []),
                      m.get("modality_status", ""),
                      score_evidence(m)[0], ' '.join(score_evidence(m)[1]),
                      json.dumps(m.get('external_scores', []), ensure_ascii=False)]
    scored = sorted(m["score"] for m in a.get("models", []) if m.get("score") is not None)
    dist = {"scored": len(scored)}
    if scored:
        dist.update({"p10": round(pct(scored, 0.10), 2), "p50": round(pct(scored, 0.50), 2),
                     "p90": round(pct(scored, 0.90), 2), "max": max(scored)})
    full = {"stamp": stamp, "day": a.get("day", stamp[:10]), "thresholds": th,
            "cost_method": a.get("cost_method", ""), "quartiles": s["quartiles"],
            "score_dist": dist, "routers_excluded": s["routers"],
            "identity_conflicts": a.get("identity_conflicts", []),
            "free_status_counts": a.get("free_status_counts", {}),
            "models_by_slug": {m["slug"]: m for m in s["all_intel"]},
            "all_intel": [m["slug"] for m in s["all_intel"]],
            "all_cost": [m["slug"] for m in s["costed"]],
            "all_cost_unknown": [m["slug"] for m in s["uncosted"]],
            "all_ratio_paid": [m["slug"] for m in s["paid_ratio"]],
            "all_ratio_free_by_score": [m["slug"] for m in s["free_block"]],
            "all_ratio_verified_free_by_score": [m["slug"] for m in s["free_block"]],
            "all_ratio_provisional_free_by_score": [m["slug"] for m in s["provisional_block"]],
            "all_ratio_unratable": [m["slug"] for m in s["unratable"] + s["free_unscored"] + s["provisional_unscored"]],
            "ocf_intel": [m["slug"] for m in s["ocf_intel"]],
            "ocf_cost": [m["slug"] for m in s["ocf_costed"]],
            "ocf_cost_unknown": [m["slug"] for m in s["ocf_uncosted"]],
            "ocf_ratio_paid": [m["slug"] for m in s["ocf_ratio"]],
            "ocf_ratio_free_by_score": [m["slug"] for m in s["ocf_free"]],
            "ocf_ratio_verified_free_by_score": [m["slug"] for m in s["ocf_free"]],
            "ocf_ratio_provisional_free_by_score": [m["slug"] for m in s["ocf_provisional"]],
            "ocf_stack": {t: {"rows": [m["slug"] for m in s["stack"][t]["rows"]], "gaps": s["stack"][t]["gaps"]} for t in TIERS},
            "ocf_practical": [{"tier": p["tier"], "variant": p["variant"],
                               "winner": p["winner"]["slug"] if p["winner"] else None,
                               "runner_up": p["runner_up"]["slug"] if p["runner_up"] else None}
                              for p in s["practical"]],
            "ocf_outliers": {k: [m["slug"] for m in v] for k, v in s["outliers"].items()},
            "family_variants": [{"family": f["family"], "peak": f["peak"], "rows": [m["slug"] for m in f["rows"]]} for f in s.get("family_variants", [])]}
    full.update(reliability_data(a))
    with open(os.path.join(rep, f"{stamp}_models.json"), "w", encoding="utf-8") as f:
        json.dump(full, f, indent=1)

    def write_workbook():
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "summary"
        ws.append(["stamp", stamp])
        for key in ("run_id", "schema_version", "started_at"):
            if key in a:
                ws.append([key, json.dumps(a[key], ensure_ascii=False)])
        ws.append(["models", s["model_count"]])
        ws.append(["ocf", s["ocf_count"]])
        fsc = a.get("free_status_counts", {})
        ws.append(["free_verified", fsc.get("verified", "")])
        ws.append(["provisional_l1", fsc.get("provisional-l1", "")])
        ws.append(["provisional_l0", fsc.get("provisional-l0", "")])
        ws.append(["total_modelsdev", a.get("total_modelsdev", "")])
        for t in TIERS:
            ws.append([f"stack_{t}", len(s["stack"][t]["rows"])])
            ws.append([f"gaps_{t}", ",".join(s["stack"][t]["gaps"])])
        H = ["id", "groups", "score", "score_provenance", "cost_per_1M", "cost_provenance", "cost_source", "ratio", "opencode_id", "providers", "free_status",
             "variant", "variant_ambiguous", "variant_label", "efforts", "default_effort", "default_effort_source",
             "efforts_source", "efforts_hint", "efforts_hint_source", "or_reasoning_status",
             "fallback_id", "fallback_provider", "nearest_callable",
             "deprecated_upstream", "deprecated_sources", "modality_status",
             "score_source", "score_urls", "external_scores"]
        tabs = {"All_Intel": s["all_intel"], "All_Cost": s["costed"] + s["uncosted"],
                "All_Ratio": s["paid_ratio"] + s["free_block"] + s["provisional_block"] + s["unratable"] + s["free_unscored"] + s["provisional_unscored"],
                "OCF_Intel": s["ocf_intel"], "OCF_Cost": s["ocf_costed"] + s["ocf_uncosted"],
                "OCF_Ratio": s["ocf_ratio"] + s["ocf_free"] + s["ocf_provisional"] + s["ocf_unratable"] + s["ocf_free_unscored"] + s["ocf_provisional_unscored"],
                "OCF_Outliers": s["outliers"]["bargains"] + s["outliers"]["overpriced"] + s["outliers"]["free_gems"]}
        for name, rows in tabs.items():
            w = wb.create_sheet(name); w.append(H)
            for m in rows:
                w.append(slim(m))
        w = wb.create_sheet("OCF_Stack"); w.append(["tier"] + H + ["gap"])
        for t in TIERS:
            for m in s["stack"][t]["rows"]:
                w.append([t] + slim(m) + [""])
            for g in s["stack"][t]["gaps"]:
                w.append([t, f"GAP:{g}"] + [''] * (len(H) - 1) + ['gap'])
        w = wb.create_sheet("OCF_Practical")
        w.append(["tier", "variant", "winner", "winner_variant", "winner_score", "winner_ratio", "winner_copy_id", "runner_up"])
        for p in s["practical"]:
            w.append([p["tier"], p["variant"],
                      p["winner"]["id"] if p["winner"] else "GAP",
                      (p["winner"].get("variant", "") if p["winner"] else ""),
                      p["winner"]["score"] if p["winner"] else None,
                      p["winner"]["ratio"] if p["winner"] else None,
                      (copy_id(p["winner"]) if p["winner"] else ""),
                      p["runner_up"]["id"] if p["runner_up"] else None])
        w = wb.create_sheet("Family_Variants"); w.append(["family", "peak"] + H)
        for f in s.get("family_variants", []):
            for m in f["rows"]:
                w.append([f["family"], f["peak"]] + slim(m))
        vws = a.get("views", {}) or {}
        _pby = {p.get("slug"): p for p in (vws.get("pricing", []) or [])}
        w = wb.create_sheet("BenchLM_Matrix")
        w.append(["id", "slug", "creator", "overall", "evidence", "agentic", "coding",
                  "reasoning", "knowledge", "in_price", "out_price"])
        for r in vws.get("benchlm_leaderboard", []):
            cats = r.get("categories", {}) or {}
            _pp = _pby.get(r.get("slug"), {}) or {}
            w.append([r.get("model"), r.get("slug"), r.get("creator"), r.get("overall"),
                      r.get("evidence"), cats.get("agentic"), cats.get("coding"),
                      cats.get("reasoning"), cats.get("knowledge"),
                      _pp.get("benchlm_in"), _pp.get("benchlm_out")])
        w = wb.create_sheet("LLMStats_Matrix")
        w.append(["id", "slug", "rank_general", "rating_general", "evals_general",
                  "rank_reasoning", "rating_reasoning", "rank_code", "rating_code",
                  "rank_agents", "rating_agents", "url"])
        _lrank = {}
        for m in s["all_intel"]:
            rk = m.get("llmstats_rank") or {}
            if rk:
                _lrank[m["slug"]] = (m.get("id", ""), rk)
        for slug, (mid, rk) in _lrank.items():
            g = rk.get("general", {}) or {}
            h = rk.get("reasoning", {}) or {}
            c = rk.get("code", {}) or {}
            t = rk.get("agents", {}) or {}
            w.append([mid, slug, g.get("rank"), g.get("rating"), g.get("evals"),
                      h.get("rank"), h.get("rating"), c.get("rank"), c.get("rating"),
                      t.get("rank"), t.get("rating"), g.get("url", "")])
        if any(key in a for key in ("schema_version", "source_health", "website_health", "churn")):
            for title, key in (("Source_Health", "source_health"), ("Churn", "churn")):
                w = wb.create_sheet(title)
                w.append(["path", "value_json"])
                if key in a:
                    for row in metadata_rows(a[key]):
                        w.append(row)
                if key == "source_health" and "website_health" in a:
                    for row in metadata_rows(a["website_health"], "website_health"):
                        w.append(row)
        if "identity_conflicts" in a:
            w = wb.create_sheet("Identity")
            w.append(IDENTITY_HEADERS)
            for row in identity_rows(a):
                w.append(row)
        wb.save(os.path.join(rep, f"{stamp}_models.xlsx"))
    write_workbook()
    with open(os.path.join(rep, f"{stamp}_report.html"), "w", encoding="utf-8") as f:
        f.write(build_html(a, s, stamp))
    print(f"report {stamp} written (xlsx ok + html)")


if __name__ == "__main__":
    from pipeline_common import stage_cli
    stage_cli(main, __doc__)
