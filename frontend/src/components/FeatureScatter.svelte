<script lang="ts">
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {niceTicks, yTicks} from "../chart-axis";
  import {num} from "../format";
  let {points, bounds, xLabel, yLabel, description,
    caption = "한 점은 같은 측정의 두 특징값입니다. 두 기간은 같은 축 범위로 표시합니다.", picked = null, onPick}: {
    points:{x:number;y:number;label:string}[];
    bounds:{xmin:number;xmax:number;ymin:number;ymax:number};
    xLabel:string;yLabel:string;description:string;
    caption?:string;
    /** Index of the point the reader picked; the parent shows what it is and where to go next. */
    picked?:number|null;
    onPick?:(index:number)=>void;
  }=$props();
  const scale=$derived.by(()=>{
    const xp=bounds.xmax===bounds.xmin?Math.max(Math.abs(bounds.xmin)*0.05,1):(bounds.xmax-bounds.xmin)*0.05;
    const yp=bounds.ymax===bounds.ymin?Math.max(Math.abs(bounds.ymin)*0.05,1):(bounds.ymax-bounds.ymin)*0.05;
    const lo=bounds.xmin-xp,hi=bounds.xmax+xp,bottom=bounds.ymin-yp,top=bounds.ymax+yp;
    return {lo,hi,bottom,top,x:(v:number)=>640*(v-lo)/(hi-lo),y:(v:number)=>240-240*(v-bottom)/(top-bottom)};
  });
  // The plot stretches, so the nearest point is measured on screen, not in the 640x240 box.
  function pick(event:MouseEvent){
    if(!onPick||!points.length)return;
    const box=(event.currentTarget as Element).getBoundingClientRect();
    const px=event.clientX-box.left,py=event.clientY-box.top;
    let best=0,distance=Infinity;
    points.forEach((point,index)=>{
      const dx=scale.x(point.x)/640*box.width-px,dy=scale.y(point.y)/240*box.height-py;
      const d=dx*dx+dy*dy;
      if(d<distance){distance=d;best=index;}
    });
    onPick(best);
  }
</script>

<figure>
  <p class="note">세로축 · {yLabel}</p>
  <ValueAxis ticks={yTicks(scale.bottom,scale.top,0,240)} height={240} unit={null}>
    <svg role="img" aria-label={description+" 가로축 "+xLabel+", 세로축 "+yLabel+". 가로축은 시간이 아닙니다."}
      viewBox="0 0 640 240" preserveAspectRatio="none">
      {#each yTicks(scale.bottom,scale.top,0,240) as tick(tick.value)}<line x1="0" x2="640" y1={tick.y} y2={tick.y} class="grid"/>{/each}
      {#each niceTicks(scale.lo,scale.hi) as tick(tick)}<line x1={scale.x(tick)} x2={scale.x(tick)} y1="0" y2="240" class="grid"/>{/each}
      {#each points as point,i(i)}<circle cx={scale.x(point.x)} cy={scale.y(point.y)} r="3" style:fill-opacity={0.3+0.65*i/Math.max(1,points.length-1)}>
        <title>{point.label} · {xLabel} {num(point.x)} · {yLabel} {num(point.y)}</title>
      </circle>{/each}
      {#if picked!==null&&points[picked]}
        <line x1={scale.x(points[picked].x)} x2={scale.x(points[picked].x)} y1={scale.y(points[picked].y)} y2={scale.y(points[picked].y)} class="picked"/>
      {/if}
      {#if onPick}<rect x="0" y="0" width="640" height="240" class="hit" onclick={pick} role="presentation"/>{/if}
    </svg>
    {#snippet footer()}<XAxis lo={scale.lo} hi={scale.hi} scale={{kind:"value"}} note={"가로축 · "+xLabel}/>{/snippet}
  </ValueAxis>
  {#if onPick && points.length}
    <label class="point-picker">측정 순서로 점 선택
      <input type="range" min="0" max={points.length-1} step="1" value={picked??0}
        aria-valuetext={points[picked??0]?.label} oninput={event=>onPick?.(Number(event.currentTarget.value))}
        onfocus={()=>{if(picked===null)onPick?.(0);}} />
    </label>
    <p class="note" aria-live="polite">{picked!==null&&points[picked]?points[picked].label+" · "+xLabel+" "+num(points[picked].x)+" · "+yLabel+" "+num(points[picked].y):"슬라이더에서 방향키로 이전·다음 측정을 선택하세요."}</p>
  {/if}
  <figcaption>{caption} 점의 색은 측정 순서에 따라 옅은색에서 진한색으로 바뀝니다.</figcaption>
</figure>

<style>
  figure{margin:var(--space-3) 0;min-width:0;max-width:760px}
  svg{display:block;width:100%;height:240px}circle{fill:var(--color-action);fill-opacity:0.75}
  .grid{stroke:var(--color-border);stroke-width:1}svg circle,svg line{vector-effect:non-scaling-stroke}
  .picked{stroke:var(--color-focus);stroke-width:12;stroke-linecap:round}
  .hit{fill:transparent;cursor:crosshair}
  .point-picker{display:grid;gap:var(--space-2);font-size:var(--font-small)}
  .point-picker input{width:100%;min-height:32px}
  .note,figcaption{color:var(--color-ink-muted);font-size:var(--font-small);margin:var(--space-2) 0;overflow-wrap:anywhere}
</style>
