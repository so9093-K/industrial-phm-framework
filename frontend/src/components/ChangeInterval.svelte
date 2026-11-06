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
  const y=(value:number)=>62-(value-low)/Math.max(high-low,1e-12)*44;
  const joins=(i:number)=>i>0&&(values[i].join??(!!finding.bucketSeconds&&Date.parse(values[i].at)-Date.parse(values[i-1].at)<=finding.bucketSeconds*1500));
  const path=$derived(values.map((row,i)=>(joins(i)?"L":"M")+x(row.at).toFixed(2)+","+y(row.value).toFixed(2)).join(" "));
  const clock=(at:string)=>new Date(at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false});
</script>
<figure aria-label={"기록 전체의 구간별 평균과 변화 구간. 변화 시작 "+clock(finding.start)+", 종료 "+clock(finding.end)}>
  <svg viewBox="0 0 600 80" preserveAspectRatio="none" role="img" aria-label="구간별 평균 추이 · 측정 공백은 연결하지 않음 · 음영은 발견한 변화 구간">
    <rect width="600" height="80" rx="8" class="track" />
    <rect x={x(finding.start)} width={Math.max(2,x(finding.end)-x(finding.start))} height="80" class="interval" />
    <line x1={x(finding.start)} x2={x(finding.start)} y1="0" y2="80" class="onset" />
    {#if path}<path d={path} class="trace" />{/if}
    {#each values as row,i (i)}<circle cx={x(row.at)} cy={y(row.value)} r="1.8" class="sample" />{/each}
  </svg>
  <figcaption><span>기록 시작{#if span}<small>{clock(span.from)}</small>{/if}</span><span>음영 · 변화 구간</span><span>기록 끝{#if span}<small>{clock(span.to)}</small>{/if}</span></figcaption>
</figure>
<style>
  figure{margin:var(--space-3) 0;min-width:0}svg{display:block;width:100%;height:80px;border-radius:var(--radius-control);overflow:hidden}
  .track{fill:var(--color-surface-selected)}.interval{fill:var(--color-caution-ink);fill-opacity:.16}.onset{stroke:var(--color-caution-ink);stroke-width:2;stroke-dasharray:5 4;vector-effect:non-scaling-stroke}.trace{fill:none;stroke:var(--color-chart-primary,var(--color-action));stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}
  .sample{fill:var(--color-chart-primary,var(--color-action))}
  figcaption{display:flex;justify-content:space-between;gap:var(--space-2);margin-top:var(--space-2);font-size:var(--font-small);color:var(--color-ink-muted)}figcaption span:last-child{text-align:right}small{display:block;font-size:inherit}@media(max-width:440px){figcaption span:nth-child(2){max-width:5em;text-align:center}}
</style>
