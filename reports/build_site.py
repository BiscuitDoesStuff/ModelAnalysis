"""3b. Site report — browsable static site like BenchLM / LLM Stats / Vals.

Reads an explicit analysis artifact and matching report, writing <stamp>_site/
with index, model pages, benchmarks, compare, methodology, confidence + data.json.
Offline; retention belongs to the coordinator.
"""
import json
import os
import html as _html
from urllib.parse import quote

if __package__:
    from .build_report import copy_id, reliability_data, reliability_html, source_summary
else:
    from build_report import copy_id, reliability_data, reliability_html, source_summary

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def esc(v):
    return _html.escape("" if v is None else str(v))


def copy_control(m):
    route = copy_id(m)
    return (f"<code class='copy' onclick='cp(this)'>{esc(route)}</code>"
            if route else "<span class='note'>no callable ID</span>")


def model_filename(slug):
    # Encode path separators as literal filename bytes; links encode the '%' again.
    return quote(str(slug), safe="") + ".html"


CSS = ("body{font-family:Segoe UI,Arial,sans-serif;background:#020617;color:#e2e8f0;margin:0;padding:24px;max-width:1200px}"
       "h1{font-size:24px}h2{color:#7dd3fc}h3{color:#bae6fd}a{color:#7dd3fc}"
       "nav.top{position:sticky;top:0;background:#020617;padding:10px 0;z-index:5;border-bottom:1px solid #334155}"
       "nav.top a{margin-right:14px;text-decoration:none}"
       ".chip{display:inline-block;background:#082f49;border:1px solid #38bdf8;border-radius:12px;padding:3px 12px;margin:2px;font-size:13px}"
       ".dim{opacity:.6}table{border-collapse:collapse;width:100%;font-size:13px}"
       "th,td{border:1px solid #334155;padding:6px 8px;text-align:left;vertical-align:top}th{background:#0f172a}"
       "tr:nth-child(even){background:#0b1220}code{color:#7dd3fc}.copy{cursor:pointer;border-bottom:1px dotted #38bdf8}"
       ".gap{color:#fbbf24;font-weight:700}.note{color:#94a3b8}.hint{font-weight:400;font-size:11px;color:#94a3b8}"
       ".search{width:280px;padding:6px 10px;margin:8px 0;background:#0f172a;color:#e2e8f0;border:1px solid #38bdf8;border-radius:8px}"
       ".twrap{overflow-x:auto}.cards{display:flex;gap:12px;flex-wrap:wrap}.card{background:#0f172a;border:1px solid #38bdf8;border-radius:10px;padding:12px 16px;min-width:220px}"
       ".tabs button{background:#1e293b;color:#e2e8f0;border:1px solid #38bdf8;border-radius:8px;padding:6px 12px;margin:2px;cursor:pointer}"
       ".tabs button.on{background:#0369a1}.ltab{display:none}.ltab.on{display:block}.btab{display:none}.btab.on{display:block}")


def page(title, stamp, nav, body):
    return (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{esc(title)} — {esc(stamp)}</title><style>{CSS}</style></head><body>"
            f"<nav class='top'>{nav}</nav><h1>{esc(title)}</h1>{body}"
            f"<script>function f(q,id){{const v=q.value.toLowerCase();"
            f"document.querySelectorAll('#'+id+' tbody tr').forEach(tr=>{{tr.style.display=tr.textContent.toLowerCase().includes(v)?'':'none';}});}}"
            f"function lt(b,n){{const tabs=b.parentElement;const group=tabs.parentElement;"
            f"Array.from(tabs.children).forEach(x=>x.classList.remove('on'));"
            f"Array.from(group.children).filter(x=>x.classList.contains('ltab')||x.classList.contains('btab'))"
            f".forEach(x=>x.classList.remove('on'));"
            f"const target=Array.from(group.children).find(x=>x.id===n);"
            f"if(target){{b.classList.add('on');target.classList.add('on');}}}}"
            f"function cp(el){{navigator.clipboard.writeText(el.textContent);}}</script></body></html>")


def nav_html(prefix=""):
    return (f"<a href='{prefix}index.html'>Leaderboard</a>"
            f"<a href='{prefix}models.html'>Models</a>"
            f"<a href='{prefix}benchmarks.html'>Benchmarks</a>"
            f"<a href='{prefix}compare.html'>Compare</a>"
            f"<a href='{prefix}methodology.html'>Methodology</a>"
            f"<a href='{prefix}confidence.html'>Confidence</a>")


def main(input_path=None, output_dir=None):
    """Validate both inputs before writing the site beside its matching report."""
    if input_path is None or output_dir is None:
        raise ValueError("input_path and output_dir are required")
    rep = os.fspath(output_dir)
    with open(input_path, encoding="utf-8") as f:
        a = json.load(f)
    from pipeline_common import validate_run_id
    stamp = validate_run_id(a.get("stamp"))
    if "run_id" in a:
        validate_run_id(a["run_id"])
    with open(os.path.join(rep, f"{stamp}_models.json"), encoding="utf-8") as rf:
        r = json.load(rf)
    for key in ("stamp", "run_id"):
        if r.get(key) != a.get(key):
            raise ValueError(f"Mixed-run report: {key} does not match analysis")
    models = [m for m in a.get("models", []) if not m.get("router")]
    views = a.get("views", {}) or {}
    site = os.path.join(rep, f"{stamp}_site")
    os.makedirs(os.path.join(site, "models"), exist_ok=True)
    by_slug = {m["slug"]: m for m in models}
    by_id = {m["id"]: m for m in models}

    def resolve(row):
        if isinstance(row, str):
            return by_slug.get(row) or by_id.get(row) or {}
        row = row or {}
        return by_slug.get(row.get("slug")) or by_id.get(row.get("id")) or by_id.get(row.get("model")) or {}

    def model_link(row, label=None):
        m = resolve(row)
        label = label if label is not None else (m.get("id") or (row if isinstance(row, str) else (row or {}).get("id", "—")))
        text = f"<code>{esc(label)}</code>"
        return f"<a href='models/{esc(quote(model_filename(m['slug']), safe=''))}'>{text}</a>" if m else text

    directory = (f"<p>{len(models)} non-router models · all models shown</p>"
                 "<input class='search' placeholder='Search all models…' oninput=\"f(this,'t-models')\">"
                 "<div class='twrap'><table id='t-models'><thead><tr><th>Model</th><th>Name</th><th>Score</th><th>Route</th></tr></thead><tbody>")
    directory += "".join(f"<tr><td>{model_link(m)}</td><td>{esc(m.get('name', ''))}</td>"
                         f"<td>{esc(m.get('score', 'unscored'))}</td><td>{copy_control(m)}</td></tr>" for m in models)
    directory += "</tbody></table></div>"
    with open(os.path.join(site, "models.html"), "w", encoding="utf-8") as f:
        f.write(page("Model directory", stamp, nav_html(), directory))

    # ---- index: source-switchable leaderboards ----
    aa_rows = sorted(models, key=lambda m: (-(m["score"] if isinstance(m.get("score"), (int, float)) else -1)))[:100]

    def aa_table():
        h = [f"<p>Showing {len(aa_rows)} of {len(models)} models · <a href='models.html'>Search all models</a></p>"
             "<input class='search' placeholder='Filter…' oninput=\"f(this,'t-aa')\">"
             "<div class='twrap'><table id='t-aa'><thead><tr><th>#</th><th>Model</th><th>Score</th>"
             "<th>Cost</th><th>Groups</th><th>Route</th><th>Evidence</th></tr></thead><tbody>"]
        for i, m in enumerate(aa_rows, 1):
            ev = (m.get("score_source") or {}).get("kind", "unscored")
            h.append(f"<tr><td>{i}</td><td>{model_link(m)}</td>"
                     f"<td>{esc(m.get('score','unscored'))}</td><td>{esc(m.get('cost_blended','unknown'))}</td>"
                     f"<td>{esc(''.join(m.get('groups',[])) or '–')}</td>"
                     f"<td>{copy_control(m)}</td><td>{esc(ev)}</td></tr>")
        return "".join(h) + "</tbody></table></div>"

    def bench_table():
        rows = views.get("benchlm_leaderboard", []) or []
        supported = [r for r in rows if (r.get("evidence") or "").lower() == "supported"]
        h = [f"<div class='tab-group'><div class='tabs'><button class='on' onclick=\"lt(this,'b-sup')\">Supported ({len(supported)})</button>"
             f"<button onclick=\"lt(this,'b-all')\">All ({len(rows)}, incl. estimated)</button></div>"
             "<div class='btab on' id='b-sup'>"
             f"<p>Showing {min(100, len(supported))} of {len(supported)} supported models</p>"
             "<input class='search' placeholder='Filter…' oninput=\"f(this,'t-b')\">"
             "<div class='twrap'><table id='t-b'><thead><tr><th>#</th><th>Model</th><th>Overall</th>"
             "<th>Evidence</th><th>Agentic</th><th>Coding</th><th>Knowledge</th></tr></thead><tbody>"]
        for i, r in enumerate(supported[:100], 1):
            cats = r.get("categories", {}) or {}
            h.append(f"<tr><td>{i}</td><td>{model_link(r, r.get('model',''))}</td><td>{esc(r.get('overall',''))}</td>"
                     f"<td>{esc(r.get('evidence',''))}</td><td>{esc(cats.get('agentic','–'))}</td>"
                     f"<td>{esc(cats.get('coding','–'))}</td><td>{esc(cats.get('knowledge','–'))}</td></tr>")
        h.append("</tbody></table></div></div><div class='btab' id='b-all'>"
                 f"<p>Showing {min(100, len(rows))} of {len(rows)} models</p>"
                 "<input class='search' placeholder='Filter…' oninput=\"f(this,'t-b2')\">"
                 "<div class='twrap'><table id='t-b2'><thead><tr><th>#</th><th>Model</th><th>Overall</th>"
                 "<th>Evidence</th><th>Agentic</th><th>Coding</th><th>Knowledge</th></tr></thead><tbody>")
        for i, r in enumerate(rows[:100], 1):
            cats = r.get("categories", {}) or {}
            h.append(f"<tr><td>{i}</td><td>{model_link(r, r.get('model',''))}</td><td>{esc(r.get('overall',''))}</td>"
                     f"<td>{esc(r.get('evidence',''))}</td><td>{esc(cats.get('agentic','–'))}</td>"
                     f"<td>{esc(cats.get('coding','–'))}</td><td>{esc(cats.get('knowledge','–'))}</td></tr>")
        h.append("</tbody></table></div></div></div>")
        return "".join(h) if rows else "<p class='note'>BenchLM snapshot missing — re-run retrieval.</p>"

    def llm_table():
        rows = views.get("llmstats_leaderboard", []) or []
        h = [f"<p>Showing {min(100, len(rows))} of {len(rows)} models</p>"
             "<div class='twrap'><table><thead><tr><th>#</th><th>Model</th><th>Rating</th><th>Evals</th><th>Source</th></tr></thead><tbody>"]
        for i, r in enumerate(rows[:100], 1):
            rk = r.get("rank")
            h.append(f"<tr><td>{esc(rk if rk is not None else i)}</td><td>{model_link(r)}</td><td>{esc(r.get('score',''))}</td>"
                     f"<td>{esc(r.get('evals','–'))}</td><td><a href='{esc(r.get('url',''))}'>page</a></td></tr>")
        return "".join(h) + "</tbody></table></div>" if rows else "<p class='note'>LLM Stats website/API coverage thin this run (needs key or page fetch).</p>"

    def vals_table():
        rows = views.get("vals_leaderboard", []) or []
        h = [f"<p>Showing {min(100, len(rows))} of {len(rows)} models</p>"
             "<div class='twrap'><table><thead><tr><th>#</th><th>Model</th><th>Accuracy %</th><th>$/test</th><th>Latency</th></tr></thead><tbody>"]
        for i, r in enumerate(rows[:100], 1):
            h.append(f"<tr><td>{i}</td><td>{model_link(r)}</td><td>{esc(r.get('accuracy',''))}</td>"
                     f"<td>{esc(r.get('cost_per_test',''))}</td><td>{esc(r.get('latency',''))}</td></tr>")
        return "".join(h) + "</tbody></table></div>" if rows else "<p class='note'>Vals website coverage thin this run.</p>"

    chips = (f"<span class='chip'>Models {len(models)}</span>"
             f"<span class='chip'>BenchLM {a.get('total_benchlm',0)}</span>"
             f"<span class='chip'>Vals {(a.get('vals_status') or {}).get('count',0)}</span>"
             f"<span class='chip'>Websites {(a.get('website_stats') or {}).get('allowlist',0)}</span>")
    index_body = (f"<p>Snapshot <b>{esc(stamp)}</b> · AA ranks, BenchLM/LLM-Stats/Vals are parallel reference scales (never mixed). {chips}</p>"
                  f"<p class='source-summary'><strong>{esc(source_summary(a))}</strong> · <a href='confidence.html'>Confidence and coverage details</a></p>"
                  "<div class='tab-group'><div class='tabs'><button class='on' onclick=\"lt(this,'l-aa')\">AA Intelligence</button>"
                  "<button onclick=\"lt(this,'l-b')\">BenchLM</button>"
                  "<button onclick=\"lt(this,'l-l')\">LLM Stats</button>"
                  "<button onclick=\"lt(this,'l-v')\">Vals</button></div>"
                  f"<div class='ltab on' id='l-aa'>{aa_table()}</div>"
                  f"<div class='ltab' id='l-b'>{bench_table()}</div>"
                  f"<div class='ltab' id='l-l'>{llm_table()}</div>"
                  f"<div class='ltab' id='l-v'>{vals_table()}</div></div>"
                  "<p class='note'>Benchmark data: <a href='https://benchlm.ai'>BenchLM</a> · "
                  "Data by <a href='https://llm-stats.com'>LLM Stats</a> · "
                  "<a href='https://www.vals.ai'>Vals AI</a> · "
                  "<a href='https://artificialanalysis.ai'>Artificial Analysis</a>.</p>")
    with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as f:
        f.write(page("Leaderboard", stamp, nav_html(), index_body))

    # ---- model pages ----
    for m in models:
        b = m.get("benchlm") or {}
        web = m.get("website") or {}
        cats = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in (b.get("categories") or {}).items())
        rk = m.get("llmstats_rank") or {}
        rk_rows = "".join(f"<tr><td>{esc(c)}</td><td>{esc((v or {}).get('rank','–'))}</td>"
                          f"<td>{esc((v or {}).get('rating','–'))}</td><td>{esc((v or {}).get('evals','–'))}</td></tr>"
                          for c, v in rk.items())
        det = m.get("llmstats_detail") or {}
        det_scores = sorted((det.get("scores", []) or []),
                            key=lambda s: (not s.get("verified"), s.get("rank") if isinstance(s.get("rank"), int) else 10**9))[:25]
        det_rows = "".join("<tr><td>" + esc(s.get("name") or s.get("bench", "")) + "</td><td>"
                           + esc(s.get("cat", "")) + "</td><td>" + esc(s.get("score", "")) + "</td><td>"
                           + esc("verified" if s.get("verified") else ("self-reported" if s.get("self_reported") else "third-party"))
                           + "</td></tr>" for s in det_scores)
        prov_rows = ""
        for p in ((m.get("llmstats_api") or {}).get("providers", []) or []):
            prov_rows += ("<tr><td>" + esc(p.get("provider_name", "")) + "</td><td>$"
                          + esc(p.get("in_per_m", "")) + "/M in</td><td>$"
                          + esc(p.get("out_per_m", "")) + "/M out</td></tr>")
        prov_html = ("<h3>LLM Stats providers</h3><table>" + prov_rows + "</table>") if prov_rows else ""
        body = (f"<p><code>{esc(m['id'])}</code> · {esc(m.get('name',''))} · groups {esc(''.join(m.get('groups',[])) or '–')} · "
                f"free {esc(m.get('free_status','none'))}</p>"
                f"<p>Route: {copy_control(m)}</p>"
                f"<h2>Scores (separate scales)</h2><table><tr><th>Source</th><th>Value</th><th>Evidence</th></tr>"
                f"<tr><td>AA Intelligence</td><td>{esc(m.get('score','unscored'))}</td><td>{esc((m.get('score_source') or {}).get('kind','unscored'))}</td></tr>"
                f"<tr><td>BenchLM overall</td><td>{esc(b.get('overall','–'))}</td><td>{esc(b.get('evidence','–'))}</td></tr>"
                f"</table>"
                f"<h3>BenchLM categories</h3><table>{cats or '<tr><td>–</td></tr>'}</table>"
                + (f"<h3>LLM Stats ranks (TrueSkill conservative)</h3><table><tr><th>Category</th><th>Rank</th><th>Rating</th><th>Evals</th></tr>{rk_rows}</table>" if rk_rows else "")
                + (f"<h3>LLM Stats benchmarks (verified first)</h3><div class='twrap'><table><tr><th>Benchmark</th><th>Category</th><th>Score</th><th>Provenance</th></tr>{det_rows}</table></div>" if det_rows else "")
                + prov_html
                + f"<h2>Capabilities</h2><table>"
                f"<tr><td>Context (OR)</td><td>{esc(m.get('context','–'))}</td></tr>"
                f"<tr><td>Efforts</td><td>{esc('/'.join(m.get('efforts',[])) or '/'.join(m.get('efforts_hint',[])) or '–')}</td></tr>"
                f"<tr><td>Providers</td><td>{esc(','.join(m.get('providers',[])))}</td></tr>"
                f"<tr><td>BenchLM context/type</td><td>{esc((m.get('benchlm_pricing') or {}).get('context','–'))} / {esc((m.get('benchlm_pricing') or {}).get('type','–'))}</td></tr>"
                f"</table><h2>Sources</h2><p class='note'>"
                + " ".join(f"<a href='{esc((v or {}).get('url',''))}'>{esc(k)}</a>" for k, v in web.items() if isinstance(v, dict) and v.get("url")) +
                "</p>")
        with open(os.path.join(site, "models", model_filename(m['slug'])), "w", encoding="utf-8") as f:
            f.write(page(m["id"], stamp, nav_html("../"), body))

    # ---- benchmarks ----
    bench_meta = a.get("benchlm_meta", {}) or {}
    bench_body = (f"<p>BenchLM {esc(bench_meta.get('methodology',''))} · updated {esc(bench_meta.get('lastUpdated',''))}</p>"
                  "<h2>Catalog</h2><table><tr><th>Benchmark</th><th>Scale</th><th>Source</th></tr>"
                  "<tr><td>AA Intelligence Index</td><td>0–100 index</td><td>Artificial Analysis API (+ research.json v-pinned)</td></tr>"
                  "<tr><td>BenchLM overall + agentic/coding/reasoning/knowledge/…</td><td>BenchLM 0–100</td><td>benchlm.ai/api/data/leaderboard (+ /md/models pages)</td></tr>"
                  "<tr><td>LLM Stats overall + category TrueSkill</td><td>TrueSkill conservative</td><td>ZeroEval API (keyed) + llm-stats.com model pages</td></tr>"
                  "<tr><td>Vals Index + task benches (Legal/Finance/Code/…)</td><td>task % ±SE</td><td>vals.ai website (best-effort HTML)</td></tr>"
                  "</table><p class='note'>Per-benchmark versions and evidence tiers live in observations (data.json). Cross-scale comparison is forbidden.</p>")
    with open(os.path.join(site, "benchmarks.html"), "w", encoding="utf-8") as f:
        f.write(page("Benchmarks", stamp, nav_html(), bench_body))

    # ---- compare: practical winners + top families ----
    _lookup = r.get("models_by_slug") or {}

    def _resolve(x):
        return _lookup.get(x, {}) if isinstance(x, str) else (x or {})

    comp = ["<h2>Practical winners (AA ranking)</h2><table><tr><th>Tier</th><th>Variant</th><th>Winner</th><th>Runner-up</th></tr>"]
    for p in r.get("ocf_practical", []):
        w = _resolve(p.get("winner"))
        u = _resolve(p.get("runner_up"))
        comp.append(f"<tr><td>{esc(p.get('tier',''))}</td><td>{esc(p.get('variant',''))}</td>"
                    f"<td>{model_link(w, w.get('id','gap'))}</td><td>{model_link(u, u.get('id','–'))}</td></tr>")
    comp.append("</table><h2>Top multi-variant families</h2>")
    for fam in (r.get("family_variants", []) or [])[:10]:
        comp.append(f"<h3>{esc(fam.get('family',''))} (peak {esc(fam.get('peak',''))})</h3><div class='twrap'><table>"
                    "<tr><th>Model</th><th>Variant</th><th>Score</th><th>Cost</th><th>Route</th></tr>")
        for m in [_resolve(x) for x in fam.get("rows", [])]:
            comp.append(f"<tr><td>{model_link(m)}</td><td>{esc(m.get('variant',''))}</td>"
                        f"<td>{esc(m.get('score',''))}</td><td>{esc(m.get('cost_blended',''))}</td>"
                        f"<td><code>{esc(copy_id(m))}</code></td></tr>")
        comp.append("</table></div>")
    with open(os.path.join(site, "compare.html"), "w", encoding="utf-8") as f:
        f.write(page("Compare", stamp, nav_html(), "".join(comp)))

    # ---- methodology + confidence ----
    meth = ("<h2>Rules</h2><ul><li>Existence from providers (OpenRouter required; others keyless/keyed with graceful skip).</li>"
            "<li>Ranking score = AA Intelligence Index only (version-pinned per day).</li>"
            "<li>BenchLM / LLM Stats / Vals are parallel reference views — never averaged, never fill AA score.</li>"
            "<li>LLM Stats Community plan requires attribution: Data by <a href='https://llm-stats.com'>LLM Stats</a>; bulk redistribution is not licensed — snapshots stay local.</li>"
            "<li>Free = strict $0 at retrieval (OR $0 + text-only + no routers) or Zen *-free; AA $0 alone = provisional [F?].</li>"
            "<li>Variants are separate rows; inherited estimates are new rows with equivalence URLs, excluded from churn history.</li>"
            "<li>Copy ID = selector else openrouter/&lt;or_id&gt; else native fallback; AA-only rows never copyable.</li></ul>")
    with open(os.path.join(site, "methodology.html"), "w", encoding="utf-8") as f:
        f.write(page("Methodology", stamp, nav_html(), meth))
    conf = views.get("confidence", {}) or {}
    ch = a.get("free_churn", {}) or {}
    tri = views.get("provisional_triage", []) or []
    tri_rows = "".join("<tr><td>" + model_link(t) + "</td><td>"
                       + esc(t.get("score", "–")) + "</td><td>" + esc(t.get("free_status", "")) + "</td><td>"
                       + copy_control(resolve(t))
                       + "</td><td>" + ("QUALIFIER — verify billing" if t.get("qualifier") else "watch") + "</td></tr>"
                       for t in tri[:20])
    conf_body = (f"<p>BenchLM evidence: supported {conf.get('supported',0)} · estimated {conf.get('estimated',0)} · other {conf.get('other',0)}</p>"
                 f"<p>Website crawl: {esc(a.get('website_stats',{}))}</p>"
                 f"<p>Churn vs {esc(ch.get('prev_day','—'))}: →paid {ch.get('flipped_to_paid_total',0)} · →free {ch.get('flipped_to_free_total',0)} · "
                 f"disappeared {ch.get('disappeared_total',0)} · new {ch.get('new_total',0)}</p>"
                 f"<h2>Provisional triage (top 20 by AA score)</h2>"
                 f"<p class='note'>Qualifier = score ≥ 40 with a callable route → verify billing for verified-free promotion. "
                 f"Current pool: {len(tri)} provisional, {sum(1 for t in tri if t.get('qualifier'))} qualifiers.</p>"
                 f"<div class='twrap'><table><tr><th>Model</th><th>Score</th><th>Status</th><th>Route</th><th>Verdict</th></tr>{tri_rows}</table></div>")
    with open(os.path.join(site, "confidence.html"), "w", encoding="utf-8") as f:
        f.write(page("Confidence", stamp, nav_html(), reliability_html(a) + conf_body))
    with open(os.path.join(site, "data.json"), "w", encoding="utf-8") as f:
        json.dump({"stamp": stamp, "views": views,
                   "benchlm_meta": bench_meta, "website_stats": a.get("website_stats", {}),
                   "free_churn": ch, **reliability_data(a)}, f, indent=1)

    print(f"site {stamp} written ({len(models)} models)")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ROOT)
    from pipeline_common import stage_cli
    stage_cli(main, __doc__)
