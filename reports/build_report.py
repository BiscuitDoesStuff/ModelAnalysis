"""3. Report — 9-section OCF views for MD/XLSX/JSON + 6-page HTML dashboard. On-use. Keeps latest only."""
import json, os, glob, html as _html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REP = os.path.join(ROOT, "reports")
os.makedirs(REP, exist_ok=True)

MD_CAP = 20
TIERS = ["max", "high", "medium"]
TIER_LABEL = {"max": "Max (50+)", "high": "High (40+)", "medium": "Medium/General (30+)"}
VARIANTS = {"OCF": set(), "OF": {"C"}, "CF": {"O"}, "F": {"O", "C"}}
OCF = {"O", "C", "F"}
VALUE_BAND = 1.5
EFFORT_TOKENS = ["max", "xhigh", "high", "medium", "low", "minimal", "none"]


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
    return str(fb) if fb and m.get('fallback_provider') not in ('', 'aa') else ""


def score_evidence(m):
    source = m.get('score_source') or {}
    text = source.get('kind', 'unscored')
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
    return bool(provs & {"openai", "anthropic", "openrouter", "groq", "cerebras",
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


def prune_reports(keep_stamps):
    pats = ["*_summary.md", "*_models.json", "*_models.xlsx", "*_report.html", "*_churn_alert.md"]
    files = []
    for p in pats:
        files += glob.glob(os.path.join(REP, p))
    for f in files:
        bn = os.path.basename(f)
        if not any(bn.startswith(s) for s in keep_stamps):
            os.remove(f)
            print(f"pruned report {os.path.basename(f)}")


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
                             and (m.get("score") or 0) >= 40 and has_callable(m)]

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
                 "</td><td>" + esc(groups_display(m)) + "</td><td>" + esc(fmt_score(m)) +
                 "</td><td>" + cost_cell + "</td><td>" +
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
                 "<td><code>" + esc(m["id"]) + "</code></td><td>" + esc(groups_display(m)) + "</td><td>" + esc(fmt_score(m)) +
                 "</td><td>" + cost_cell + "</td><td>" + esc(m["ratio"] if m.get("ratio") is not None else "–") + "</td><td>" +
                 var_cell + "</td><td>" + esc(efforts_display(m) or "–") + "</td><td>" + route_cell +
                 "</td><td>" + esc(",".join(m.get("providers", []))) + "</td><td>" + evidence_html(m) + "</td></tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


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
            ("free", "Free"), ("explore", "Explore")]
    nav = "".join(f"<button data-t='t-{tid}' onclick='showTab(this)'>{t}</button>" for tid, t in tabs)

    ov = f"<p>Snapshot <b>{esc(stamp)}</b> · thresholds {th['max']}/{th['high']}/{th['medium']} " \
         "· free models never enter ratios, ranked by score instead. " \
         "[F?] = provisional free (AA $0, billing unverified; exact level in JSON/XLSX). " \
         "Variants (max/xhigh/high/medium/…) are separate ranked rows from AA; " \
         "Select an available <code>provider/model#variant</code> in OpenCode V2 (OR efforts shown per row, *=default). " \
         "Inherited scores are estimates from a matched effort, not measurements of the destination route. External metrics retain their own scale. " \
         "L0 = AA $0 only, intel-only unless a native fallback ID is shown.</p>"
    ch = a.get("free_churn")
    if ch and ch.get("prev_day"):
        ov += (f"<p class='note'>Free-status churn vs {esc(ch['prev_day'])}: "
               f"→paid {ch.get('flipped_to_paid_total', 0)} · →free {ch.get('flipped_to_free_total', 0)} · "
               f"level-changed {ch.get('level_changed_total', 0)} · disappeared {ch.get('disappeared_total', 0)} · "
               f"new {ch.get('new_total', 0)}.</p>")
    # Start-here top picks: quality / value / free, all copy-ready.
    value_bands = build_value_bands(s["ocf_ratio"])
    top_quality = s["stack"]["max"]["rows"][0] if s["stack"]["max"]["rows"] else None
    top_value = value_bands[0]["winner"] if value_bands else None
    top_free = (s["ocf_free"] + s["ocf_provisional"][:1])[:1]
    top_free = top_free[0] if top_free else None

    def _pick_card(title, m, extra=""):
        if not m:
            return f"<div class='card'><h3>{esc(title)}</h3><p>— (gap)</p></div>"
        cp = esc(copy_id(m) or "AA-only / no callable ID")
        return (f"<div class='card'><h3>{esc(title)}</h3>"
                f"<p><code>{esc(m['id'])}</code> ({esc(fmt_score(m))}, {esc(fmt_cost(m))})</p>"
                f"<p>Copy: <code class='copy' onclick=\"copyId(this)\" title='click to copy'>{cp}</code></p>"
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
           "stays in MD/JSON/XLSX. HTML is the 6-page user view: Start here · Best value · Stack · Variants · Free · Explore.</p>")

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
    fams = [f for f in s.get("family_variants", []) if (f.get("peak") or 0) >= 30.0][:30]
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

    body = (sec("start", "Start here", ov) +
            sec("value", "Best value — close score, big cost gap", value_html) +
            sec("stack", "Stack — tiered callable picks", stack_html) +
            sec("compare", "Variants — family compare", compare_html) +
            sec("free", "Free — verified + provisional [F?]", free_html) +
            sec("explore", "Explore — all models", explore_html))

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
</script></body></html>"""


def main():
    afiles = sorted(glob.glob(os.path.join(ROOT, "analysis", "*_analysis.json")), key=os.path.getmtime)
    if not afiles:
        print("run analysis first")
        return
    with open(afiles[-1], encoding="utf-8") as f:
        a = json.load(f)
    stamp = a.get("stamp", a.get("day", "unknown"))
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
         f"Routers {len(s['routers'])} excluded\n",
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
    ch = a.get("free_churn")
    if ch and ch.get("prev_day"):
        L.append(f"\n_Churn vs {ch['prev_day']}: →paid {ch.get('flipped_to_paid_total', 0)} " +
                 (", ".join(f"`{i}`" for i in ch.get('flipped_to_paid', [])[:MD_CAP]) if ch.get('flipped_to_paid') else "—") +
                 f" · →free {ch.get('flipped_to_free_total', 0)}" +
                 (", ".join(f"`{i}`" for i in ch.get('flipped_to_free', [])[:MD_CAP]) if ch.get('flipped_to_free') else "") +
                 f" · disappeared {ch.get('disappeared_total', 0)} · new {ch.get('new_total', 0)}._\n")
    with open(os.path.join(REP, f"{stamp}_summary.md"), "w", encoding="utf-8") as f:
        f.write("".join(L))

    slim = lambda m: [m["id"], groups_display(m), m["score"], m["cost_blended"],
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
            "collisions": a.get("collisions", []),
            "free_status_counts": a.get("free_status_counts", {}),
            "free_churn": a.get("free_churn", {}),
            "all_intel": s["all_intel"], "all_cost": s["costed"], "all_cost_unknown": s["uncosted"],
            "all_ratio_paid": s["paid_ratio"], "all_ratio_free_by_score": s["free_block"],
            "all_ratio_verified_free_by_score": s["free_block"],
            "all_ratio_provisional_free_by_score": s["provisional_block"],
            "all_ratio_unratable": s["unratable"] + s["free_unscored"] + s["provisional_unscored"],
            "ocf_intel": s["ocf_intel"], "ocf_cost": s["ocf_costed"],
            "ocf_cost_unknown": s["ocf_uncosted"], "ocf_ratio_paid": s["ocf_ratio"],
            "ocf_ratio_free_by_score": s["ocf_free"],
            "ocf_ratio_verified_free_by_score": s["ocf_free"],
            "ocf_ratio_provisional_free_by_score": s["ocf_provisional"],
            "ocf_stack": {t: {"rows": s["stack"][t]["rows"], "gaps": s["stack"][t]["gaps"]} for t in TIERS},
            "ocf_practical": s["practical"], "ocf_outliers": s["outliers"],
            "family_variants": s.get("family_variants", [])}
    with open(os.path.join(REP, f"{stamp}_models.json"), "w", encoding="utf-8") as f:
        json.dump(full, f, indent=1)

    try:
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "summary"
        ws.append(["stamp", stamp])
        ws.append(["models", s["model_count"]])
        ws.append(["ocf", s["ocf_count"]])
        fsc = a.get("free_status_counts", {})
        ws.append(["free_verified", fsc.get("verified", "")])
        ws.append(["provisional_l1", fsc.get("provisional-l1", "")])
        ws.append(["provisional_l0", fsc.get("provisional-l0", "")])
        ws.append(["total_groq", a.get("total_groq", "")])
        ws.append(["total_cerebras", a.get("total_cerebras", "")])
        ws.append(["total_modelsdev", a.get("total_modelsdev", "")])
        ch = a.get("free_churn", {})
        if ch and ch.get("prev_day"):
            ws.append(["churn_vs", ch.get("prev_day", "")])
            ws.append(["churn_to_paid", ch.get("flipped_to_paid_total", 0)])
            ws.append(["churn_to_free", ch.get("flipped_to_free_total", 0)])
            ws.append(["churn_disappeared", ch.get("disappeared_total", 0)])
            ws.append(["churn_new", ch.get("new_total", 0)])
        for t in TIERS:
            ws.append([f"stack_{t}", len(s["stack"][t]["rows"])])
            ws.append([f"gaps_{t}", ",".join(s["stack"][t]["gaps"])])
        H = ["id", "groups", "score", "cost_per_1M", "cost_source", "ratio", "opencode_id", "providers", "free_status",
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
        wb.save(os.path.join(REP, f"{stamp}_models.xlsx"))
        x = "xlsx ok"
    except Exception as e:
        x = f"xlsx skipped: {e}"
    with open(os.path.join(REP, f"{stamp}_report.html"), "w", encoding="utf-8") as f:
        f.write(build_html(a, s, stamp))
    prune_reports([os.path.basename(f).replace("_analysis.json", "") for f in afiles[-1:]])
    print(f"report {stamp} written ({x} + html)")


if __name__ == "__main__":
    main()
