<script lang="ts">
  import XAxis from "./XAxis.svelte";
  import {frequencyText} from "../spectrum";
  import {frequencyCells,type FrequencyRange} from "../frequency-view";
  import {GRADIENT,shade,type Waterfall,type WaterfallChannel} from "../waterfall";
  let {data,channel,domain,band=null,selected,onSelect,place,height=150}:{
    data:Waterfall;channel:WaterfallChannel;domain:FrequencyRange;band?:FrequencyRange|null;
    selected:number|null;onSelect:(ordinal:number)=>void;place:(at:number)=>string;height?:number;
  }=$props();
  let picked:{row:number;bin:number;left:number;top:number}|null=$state(null);
  const selectedRow=$derived(selected===null?-1:data.acquisitions.indexOf(selected));
  const cells=$derived(frequencyCells(data.frequencies,domain));
  const ticks=$derived([...new Set([0,Math.floor((data.acquisitions.length-1)/2),data.acquisitions.length-1])]);
  $effect(()=>{domain;channel;picked=null;});
  function paint(canvas:HTMLCanvasElement,input:{data:Waterfall;channel:WaterfallChannel;cells:typeof cells}) {
    let current=input;
    const draw=()=>{
      canvas.width=Math.max(1,Math.round(canvas.clientWidth*Math.min(devicePixelRatio||1,2)));
      canvas.height=current.data.acquisitions.length;
      const ctx=canvas.getContext("2d");if(!ctx)return;
      current.channel.decibels.forEach((values,row)=>current.cells.forEach(cell=>{
        ctx.fillStyle="rgb("+shade(values[cell.index],current.data.floorDb).join(",")+")";
        ctx.fillRect(cell.left*canvas.width,row,cell.width*canvas.width+.5,1);
      }));
    };
    const resize=new ResizeObserver(draw);resize.observe(canvas);draw();
    return {update:(next:typeof input)=>{current=next;draw();},destroy:()=>resize.disconnect()};
  }
  function position(event:MouseEvent|PointerEvent) {
    const box=(event.currentTarget as HTMLElement).getBoundingClientRect();
    const x=Math.max(0,Math.min(1,(event.clientX-box.left)/box.width));
    const row=Math.max(0,Math.min(data.acquisitions.length-1,Math.floor((event.clientY-box.top)/box.height*data.acquisitions.length)));
    const cell=cells.find(cell=>cell.left<=x&&x<=cell.left+cell.width);
    return {row,bin:cell?.index??cells[0]?.index??0,left:Math.min(60,x*100),top:event.clientY-box.top};
  }
  function keyRow(event:KeyboardEvent) {
    if(!["ArrowUp","ArrowDown","Home","End","Enter"," "].includes(event.key))return;
    event.preventDefault();
    const row=Math.max(0,selectedRow),index=event.key==="Home"?0:event.key==="End"?data.acquisitions.length-1
      :Math.max(0,Math.min(data.acquisitions.length-1,row+(event.key==="ArrowDown"?1:event.key==="ArrowUp"?-1:0)));
    onSelect(data.acquisitions[index]);
  }
</script>

<section class="waterfall" aria-label="측정별 주파수 지도">
  <h3>측정별 주파수 지도</h3>
  <div class="frequency-map" data-hz-from={domain.from} data-hz-to={domain.to}>
    <div class="rows" style:height={height+"px"} aria-hidden="true">
      {#each ticks as row(row)}<span style:top={(100*(row+.5)/data.acquisitions.length)+"%"}>{data.acquisitions[row]}회</span>{/each}
    </div>
    <div class="map">
      <canvas use:paint={{data,channel,cells}} style:height={height+"px"}
        onpointermove={event=>picked=position(event)} onpointerleave={()=>picked=null}
        role="button" tabindex="0" onclick={event=>onSelect(data.acquisitions[position(event).row])} onkeydown={keyRow}
        aria-label={channel.label+" 측정별 주파수 세기 · 위아래 방향키로 측정 선택"}></canvas>
      {#if selectedRow>=0}<span class="selected-row" aria-hidden="true" style:top={(height*(selectedRow+.5)/data.acquisitions.length)+"px"}></span>{/if}
      {#if band}{#each [...new Set([band.from,band.to])] as edge(edge)}
        {#if edge>=domain.from&&edge<=domain.to}<span class="band-edge" style:left={(100*(edge-domain.from)/(domain.to-domain.from))+"%"} style:height={height+"px"}></span>{/if}
      {/each}{/if}
      {#if picked}<div class="tip" style:left={"min("+picked.left+"%,max(0px,calc(100% - 240px)))"} style:top={Math.min(height-50,picked.top+8)+"px"}>
        <strong>{place(data.acquisitions[picked.row])}</strong><span>{frequencyText(data.frequencies[picked.bin])} Hz · {channel.decibels[picked.row][picked.bin].toFixed(1)} dB</span>
      </div>{/if}
      <XAxis lo={domain.from} hi={domain.to} scale={{kind:"value"}} suffix="Hz"/>
    </div>
  </div>
  <div class="legend"><span>측정 순서 ↓ · {data.acquisitions.length}회 표시</span><span>{data.floorDb} dB 이하<i style:background={GRADIENT}></i>0 dB</span></div>
</section>
<style>
  .waterfall{min-width:0}h3{margin:0 0 var(--space-2);font-size:var(--font-small);font-weight:650}
  .frequency-map{display:grid;grid-template-columns:var(--frequency-gutter,4.25rem) minmax(0,1fr);gap:var(--space-2);padding-top:var(--space-5)}
  .rows{position:relative;font-size:12px;color:var(--color-ink-muted);text-align:right;font-variant-numeric:tabular-nums}
  .rows>span{position:absolute;right:0;transform:translateY(-50%);white-space:nowrap}.map{position:relative;min-width:0}
  canvas{display:block;width:100%;image-rendering:pixelated;cursor:crosshair}canvas:focus-visible{outline:3px solid var(--color-focus);outline-offset:3px}
  .selected-row{position:absolute;left:0;right:0;border-top:2px solid var(--color-ink);pointer-events:none}
  .band-edge{position:absolute;top:0;border-left:1px dashed var(--color-caution-ink);pointer-events:none}
  .tip{position:absolute;z-index:1;display:grid;padding:var(--space-2);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-control);font-size:12px;pointer-events:none;width:max-content;max-width:min(240px,100%);overflow-wrap:anywhere;box-shadow:0 2px 8px #0002}
  .legend{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:var(--space-1) var(--space-3);font-size:12px;color:var(--color-ink-muted)}
  .legend>span:last-child{display:flex;align-items:center;gap:var(--space-2)}.legend i{width:70px;height:8px;display:inline-block}
</style>
