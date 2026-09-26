/* Inlined by build_report.py: graphModels contains only the non-router snapshot rows. */
(() => {
  'use strict';
  const maxSelected = 12;
  const colors = ['#38bdf8', '#fbbf24', '#4ade80', '#f472b6', '#c4b5fd', '#fb923c',
    '#2dd4bf', '#f87171', '#a3e635', '#e879f9', '#60a5fa', '#fcd34d'];
  const bySlug = new Map(graphModels.map(m => [m.slug, m]));
  const selected = new Set();
  const search = document.getElementById('g-search');
  const results = document.getElementById('g-results');
  const notice = document.getElementById('g-message');
  const plot = document.getElementById('g-plot');
  const legend = document.getElementById('g-legend');
  const bars = document.getElementById('g-bars');
  const details = document.getElementById('g-details');
  const scale = document.getElementById('g-scale');
  const svgNS = 'http://www.w3.org/2000/svg';

  function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  function svg(tag, attributes, text) {
    const el = document.createElementNS(svgNS, tag);
    for (const [key, val] of Object.entries(attributes)) el.setAttribute(key, String(val));
    if (text !== undefined) el.textContent = text;
    plot.appendChild(el);
    return el;
  }
  function number(value) {
    return Number.isFinite(value) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: 2}) : 'unknown';
  }
  function price(value) {
    return Number.isFinite(value) ? '$' + number(value) + '/1M' : 'cost unknown';
  }
  function label(m) {
    const suffix = m.variant && !m.id.toLowerCase().endsWith(' (' + m.variant.toLowerCase() + ')') ?
      ' (' + m.variant + ')' : '';
    return m.id + (suffix || (!m.variant && m.ambiguous ? ' (ambiguous effort)' : ''));
  }
  function chosen() {
    return Array.from(selected, slug => bySlug.get(slug)).filter(Boolean);
  }

  function renderResults() {
    const query = search.value.trim().toLowerCase();
    const matches = graphModels.filter(m => (m.id + ' ' + m.name + ' ' + m.variant).toLowerCase().includes(query));
    results.replaceChildren();
    for (const m of matches.slice(0, 60)) {
      const active = selected.has(m.slug);
      const button = element('button', label(m) + ' · ' + number(m.score) + ' · ' + price(m.cost));
      button.type = 'button';
      button.setAttribute('aria-pressed', String(active));
      button.setAttribute('aria-label', (active ? 'Remove ' : 'Add ') + label(m));
      button.disabled = !active && selected.size >= maxSelected;
      button.addEventListener('click', () => {
        if (selected.has(m.slug)) selected.delete(m.slug);
        else if (selected.size < maxSelected) selected.add(m.slug);
        render();
      });
      results.appendChild(button);
    }
    const resultNote = matches.length > 60 ? ' Showing first 60 of ' + matches.length + ' matches; narrow the search.' :
      matches.length ? ' ' + matches.length + ' matches.' : ' No matching models.';
    notice.textContent = (selected.size === maxSelected ? 'Selection limit reached; remove a model to add another.' :
      'Choose models to compare.') + resultNote;
  }

  function renderPlot(models) {
    plot.replaceChildren();
    const valid = models.filter(m => Number.isFinite(m.score) && Number.isFinite(m.cost));
    const left = 79, right = 814, top = 30, bottom = 395;
    const maxScore = Math.max(60, ...valid.map(m => m.score));
    const maxCost = Math.max(1, ...valid.map(m => m.cost));
    const compress = scale.value === 'compressed';
    const costFraction = value => compress ? Math.log1p(value) / Math.log1p(maxCost) : value / maxCost;
    const costTick = fraction => compress ? Math.expm1(fraction * Math.log1p(maxCost)) : fraction * maxCost;
    for (let tick = 0; tick <= 4; tick++) {
      const x = left + tick * (right - left) / 4;
      const y = bottom - tick * (bottom - top) / 4;
      svg('line', {x1: x, y1: top, x2: x, y2: bottom, stroke: '#334155'});
      svg('line', {x1: left, y1: y, x2: right, y2: y, stroke: '#334155'});
      svg('text', {x: x, y: bottom + 23, fill: '#cbd5e1', 'text-anchor': 'middle', 'font-size': 13}, number(tick * maxScore / 4));
      svg('text', {x: left - 8, y: y + 4, fill: '#cbd5e1', 'text-anchor': 'end', 'font-size': 13}, '$' + number(costTick(tick / 4)));
    }
    svg('text', {x: (left + right) / 2, y: 447, fill: '#e2e8f0', 'text-anchor': 'middle', 'font-size': 15}, 'AA Intelligence Index (higher →)');
    svg('text', {x: 15, y: (top + bottom) / 2, fill: '#e2e8f0', 'text-anchor': 'middle', 'font-size': 15,
      transform: 'rotate(-90 15 ' + ((top + bottom) / 2) + ')'}, 'Blended $/1M tokens (cheaper ↓)');
    if (!valid.length) {
      svg('text', {x: 440, y: 205, fill: '#94a3b8', 'text-anchor': 'middle', 'font-size': 16},
        models.length ? 'No selected models have both score and price.' : 'Select models above to draw the graph.');
    }
    for (const m of valid) {
      const index = models.indexOf(m);
      const x = left + Math.max(0, m.score) / maxScore * (right - left);
      const y = bottom - Math.max(0, costFraction(m.cost)) * (bottom - top);
      const point = svg('circle', {cx: x, cy: y, r: 11, fill: colors[index], stroke: '#020617', 'stroke-width': 2});
      const title = document.createElementNS(svgNS, 'title');
      title.textContent = label(m) + ': score ' + number(m.score) + (m.estimate ? ' (estimate)' : '') + ', ' + price(m.cost);
      point.appendChild(title);
      svg('text', {x: x, y: y + 4, fill: '#020617', 'text-anchor': 'middle', 'font-weight': 'bold',
        'font-size': 11, 'pointer-events': 'none'}, String(index + 1));
    }
  }

  function renderBars(models) {
    bars.replaceChildren();
    if (!models.length) return;
    const maxScore = Math.max(60, ...models.filter(m => Number.isFinite(m.score)).map(m => m.score));
    const maxCost = Math.max(1, ...models.filter(m => Number.isFinite(m.cost)).map(m => m.cost));
    for (const [heading, field, maximum, format] of [
      ['Score (higher is better)', 'score', maxScore, number],
      ['Blended price (lower is cheaper)', 'cost', maxCost, price]]) {
      const panel = element('div');
      panel.appendChild(element('h3', heading));
      models.forEach((m, index) => {
        const row = element('div', undefined, 'g-bar-row');
        const name = element('span', (index + 1) + '. ' + label(m));
        name.title = label(m);
        const track = element('div', undefined, 'g-bar-track');
        if (Number.isFinite(m[field])) {
          const fill = element('div', undefined, 'g-bar-fill');
          fill.style.width = Math.max(0, Math.min(100, m[field] / maximum * 100)) + '%';
          fill.style.background = colors[index];
          track.appendChild(fill);
        }
        row.append(name, track, element('span', format(m[field]) + (field === 'score' && m.estimate ? ' estimate' : '')));
        panel.appendChild(row);
      });
      bars.appendChild(panel);
    }
  }

  function renderDetails(models) {
    details.replaceChildren();
    legend.replaceChildren();
    if (!models.length) {
      details.appendChild(element('p', 'No models selected. Search above to add them.', 'note'));
      return;
    }
    const table = element('table');
    const head = element('thead');
    const header = element('tr');
    for (const col of ['Model', 'Score', 'Blended $/1M', 'Free status', 'Route ID / selector', '']) {
      header.appendChild(element('th', col));
    }
    head.appendChild(header);
    const body = element('tbody');
    models.forEach((m, index) => {
      const item = element('span', (index + 1) + '. ' + label(m));
      item.style.borderLeft = '5px solid ' + colors[index];
      legend.appendChild(item);
      const row = element('tr');
      const flags = (m.deprecated ? ' · deprecated-upstream' : '') + (m.modality_unverified ? ' · modality-unverified' : '');
      row.appendChild(element('td', label(m) + flags));
      row.appendChild(element('td', number(m.score) + (m.estimate ? ' (estimate)' : '')));
      row.appendChild(element('td', price(m.cost) + ' [' + m.cost_source + ']'));
      row.appendChild(element('td', m.free_status === 'verified' ? 'F verified' :
        m.free_status.startsWith('provisional') ? 'F? ' + m.free_status : 'not free'));
      row.appendChild(element('td', m.route || 'AA-only / no callable ID'));
      const actions = element('td');
      if (m.route) {
        const copy = element('button', 'Copy ID');
        copy.type = 'button';
        copy.addEventListener('click', async () => {
          try {
            await navigator.clipboard.writeText(m.route);
            notice.textContent = 'Copied ' + m.route;
          } catch (_) {
            notice.textContent = 'Clipboard unavailable; select the route text in the table to copy it.';
          }
        });
        actions.appendChild(copy);
      }
      const remove = element('button', 'Remove ' + (index + 1));
      remove.type = 'button';
      remove.setAttribute('aria-label', 'Remove ' + label(m));
      remove.addEventListener('click', () => { selected.delete(m.slug); render(); });
      actions.appendChild(remove);
      row.appendChild(actions);
      body.appendChild(row);
    });
    table.append(head, body);
    details.appendChild(table);
  }

  function render() {
    const models = chosen();
    document.getElementById('g-count').textContent = models.length + '/' + maxSelected + ' selected';
    renderResults();
    renderPlot(models);
    renderBars(models);
    renderDetails(models);
  }
  search.addEventListener('input', renderResults);
  scale.addEventListener('change', () => renderPlot(chosen()));
  document.getElementById('g-clear').addEventListener('click', () => { selected.clear(); render(); });
  render();
})();
