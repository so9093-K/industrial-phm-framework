<script lang="ts">
  import {tracePath} from "../asset-overview";
  import type {Span, TimelinePoint} from "../asset-timeline";
  import type {XScale} from "../time-axis";
  import PlotCursor from "./PlotCursor.svelte";
  import XAxis from "./XAxis.svelte";

  let {points, record, view, change, position, scale, place, onMove}: {
    points: TimelinePoint[]; record: Span; view: Span; change: Span; position: number | null; scale: XScale;
    place: (at: number) => string; onMove: (at: number) => void;
  } = $props();

  const width = 1000;
  const height = 36;
  const positions = $derived(points.map(point => point.x));
  const low = $derived(Math.min(...points.map(point => point.value)));
  const high = $derived(Math.max(...points.map(point => point.value)));
  const x = (at: number) => width * Math.min(1, Math.max(0, (at - record.from) / (record.to - record.from)));
  const y = (value: number) => high === low ? height / 2 : height - 4 - (value - low) / (high - low) * (height - 8);
  const path = $derived(tracePath(points.map(point => ({x: x(point.x), y: y(point.value), join: point.join === true}))));
  const viewLabel = $derived(view.from === record.from && view.to === record.to
    ? "전체 범위 표시 중" : place(view.from) + " ~ " + place(view.to));
</script>

{#if points.length > 1 && record.to > record.from}
  <div class="navigator">
    <div class="caption"><strong>기록 전체</strong><span>현재 보기 · {viewLabel}</span></div>
    <PlotCursor {positions} value={position ?? (view.from + view.to) / 2} lo={record.from} hi={record.to}
      label="기록 전체에서 볼 구간 이동" formatValue={place} onSelect={onMove}>
      <svg viewBox="0 0 1000 36" preserveAspectRatio="none" role="img" aria-label="전체 기록에서 변화와 현재 보기의 위치">
        <rect x={x(change.from)} y="0" width={Math.max(2, x(change.to) - x(change.from))} {height} class="change"/>
        <path d={path}/>
        <rect x={x(view.from) + 1} y="1" width={Math.max(2, x(view.to) - x(view.from) - 2)} height={height - 2} rx="3" class="view"/>
      </svg>
    </PlotCursor>
    <XAxis lo={record.from} hi={record.to} {scale}/>
  </div>
{/if}

<style>
  .navigator { margin:10px 0 0 64px; min-width:0; }
  .caption { display:flex; flex-wrap:wrap; justify-content:space-between; gap:2px 8px; margin-bottom:5px; font-size:var(--font-label); color:var(--color-ink-muted); }
  .caption strong { color:var(--color-ink); }
  svg { display:block; width:100%; height:36px; border-radius:4px; overflow:hidden; background:var(--color-surface-selected); }
  .change { fill:var(--color-change-fill); }
  .view { fill:none; stroke:var(--color-action); stroke-width:1.5; }
  path { fill:none; stroke:var(--color-ink-muted); stroke-width:1; }
  path,.view { vector-effect:non-scaling-stroke; }
</style>
