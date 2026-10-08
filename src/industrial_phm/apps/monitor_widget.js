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
let activeLocale = 'en-US';
let activeMessages = {};
const t = (key, fallback = key) => activeMessages[key] ?? fallback;
const number = v => v == null ? '—' : new Intl.NumberFormat(activeLocale, {
  maximumSignificantDigits: 5
}).format(v);
const time = (v, full = false) => v == null ? t('monitor.not_recorded', 'Not recorded') : new Intl.DateTimeFormat(activeLocale, {
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
const shortTime = v => v == null ? t('monitor.not_recorded', 'Not recorded') : new Intl.DateTimeFormat(activeLocale, {
  timeZone: 'UTC',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23'
}).format(new Date(v));
const age = (at, now) => {
  if (at == null) return t('monitor.no_receipt_recorded', 'No receipt recorded');
  const d = (now - at) / 1000;
  if (d < 0) return t('monitor.future_timestamp', 'Future timestamp');
  if (activeLocale === 'ko-KR') {
    if (d < 60) return `${Math.round(d)}초 전`;
    if (d < 3600) return `${Math.floor(d/60)}분 전`;
    return `${Math.floor(d/3600)}시간 전`;
  }
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
    sequence = 0,
    disabledControls = new Map(),
    pendingTimer = null,
    lastActionError = "";
  const root = $('div', 'mw-shell');
  el.replaceChildren(root);
  const emit = (kind, values = {}) => {
    if (root.classList.contains('mw-pending')) return;
    if ((kind === 'focus' && values.channel === s.focus) || (kind === 'range' && values.range === s.range) ||
      (kind === 'navigate' && values.page === s.page)) return;
    if (kind === 'asset' && values.id === s.asset_id) {
      root.querySelector('.mw-overlay')?.remove();
      root.querySelector('.mw-asset')?.focus();
      return;
    }

    const active = root.getRootNode().activeElement || doc.activeElement;
    if (active && active.tagName === 'BUTTON') {
      sessionStorage.setItem('phm-monitor-active-control', active.getAttribute('aria-label') || active.textContent.trim());
    }
    clearTimeout(pendingTimer);
    root.querySelector('.mw-action-error')?.remove();
    lastActionError = '';
    root.classList.add('mw-pending');
    disabledControls = new Map([...root.querySelectorAll('button,input')].map(control => [control, control.disabled]));
    disabledControls.forEach((_, control) => {
      control.disabled = true;
    });
    pendingTimer = setTimeout(() => showActionError(t('monitor.update_timeout', 'The view did not finish updating. Refresh to retry.')), 15000);
    model.set('event', {
      kind,
      ...values,
      sequence: ++sequence
    });
    model.save_changes();
  };

  function showActionError(message) {
    clearTimeout(pendingTimer);
    root.classList.remove('mw-pending');
    disabledControls.forEach((disabled, control) => {
      control.disabled = disabled;
    });
    disabledControls.clear();
    root.querySelector('.mw-action-error')?.remove();
    lastActionError = message;
    if (!message) return;
    const error = $('div', 'mw-error mw-action-error');
    error.setAttribute('role', 'alert');
    error.append($('span', '', message));
    const retry = $('button', 'mw-text-action', t('monitor.retry_refresh', 'Retry refresh'));
    retry.type = 'button';
    retry.addEventListener('click', () => emit('refresh'));
    error.append(retry);
    root.querySelector('.mw-main')?.prepend(error);
  }
  const onResponse = () => {
    const reply = model.get('response');
    if (reply.sequence !== sequence) return;
    if (reply.status !== 'ok') showActionError(reply.message || t('monitor.update_failed', 'The update failed. Refresh to retry.'));
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
    clearTimeout(pendingTimer);
    s = model.get('snapshot');
    activeLocale = s.locale || 'en-US';
    activeMessages = s.messages || {};
    root.lang = activeLocale;
    root.dataset.locale = activeLocale;
    root.replaceChildren();
    root.classList.remove('mw-pending');
    root.dataset.currentInvestigation = s.active_investigation?.[1] || '';
    const nav = $('header', 'mw-topbar');
    const brand = $('div', 'mw-brand');
    brand.append($('span', 'mw-brand-mark', '∿'), $('span', '', 'INDUSTRIAL'), $('span', 'mw-brand-sub', 'PHM'));
    nav.append(brand);
    const links = $('nav', 'mw-pages');
    links.setAttribute('aria-label', t('monitor.operations_pages', 'Operations pages'));
    for (const page of s.pages) {
      const b = button(s.page_labels?.[page] || page, () => emit('navigate', {
        page
      }), 'mw-page' + (s.page === page ? ' mw-active' : ''));
      b.setAttribute('aria-current', s.page === page ? 'page' : 'false');
      links.append(b);
    }
    nav.append(links);
    const refresh = button('', () => emit('refresh'), 'mw-refresh');
    refresh.append(icon('refresh'), $('span', '', t('monitor.refresh', 'Refresh')));
    refresh.setAttribute('aria-label', t('monitor.refresh_aria', 'Refresh observations'));
    nav.append(refresh);
    root.append(nav);
    if (s.page !== 'monitor') return;
    const title = $('section', 'mw-context');
    const identity = $('div', 'mw-identity');
    identity.append($('div', 'mw-eyebrow', t('monitor.eyebrow', 'OPERATIONS / MONITOR')));
    const asset = button('', () => openAssets(), 'mw-asset');
    asset.append($('h1', '', s.asset_name || t('monitor.choose_asset', 'Choose an asset')), icon('chevron'));
    asset.setAttribute('aria-label', t('monitor.choose_asset_aria', 'Choose asset'));
    identity.append(asset);
    const subtitle = $('div', 'mw-context-sub');
    subtitle.append($('span', '', s.asset_name !== s.asset_id
      ? s.asset_id
      : t('monitor.stored_signals_snapshot', '{count} stored signals · observation snapshot')
          .replace('{count}', String(s.stored_signal_count))));
    identity.append(subtitle);
    title.append(identity);
    const flow = $('div', 'mw-flow');
    const status = $('span', 'mw-status' + (s.status_id === 'running' ? ' mw-receiving' : ''));
    // The badge is source session evidence, named as on Signals.
    const flowState = s.status_id === 'no-source-context'
      ? t('monitor.no_source_context', 'No source context')
      : `${t('monitor.source_flow', 'Source flow')} · ${s.status}`;
    status.append($('i', ''), $('span', '', flowState));
    flow.append(status);
    const receipt = $('div', 'mw-receipt');
    receipt.append(
      $('span', 'mw-muted', t('monitor.source_receipt', 'SOURCE RECEIPT')),
      $('strong', '', age(s.source_at, s.assessed_at)),
      $('span', 'mw-muted', s.source_at ? `${time(s.source_at,true)} UTC` : t('monitor.no_receive_timestamp', 'No receive timestamp'))
    );
    flow.append(receipt);
    const assessment = $('div', 'mw-assessment', `${t('monitor.status_at', 'Status at')} ${time(s.assessed_at,true)} UTC`);
    assessment.append($('span', 'mw-muted', t('monitor.manual_snapshot', 'Manual snapshot · Refresh to reassess')));
    flow.append(assessment);
    title.append(flow);
    root.append(title);
    const workspace = $('section', 'mw-workspace');
    const explorer = $('aside', 'mw-explorer');
    explorer.setAttribute('aria-label', t('monitor.signal_explorer', 'Signal explorer'));
    const explorerHead = $('div', 'mw-explorer-head');
    explorerHead.append($('h2', '', t('monitor.signals', 'Signals')), $('span', 'mw-count', String(s.signals.length)));
    explorer.append(explorerHead);
    const searchWrap = $('div', 'mw-search');
    searchWrap.append(icon('search'));
    const search = $('input');
    search.type = 'search';
    search.placeholder = t('monitor.find_signal', 'Find a signal');
    search.setAttribute('aria-label', t('monitor.find_signal', 'Find a signal'));
    query = sessionStorage.getItem('phm-monitor-search:' + s.asset_id) || '';
    search.value = query;
    searchWrap.append(search);
    explorer.append(searchWrap);
    const list = $('div', 'mw-signal-list');
    explorer.append(list);
    const footer = $('div', 'mw-explorer-foot');
    footer.append($('span', '', t('monitor.select_signal', 'Select a signal to inspect')), $('span', 'mw-muted', t('monitor.compare_help', 'Use + to compare · up to 6 signals')));
    explorer.append(footer);

    function listSignals() {
      list.replaceChildren();
      const groups = new Map();
      const filtered = s.signals.filter(row => [row.channel, row.observed_property, row.scope, row.source].join(' ').toLowerCase().includes(query.toLowerCase()));
      const catalog = new Map();
      for (const row of filtered) {
        if (!catalog.has(row.channel)) catalog.set(row.channel, []);
        catalog.get(row.channel).push(row);
      }
      for (const [channel, origins] of catalog) {
        const row = {
          ...origins[0],
          origins
        };
        const meanings = new Set(origins.map(item => item.observed_property || 'unresolved'));
        const group = meanings.size > 1 ? 'Multiple recorded meanings' :
          row.observed_property && row.observed_property !== 'unresolved' ? row.observed_property : 'Unresolved signals';
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(row);
      }
      const focusGroup = s.signals.find(row => row.channel === s.focus)?.observed_property;
      const unresolvedGroup = t('monitor.group_unresolved', 'Unresolved signals');
    const orderedGroups = [...groups].sort(([a], [b]) =>
      (a === focusGroup ? -1 : b === focusGroup ? 1 : 0)
      || (a === unresolvedGroup ? 1 : b === unresolvedGroup ? -1 : a.localeCompare(b))
    );
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
          pick.setAttribute(
      'aria-label',
      t('monitor.inspect_channel', 'Inspect {channel}').replace('{channel}', row.channel)
    );
          pick.setAttribute('aria-pressed', String(isFocus));
          const info = $('div', 'mw-signal-info');
          info.append(
      $('strong', '', row.origins.length > 1 ? row.channel : row.scope || row.channel),
      $('span', 'mw-signal-id',
        row.origins.length > 1
          ? t('monitor.all_origins', 'All origins · {count} source/point records')
              .replace('{count}', String(row.origins.length))
          : (row.scope || (row.observed_property && row.observed_property !== 'unresolved'))
            ? row.channel
            : t('monitor.meaning_not_confirmed', 'Meaning not confirmed')
      )
    );
          const val = $('div', 'mw-signal-reading');
          val.append(
      $('strong', '',
        row.origins.length > 1
          ? t('monitor.origins', '{count} origins').replace('{count}', String(row.origins.length))
          : number(row.value)
      ),
      $('span', '',
        row.origins.length > 1
          ? t('monitor.kept_separate', 'kept separate')
          : row.unit === 'unknown' ? '' : row.unit || ''
      )
    );
          pick.append(info, val);
          pick.title = row.origins.map(origin =>
      `${origin.source}${origin.measurement_point ? ' / ' + origin.measurement_point : ''} · `
      + `${t('monitor.event', 'Event')}: ${origin.time || t('monitor.not_recorded', 'Not recorded')} · `
      + `${t('monitor.quality', 'Quality')}: ${origin.source_quality}`
    ).join('\n');
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
          compare.setAttribute(
      'aria-label',
      t('monitor.compare_channel', 'Compare {channel}').replace('{channel}', row.channel)
    );
          compare.setAttribute('aria-pressed', String(isSelected));
          item.append(pick, compare);
          group.append(item);
        }
        list.append(group);
      }
      if (!filtered.length) list.append($('div', 'mw-empty', t('monitor.no_matching_signals', 'No matching signals. Try a channel or measurement name.')));
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
    label.append($('div', 'mw-eyebrow', t('monitor.observation_workspace', 'OBSERVATION WORKSPACE')), $('h2', '', t('monitor.signal_comparison', 'Signal comparison')));
    toolbar.append(label);
    const periods = $('div', 'mw-periods');
    periods.setAttribute('role', 'group');
    periods.setAttribute('aria-label', t('monitor.event_time_range', 'Event-time range'));
    for (const period of ['15m', '1h', '24h', '7d']) {
      const b = button(period, () => emit('range', {
        range: period
      }), 'mw-period' + (s.range === period ? ' mw-selected' : ''));
      b.setAttribute('aria-pressed', String(s.range === period));
      periods.append(b);
    }
    toolbar.append(periods);
    main.append(toolbar);
    main.append($('div', 'mw-origin-scope', t('monitor.channel_scope', 'Channel scope: all recorded sources/points · origins remain separate')));
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
          remove.setAttribute(
      'aria-label',
      t('monitor.remove_channel', 'Remove {channel}').replace('{channel}', channel)
    );
          head.append(remove);
        }
        reading.append(head);
        const value = $('div', 'mw-reading-value');
        value.append($('strong', '', number(row.value)), $('span', '', row.unit === 'unknown' ? t('monitor.unit_unknown', 'unit unknown') : row.unit || ''));
        reading.append(value);
        let quality = row.quality === 'no recorded issue' ? row.source_quality : row.quality;
        if (row.event_time_state && row.event_time_state !== 'recorded') {
      quality += ` · ${t('monitor.event_time', 'event time')} ${row.event_time_state}`;
    }
        const meta = $('div', 'mw-reading-meta');
        const at = row.time ? Date.parse(row.time) : null;
        const sameDay = at != null && s.chart && new Date(at).toISOString().slice(0, 10) === new Date(s.chart.end).toISOString().slice(0, 10);
        meta.append($('span', quality === 'good' ? 'mw-good' : '', `${t('monitor.quality', 'Quality')} · ${quality||t('monitor.unknown', 'unknown')}`), $('time', '', at == null ? t('monitor.event_time_unavailable', 'Event time unavailable') : `${time(at, !sameDay)} UTC`));
        meta.title =
      `${t('monitor.event', 'Event')}: ${row.time || t('monitor.not_recorded', 'Not recorded')}\n`
      + `${row.source}${row.measurement_point ? ' / ' + row.measurement_point : ''}\n`
      + `${t('monitor.event_time', 'event time')}: ${row.event_time_state}`;
        if (rows.length > 1) meta.prepend($('span', 'mw-origin-label', row.source + (row.measurement_point ? ' / ' + row.measurement_point : '')));
        reading.append(meta);
        readings.append(reading);
      }
    }
    main.append(readings);
    const clock = $('div', 'mw-chart-clock');
    clock.append($('span', '', t('monitor.stored_event_time', 'STORED EVENT TIME · UTC')), $('span', '', s.chart ? `${time(s.chart.start,true)} — ${time(s.chart.end,true)}` : t('monitor.no_event_time_window', 'No event-time window')));
    main.append(clock);
    const chart = $('div', 'mw-plot');
    chart.setAttribute('role', 'group');
    chart.setAttribute('aria-label', t('monitor.recorded_signal_comparison', 'Recorded signal comparison'));
    main.append(chart);
    cleanChart = drawChart(chart, s.chart, s.evidence || [], id => emit("evidence", {
      id
    }));
    const explanation = $('div', 'mw-chart-caption');
    explanation.append($('span', '', t('monitor.chart_caption', 'Mean · min/max · top marks: analysis windows (arrow keys move) · amber: exclusions')), $('span', 'mw-muted', t('monitor.bucket_note', 'Bucket summaries are not synchronized raw samples')));
    main.append(explanation);
    const bottom = $('div', 'mw-main-bottom');
    bottom.append($('span', 'mw-muted', `${t('monitor.snapshot', 'Snapshot')} ${time(s.assessed_at)} UTC`));
    const detail = button(t('monitor.inspect_signal', 'Inspect selected signal'), () => emit('detail'), 'mw-text-action');
    detail.append(icon('arrow'));
    bottom.append(detail);
    main.append(bottom);
    workspace.append(explorer, main);
    root.append(workspace);
    const supporting = $('section', 'mw-support');
    const evidence = $('div', 'mw-evidence');
    const evidenceHead = $('div', 'mw-panel-head');
    evidenceHead.append(
      $('h2', '', t('monitor.analysis_evidence', 'Analysis evidence')),
      $('span', 'mw-muted',
        t('monitor.loaded_evidence_count', '{count} loaded items in this event-time window')
          .replace('{count}', String((s.evidence || []).length))
      )
    );
    evidence.append(evidenceHead);
    const evidenceList = $('div', 'mw-evidence-list');
    evidenceList.setAttribute('role', 'region');
    evidenceList.setAttribute('aria-label', t('monitor.analysis_evidence_region', 'Analysis evidence in this window'));
    evidenceList.tabIndex = 0;
    evidence.append(evidenceList);
    for (const item of s.evidence || []) {
      const b = button('', () => emit('evidence', {
        id: item.id
      }), 'mw-evidence-row');
      b.dataset.evidenceId = item.id;
      const name = $('div');
      name.append($('strong', '', item.label), $('span', 'mw-muted', `${time(item.start)} — ${time(item.end)} UTC`));
      b.append($('span', 'mw-evidence-mark', '↗'), name, $('span', 'mw-review-state', item.review), icon('arrow'));
      evidenceList.append(b);
    }
    if (!(s.evidence || []).length) evidence.append($('div', 'mw-empty', t('monitor.no_analysis_overlap', 'No loaded analysis overlaps this window.')));
    const attention = $('div', 'mw-attention');
    const attentionHead = $('div', 'mw-panel-head');
    attentionHead.append($('h2', '', t('monitor.needs_inspection', 'Needs inspection')), $('span', 'mw-count', String((s.attention || []).length)));
    attention.append(attentionHead);
    for (const item of s.attention || []) {
      const b = button('', () => emit('attention', {
        id: item.id
      }), 'mw-attention-row');
      b.append($('span', 'mw-category', item.category), $('span', '', item.title), icon('arrow'));
      b.title = item.detail;
      attention.append(b);
    }
    if (!(s.attention || []).length) attention.append($('div', 'mw-empty', t('monitor.no_inspection_items', 'No recorded inspection items for this context.')));
    supporting.append(evidence, attention);
    root.append(supporting);
    if (lastActionError) showActionError(lastActionError);
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
    dialog.setAttribute('aria-label', t('monitor.choose_asset', 'Choose an asset'));
    dialog.setAttribute('aria-modal', 'true');
    const head = $('div', 'mw-panel-head');
    head.append($('h2', '', t('monitor.choose_asset', 'Choose an asset')));
    const close = button('', () => {
      overlay.remove();
      root.querySelector('.mw-asset').focus();
    }, 'mw-remove');
    close.append(icon('close'));
    close.setAttribute('aria-label', t('monitor.close_asset_picker', 'Close asset picker'));
    head.append(close);
    dialog.append(head);
    const input = $('input', 'mw-asset-search');
    input.type = 'search';
    input.placeholder = t('monitor.search_assets', 'Search assets');
    input.setAttribute('aria-label', t('monitor.search_assets', 'Search assets'));
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
        if (e.shiftKey && (root.getRootNode().activeElement || doc.activeElement) === focusables[0]) {
          e.preventDefault();
          focusables.at(-1).focus();
        } else if (!e.shiftKey && (root.getRootNode().activeElement || doc.activeElement) === focusables.at(-1)) {
          e.preventDefault();
          focusables[0].focus();
        }
      }
    });
    root.append(overlay);
    input.focus();
  }
  model.on('change:snapshot', draw);
  model.on('change:response', onResponse);
  draw();
  return () => {
    cleanChart();
    model.off('change:snapshot', draw);
    model.off('change:response', onResponse);
    clearTimeout(pendingTimer);
  };
}

function drawChart(container, data, windows, onEvidence) {
  if (!data || !data.groups.length) {
    container.append($('div', 'mw-chart-empty', t('monitor.no_stored_observations', 'No stored observations in this window. Select an available signal or another range.')));
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
      top = 45,
      bottom = 36;
    const svg = svgEl('svg', {
      viewBox: `0 0 ${W} ${H}`,
      width: W,
      height: H,
      role: 'group',
      'aria-label': t('monitor.stored_bucket_summaries', 'Stored bucket summaries')
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
        y: pTop - 27,
        class: 'mw-axis-title'
      }, `${group.title} · ${group.unit}`));
      const originLabel = `${group.origin} · ${group.interpretation}`;
      const labelBudget = Math.max(20, Math.floor((W - left - right) / 7));
      const origin = svgEl('text', {
          x: left,
          y: pTop - 11,
          class: 'mw-axis-origin'
        },
        originLabel.length > labelBudget ? originLabel.slice(0, labelBudget - 1) + '…' : originLabel);
      origin.append(svgEl('title', {}, originLabel));
      svg.append(origin);
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
      // Full-height targets stay transparent so many windows do not darken the data;
      // a thin mark shows each window and the hovered/focused one is highlighted.
      // One tab stop per panel; arrow keys move between its windows.
      const targets = [];
      for (const window of windows) {
        const begin = Math.max(data.start, window.start),
          end = Math.min(data.end, window.end);
        if (end < begin) continue;
        const wx = x(begin),
          ww = Math.max(2, x(end) - x(begin));
        svg.append(svgEl('rect', {
          x: wx,
          y: pTop,
          width: ww,
          height: 4,
          class: 'mw-window-mark'
        }));
        const target = svgEl('rect', {
          x: wx,
          y: pTop,
          width: ww,
          height: pBottom - pTop,
          class: 'mw-window',
          role: 'button',
          'data-evidence-id': window.id,
          tabindex: targets.length ? -1 : 0,
          'aria-label': t('monitor.open_analysis_evidence', 'Open {label} analysis evidence')
          .replace('{label}', window.label)
        });
        target.append(svgEl('title', {}, `${window.label} · ${time(window.start)} — ${time(window.end)} UTC`));
        target.addEventListener('click', () => onEvidence(window.id));
        target.addEventListener('keydown', e => {
          const at = targets.indexOf(target);
          const next = {
            ArrowRight: at + 1,
            ArrowDown: at + 1,
            ArrowLeft: at - 1,
            ArrowUp: at - 1,
            Home: 0,
            End: targets.length - 1
          }[e.key];
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onEvidence(window.id);
          } else if (next !== undefined && targets[next]) {
            e.preventDefault();
            target.setAttribute('tabindex', -1);
            targets[next].setAttribute('tabindex', 0);
            targets[next].focus();
          }
        });
        targets.push(target);
        svg.append(target);
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
      }, t('monitor.no_usable_bucket_values', 'No usable bucket values')));
    });
    for (let i = 0; i < 5; i++) {
      const t = data.start + (data.end - data.start) * i / 4;
      svg.append(svgEl('text', {
        x: x(t),
        y: H - 9,
        'text-anchor': i === 0 ? 'start' : i === 4 ? 'end' : 'middle',
        class: 'mw-axis'
      }, data.end - data.start >= 86400000 ? new Intl.DateTimeFormat(activeLocale, {
        timeZone: 'UTC',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23'
      }).format(new Date(t)) : shortTime(t)));
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
      tooltip.replaceChildren(
      $('div', 'mw-tooltip-title', t('monitor.bucket_summary', 'BUCKET SUMMARY · UTC')),
      $('div', 'mw-tooltip-cursor',
        t('monitor.cursor', 'Cursor {time}').replace('{time}', time(at, true))
      )
    );
      let hits = 0;
      for (const group of data.groups)
        for (const series of group.series) {
          const b = series.buckets.find(b => at >= b.start && at < b.end);
          if (!b) continue;
          const row = $('div', 'mw-tooltip-row');
          row.append($('span', '', series.channel), $('strong', '', b.usable ? `${number(b.mean)} ${group.unit}` : t('monitor.no_usable_value', 'No usable value')));
          row.style.setProperty('--series-color', series.color);
          tooltip.append(row);
          tooltip.append($('div', 'mw-tooltip-window', `${time(b.start,true)} — ${time(b.end,true)} UTC`));
          tooltip.append(
      $('div', 'mw-tooltip-range',
        t('monitor.bucket_stats', 'Min {min} · max {max} · mean {mean}')
          .replace('{min}', number(b.min))
          .replace('{max}', number(b.max))
          .replace('{mean}', number(b.mean))
      )
    );
          tooltip.append($('div', 'mw-tooltip-source', `${t('monitor.observed', 'Observed')} ${time(b.first,true)} — ${time(b.last,true)} UTC`));
          tooltip.append(
      $('div', 'mw-tooltip-source',
        t(
          'monitor.bucket_counts',
          '{source} · {usable} usable · null {null} · non-good {non_good} · conflict {conflict}'
        )
          .replace('{source}', `${series.source}${series.point ? ' / ' + series.point : ''}`)
          .replace('{usable}', String(b.usable))
          .replace('{null}', String(b.null))
          .replace('{non_good}', String(b.non_good))
          .replace('{conflict}', String(b.conflict))
      )
    );
          hits++;
        }
      if (!hits) tooltip.append($('div', 'mw-muted', t('monitor.no_observations_bucket', 'No observations in this bucket.')));
      tooltip.hidden = false;
      tooltip.style.left = Math.max(8, Math.min(container.clientWidth - 340, px + 12)) + 'px';
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
