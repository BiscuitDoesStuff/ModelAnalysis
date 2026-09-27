"""Shared presentation layer for the dashboard and the static site.

Colour tokens (dark default, light via prefers-color-scheme) with a WCAG
contrast check, accessible components (copy button, tabs, labelled filter,
captioned tables), one page shell and script, and check_html, the structure
checker pipeline.validate_bundle and tests/test_ui.py run on every page.
"""
import html as _html
from html.parser import HTMLParser

TOKENS = {
    "dark": {"bg": "#020617", "surface": "#0f172a", "control": "#1e293b", "row": "#0b1220",
             "text": "#e2e8f0", "muted": "#94a3b8", "accent": "#7dd3fc", "accent2": "#bae6fd",
             "border": "#334155", "line": "#38bdf8", "chip": "#082f49", "warn": "#fbbf24",
             "ok": "#4ade80", "selected": "#0369a1", "selected_text": "#ffffff"},
    "light": {"bg": "#ffffff", "surface": "#f1f5f9", "control": "#e2e8f0", "row": "#f8fafc",
              "text": "#0f172a", "muted": "#475569", "accent": "#0369a1", "accent2": "#075985",
              "border": "#cbd5e1", "line": "#0284c7", "chip": "#e0f2fe", "warn": "#92400e",
              "ok": "#15803d", "selected": "#0369a1", "selected_text": "#ffffff"},
}
# (foreground, background) token pairs that carry text; each must reach 4.5:1 in both themes.
CONTRAST_PAIRS = [(fg, bg) for fg in ("text", "muted", "accent", "accent2", "warn", "ok")
                  for bg in ("bg", "surface", "row")] + [
    ("text", "control"), ("muted", "control"), ("accent", "control"), ("text", "chip"),
    ("selected_text", "selected")]
AA_TEXT = 4.5


def _luminance(colour):
    rgb = [int(colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(fg, bg):
    """WCAG 2 contrast ratio between two #rrggbb colours (1..21)."""
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def esc(v):
    return _html.escape("" if v is None else str(v))


def _vars(theme):
    return ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in TOKENS[theme].items())


def css():
    return (
        f":root{{color-scheme:dark;{_vars('dark')}}}"
        f"@media (prefers-color-scheme: light){{:root{{color-scheme:light;{_vars('light')}}}}}"
        "body{font-family:Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text);margin:0;padding:24px;max-width:1200px}"
        "h1{font-size:24px}h2{color:var(--accent)}h3{color:var(--accent2)}a{color:var(--accent)}code{color:var(--accent)}"
        ".skip{position:absolute;left:-9999px;top:0;background:var(--selected);color:var(--selected-text);padding:8px 12px;z-index:10}"
        ".skip:focus{left:8px}"
        ".sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}"
        ":focus-visible{outline:3px solid var(--warn);outline-offset:2px}"
        "main:focus{outline:none}"
        "nav.top{position:sticky;top:0;background:var(--bg);padding:10px 0;z-index:5;border-bottom:1px solid var(--border);"
        "display:flex;flex-wrap:wrap;gap:4px 14px}"
        "nav.top a{text-decoration:none}nav.top a[aria-current=page]{text-decoration:underline;font-weight:700}"
        ".chip{display:inline-block;background:var(--chip);border:1px solid var(--line);border-radius:12px;padding:3px 12px;margin:2px;font-size:13px}"
        ".chip.dim{border-style:dashed;color:var(--muted)}"
        "table{border-collapse:collapse;width:100%;font-size:13px}"
        "th,td{border:1px solid var(--border);padding:6px 8px;text-align:left;vertical-align:top}"
        "th{background:var(--surface)}tbody tr:nth-child(even){background:var(--row)}"
        "caption{text-align:left;font-weight:600;padding:4px 0;color:var(--accent2)}"
        "button.copy{font:inherit;font-family:Consolas,monospace;color:var(--accent);background:none;border:0;"
        "border-bottom:1px dotted var(--line);padding:0;cursor:pointer;text-align:left;overflow-wrap:break-word}"
        "button.copy.done{color:var(--ok)}"
        ".nm{color:var(--muted);font-size:12px}.gap{color:var(--warn);font-weight:700}.note{color:var(--muted)}"
        ".hint{font-weight:400;font-size:11px;color:var(--muted)}.unk{color:var(--muted);font-style:italic}"
        ".search,.filters select{padding:6px 10px;margin:8px 4px 8px 0;background:var(--surface);color:var(--text);"
        "border:1px solid var(--line);border-radius:8px}"
        ".search{width:280px}.filters label{margin-right:8px}"
        ".twrap{overflow-x:auto;max-width:100%}.cards{display:flex;gap:12px;flex-wrap:wrap}"
        ".card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 16px;min-width:200px}"
        ".bign{font-size:15px}"
        "[role=tablist]{display:flex;flex-wrap:wrap;gap:4px;padding:10px 0}"
        "[role=tab]{background:var(--control);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit}"
        "[role=tab][aria-selected=true]{background:var(--selected);color:var(--selected-text)}"
        ".tabbar{position:sticky;top:0;background:var(--bg);z-index:5}"
        "@media (max-width:480px){body{padding:12px}.search{width:100%;box-sizing:border-box}"
        ".card{min-width:0;flex:1 1 100%}table{font-size:12px}th,td{padding:4px 5px}.twrap>table{min-width:640px}"
        "[role=tab]{padding:6px 8px}h1{font-size:20px}}"
    )


# One delegated handler set per page: copy buttons, tabs (click + arrow/Home/End), table filters.
SCRIPT = """(() => {
  const status = document.getElementById('copy-status');
  const say = text => { if (status) { status.textContent = ''; setTimeout(() => { status.textContent = text; }, 30); } };
  document.addEventListener('click', event => {
    const button = event.target.closest('button.copy[data-copy]');
    if (!button) return;
    const value = button.dataset.copy;
    const failed = () => say('Clipboard unavailable; select the route text to copy it.');
    if (!navigator.clipboard || !navigator.clipboard.writeText) { failed(); return; }
    navigator.clipboard.writeText(value).then(() => {
      button.classList.add('done');
      setTimeout(() => button.classList.remove('done'), 900);
      say('Copied ' + value);
    }, failed);
  });
  const tabsOf = tab => Array.from(tab.closest('[role=tablist]').querySelectorAll(':scope > [role=tab]'));
  function select(tab, focus) {
    for (const other of tabsOf(tab)) {
      const on = other === tab;
      other.setAttribute('aria-selected', String(on));
      other.tabIndex = on ? 0 : -1;
      const panel = document.getElementById(other.getAttribute('aria-controls'));
      if (panel) panel.hidden = !on;
    }
    if (focus) tab.focus();
    markScrollers();
  }
  // A wrapper that scrolls sideways (wide table, chart on a phone) must be reachable by
  // keyboard: focusable and named only while it actually overflows.
  function markScrollers() {
    document.querySelectorAll('.twrap, .g-chart').forEach(el => {
      if (el.scrollWidth > el.clientWidth + 1) {
        const caption = el.querySelector('caption');
        el.tabIndex = 0;
        el.setAttribute('role', 'region');
        el.setAttribute('aria-label', 'Scrollable: ' + (caption ? caption.textContent : 'chart'));
      } else if (el.getAttribute('role') === 'region') {
        el.removeAttribute('tabindex');
        el.removeAttribute('role');
        el.removeAttribute('aria-label');
      }
    });
  }
  markScrollers();
  window.addEventListener('resize', markScrollers);
  document.addEventListener('click', event => {
    const tab = event.target.closest('[role=tab]');
    if (tab) select(tab, false);
  });
  document.addEventListener('keydown', event => {
    const tab = event.target.closest && event.target.closest('[role=tab]');
    if (!tab) return;
    const tabs = tabsOf(tab);
    let i = tabs.indexOf(tab);
    if (event.key === 'ArrowRight') i = (i + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') i = (i - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') i = 0;
    else if (event.key === 'End') i = tabs.length - 1;
    else return;
    event.preventDefault();
    select(tabs[i], true);
  });
  document.addEventListener('input', event => {
    const input = event.target;
    if (!input.matches || !input.matches('input[data-filter]')) return;
    const block = input.closest('.tblock');
    const query = input.value.toLowerCase();
    if (block) block.querySelectorAll('tbody tr').forEach(tr => { tr.hidden = !tr.textContent.toLowerCase().includes(query); });
  });
})();"""


def copy_button(route):
    """Keyboard-reachable copy control; empty for display-only rows (never copyable)."""
    if not route:
        return ""
    r = esc(route)
    # <wbr> lets long routes wrap after a slash instead of mid-word; data-copy holds the exact value.
    return (f"<button type='button' class='copy' data-copy='{r}' aria-label='Copy route {r}'>"
            f"{r.replace('/', '/<wbr>')}</button>")


def status_region():
    return "<p id='copy-status' class='sr-only' role='status' aria-live='polite'></p>"


def filter_input(text="Filter this table"):
    """Labelled filter for the table in the same .tblock."""
    return (f"<label><span class='sr-only'>{esc(text)}</span>"
            f"<input type='search' class='search' data-filter placeholder='{esc(text)}…' autocomplete='off'></label>")


def select_input(text, select_id, options, onchange=""):
    """A labelled <select>; options are (value, label) pairs."""
    opts = "".join(f"<option value='{esc(v)}'>{esc(label)}</option>" for v, label in options)
    handler = f" onchange='{esc(onchange)}'" if onchange else ""
    return f"<label for='{esc(select_id)}'>{esc(text)}</label> <select id='{esc(select_id)}'{handler}>{opts}</select>"


def table(caption, headers, rows_html, attrs="", hide_caption=False):
    """A captioned table with scoped column headers; rows_html is the tbody content."""
    cls = " class='sr-only'" if hide_caption else ""
    cap = f"<caption{cls}>{esc(caption)}</caption>"
    head = "".join(f"<th scope='col'>{esc(h)}</th>" for h in headers)
    return f"<table{attrs}>{cap}<thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table>"


def kv_table(caption, rows, headers=None, hide_caption=False):
    """Label/value table: the first cell of each row is a row header.

    rows are (label, *cells); each cell is escaped HTML, or a complete <td …>
    element (provenance cells from build_report.score_td/price_td) used as is.
    """
    body = []
    for label, *cells in rows:
        tds = "".join(c if c.startswith("<td") else f"<td>{c}</td>" for c in cells)
        body.append(f"<tr><th scope='row'>{esc(label)}</th>{tds}</tr>")
    head = ("<thead><tr>" + "".join(f"<th scope='col'>{esc(h)}</th>" for h in headers) + "</tr></thead>") if headers else ""
    cls = " class='sr-only'" if hide_caption else ""
    return f"<table><caption{cls}>{esc(caption)}</caption>{head}<tbody>{''.join(body)}</tbody></table>"


def tabs(items, label, selected=0, list_class=""):
    """ARIA tabs: items are (panel_id, tab_label, body_html). Tab ids are 'tab-' + panel_id."""
    buttons, panels = [], []
    for i, (pid, text, body) in enumerate(items):
        on = i == selected
        buttons.append(f"<button type='button' role='tab' id='tab-{esc(pid)}' aria-controls='{esc(pid)}' "
                       f"aria-selected='{'true' if on else 'false'}' tabindex='{0 if on else -1}'>{esc(text)}</button>")
        panels.append(f"<div role='tabpanel' id='{esc(pid)}' aria-labelledby='tab-{esc(pid)}' tabindex='0'"
                      f"{'' if on else ' hidden'}>{body}</div>")
    cls = f" class='{esc(list_class)}'" if list_class else ""
    return f"<div class='tab-group'><div role='tablist' aria-label='{esc(label)}'{cls}>{''.join(buttons)}</div>{''.join(panels)}</div>"


def page_shell(title, body, header="", extra_css="", extra_script="", lang="en"):
    """Skip link, header, main landmark, status region, shared CSS and script."""
    return (f"<!DOCTYPE html><html lang='{lang}'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{css()}{extra_css}</style></head><body>"
            "<a class='skip' href='#main'>Skip to content</a>"
            f"{header}<main id='main' tabindex='-1'>{body}</main>{status_region()}"
            f"<script>{SCRIPT}</script>{extra_script}</body></html>")


class _Checker(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    SCOPES = {"col", "row", "colgroup", "rowgroup"}

    def __init__(self, allowed_routes):
        super().__init__(convert_charrefs=True)
        self.allowed = allowed_routes
        self.problems = []
        self.stack = []          # [tag, attrs, text parts]
        self.tables = []         # caption seen per open table
        self.label_for, self.ids, self.controls = set(), {}, []
        self.fields = []         # (tag, attrs, inside_label)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids[a["id"]] = a
        if tag == "label" and a.get("for"):
            self.label_for.add(a["for"])
        if tag in ("input", "select", "textarea") and a.get("type") != "hidden":
            self.fields.append((tag, a, any(t == "label" for t, _, _ in self.stack)))
        if tag == "table":
            self.tables.append(False)
        elif tag == "caption" and self.tables:
            self.tables[-1] = True
        elif tag == "th" and a.get("scope") not in self.SCOPES:
            self.problems.append("th without scope")
        if a.get("role") == "tab":
            self.controls.append(a)
        if "copy" in (a.get("class") or "").split():
            if tag != "button":
                self.problems.append(f"copy control is a <{tag}>, not a button")
            elif self.allowed is not None and a.get("data-copy") not in self.allowed:
                self.problems.append(f"copy button for non-callable route {a.get('data-copy')!r}")
        if tag not in self.VOID:
            self.stack.append((tag, a, []))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not any(t == tag for t, _, _ in self.stack):
            return
        while self.stack:
            t, a, text = self.stack.pop()
            if t == "button":
                if not ("".join(text).strip() or a.get("aria-label") or a.get("aria-labelledby") or a.get("title")):
                    self.problems.append(f"button without accessible name (id={a.get('id')!r})")
                if self.stack:
                    self.stack[-1][2].extend(text)
            elif self.stack:
                self.stack[-1][2].extend(text)
            if t == "table":
                if not self.tables.pop():
                    self.problems.append(f"table without caption (id={a.get('id')!r})")
            if t == tag:
                break

    def handle_data(self, data):
        if self.stack:
            self.stack[-1][2].append(data)

    def finish(self):
        for tag, a, in_label in self.fields:
            if not (in_label or a.get("id") in self.label_for or a.get("aria-label") or a.get("aria-labelledby")):
                self.problems.append(f"<{tag}> without label (id={a.get('id')!r})")
        owned = set()
        for tab in self.controls:
            panel = self.ids.get(tab.get("aria-controls") or "")
            if not panel or panel.get("role") != "tabpanel":
                self.problems.append(f"tab {tab.get('id')!r} controls no tabpanel")
            else:
                owned.add(tab["aria-controls"])
                if panel.get("aria-labelledby") != tab.get("id"):
                    self.problems.append(f"tabpanel {tab['aria-controls']!r} not labelled by its tab")
        for pid, a in self.ids.items():
            if a.get("role") == "tabpanel" and pid not in owned:
                self.problems.append(f"tabpanel {pid!r} has no tab")
        return self.problems


def check_html(text, allowed_routes=None):
    """Accessibility structure problems in one page (empty list = clean).

    Buttons need a name, inputs/selects a label, tabs a tabpanel (and back),
    tables a caption, every th a scope; copy controls must be buttons and, when
    allowed_routes is given, copy only callable routes.
    """
    checker = _Checker(None if allowed_routes is None else set(allowed_routes))
    checker.feed(text)
    checker.close()
    return checker.finish()
