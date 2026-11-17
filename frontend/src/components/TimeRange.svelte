<script lang="ts">
  let {slots,start,end,active,label,onChange,onClear}:{slots:number;start:number;end:number;active:boolean;
    label:(slot:number)=>string;onChange:(edge:"start"|"end",slot:number)=>void;onClear:()=>void}=$props();
  function move(edge:"start"|"end",input:HTMLInputElement){
    const value=Number(input.value);
    const slot=edge==="start"?Math.min(value,end):Math.max(value-1,start);
    // Repeated Home/End can change the native input without changing the selected slot.
    input.value=String(edge==="start"?slot:slot+1);
    onChange(edge,slot);
  }
</script>
<fieldset class="time-range" aria-label="시점·구간 고르기">
  <legend>구간 선택 <small>{active?"Esc로 선택 해제":"양끝 손잡이를 옮겨 구간을 고르세요"}</small></legend>
  <div class="handles" style={"--left:"+start/slots*100+"%;--right:"+(end+1)/slots*100+"%"}>
    <div class="rail"></div>{#if active}<div class="selected"></div>{/if}
    <input type="range" min="0" max={slots} value={start} aria-label="시작" aria-valuetext={label(start)}
      oninput={event=>move("start",event.currentTarget)} onkeydown={event=>{if(event.key==="Escape")onClear();}}/>
    <input type="range" min="0" max={slots} value={end+1} aria-label="끝" aria-valuetext={label(end+1)}
      oninput={event=>move("end",event.currentTarget)} onkeydown={event=>{if(event.key==="Escape")onClear();}}/>
  </div>
  <div class="dates"><span>시작 · {label(start)}</span><span>끝 · {label(end+1)}</span></div>
</fieldset>
<style>
  fieldset{border:0;padding:0;margin:var(--space-3) 0;min-width:0}legend{font-size:var(--font-small);font-weight:650;padding:0}small{font-weight:400;color:var(--color-ink-muted);margin-left:var(--space-2)}
  .handles{height:36px;position:relative}.rail,.selected{position:absolute;top:16px;height:4px;border-radius:2px}.rail{left:0;right:0;background:var(--color-control-border)}.selected{left:var(--left);width:calc(var(--right) - var(--left));background:var(--color-action)}
  input[type="range"]{appearance:none;position:absolute;left:-10px;width:calc(100% + 20px);height:36px;margin:0;padding:0;border:0;background:transparent;pointer-events:none}
  input::-webkit-slider-runnable-track{background:transparent;height:20px}input::-moz-range-track{background:transparent;height:20px}
  input::-webkit-slider-thumb{appearance:none;width:20px;height:20px;border:2px solid var(--color-action);border-radius:50%;background:white;pointer-events:auto;cursor:ew-resize}
  input::-moz-range-thumb{width:16px;height:16px;border:2px solid var(--color-action);border-radius:50%;background:white;pointer-events:auto;cursor:ew-resize}
  input:focus-visible{outline:none}input:focus-visible::-webkit-slider-thumb{outline:3px solid var(--color-focus);outline-offset:2px}input:focus-visible::-moz-range-thumb{outline:3px solid var(--color-focus);outline-offset:2px}
  .dates{display:flex;justify-content:space-between;gap:var(--space-3);font-size:var(--font-label);color:var(--color-ink-muted)}.dates span:last-child{text-align:right}
</style>
