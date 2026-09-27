"""3b. Site report — browsable static site like BenchLM / LLM Stats / Vals.

Reads an explicit analysis artifact and matching report, writing <stamp>_site/
with index, model pages, benchmarks, compare, methodology, confidence + data.json.
Offline; retention belongs to the coordinator.
"""
import json
import os
from urllib.parse import quote

if __package__:
    from . import ui
    from .build_report import (IDENTITY_HEADERS, copy_id, evidence_expiry_text, identity_rows, price_td,
                               reliability_data, reliability_html, row_view, score_td, source_summary)
else:
    import ui
    from build_report import (IDENTITY_HEADERS, copy_id, evidence_expiry_text, identity_rows, price_td,
                              reliability_data, reliability_html, row_view, score_td, source_summary)
from analysis.common import evidence_label

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
esc = ui.esc


def copy_control(m):
    return ui.copy_button(copy_id(m)) or "<span class='note'>no callable ID</span>"


def route_copy_id(route):
    """What a user pastes for one catalog route (OpenRouter IDs get the opencode prefix)."""
    rid = route.get("id", "")
    return rid if route.get("provider") != "openrouter" or rid.startswith("openrouter/") else f"openrouter/{rid}"


def routes_html(m):
    routes = m.get("routes") or []
    ident = m.get("identity") or {}
    if not routes and not ident:
        return ""
    rows = "".join(f"<tr><td>{esc(r.get('provider'))}</td><td>{ui.copy_button(route_copy_id(r))}</td>"
                   f"<td>{esc(', '.join(r.get('free_evidence') or []) or '–')}</td></tr>" for r in routes)
    conflicts = "".join(f"<li>{esc(c.get('kind'))}: {esc(c.get('reason'))}</li>" for c in ident.get("conflicts") or [])
    return (f"<h2>Routes</h2><p class='note'>Identity {esc(ident.get('key', '–'))} · basis {esc(ident.get('basis', '–'))}</p>"
            + (ui.table("Provider routes", ["Provider", "Route", "Free evidence"], rows) if rows
               else "<p class='note'>No provider routes (benchmark or AA row only).</p>")
            + (f"<p>Identity conflicts:</p><ul>{conflicts}</ul>" if conflicts else ""))


def model_filename(slug):
    # Encode path separators as literal filename bytes; links encode the '%' again.
    return quote(str(slug), safe="") + ".html"


PAGES = [("index.html", "Leaderboard"), ("models.html", "Models"), ("benchmarks.html", "Benchmarks"),
         ("compare.html", "Compare"), ("methodology.html", "Methodology"), ("confidence.html", "Confidence")]


def page(title, stamp, nav, body):
    header = f"<header><nav class='top' aria-label='Site'>{nav}</nav></header>"
    return ui.page_shell(f"{title} — {stamp}", f"<h1>{esc(title)}</h1>{body}", header=header)


def nav_html(prefix="", current=""):
    return "".join(f"<a href='{prefix}{href}'" + (" aria-current='page'" if href == current else "") + f">{label}</a>"
                   for href, label in PAGES)


def model_cells(m):
    """Shared model columns (same text as the dashboard): score, price + source, free status."""
    return score_td(m) + price_td(m) + f"<td>{esc(row_view(m)['free'])}</td>"


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

    def write(name, title, body, prefix=""):
        with open(os.path.join(site, name), "w", encoding="utf-8") as f:
            f.write(page(title, stamp, nav_html(prefix, "" if prefix else name), body))

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

    def filtered(caption, headers, rows_html, tid, label="Filter this table"):
        return ("<div class='tblock'>" + ui.filter_input(label) + "<div class='twrap'>"
                + ui.table(caption, headers, rows_html, attrs=f" id='{tid}'") + "</div></div>")

    directory_rows = "".join(f"<tr><td>{model_link(m)}</td><td>{esc(m.get('name', ''))}</td>{model_cells(m)}"
                             f"<td>{copy_control(m)}</td></tr>" for m in models)
    write("models.html", "Model directory",
          f"<p>{len(models)} non-router models · all models shown</p>"
          + filtered("All non-router models", ["Model", "Name", "Score", "Price", "Free", "Route"],
                     directory_rows, "t-models", "Search all models"))

    # ---- index: source-switchable leaderboards ----
    aa_rows = sorted(models, key=lambda m: (-(m["score"] if isinstance(m.get("score"), (int, float)) else -1)))[:100]

    def aa_table():
        rows = "".join(f"<tr><td>{i}</td><td>{model_link(m)}</td>{model_cells(m)}"
                       f"<td>{esc(row_view(m)['groups'])}</td><td>{copy_control(m)}</td>"
                       f"<td>{esc(row_view(m)['evidence'])}</td></tr>" for i, m in enumerate(aa_rows, 1))
        return (f"<p>Showing {len(aa_rows)} of {len(models)} models · <a href='models.html'>Search all models</a></p>"
                + filtered("AA Intelligence Index leaderboard",
                           ["#", "Model", "Score", "Price", "Free", "Groups", "Route", "Evidence"], rows, "t-aa"))

    def bench_rows(rows):
        out = []
        for i, r in enumerate(rows[:100], 1):
            cats = r.get("categories", {}) or {}
            out.append(f"<tr><td>{i}</td><td>{model_link(r, r.get('model', ''))}</td><td>{esc(r.get('overall', ''))}</td>"
                       f"<td>{esc(r.get('evidence', ''))}</td><td>{esc(cats.get('agentic', '–'))}</td>"
                       f"<td>{esc(cats.get('coding', '–'))}</td><td>{esc(cats.get('knowledge', '–'))}</td></tr>")
        return "".join(out)

    def bench_table():
        rows = views.get("benchlm_leaderboard", []) or []
        if not rows:
            return "<p class='note'>BenchLM snapshot missing — re-run retrieval.</p>"
        supported = [r for r in rows if (r.get("evidence") or "").lower() == "supported"]
        headers = ["#", "Model", "Overall", "Evidence", "Agentic", "Coding", "Knowledge"]
        return ui.tabs([
            ("b-sup", f"Supported ({len(supported)})",
             f"<p>Showing {min(100, len(supported))} of {len(supported)} supported models</p>"
             + filtered("BenchLM leaderboard, supported evidence", headers, bench_rows(supported), "t-b")),
            ("b-all", f"All ({len(rows)}, incl. estimated)",
             f"<p>Showing {min(100, len(rows))} of {len(rows)} models</p>"
             + filtered("BenchLM leaderboard, all evidence", headers, bench_rows(rows), "t-b2"))], "BenchLM evidence")

    def llm_table():
        rows = views.get("llmstats_leaderboard", []) or []
        if not rows:
            return "<p class='note'>LLM Stats website/API coverage thin this run (needs key or page fetch).</p>"
        body = "".join(f"<tr><td>{esc(r.get('rank') if r.get('rank') is not None else i)}</td><td>{model_link(r)}</td>"
                       f"<td>{esc(r.get('score', ''))}</td><td>{esc(r.get('evals', '–'))}</td>"
                       f"<td><a href='{esc(r.get('url', ''))}'>page</a></td></tr>" for i, r in enumerate(rows[:100], 1))
        return (f"<p>Showing {min(100, len(rows))} of {len(rows)} models</p><div class='twrap'>"
                + ui.table("LLM Stats leaderboard", ["#", "Model", "Rating", "Evals", "Source"], body) + "</div>")

    def vals_table():
        rows = views.get("vals_leaderboard", []) or []
        if not rows:
            return "<p class='note'>Vals website coverage thin this run.</p>"
        body = "".join(f"<tr><td>{i}</td><td>{model_link(r)}</td><td>{esc(r.get('accuracy', ''))}</td>"
                       f"<td>{esc(r.get('cost_per_test', ''))}</td><td>{esc(r.get('latency', ''))}</td></tr>"
                       for i, r in enumerate(rows[:100], 1))
        return (f"<p>Showing {min(100, len(rows))} of {len(rows)} models</p><div class='twrap'>"
                + ui.table("Vals leaderboard", ["#", "Model", "Accuracy %", "$/test", "Latency"], body) + "</div>")

    chips = (f"<span class='chip'>Models {len(models)}</span>"
             f"<span class='chip'>BenchLM {a.get('total_benchlm',0)}</span>"
             f"<span class='chip'>Vals {(a.get('vals_status') or {}).get('count',0)}</span>"
             f"<span class='chip'>Websites {(a.get('website_stats') or {}).get('allowlist',0)}</span>")
    index_body = (f"<p>Snapshot <b>{esc(stamp)}</b> · AA ranks, BenchLM/LLM-Stats/Vals are parallel reference scales (never mixed). {chips}</p>"
                  f"<p class='source-summary'><strong>{esc(source_summary(a))}</strong> · <a href='confidence.html'>Confidence and coverage details</a></p>"
                  + ui.tabs([("l-aa", "AA Intelligence", aa_table()), ("l-b", "BenchLM", bench_table()),
                             ("l-l", "LLM Stats", llm_table()), ("l-v", "Vals", vals_table())], "Leaderboard source")
                  + "<p class='note'>Benchmark data: <a href='https://benchlm.ai'>BenchLM</a> · "
                  "Data by <a href='https://llm-stats.com'>LLM Stats</a> · "
                  "<a href='https://www.vals.ai'>Vals AI</a> · "
                  "<a href='https://artificialanalysis.ai'>Artificial Analysis</a>.</p>")
    write("index.html", "Leaderboard", index_body)

    # ---- model pages ----
    for m in models:
        v = row_view(m)
        b = m.get("benchlm") or {}
        web = m.get("website") or {}
        rk = m.get("llmstats_rank") or {}
        rk_rows = "".join(f"<tr><th scope='row'>{esc(c)}</th><td>{esc((x or {}).get('rank','–'))}</td>"
                          f"<td>{esc((x or {}).get('rating','–'))}</td><td>{esc((x or {}).get('evals','–'))}</td></tr>"
                          for c, x in rk.items())
        det = m.get("llmstats_detail") or {}
        det_scores = sorted((det.get("scores", []) or []),
                            key=lambda s: (not s.get("verified"), s.get("rank") if isinstance(s.get("rank"), int) else 10**9))[:25]
        det_rows = "".join("<tr><td>" + esc(s.get("name") or s.get("bench", "")) + "</td><td>"
                           + esc(s.get("cat", "")) + "</td><td>" + esc(s.get("score", "")) + "</td><td>"
                           + esc("verified" if s.get("verified") else ("self-reported" if s.get("self_reported") else "third-party"))
                           + "</td></tr>" for s in det_scores)
        prov_rows = "".join("<tr><td>" + esc(p.get("provider_name", "")) + "</td><td>$" + esc(p.get("in_per_m", ""))
                            + "/M in</td><td>$" + esc(p.get("out_per_m", "")) + "/M out</td></tr>"
                            for p in ((m.get("llmstats_api") or {}).get("providers", []) or []))
        cats = [(k, esc(x)) for k, x in (b.get("categories") or {}).items()]
        body = (f"<p><code>{esc(m['id'])}</code> · {esc(m.get('name',''))} · groups {esc(''.join(m.get('groups',[])) or '–')} · "
                f"{esc(v['free'])}</p>"
                f"<p>Route: {copy_control(m)}</p>" + routes_html(m) +
                "<h2>Scores (separate scales)</h2>"
                + ui.kv_table("Scores (separate scales)", [
                    ("AA Intelligence", score_td(m), esc(v["evidence"])),
                    ("Price (USD/1M, 3:1 blend)", price_td(m), esc(v["price_source"])),
                    ("BenchLM overall", esc(b.get("overall", "–")),
                     esc(evidence_label("external-reference") + " (BenchLM: " + str(b.get("evidence") or "unstated") + ")" if b else "–"))],
                    headers=["Source", "Value", "Evidence"], hide_caption=True)
                + "<h3>BenchLM categories</h3>"
                + (ui.kv_table("BenchLM categories", cats, hide_caption=True) if cats else "<p class='note'>No BenchLM categories.</p>")
                + (("<h3>LLM Stats ranks (TrueSkill conservative)</h3>"
                    + ui.table("LLM Stats ranks", ["Category", "Rank", "Rating", "Evals"], rk_rows, hide_caption=True)) if rk_rows else "")
                + (("<h3>LLM Stats benchmarks (verified first)</h3><div class='twrap'>"
                    + ui.table("LLM Stats benchmarks", ["Benchmark", "Category", "Score", "Provenance"], det_rows, hide_caption=True)
                    + "</div>")
                   if det_rows else "")
                + (("<h3>LLM Stats providers</h3>"
                    + ui.table("LLM Stats providers", ["Provider", "Input", "Output"], prov_rows, hide_caption=True))
                   if prov_rows else "")
                + "<h2>Capabilities</h2>"
                + ui.kv_table("Capabilities", [
                    ("Context (OR)", esc(m.get("context") or "–")),
                    ("Efforts", esc("/".join(m.get("efforts", [])) or "/".join(m.get("efforts_hint", [])) or "–")),
                    ("Providers", esc(",".join(m.get("providers", [])))),
                    ("BenchLM context/type", esc((m.get("benchlm_pricing") or {}).get("context", "–")) + " / "
                     + esc((m.get("benchlm_pricing") or {}).get("type", "–")))], hide_caption=True)
                + "<h2>Sources</h2><p class='note'>"
                + " ".join(f"<a href='{esc((x or {}).get('url',''))}'>{esc(k)}</a>" for k, x in web.items() if isinstance(x, dict) and x.get("url"))
                + "</p>")
        write(os.path.join("models", model_filename(m["slug"])), m["id"], body, prefix="../")

    # ---- benchmarks ----
    bench_meta = a.get("benchlm_meta", {}) or {}
    catalog = [("AA Intelligence Index", "0–100 index", "Artificial Analysis API (+ research.json v-pinned)"),
               ("BenchLM overall + agentic/coding/reasoning/knowledge/…", "BenchLM 0–100", "benchlm.ai/api/data/leaderboard (+ /md/models pages)"),
               ("LLM Stats overall + category TrueSkill", "TrueSkill conservative", "ZeroEval API (keyed) + llm-stats.com model pages"),
               ("Vals Index + task benches (Legal/Finance/Code/…)", "task % ±SE", "vals.ai website (best-effort HTML)")]
    bench_body = (f"<p>BenchLM {esc(bench_meta.get('methodology',''))} · updated {esc(bench_meta.get('lastUpdated',''))}</p>"
                  "<h2>Catalog</h2>" + ui.kv_table("Benchmark catalog", [(n, esc(sc), esc(src)) for n, sc, src in catalog],
                                                   headers=["Benchmark", "Scale", "Source"], hide_caption=True)
                  + "<p class='note'>Per-benchmark versions and evidence tiers live in observations (data.json). Cross-scale comparison is forbidden.</p>")
    write("benchmarks.html", "Benchmarks", bench_body)

    # ---- compare: practical winners + top families ----
    _lookup = r.get("models_by_slug") or {}

    def _resolve(x):
        return _lookup.get(x, {}) if isinstance(x, str) else (x or {})

    prac = "".join(f"<tr><td>{esc(p.get('tier',''))}</td><td>{esc(p.get('variant',''))}</td>"
                   f"<td>{model_link(w, w.get('id','gap'))}</td><td>{model_link(u, u.get('id','–'))}</td></tr>"
                   for p in r.get("ocf_practical", []) for w, u in [(_resolve(p.get("winner")), _resolve(p.get("runner_up")))])
    comp = ["<h2>Practical winners (AA ranking)</h2>"
            + ui.table("Practical winners", ["Tier", "Variant", "Winner", "Runner-up"], prac, hide_caption=True),
            "<h2>Top multi-variant families</h2>"]
    for fam in (r.get("family_variants", []) or [])[:10]:
        rows = "".join(f"<tr><td>{model_link(m)}</td><td>{esc(m.get('variant',''))}</td>{model_cells(m)}"
                       f"<td>{copy_control(m)}</td></tr>" for m in [_resolve(x) for x in fam.get("rows", [])])
        comp.append(f"<h3>{esc(fam.get('family',''))} (peak {esc(fam.get('peak',''))})</h3><div class='twrap'>"
                    + ui.table(f"Family {fam.get('family', '')}", ["Model", "Variant", "Score", "Price", "Free", "Route"], rows,
                               hide_caption=True) + "</div>")
    write("compare.html", "Compare", "".join(comp))

    # ---- methodology + confidence ----
    meth = ((f"<p><strong>{esc(evidence_expiry_text(a))}</strong></p>" if evidence_expiry_text(a) else "") +
            "<h2>Rules</h2><ul><li>Existence from providers (OpenRouter required; others keyless/keyed with graceful skip).</li>"
            "<li>Ranking score = AA Intelligence Index only; its version comes from dated ranges in research.json (aa_index_versions).</li>"
            "<li>BenchLM / LLM Stats / Vals are parallel reference views — never averaged, never fill AA score.</li>"
            "<li>LLM Stats Community plan requires attribution: Data by <a href='https://llm-stats.com'>LLM Stats</a>; bulk redistribution is not licensed — snapshots stay local.</li>"
            "<li>Free = strict $0 at retrieval (OR $0 + text-only + no routers) or Zen *-free; AA $0 alone = provisional [F?].</li>"
            "<li>Variants are separate rows; inherited estimates are new rows with equivalence URLs, excluded from churn history.</li>"
            "<li>Copy ID = selector else openrouter/&lt;or_id&gt; else native fallback; AA-only rows never copyable.</li>"
            "<li>A missing price or score reads <span class='unk'>unknown</span> / <span class='unk'>unscored</span>; $0/1M is a real zero.</li></ul>")
    write("methodology.html", "Methodology", meth)
    conf = views.get("confidence", {}) or {}
    tri = views.get("provisional_triage", []) or []
    tri_rows = "".join("<tr><td>" + model_link(t) + "</td><td>"
                       + esc(t.get("score", "–")) + "</td><td>" + esc(t.get("free_status", "")) + "</td><td>"
                       + copy_control(resolve(t))
                       + "</td><td>" + ("QUALIFIER — verify billing" if t.get("qualifier") else "watch") + "</td></tr>"
                       for t in tri[:20])
    ident_rows = "".join("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in row) + "</tr>" for row in identity_rows(a))
    ident_html = ("<h2>Identity conflicts</h2><p class='note'>Routes with the same model name that were kept apart "
                  "(different vendors, or a vendor-unknown route matching several) or joined with a caveat. "
                  "Add joins/splits with evidence in analysis/identity.json.</p><div class='twrap'>"
                  + ui.table("Identity conflicts", IDENTITY_HEADERS,
                             ident_rows or f"<tr><td colspan='{len(IDENTITY_HEADERS)}'>No identity conflicts.</td></tr>")
                  + "</div>") if "identity_conflicts" in a else ""
    conf_body = ident_html + (f"<p>BenchLM evidence: supported {conf.get('supported',0)} · estimated {conf.get('estimated',0)} · other {conf.get('other',0)}</p>"
                 f"<p>Website crawl: {esc(a.get('website_stats',{}))}</p>"
                 f"<h2>Provisional triage (top 20 by AA score)</h2>"
                 f"<p class='note'>Qualifier = score ≥ 40 with a callable route → verify billing for verified-free promotion. "
                 f"Current pool: {len(tri)} provisional, {sum(1 for t in tri if t.get('qualifier'))} qualifiers.</p>"
                 "<div class='twrap'>" + ui.table("Provisional triage", ["Model", "Score", "Status", "Route", "Verdict"], tri_rows)
                 + "</div>")
    write("confidence.html", "Confidence", reliability_html(a) + conf_body)
    with open(os.path.join(site, "data.json"), "w", encoding="utf-8") as f:
        json.dump({"stamp": stamp, "views": views,
                   "benchlm_meta": bench_meta, "website_stats": a.get("website_stats", {}),
                   **reliability_data(a)}, f, indent=1)

    print(f"site {stamp} written ({len(models)} models)")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ROOT)
    from pipeline_common import stage_cli
    stage_cli(main, __doc__)
