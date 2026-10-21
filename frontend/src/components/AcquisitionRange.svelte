<script lang="ts">
  import {measurementLabel} from "../time-axis";
  import type {Span} from "../spectrum";
  let {name, span, first, last, period = null, onChange}: {
    name: string; span: Span; first: number; last: number; period?: number | null;
    onChange: (edge: "from" | "to", ordinal: number) => void;
  } = $props();
  const interval = $derived(period && Number.isFinite(period) && period > 0 ? period : null);
  const unit = $derived(interval !== null && interval >= 60 ? 60 : 1);
  const label = $derived(interval === null ? "측정 회차" : "기록 시작 후 (" + (unit === 60 ? "분" : "초") + ")");
  const value = (ordinal: number) => interval === null ? ordinal : Number(((ordinal - 1) * interval / unit).toFixed(9));
  function edit(edge: "from" | "to", raw: string) {
    let ordinal = raw.trim() ? Number(raw) : NaN;
    if (interval !== null) ordinal = ordinal * unit / interval + 1;
    // Decimal unit conversion must not turn an integral original address into 75.999999999.
    if (Number.isFinite(ordinal) && Math.abs(ordinal - Math.round(ordinal)) < 1e-8) ordinal = Math.round(ordinal);
    onChange(edge, ordinal);
  }
</script>

<fieldset>
  <legend>기간 {name.toUpperCase()} · {label}</legend>
  <label>시작 <input type="number" min={value(first)} max={value(last)} step={interval === null ? 1 : interval / unit}
    value={value(span.from)} onchange={e => edit("from", e.currentTarget.value)} /></label>
  <label>끝 <input type="number" min={value(first)} max={value(last)} step={interval === null ? 1 : interval / unit}
    value={value(span.to)} onchange={e => edit("to", e.currentTarget.value)} /></label>
  {#if Number.isSafeInteger(span.from) && Number.isSafeInteger(span.to)}
    <p>{measurementLabel(span.from, interval)} ~ {measurementLabel(span.to, interval)}</p>
  {:else}<p>측정에 맞는 구간 경계를 입력하세요.</p>{/if}
</fieldset>

<style>
  fieldset{min-width:0;display:grid;gap:var(--space-3);border:1px solid var(--color-border);border-radius:var(--radius-panel)}
  label{display:grid;gap:var(--space-2);font-weight:650}
  input{width:100%;min-width:0;border:1px solid var(--color-border);border-radius:var(--radius-control);color:var(--color-ink);background:var(--color-surface);padding:var(--space-3)}
  p{color:var(--color-ink-muted);font-size:var(--font-small);margin:0;overflow-wrap:anywhere}
</style>
