<script lang="ts">
  import type {EvidenceFocus} from "../change-evidence";
  import {readSpectrum,type SpectrumChannel} from "../spectrum";
  import {measure} from "../chart-axis";
  let {focus,assetId,active=true}: {focus: EvidenceFocus;assetId:string;active?:boolean} = $props();
  const rows = $derived(focus.kind === "history" ? focus.item.related : focus.change.related);
  const condition = $derived(focus.kind === "history" ? focus.condition : null);
  const operation = $derived(focus.kind === "history" ? focus.record.operation.find(o => o.key === focus.item.operation?.key) : null);
  const shares = $derived(focus.kind === "history" ? focus.item.operation : null);
  const band = $derived(focus.kind === "history" ? focus.item.band : null);
  let spectrum:SpectrumChannel|null=$state(null),spectralState=$state("idle");
  const changedBand=$derived.by(()=>{const current:SpectrumChannel|null=spectrum;return current?[...current.shares].sort((a,b)=>Math.abs(b.b-b.a)-Math.abs(a.b-a.a))[0]??null:null;});
  $effect(()=>{
    const current=focus;
    spectrum=null;
    if(!active||current.kind!=="vibration"||!current.record.sourceId||!current.record.bindingId)return;
    const request=new AbortController();spectralState="loading";
    const change=current.change,channel=change.feature.slice(8,change.feature.lastIndexOf("."));
    void readSpectrum(assetId,{source:current.record.sourceId,binding:current.record.bindingId,first:current.record.first??1,last:current.record.last??change.to,count:(current.record.last??change.to)-(current.record.first??1)+1},
      {a:change.baseline,b:{from:change.from,to:change.to}},request.signal).then(read=>{
        if(!request.signal.aborted){spectrum=read.channels.find(row=>row.id===channel)??null;spectralState="ready";}
      }).catch(()=>{if(!request.signal.aborted)spectralState="failed";});
    return()=>request.abort();
  });
  const label = (row: typeof rows[number]) => row.label;
  const width = (v: number, a: number, b: number) => Math.abs(v) / Math.max(Math.abs(a), Math.abs(b), 1e-12) * 100;
</script>
<aside class="context" aria-label="선택한 변화의 관련 관측">
  <h3>{focus.kind === "history" ? "같은 구간의 다른 신호" : "함께 달라진 진동 특징"}</h3>
  {#if condition}<p class="condition">{condition}인 측정끼리 비교</p>{/if}
  {#if rows.length}<div class="legend"><span>비교 구간</span><span>변화 구간</span></div>
    <dl>{#each rows.slice(0, focus.kind==="vibration"?1:3) as row(label(row))}<div class="fact">
      <dt>{row.label}</dt><dd><span>{measure(row.reference,row.unit,3)}</span><strong>{measure(row.current,row.unit,3)}</strong></dd>
      {#if row.reference >= 0 && row.current >= 0}<div class="bars" aria-hidden="true"><i style:width={width(row.reference,row.reference,row.current)+"%"}></i><i style:width={width(row.current,row.reference,row.current)+"%"}></i></div>{/if}
    </div>{/each}</dl>
  {:else}<p>함께 비교할 신호가 이 기록에 없습니다.</p>{/if}
  {#if operation && shares?.baseline && shares.interval && band != null}
    <div class="operation"><h3>{condition}의 측정 비중</h3>
      <div class="values"><span>{Math.round(shares.baseline[band]*100)}%</span><strong>{Math.round(shares.interval[band]*100)}%</strong></div>
      <p>전류 수준을 맞춘 비교이며 실제 부하 조건 전체가 같다는 뜻은 아닙니다.</p>
    </div>
  {/if}
  {#if focus.kind==="vibration" && active}<div class="operation">
    <h3>주파수에서 달라진 성분</h3>
    {#if spectrum && changedBand}<p>{Math.round(changedBand.from).toLocaleString()}–{Math.round(changedBand.to).toLocaleString()} Hz 비중</p>
      <div class="values"><span>{(changedBand.a*100).toFixed(1)}%</span><strong>{(changedBand.b*100).toFixed(1)}%</strong></div>
      <div class="bars" aria-hidden="true"><i style:width={changedBand.a*100+"%"}></i><i style:width={changedBand.b*100+"%"}></i></div>
      {#if spectrum.ratio!==null}<p>전체 진동 에너지 · 비교 구간의 <strong>{spectrum.ratio.toLocaleString("ko-KR",{maximumSignificantDigits:3})}배</strong></p>{/if}
    {:else}<p>{spectralState==="loading"?"같은 구간의 원본 파형을 비교하고 있습니다.":"이 구간의 원본 파형을 읽지 못했습니다."}</p>{/if}
  </div>{/if}
</aside>
<style>
  .context{min-width:0;display:grid;align-content:start;gap:10px}h3{margin:0;font-size:var(--font-body)}p{margin:0;color:var(--color-ink-muted);font-size:var(--font-small);line-height:1.5}.condition{font-weight:600}.legend,dd,.values{display:flex;justify-content:space-between;gap:8px}.legend{font-size:var(--font-label);color:var(--color-ink-muted)}dl{display:grid;gap:14px;margin:0}.fact{display:grid;gap:5px}dt{font-size:var(--font-small)}dd,.values{margin:0;font-size:var(--font-body);font-variant-numeric:tabular-nums}dd>span,.values>span{color:var(--color-ink-muted)}.bars{display:grid;gap:3px}.bars i{display:block;height:5px;border-radius:2px;background:var(--color-ink-muted)}.bars i+i{background:var(--color-action)}.operation{display:grid;gap:8px;border-top:1px solid var(--color-border);padding-top:12px;margin-top:4px}.operation p{font-size:var(--font-label)}
</style>
