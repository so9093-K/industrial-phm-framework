<script lang="ts">
  import {focusChange,type FoundInterval} from "../record-findings";
  import {measure, yTicks} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  let {finding,height=220,focus=false}:{finding:FoundInterval;height?:number;focus?:boolean}=$props();
  // The entry screen shows the measured change against its reference line. Full context
  // remains available in the whole-record strip and the signal investigation.
  const displayed=$derived(focus?focusChange(finding):finding);
  const values=$derived(displayed.trace??[]);
  const span=$derived(values.length?{from:values[0].at,to:new Date(Date.parse(values.at(-1)!.at)+(finding.bucketSeconds??0)*1000).toISOString()}:finding.context?.record);
  const start=$derived(span?Date.parse(span.from):Date.parse(finding.start));
  const end=$derived(span?Date.parse(span.to):Date.parse(finding.end));
  const x=(at:string)=>Math.max(0,Math.min(600,(Date.parse(at)-start)/Math.max(1,end-start)*600));
  // 처음 30%의 중앙값도 세로축 안에 들어야 두 숫자를 그래프에서 견줄 수 있다.
  const reference=$derived(finding.reference);
  const low=$derived(values.length?Math.min(...values.map(row=>row.value),reference??Infinity):0);
  const high=$derived(values.length?Math.max(...values.map(row=>row.value),reference??-Infinity):1);
  const pad=$derived(high>low?(high-low)*.12:Math.max(Math.abs(low)*.05,1));
  const y=(value:number)=>height-(value-low+pad)/(high-low+2*pad)*height;
  // The values the trace spans, on the left, so a small move does not look like a large one.
  const ticks=$derived(yTicks(low-pad,high+pad,0,height,5));
  const joins=(i:number)=>i>0&&(values[i].join??(!!finding.bucketSeconds&&Date.parse(values[i].at)-Date.parse(values[i-1].at)<=finding.bucketSeconds*1500));
  const path=$derived(values.map((row,i)=>(joins(i)?"L":"M")+x(row.at).toFixed(2)+","+y(row.value).toFixed(2)).join(" "));
  const clock=(at:string)=>new Date(at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false});
</script>
<figure aria-label={(focus?"변화 구간의 평균과 비교 기준. 변화 시작 ":"변화 전후의 구간별 평균과 변화 구간. 변화 시작 ")+clock(finding.start)+", 종료 "+clock(finding.end)}>
  <ValueAxis {ticks} {height} unit={finding.unit}>
  <svg viewBox={"0 0 600 "+height} style:height={height+"px"} preserveAspectRatio="none" role="img" aria-label={focus?"변화 구간의 구간별 평균 · 점선은 기준 기간의 중앙값 · 측정 공백은 연결하지 않음":"구간별 평균 추이 · 측정 공백은 연결하지 않음 · 음영은 발견한 변화 구간"}>
    <rect width="600" height={height} rx="8" class="track" />
    {#each ticks as tick (tick.value)}<line x1="0" x2="600" y1={tick.y} y2={tick.y} class="grid" />{/each}
    <rect x={x(finding.start)} width={Math.max(2,x(finding.end)-x(finding.start))} height={height} class="interval" />
    <line x1={x(finding.start)} x2={x(finding.start)} y1="0" y2={height} class="onset" />
    {#if reference!==null}<line x1="0" x2="600" y1={y(reference)} y2={y(reference)} class="reference" />{/if}
    {#if path}<path d={path} class="trace" />{/if}
    {#each values as row,i (i)}<circle cx={x(row.at)} cy={y(row.value)} r="1.8" class="sample"><title>{clock(row.at)} · {measure(row.value,finding.unit)}</title></circle>{/each}
  </svg>
  {#snippet footer()}
  <XAxis lo={start} hi={Math.max(end, start + 1)} scale={{kind: "clock"}} />
  <figcaption><span class="legend">{#if !focus}<i class="key interval"></i>{/if}변화 구간{#if reference!==null} <i class="key reference"></i>처음 30%의 중앙값 {measure(reference,finding.unit)}{/if}</span></figcaption>
  {/snippet}
  </ValueAxis>
</figure>
<style>
  figure{margin:var(--space-3) 0;min-width:0}svg{display:block;width:100%;border-radius:var(--radius-control);overflow:hidden}
  .track{fill:var(--color-surface-selected)}.interval{fill:var(--color-caution-ink);fill-opacity:.16}.onset{stroke:var(--color-caution-ink);stroke-width:2;stroke-dasharray:5 4;vector-effect:non-scaling-stroke}.trace{fill:none;stroke:var(--color-chart-primary,var(--color-action));stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}
  .grid{stroke:var(--color-border);stroke-width:1;vector-effect:non-scaling-stroke}
  .reference{stroke:var(--color-ink);stroke-width:1.5;stroke-dasharray:6 4;opacity:.7;vector-effect:non-scaling-stroke}
  .legend{display:inline-flex;flex-wrap:wrap;align-items:center;gap:var(--space-1) var(--space-2)}.key{display:inline-block;width:14px;height:10px;border-radius:2px}.key.interval{background:var(--color-caution-ink);opacity:.3}.key.reference{height:0;border-top:2px dashed var(--color-ink);border-radius:0;margin-left:var(--space-2)}
  .sample{fill:var(--color-chart-primary,var(--color-action))}
  figcaption{display:flex;gap:var(--space-2);margin-top:var(--space-1);font-size:var(--font-small);color:var(--color-ink-muted)}
</style>
