const colors = ['#82b6ff', '#66d2b0', '#edbd74', '#b6a4f2', '#e68da5', '#78cddd'];
const $ = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const svgEl = (tag, attrs = {}, text) => {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== undefined) e.textContent = text;
  return e;
};
const number = v => v == null ? '—' : new Intl.NumberFormat('en', {
  maximumSignificantDigits: 5
}).format(v);
const time = (v, full = false) => v == null ? 'Not recorded' : new Intl.DateTimeFormat('en-GB', {
  timeZone: 'UTC',
  ...(full ? {
    year: 'numeric',
    month: 'short',
    day: '2-digit'
  } : {}),
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23'
}).format(new Date(v));
const age = (at, now) => {
  if (at == null) return 'No receipt recorded';
  const d = (now - at) / 1000;
  if (d < 0) return 'Future timestamp';
  if (d < 60) return `${Math.round(d)}s ago`;
  if (d < 3600) return `${Math.floor(d/60)}m ago`;
  return `${Math.floor(d/3600)}h ago`;
};
const icon = name => {
  const p = {
    search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0a8 8 0 1 1 16 0',
    arrow: 'M5 12h14 M13 6l6 6-6 6',
    chevron: 'M6 9l6 6 6-6',
    refresh: 'M20 7v5h-5 M4 17v-5h5 M6 7a7 7 0 0 1 12-2l2 2 M18 17a7 7 0 0 1-12 2l-2-2',
    close: 'M6 6l12 12 M18 6L6 18',
    plus: 'M12 5v14 M5 12h14',
    check: 'M5 12l4 4L19 6'
  };
  const e = svgEl('svg', {
    viewBox: '0 0 24 24',
    width: 16,
    height: 16,
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': 1.6,
    'aria-hidden': true
  });
  e.append(svgEl('path', {
    d: p[name] || p.arrow,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round'
  }));
  return e;
};

function render({
  model,
  el
}) {
  const doc = el.ownerDocument;
  let s = model.get('snapshot'),
    query = '',
    cleanChart = () => {},
    sequence = 0;
  const root = $('div', 'mw-shell');
  el.replaceChildren(root);
  const emit = (kind, values = {}) => {
    const active = root.getRootNode().activeElement || doc.activeElement;
    if (active && active.tagName === 'BUTTON') {
      sessionStorage.setItem('phm-monitor-active-control', active.getAttribute('aria-label') || active.textContent.trim());
    }
    root.classList.add('mw-pending');
    model.set('event', {
      kind,
      ...values,
      sequence: ++sequence
    });
    model.save_changes();
  };
  const button = (text, action, cls = 'mw-button') => {
    const b = $('button', cls, text);
    b.type = 'button';
    b.addEventListener('click', action);
    return b;
  };
  const selected = () => [s.focus, ...(s.comparisons || [])].filter(Boolean);

  function draw() {
    cleanChart();
    s = model.get('snapshot');
    root.replaceChildren();
    root.classList.remove('mw-pending');
    root.dataset.currentInvestigation = s.active_investigation?.[1] || '';
    const nav = $('header', 'mw-topbar');
    const brand = $('div', 'mw-brand');
    brand.append($('span', 'mw-brand-mark', '∿'), $('span', '', 'INDUSTRIAL'), $('span', 'mw-brand-sub', 'PHM'));
    nav.append(brand);
    const links = $('nav', 'mw-pages');
    links.setAttribute('aria-label', 'Operations pages');
    for (const page of s.pages) {
      const b = button(page, () => emit('navigate', {
        page
      }), 'mw-page' + (s.page === page ? ' mw-active' : ''));
      b.setAttribute('aria-current', s.page === page ? 'page' : 'false');
      links.append(b);
    }
    nav.append(links);
    const refresh = button('', () => emit('refresh'), 'mw-refresh');
    refresh.append(icon('refresh'), $('span', '', 'Refresh'));
    refresh.setAttribute('aria-label', 'Refresh observations');
    nav.append(refresh);
    root.append(nav);
    if (s.page !== 'Monitor') return;
    const title = $('section', 'mw-context');
    const identity = $('div', 'mw-identity');
    identity.append($('div', 'mw-eyebrow', 'OPERATIONS / MONITOR'));
    const asset = button('', () => openAssets(), 'mw-asset');
    asset.append($('h1', '', s.asset_name || 'Choose an asset'), icon('chevron'));
    asset.setAttribute('aria-label', 'Choose asset');
    identity.append(asset);
    const subtitle = $('div', 'mw-context-sub');
    subtitle.append($('span', '', s.asset_name !== s.asset_id ? s.asset_id : `${s.stored_signal_count} stored signals · observation snapshot`));
    identity.append(subtitle);
    title.append(identity);
    const flow = $('div', 'mw-flow');
    const status = $('span', 'mw-status' + (s.status === 'Receiving' ? ' mw-receiving' : ''));
    status.append($('i', ''), $('span', '', s.status || 'No source context'));
    flow.append(status);
    const receipt = $('div', 'mw-receipt');
    receipt.append($('span', 'mw-muted', 'SOURCE RECEIPT'), $('strong', '', age(s.source_at, s.assessed_at)), $('span', 'mw-muted', s.source_at ? `${time(s.source_at,true)} UTC` : 'No receive timestamp'));
    flow.append(receipt);
    title.append(flow);
    root.append(title);
    const workspace = $('section', 'mw-workspace');
    const explorer = $('aside', 'mw-explorer');
    explorer.setAttribute('aria-label', 'Signal explorer');
    const explorerHead = $('div', 'mw-explorer-head');
    explorerHead.append($('h2', '', 'Signals'), $('span', 'mw-count', String(s.signals.length)));
    explorer.append(explorerHead);
    const searchWrap = $('div', 'mw-search');
    searchWrap.append(icon('search'));
    const search = $('input');
    search.type = 'search';
    search.placeholder = 'Find a signal';
    search.setAttribute('aria-label', 'Find a signal');
    query = sessionStorage.getItem('phm-monitor-search:' + s.asset_id) || '';
    search.value = query;
    searchWrap.append(search);
    explorer.append(searchWrap);
    const list = $('div', 'mw-signal-list');
    explorer.append(list);
    const footer = $('div', 'mw-explorer-foot');
    footer.append($('span', '', 'Select a signal to inspect'), $('span', 'mw-muted', 'Use + to compare · up to 6 signals'));
    explorer.append(footer);

    function listSignals() {
      list.replaceChildren();
      const groups = new Map();
      const filtered = s.signals.filter(row => [row.channel, row.observed_property, row.scope, row.source].join(' ').toLowerCase().includes(query.toLowerCase()));
      for (const row of filtered) {
        const group = row.observed_property && row.observed_property !== 'unresolved' ? row.observed_property : 'Unresolved signals';
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(row);
      }
      const focusGroup = s.signals.find(row => row.channel === s.focus)?.observed_property;
      const orderedGroups = [...groups].sort(([a], [b]) => (a === focusGroup ? -1 : b === focusGroup ? 1 : 0) || (a === 'Unresolved signals' ? 1 : b === 'Unresolved signals' ? -1 : a.localeCompare(b)));
      for (const [name, rows] of orderedGroups) {
        const group = $('section', 'mw-signal-group');
        group.append($('h3', '', name), $('span', 'mw-group-count', String(rows.length)));
        for (const row of rows) {
          const isFocus = s.focus === row.channel,
            isSelected = selected().includes(row.channel);
          const item = $('div', 'mw-signal' + (isFocus ? ' mw-focused' : isSelected ? ' mw-compared' : ''));
          const pick = button('', () => emit('focus', {
            channel: row.channel
          }), 'mw-signal-pick');
          pick.setAttribute('aria-label', `Inspect ${row.channel}`);
          pick.setAttribute('aria-pressed', String(isFocus));
          const info = $('div', 'mw-signal-info');
          info.append($('strong', '', row.scope || row.channel), $('span', 'mw-signal-id', (row.scope || (row.observed_property && row.observed_property !== 'unresolved')) ? row.channel : 'Meaning not confirmed'));
          const val = $('div', 'mw-signal-reading');
          val.append($('strong', '', number(row.value)), $('span', '', row.unit === 'unknown' ? '' : row.unit || ''));
          pick.append(info, val);
          pick.title = `${row.source}${row.measurement_point?' / '+row.measurement_point:''}\nEvent: ${row.time||'not recorded'}\nQuality: ${row.source_quality} · ${row.quality}`;
          const compare = button('', () => {
            let channels = [...(s.comparisons || [])];
            if (channels.includes(row.channel)) channels = channels.filter(c => c !== row.channel);
            else if (channels.length < 5) channels.push(row.channel);
            emit('compare', {
              channels
            });
          }, 'mw-compare');
          compare.append(icon(isSelected ? 'check' : 'plus'));
          compare.disabled = isFocus || (!isSelected && (s.comparisons || []).length >= 5);
          compare.setAttribute('aria-label', `Compare ${row.channel}`);
          compare.setAttribute('aria-pressed', String(isSelected));
          item.append(pick, compare);
          group.append(item);
        }
        list.append(group);
      }
      if (!filtered.length) list.append($('div', 'mw-empty', 'No matching signals. Try a channel or measurement name.'));
    }
    search.addEventListener('input', () => {
      query = search.value;
      sessionStorage.setItem('phm-monitor-search:' + s.asset_id, query);
      listSignals();
    });
    listSignals();
    const main = $('main', 'mw-main');
    const toolbar = $('div', 'mw-chart-toolbar');
    const label = $('div');
    label.append($('div', 'mw-eyebrow', 'OBSERVATION WORKSPACE'), $('h2', '', 'Signal comparison'));
    toolbar.append(label);
    const periods = $('div', 'mw-periods');
    periods.setAttribute('role', 'group');
    periods.setAttribute('aria-label', 'Event-time range');
    for (const period of ['15m', '1h', '24h', '7d']) {
      const b = button(period, () => emit('range', {
        range: period
      }), 'mw-period' + (s.range === period ? ' mw-selected' : ''));
      b.setAttribute('aria-pressed', String(s.range === period));
      periods.append(b);
    }
    toolbar.append(periods);
    main.append(toolbar);
    const readings = $('div', 'mw-readings');
    for (const [i, channel] of selected().entries()) {
      const rows = s.signals.filter(row => row.channel === channel);
      for (const row of rows) {
        const reading = $('article', 'mw-reading');
        reading.style.setProperty('--series-color', colors[i % colors.length]);
        const head = $('div', 'mw-reading-label');
        head.append($('i', ''), $('span', '', row.channel));
        if (channel !== s.focus) {
          const remove = button('', () => emit('compare', {
            channels: (s.comparisons || []).filter(c => c !== channel)
          }), 'mw-remove');
          remove.append(icon('close'));
          remove.setAttribute('aria-label', `Remove ${channel}`);
          head.append(remove);
        }
        reading.append(head);
        const value = $('div', 'mw-reading-value');
        value.append($('strong', '', number(row.value)), $('span', '', row.unit === 'unknown' ? 'unit unknown' : row.unit || ''));
        reading.append(value);
        let quality = row.quality === 'no recorded issue' ? row.source_quality : row.quality;
        if (row.event_time_state && row.event_time_state !== 'recorded') quality += ` · event time ${row.event_time_state}`;
        const meta = $('div', 'mw-reading-meta');
        meta.append($('span', quality === 'good' ? 'mw-good' : '', `Quality · ${quality||'unknown'}`), $('time', '', row.time ? time(Date.parse(row.time), true) + ' UTC' : 'Event time unavailable'));
        meta.title = `Event: ${row.time||'not recorded'}\n${row.source}${row.measurement_point?' / '+row.measurement_point:''}\n${row.event_time_state}`;
        reading.append(meta);
        readings.append(reading);
      }
    }
    main.append(readings);
    const clock = $('div', 'mw-chart-clock');
    clock.append($('span', '', 'STORED EVENT TIME · UTC'), $('span', '', s.chart ? `${time(s.chart.start,true)} — ${time(s.chart.end,true)}` : 'No event-time window'));
    main.append(clock);
    const chart = $('div', 'mw-plot');
    chart.setAttribute('role', 'img');
    chart.setAttribute('aria-label', 'Recorded signal comparison');
    main.append(chart);
    cleanChart = drawChart(chart, s.chart, s.evidence || [], id => emit("evidence", {
      id
    }));
    const explanation = $('div', 'mw-chart-caption');
    explanation.append($('span', '', 'Mean · min/max · shading: analysis window · amber: exclusions'), $('span', 'mw-muted', 'Bucket summaries are not synchronized raw samples'));
    main.append(explanation);
    const bottom = $('div', 'mw-main-bottom');
    bottom.append($('span', 'mw-muted', `Snapshot ${time(s.assessed_at)} UTC · use Refresh for new observations`));
    const detail = button('Inspect selected signal', () => emit('detail'), 'mw-text-action');
    detail.append(icon('arrow'));
    bottom.append(detail);
    main.append(bottom);
    workspace.append(explorer, main);
    root.append(workspace);
    const supporting = $('section', 'mw-support');
    const evidence = $('div', 'mw-evidence');
    const evidenceHead = $('div', 'mw-panel-head');
    evidenceHead.append($('h2', '', 'Analysis evidence'), $('span', 'mw-muted', 'In this event-time window'));
    evidence.append(evidenceHead);
    for (const item of s.evidence || []) {
      const b = button('', () => emit('evidence', {
        id: item.id
      }), 'mw-evidence-row');
      b.dataset.evidenceId = item.id;
      const name = $('div');
      name.append($('strong', '', item.label), $('span', 'mw-muted', `${time(item.start)} — ${time(item.end)} UTC`));
      b.append($('span', 'mw-evidence-mark', '↗'), name, $('span', 'mw-review-state', item.review), icon('arrow'));
      evidence.append(b);
    }
    if (!(s.evidence || []).length) evidence.append($('div', 'mw-empty', 'No persisted analysis overlaps this window.'));
    const attention = $('div', 'mw-attention');
    const attentionHead = $('div', 'mw-panel-head');
    attentionHead.append($('h2', '', 'Needs inspection'), $('span', 'mw-count', String((s.attention || []).length)));
    attention.append(attentionHead);
    for (const item of s.attention || []) {
      const b = button('', () => emit('attention', {
        id: item.id
      }), 'mw-attention-row');
      b.append($('span', 'mw-category', item.category), $('span', '', item.title), icon('arrow'));
      b.title = item.detail;
      attention.append(b);
    }
    if (!(s.attention || []).length) attention.append($('div', 'mw-empty', 'No recorded inspection items for this context.'));
    supporting.append(evidence, attention);
    root.append(supporting);
    if (s.error) {
      const error = $('div', 'mw-error');
      error.setAttribute('role', 'alert');
      error.textContent = s.error;
      main.prepend(error);
    }
    const activeLabel = sessionStorage.getItem('phm-monitor-active-control');
    const activeControl = [...root.querySelectorAll('button')].find(button =>
      (button.getAttribute('aria-label') || button.textContent.trim()) === activeLabel);
    if (activeControl) activeControl.focus({
      preventScroll: true
    });

  }

  function openAssets() {
    const overlay = $('div', 'mw-overlay');
    const dialog = $('div', 'mw-asset-dialog');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-label', 'Choose an asset');
    dialog.setAttribute('aria-modal', 'true');
    const head = $('div', 'mw-panel-head');
    head.append($('h2', '', 'Choose an asset'));
    const close = button('', () => {
      overlay.remove();
      root.querySelector('.mw-asset').focus();
    }, 'mw-remove');
    close.append(icon('close'));
    close.setAttribute('aria-label', 'Close asset picker');
    head.append(close);
    dialog.append(head);
    const input = $('input', 'mw-asset-search');
    input.type = 'search';
    input.placeholder = 'Search assets';
    input.setAttribute('aria-label', 'Search assets');
    dialog.append(input);
    const list = $('div');
    dialog.append(list);
    const fill = () => {
      list.replaceChildren();
      for (const asset of s.assets.filter(a => (a.name + ' ' + a.id).toLowerCase().includes(input.value.toLowerCase()))) {
        const b = button('', () => emit('asset', {
          id: asset.id
        }), 'mw-asset-option');
        b.append($('strong', '', asset.name), $('span', 'mw-muted', asset.id));
        if (asset.id === s.asset_id) b.append(icon('check'));
        list.append(b);
      }
    };
    input.addEventListener('input', fill);
    fill();
    overlay.append(dialog);
    overlay.addEventListener('click', e => {
      if (e.target === overlay) overlay.remove();
    });
    dialog.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        overlay.remove();
        root.querySelector('.mw-asset').focus();
      }
      if (e.key === 'Tab') {
        const focusables = [...dialog.querySelectorAll('button,input')];
        if (e.shiftKey && document.activeElement === focusables[0]) {
          e.preventDefault();
          focusables.at(-1).focus();
        } else if (!e.shiftKey && document.activeElement === focusables.at(-1)) {
          e.preventDefault();
          focusables[0].focus();
        }
      }
    });
    root.append(overlay);
    input.focus();
  }
  model.on('change:snapshot', draw);
  draw();
  return () => {
    cleanChart();
    model.off('change:snapshot', draw);
  };
}

function drawChart(container, data, windows, onEvidence) {
  if (!data || !data.groups.length) {
    container.append($('div', 'mw-chart-empty', 'No stored observations in this window. Select an available signal or another range.'));
    return () => {};
  }
  const tooltip = $('div', 'mw-tooltip');
  tooltip.hidden = true;
  container.append(tooltip);
  let cleanup = [];
  const paint = () => {
    cleanup.forEach(fn => fn());
    cleanup = [];
    container.querySelectorAll('svg').forEach(e => e.remove());
    const W = Math.max(320, container.clientWidth),
      H = Math.max(270, data.groups.length * 200),
      left = 54,
      right = 18,
      top = 30,
      bottom = 36;
    const svg = svgEl('svg', {
      viewBox: `0 0 ${W} ${H}`,
      width: W,
      height: H,
      'aria-label': 'Stored bucket summaries'
    });
    container.append(svg);
    const x = t => left + (t - data.start) / (data.end - data.start) * (W - left - right);
    const cursors = [];
    data.groups.forEach((group, index) => {
      const panelH = (H - bottom) / data.groups.length,
        pTop = index * panelH + top,
        pBottom = (index + 1) * panelH - 15;
      const values = group.series.flatMap(series => series.buckets.filter(b => b.usable && b.mean != null).flatMap(b => [b.min, b.max])).filter(v => v != null);
      let low = values.length ? Math.min(...values) : 0,
        high = values.length ? Math.max(...values) : 1;
      if (low === high) {
        low -= Math.abs(low) * .05 || 1;
        high += Math.abs(high) * .05 || 1;
      } else {
        const pad = (high - low) * .07;
        low = low >= 0 ? Math.max(0, low - pad) : low - pad;
        high += pad;
      }
      const rough = (high - low) / 4,
        power = 10 ** Math.floor(Math.log10(rough)),
        base = rough / power,
        step = (base <= 1 ? 1 : base <= 2 ? 2 : base <= 5 ? 5 : 10) * power;
      low = Math.floor(low / step) * step;
      high = Math.ceil(high / step) * step;
      const y = v => pBottom - (v - low) / (high - low) * (pBottom - pTop);
      svg.append(svgEl('text', {
        x: left,
        y: pTop - 13,
        class: 'mw-axis-title'
      }, `${group.title} · ${group.unit}`));
      for (let value = low; value <= high + step / 100; value += step) {
        const py = y(value);
        svg.append(svgEl('line', {
          x1: left,
          x2: W - right,
          y1: py,
          y2: py,
          class: 'mw-grid'
        }), svgEl('text', {
          x: left - 10,
          y: py + 4,
          'text-anchor': 'end',
          class: 'mw-axis'
        }, number(value)));
      }
      for (const window of windows) {
        const begin = Math.max(data.start, window.start),
          end = Math.min(data.end, window.end);
        if (end < begin) continue;
        const shade = svgEl('rect', {
          x: x(begin),
          y: pTop,
          width: Math.max(2, x(end) - x(begin)),
          height: pBottom - pTop,
          fill: '#82b6ff',
          'fill-opacity': .07,
          role: 'button',
          tabindex: 0,
          'aria-label': `Open ${window.label} analysis evidence`
        });
        shade.append(svgEl('title', {}, `${window.label} · ${time(window.start)} — ${time(window.end)} UTC`));
        shade.addEventListener('click', () => onEvidence(window.id));
        shade.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onEvidence(window.id);
          }
        });
        svg.append(shade);
      }
      for (const series of group.series) {
        let path = '',
          previous = null;
        for (const b of series.buckets) {
          const mid = (b.start + b.end) / 2,
            px = x(mid);
          if (b.null || b.non_good || b.conflict) svg.append(svgEl('line', {
            x1: px,
            x2: px,
            y1: pBottom - 5,
            y2: pBottom,
            stroke: '#edbd74',
            'stroke-width': 2
          }));
          if (!b.usable || b.mean == null) {
            previous = null;
            continue;
          }
          const py = y(b.mean),
            continuous = previous !== null && b.start - previous <= (b.end - b.start) * 1.01;
          path += `${continuous?'L':'M'}${px.toFixed(2)},${py.toFixed(2)} `;
          previous = b.start;
          svg.append(svgEl('line', {
            x1: px,
            x2: px,
            y1: y(b.min),
            y2: y(b.max),
            stroke: series.color,
            'stroke-opacity': .24,
            'stroke-width': 2
          }));
          svg.append(svgEl('circle', {
            cx: px,
            cy: py,
            r: 2.4,
            fill: series.color
          }));
        }
        svg.append(svgEl('path', {
          d: path,
          fill: 'none',
          stroke: series.color,
          'stroke-width': 1.7,
          'stroke-linejoin': 'round',
          'stroke-dasharray': series.dash || 'none'
        }));
      }
      const cursor = svgEl('line', {
        x1: 0,
        x2: 0,
        y1: pTop,
        y2: pBottom,
        class: 'mw-crosshair',
        visibility: 'hidden'
      });
      svg.append(cursor);
      cursors.push(cursor);
      if (!values.length) svg.append(svgEl('text', {
        x: (W + left) / 2,
        y: (pTop + pBottom) / 2,
        'text-anchor': 'middle',
        class: 'mw-axis'
      }, 'No usable bucket values'));
    });
    for (let i = 0; i < 5; i++) {
      const t = data.start + (data.end - data.start) * i / 4;
      svg.append(svgEl('text', {
        x: x(t),
        y: H - 9,
        'text-anchor': i === 0 ? 'start' : i === 4 ? 'end' : 'middle',
        class: 'mw-axis'
      }, time(t).slice(0, 5)));
    }
    const move = e => {
      const rect = svg.getBoundingClientRect(),
        px = (e.clientX - rect.left) * W / rect.width;
      if (px < left || px > W - right) {
        hide();
        return;
      }
      const at = data.start + (px - left) / (W - left - right) * (data.end - data.start);
      cursors.forEach(c => {
        c.setAttribute('x1', px);
        c.setAttribute('x2', px);
        c.setAttribute('visibility', 'visible');
      });
      tooltip.replaceChildren($('div', 'mw-tooltip-title', `BUCKET SUMMARY · ${time(at)} UTC`));
      let hits = 0;
      for (const group of data.groups)
        for (const series of group.series) {
          const b = series.buckets.find(b => at >= b.start && at < b.end);
          if (!b) continue;
          const row = $('div', 'mw-tooltip-row');
          row.append($('span', '', series.channel), $('strong', '', b.usable ? `${number(b.mean)} ${group.unit}` : 'No usable value'));
          row.style.setProperty('--series-color', series.color);
          tooltip.append(row);
          tooltip.append($('div', 'mw-tooltip-source', `${series.source}${series.point?' / '+series.point:''} · ${b.usable} usable · null ${b.null} · non-good ${b.non_good} · conflict ${b.conflict}`));
          hits++;
        }
      if (!hits) tooltip.append($('div', 'mw-muted', 'No observations in this bucket.'));
      tooltip.hidden = false;
      tooltip.style.left = Math.max(8, Math.min(container.clientWidth - 300, px + 12)) + 'px';
      tooltip.style.top = '34px';
    };
    const hide = () => {
      tooltip.hidden = true;
      cursors.forEach(c => c.setAttribute('visibility', 'hidden'));
    };
    svg.addEventListener('pointermove', move);
    svg.addEventListener('pointerleave', hide);
    cleanup.push(() => {
      svg.removeEventListener('pointermove', move);
      svg.removeEventListener('pointerleave', hide);
    });
  };
  const observer = new ResizeObserver(paint);
  observer.observe(container);
  paint();
  return () => {
    observer.disconnect();
    cleanup.forEach(fn => fn());
  };
}
export default {
  render
};
