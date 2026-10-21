<script lang="ts">
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {niceTicks, yTicks} from "../chart-axis";
  import {num} from "../format";
  let {points, bounds, xLabel, yLabel, description}: {
    points:{x:number;y:number;label:string}[];
    bounds:{xmin:number;xmax:number;ymin:number;ymax:number};
    xLabel:string;yLabel:string;description:string;
  }=$props();
  const scale=$derived.by(()=>{
    const xp=bounds.xmax===bounds.xmin?Math.max(Math.abs(bounds.xmin)*0.05,1):(bounds.xmax-bounds.xmin)*0.05;
    const yp=bounds.ymax===bounds.ymin?Math.max(Math.abs(bounds.ymin)*0.05,1):(bounds.ymax-bounds.ymin)*0.05;
    const lo=bounds.xmin-xp,hi=bounds.xmax+xp,bottom=bounds.ymin-yp,top=bounds.ymax+yp;
    return {lo,hi,bottom,top,x:(v:number)=>640*(v-lo)/(hi-lo),y:(v:number)=>240-240*(v-bottom)/(top-bottom)};
  });
</script>

<figure>
  <p class="note">세로축 · {yLabel}</p>
  <ValueAxis ticks={yTicks(scale.bottom,scale.top,0,240)} height={240} unit={null}>
    <svg role="img" aria-label={description+" 가로축 "+xLabel+", 세로축 "+yLabel+". 가로축은 시간이 아닙니다."}
      viewBox="0 0 640 240" preserveAspectRatio="none">
      {#each yTicks(scale.bottom,scale.top,0,240) as tick(tick.value)}<line x1="0" x2="640" y1={tick.y} y2={tick.y} class="grid"/>{/each}
      {#each niceTicks(scale.lo,scale.hi) as tick(tick)}<line x1={scale.x(tick)} x2={scale.x(tick)} y1="0" y2="240" class="grid"/>{/each}
      {#each points as point,i(i)}<circle cx={scale.x(point.x)} cy={scale.y(point.y)} r="3">
        <title>{point.label} · {xLabel} {num(point.x)} · {yLabel} {num(point.y)}</title>
      </circle>{/each}
    </svg>
    {#snippet footer()}<XAxis lo={scale.lo} hi={scale.hi} scale={{kind:"value"}} note={"가로축 · "+xLabel}/>{/snippet}
  </ValueAxis>
  <figcaption>한 점은 같은 측정의 두 특징값입니다. 두 기간은 같은 축 범위로 표시합니다.</figcaption>
</figure>

<style>
  figure{margin:var(--space-3) 0;min-width:0;max-width:760px}
  svg{display:block;width:100%;height:240px}circle{fill:var(--color-action);fill-opacity:0.75}
  .grid{stroke:var(--color-border);stroke-width:1}svg circle,svg line{vector-effect:non-scaling-stroke}
  .note,figcaption{color:var(--color-ink-muted);font-size:var(--font-small);margin:var(--space-2) 0;overflow-wrap:anywhere}
</style>
