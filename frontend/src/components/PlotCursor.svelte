<script lang="ts">
  import type {Snippet} from "svelte";
  import {nearestPosition,movePosition} from "../plot-selection";
  let {positions,value,lo,hi,label,onSelect,children}:{positions:number[];value:number|null;lo:number;hi:number;
    label:string;onSelect?:((at:number)=>void);children:Snippet}=$props();
  function pick(event:PointerEvent){
    const rect=(event.currentTarget as HTMLElement).getBoundingClientRect();
    const at=nearestPosition(positions,lo+Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*(hi-lo));
    if(at!==null)onSelect?.(at);
  }
  function keydown(event:KeyboardEvent){
    const at=movePosition(positions,value,event.key);
    if(at!==null){event.preventDefault();onSelect?.(at);}
  }
</script>
{#if onSelect && positions.length}
  <div class="cursor" role="slider" tabindex="0" aria-label={label} aria-valuemin={positions[0]}
    aria-valuemax={positions.at(-1)} aria-valuenow={nearestPosition(positions,value??hi)??undefined}
    onkeydown={keydown} onpointerdown={event=>{event.currentTarget.focus();event.currentTarget.setPointerCapture(event.pointerId);pick(event);}}
    onpointermove={event=>{if(event.buttons===1)pick(event);}}>
    {@render children()}
  </div>
{:else}{@render children()}{/if}
<style>
  .cursor{position:relative;cursor:crosshair;touch-action:pan-y;outline-offset:3px;border-radius:3px}
  .cursor:focus-visible{outline:2px solid var(--color-action)}
</style>
