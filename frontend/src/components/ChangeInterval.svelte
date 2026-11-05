<script lang="ts">
  import type {FoundInterval} from "../record-findings";
  let {finding}:{finding:FoundInterval}=$props();
  const span=$derived(finding.context?.record);
  const start=$derived(span?Date.parse(span.from):Date.parse(finding.start));
  const end=$derived(span?Date.parse(span.to):Date.parse(finding.end));
  const x=(at:string)=>Math.max(0,Math.min(600,(Date.parse(at)-start)/Math.max(1,end-start)*600));
  const values=$derived(finding.trace??[]);
  const low=$derived(values.length?Math.min(...values.map(row=>row.value)):0);
  const high=$derived(values.length?Math.max(...values.map(row=>row.value)):1);
  const path=$derived(values.map((row,i)=>(i?"L":"M")+x(row.at).toFixed(2)+","+(62-(row.value-low)/Math.max(high-low,1e-12)*44).toFixed(2)).join(" "));
  const clock=(at:string)=>new Date(at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false});
</script>
<figure aria-label={"기록 전체의 집계값과 변화 구간. 변화 시작 "+clock(finding.start)+", 종료 "+clock(finding.end)}>
  <svg viewBox="0 0 600 80" preserveAspectRatio="none" role="img" aria-label="집계값 추이 · 음영은 발견한 변화 구간">
    <rect width="600" height="80" rx="8" class="track" />
    <rect x={x(finding.start)} width={Math.max(2,x(finding.end)-x(finding.start))} height="80" class="interval" />
    <line x1={x(finding.start)} x2={x(finding.start)} y1="0" y2="80" class="onset" />
    {#if path}<path d={path} class="trace" />{/if}
  </svg>
  <figcaption><span>기록 시작{#if span}<small>{clock(span.from)}</small>{/if}</span><span>음영 · 변화 구간</span><span>기록 끝{#if span}<small>{clock(span.to)}</small>{/if}</span></figcaption>
</figure>
<style>
  figure{margin:var(--space-3) 0;min-width:0}svg{display:block;width:100%;height:80px;border-radius:var(--radius-control);overflow:hidden}
  .track{fill:var(--color-surface-selected)}.interval{fill:var(--color-caution-ink);fill-opacity:.16}.onset{stroke:var(--color-caution-ink);stroke-width:2;stroke-dasharray:5 4;vector-effect:non-scaling-stroke}.trace{fill:none;stroke:var(--color-chart-primary,var(--color-action));stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}
  figcaption{display:flex;justify-content:space-between;gap:var(--space-2);margin-top:var(--space-2);font-size:var(--font-small);color:var(--color-ink-muted)}figcaption span:last-child{text-align:right}small{display:block;font-size:inherit}@media(max-width:440px){figcaption span:nth-child(2){max-width:5em;text-align:center}}
</style>
