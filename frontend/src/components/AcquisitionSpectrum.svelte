<script lang="ts">
  import AnalysisControls from "./AnalysisControls.svelte";
  import SourceIdentity from "./SourceIdentity.svelte";
  import AcquisitionRange from "./AcquisitionRange.svelte";
  import type {AcquisitionTiming} from "../asset-data";
  import {measurementLabel} from "../time-axis";
  import {measurementLinks} from "../measurement-links";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {yTicks} from "../chart-axis";
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import CautionNote from "./CautionNote.svelte";
  import SpectrumWaterfall from "./SpectrumWaterfall.svelte";
  import AnalysisMessage from "./AnalysisMessage.svelte";
  import {spectrumMessage,times} from "../analysis-messages";
  import {readAcquisition,readSpectrum,defaultSpans,validateSpans,peakSummary, frequencyText,
    SpectrumUnavailable,WaveformUnavailable,
    type Acquisition,type Spans,type Spectrum,type SpectrumChannel} from "../spectrum";
  import {readVibrationSummary,vibrationDefault,VIBRATION_SUMMARY_NOTE} from "../summary-defaults";

  let {assetId,timing=null}:{assetId:string;timing?:AcquisitionTiming|null}=$props();
  type State="loading"|"ready"|"empty"|"failed"|"unavailable"|"missing-waveform";
  let sourceState:State=$state("loading");
  let resultState:State=$state("empty");
  let acquisition:Acquisition|null=$state(null);
  let spans:Spans|null=$state(null);
  let result:Spectrum|null=$state(null);
  const period = $derived.by(() => {
    const current: Acquisition | null = acquisition;
    return current && timing && timing.sourceId === current.source ? timing.periodSeconds : null;
  });
  const place = (at:number) => measurementLabel(at, period);
  let error=$state("");
  let selectionNotice=$state("");
  let fromSummary=$state(false);
  // Where the first measurement of B stands against the one before it answers "since when".
  const B_START:Record<string,string>={spectrum:"기간 B 첫 측정을 바로 앞 측정과 주파수 비교",model:"기간 B 첫 측정의 원본 파형·모델 점수"};
  const message=$derived.by(()=>{
    const read:Spectrum|null=result,source:Acquisition|null=acquisition;
    if(!read||!source||!read.used.b.length)return null;
    const next=measurementLinks(assetId,Math.min(...read.used.b),{first:source.first,last:source.last,bindingId:source.binding})
      .filter(link=>link.key in B_START).map(link=>({label:B_START[link.key],href:link.href}));
    return spectrumMessage(read.channels.map(channel=>({label:channel.label,ratio:channel.ratio,shares:channel.shares})),
      {a:read.used.a.length,b:read.used.b.length},next);
  });
  let sourceRequest:AbortController|null=null;
  let spectrumRequest:AbortController|null=null;

  const fmt=(value:number)=>value.toExponential(3);
  // Vibration energy is usually dominated by one low band; dB keeps the other bands readable.
  let decibel=$state(true);
  const initialBand = new URLSearchParams(location.search);
  const bandFrom = Number(initialBand.get("spectrum_hz_from") ?? NaN), bandTo = Number(initialBand.get("spectrum_hz_to") ?? NaN);
  let focused:{from:number;to:number}|null=$state(Number.isFinite(bandFrom) && Number.isFinite(bandTo) && bandFrom >= 0 && bandTo > bandFrom ? {from:bandFrom,to:bandTo} : null);
  let initialZoom = !initialBand.has("spectrum_hz_from") && initialBand.get("spectrum_hz")!=="all";
  let selectedChannel = $state(initialBand.get("spectrum_channel")??"");
  function view(channel:SpectrumChannel, frequencies:number[]) {
    const selected=focused;
    const indices=frequencies.map((_,i)=>i).filter(i=>!selected||(frequencies[i]>=selected.from&&frequencies[i]<=selected.to));
    // A display bin can be wider than a reported full-resolution change band.
    if(indices.length<2)return {frequencies,a:channel.a,b:channel.b,zoomed:false};
    return {frequencies:indices.map(i=>frequencies[i]),a:indices.map(i=>channel.a[i]),b:indices.map(i=>channel.b[i]),zoomed:!!selected};
  }
  function bandRect(band:{from:number;to:number}, frequencies:number[]) {
    const lo=frequencies[0],hi=frequencies.at(-1)!;
    const start=Math.max(lo,band.from),end=Math.min(hi,band.to);
    return end>=start?{x:800*(start-lo)/Math.max(hi-lo,1e-12),width:Math.max(2,800*(end-start)/Math.max(hi-lo,1e-12))}:null;
  }
  function zoomBand(band:{from:number;to:number}, frequencies:number[]) {
    const step=frequencies.length>1?frequencies[1]-frequencies[0]:1;
    const padding=Math.max(band.to-band.from,step*3);
    focused={from:Math.max(frequencies[0],band.from-padding),to:Math.min(frequencies.at(-1)!,band.to+padding)};
    remember();
  }
  type Axis={lo:number;hi:number;map:(value:number)=>number};
  // Linear shows power as stored. dB is relative to the channel's strongest band (0 dB) and
  // floored at -60 dB, so small bands stay readable next to one dominant low-frequency peak.
  function axisFor(channel:SpectrumChannel,inDecibel:boolean):Axis {
    const top=Math.max(...channel.a,...channel.b,1e-16);
    if(!inDecibel)return {lo:0,hi:top*1.05,map:value=>value};
    const map=(value:number)=>Math.max(-60,10*Math.log10(Math.max(value,1e-300)/top));
    const lowest=Math.min(...channel.a.map(map),...channel.b.map(map));
    return {lo:Math.min(-10,Math.floor(lowest/10)*10),hi:3,map};
  }
  // Drawn on a stretchable 800x180 plot; every label is page text, not scaled SVG text.
  function trace(values:number[],axis:Axis,frequencies:number[]):string {
    const lo=frequencies[0], hi=frequencies[frequencies.length-1];
    return values.map((n,i)=>{
      const x=800*(frequencies[i]-lo)/Math.max(hi-lo,1e-12);
      const y=180-180*(axis.map(n)-axis.lo)/(axis.hi-axis.lo);
      return x.toFixed(1)+","+y.toFixed(1);
    }).join(" ");
  }
  // A band whose power barely moved is not "크게 달라진"; 1 dB is about a quarter more or less power.
  const MEANINGFUL_DB=1;
  function remember() {
    if(!spans)return;
    const url=new URL(location.href);
    url.searchParams.set("monitor_asset",assetId);
    for(const n of ["a","b"] as const) {
      url.searchParams.set("spectrum_"+n+"_from",String(spans[n].from));
      url.searchParams.set("spectrum_"+n+"_to",String(spans[n].to));
    }
    for(const [key,value] of [["spectrum_hz_from",focused?.from],["spectrum_hz_to",focused?.to]] as const) {
      if(value === undefined)url.searchParams.delete(key);else url.searchParams.set(key,String(value));
    }
    if(focused)url.searchParams.delete("spectrum_hz");else url.searchParams.set("spectrum_hz","all");
    if(selectedChannel)url.searchParams.set("spectrum_channel",selectedChannel);else url.searchParams.delete("spectrum_channel");
    history.replaceState(history.state,"",url);
  }
  function savedSpans(fallback:Spans):Spans {
    const q=new URLSearchParams(location.search);
    const prefix=q.has("spectrum_a_from")?"spectrum_":q.has("feature_a_from")?"feature_":"acq_";
    const span=(name:"a"|"b")=>({
      from:Number(q.get(prefix+name+"_from")),
      to:Number(q.get(prefix+name+"_to")),
    });
    if(!["a_from","a_to","b_from","b_to"].every(key=>q.has(prefix+key)))return fallback;
    try{
      const result={a:span("a"),b:span("b")};
      validateSpans(result);return result;
    }catch{return fallback;}
  }
  async function readSource(){
    sourceRequest?.abort();spectrumRequest?.abort();
    const req=new AbortController();sourceRequest=req;
    sourceState="loading";resultState="empty";acquisition=null;result=null;error="";
    try{
      const data=await readAcquisition(assetId,req.signal);
      if(req.signal.aborted)return;
      if(!data){sourceState="empty";return;}
      acquisition=data;
      // 아무 기간도 고르지 않고 열었으면 상태 요약의 대표 변화와 같은 두 기간을 견준다.
      const q=new URLSearchParams(location.search);
      const chosen=["spectrum_a_from","feature_a_from","acq_a_from"].some(k=>q.has(k));
      const found=!chosen?await readVibrationSummary(assetId,req.signal):null;
      if(req.signal.aborted)return;
      const summary=found&&found.intervals[0]?vibrationDefault(found,data.binding,[found.intervals[0].feature]):null;
      fromSummary=summary!==null;
      try{spans=summary?summary.spans:savedSpans(defaultSpans(data));}catch(cause:unknown){
        sourceState="unavailable";error=cause instanceof Error?cause.message:"파형 비교 기록이 부족합니다.";return;
      }
      sourceState="ready";remember();await analyze();
    }catch(cause:unknown){
      if(req.signal.aborted)return;
      sourceState="failed";
      error=cause instanceof Error?cause.message:"측정 원본 목록을 조회할 수 없습니다.";
    }
  }
  function change(n:"a"|"b",edge:"from"|"to",input:string){
    if(!spans)return;
    spans={...spans,[n]:{...spans[n],[edge]:Number(input)}};
    spectrumRequest?.abort();result=null;resultState="empty";selectionNotice="";fromSummary=false;
  }
  function useMeasurement(n:"a"|"b",ordinal:number){
    if(!spans||!acquisition||!Number.isSafeInteger(ordinal)||ordinal<acquisition.first||ordinal>acquisition.last)return;
    spans={...spans,[n]:{from:ordinal,to:ordinal}};fromSummary=false;
    selectionNotice="기간 "+n.toUpperCase()+"를 "+place(ordinal)+" 한 측정으로 바꿨습니다. 반대 기간은 유지했습니다.";
    remember();void analyze();
  }
  async function analyze(){
    spectrumRequest?.abort();
    const req=new AbortController();spectrumRequest=req;
    result=null;resultState="loading";error="";
    try{
      if(!spans||!acquisition)throw new Error("파형 원본과 측정 구간을 확인하세요.");
      validateSpans(spans);
      const frozen:Spans={a:{...spans.a},b:{...spans.b}};
      const data=await readSpectrum(assetId,acquisition,frozen,req.signal);
      if(req.signal.aborted)return;
      if(!data.channels.some(row=>row.id===selectedChannel))selectedChannel=data.channels[0]?.id??"";
      if(focused && data.frequencies.filter(hz=>focused!.from<=hz&&hz<=focused!.to).length<2){focused=null;selectionNotice="저장한 대역에 표시할 주파수 구간이 부족해 전체 주파수를 표시합니다.";}
      result=data;resultState=data.channels.length?"ready":"empty";remember();
      if(initialZoom){
        initialZoom=false;
        const changed=data.channels.flatMap(channel=>channel.shares).filter(band=>Math.abs(band.b-band.a)>=.1)
          .sort((a,b)=>Math.abs(b.b-b.a)-Math.abs(a.b-a.a))[0];
        if(changed)zoomBand(changed,data.frequencies);
      }
    }catch(cause:unknown){
      if(req.signal.aborted)return;
      error=cause instanceof Error?cause.message:"원본 파워 스펙트럼을 확인할 수 없습니다.";
      resultState=cause instanceof SpectrumUnavailable?"unavailable"
        :cause instanceof WaveformUnavailable?"missing-waveform":"failed";
    }
  }
  onMount(()=>{void readSource();return()=>{sourceRequest?.abort();spectrumRequest?.abort();};});
</script>
<section class="ui-panel spectra" aria-labelledby="spectra-title">
  <h2 class="visually-hidden" id="spectra-title">주파수 분석</h2>
  {#if sourceState==="loading"}
    <StatusNotice message="진동 원본 파형 목록을 불러오고 있습니다."/>
  {:else if sourceState==="empty"||sourceState==="unavailable"}
    <StatusNotice kind="uncertain" title="주파수를 비교할 원본 파형이 없습니다"
      message={error||"저장된 진동 원본 파형이 없거나 비교할 측정이 부족합니다."}/>
  {:else if sourceState==="failed"}
    <StatusNotice kind="failure" title="원본 파형 목록을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void readSource()}/>
  {:else if acquisition&&spans}
    <div class="analysis-workspace analysis-full"><AnalysisControls title="비교 기간"
      summary={"기간 A · "+spans.a.from+"–"+spans.a.to+"번째 / 기간 B · "+spans.b.from+"–"+spans.b.to+"번째 측정"}>{#snippet children(close)}{#if acquisition && spans}

    <label class="scale"><input type="checkbox" bind:checked={decibel}/> 세로축을 dB로 보기 · 끄면 실제 세기(선형)로 봅니다</label>
    <SourceIdentity id={acquisition.source}/><p class="context">{place(acquisition.first)} ~ {place(acquisition.last)}</p>
    <section class="conditions">
    <div class="periods">
      {#each ["a","b"] as label(label)}
        {@const name=label as "a"|"b"}
        <AcquisitionRange name={name} span={spans[name]} first={acquisition.first} last={acquisition.last} {period}
          onChange={(edge, ordinal) => change(name, edge, String(ordinal))} />
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>{close();void analyze();}}>
      주파수 비교하기
    </button></section>

    {/if}{/snippet}</AnalysisControls>
    <div class="analysis-body">
    {#if resultState==="loading"}
      <StatusNotice message="원본 파형의 주파수별 세기를 계산하고 있습니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="주파수 분석을 불러오지 못했습니다" message={error}
        actionLabel="같은 측정으로 다시 불러오기" onAction={()=>void analyze()}/>
    {:else if resultState==="missing-waveform"}
      <StatusNotice kind="uncertain" title="원본 파형을 확인할 수 없습니다" message={error}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="고른 측정의 원본 파형이 없습니다" message={error}/>
    {:else if resultState==="empty"}
      <StatusNotice message="두 기간을 고르고 주파수 비교하기를 누르세요."/>
    {:else if result}
      {#if message}<p class="result-statement">{message.headline}</p>{/if}
      {#if selectionNotice}<p class="context" role="status">{selectionNotice}</p>{/if}
      <div class="spectrum-toolbar">
        <div role="group" aria-label="진동 방향">
          {#each result.channels as channel (channel.id)}<button type="button" class="ui-button" aria-pressed={selectedChannel===channel.id} onclick={()=>{selectedChannel=channel.id;remember();}}>{channel.label}</button>{/each}
        </div>
        <p>{focused?frequencyText(focused.from)+"–"+frequencyText(focused.to)+" Hz · 두 그래프 함께 확대":"전체 주파수"}</p>
        {#if focused}<button type="button" class="ui-button" onclick={()=>{focused=null;remember();}}>전체 주파수 보기</button>{/if}
      </div>
      <div class="spectrum-investigation">
      <div class="channels">
      {#each result.channels.filter(row=>row.id===selectedChannel) as channel(channel.id)}
        {@const changed=channel.bands.filter(band=>Math.abs(band.changeDb)>=MEANINGFUL_DB)}
        {@const displayed=view(channel,result.frequencies)}
        {@const frequencies=displayed.frequencies}
        {@const axis=axisFor(channel,decibel)}
        {@const step=frequencies.length>1?frequencies[1]-frequencies[0]:null}
        <section class="series">
          <h3>두 기간의 주파수 비교</h3>
          <p class="axis-note">세로축 · 주파수별 평균 세기 · {decibel?"두 기간 중 가장 센 주파수 대비 dB · ":channel.unit?channel.unit+" · ":""}두 기간은 같은 눈금</p>
          <ValueAxis ticks={yTicks(axis.lo,axis.hi,0,180)} height={180} unit={decibel?"dB":null}>
          <svg role="img" viewBox="0 0 800 180" preserveAspectRatio="none"
            aria-label={"주파수별 세기. 기간 A는 실선, 기간 B는 점선입니다. " + frequencies[0].toFixed(1) + "Hz부터 " + frequencies[frequencies.length-1].toFixed(1) + "Hz까지. 정확한 값은 표에 있습니다."}>
            {#each yTicks(axis.lo,axis.hi,0,180) as tick(tick.value)}<line x1="0" x2="800" y1={tick.y} y2={tick.y} class="grid"/>{/each}
            {#each changed as band,i(i)}
              {@const area=bandRect(band,frequencies)}
              {#if area}<rect x={area.x} width={area.width} y="0" height="180" class="changed-band"><title>{frequencyText(band.from)}~{frequencyText(band.to)} Hz · {band.changeDb.toFixed(1)} dB 변화</title></rect>{/if}
            {/each}
            <polyline points={trace(displayed.a,axis,frequencies)} class="line-a"/>
            <polyline points={trace(displayed.b,axis,frequencies)} class="line-b"/>
            <path d="M0 0 V180 H800" class="axis"/>
          </svg>
          {#snippet footer()}<XAxis lo={frequencies[0]} hi={frequencies[frequencies.length-1]}
            scale={{kind:"value"}} note="가로축 · 주파수 (Hz)"/>{/snippet}
          </ValueAxis>
          <p class="legend"><span><i class="key a"></i>기간 A (실선)</span><span><i class="key b"></i>기간 B (점선)</span><span>음영 · {MEANINGFUL_DB} dB 이상 달라진 대역</span></p>
          {#if changed.length}<div class="band-choices" role="group" aria-label="변화 대역 확대">
            {#each changed.slice(0,3) as band,i(i)}<button type="button" class="band-button" onclick={()=>zoomBand(band,result!.frequencies)}>{frequencyText(band.from)}–{frequencyText(band.to)} Hz 확대</button>{/each}
          </div>{/if}
          <details><summary>피크·대역별 수치</summary>
          <h4>가장 센 주파수</h4>
          <p class="peaks">기간 A · {peakSummary(result.frequencies,channel.a)}
            <span class="sep">/</span> 기간 B · {peakSummary(result.frequencies,channel.b)}</p>
          {#if step}<p class="context">센 순서로 최대 3개 · 약 {frequencyText(step)} Hz 간격으로 묶은 세기라 정확한 주파수는 그 간격 안에 있습니다.</p>{/if}
          {#if changed.length}
            <h4>세기가 크게 달라진 주파수</h4>
            <ol>
              {#each changed as band,i(i)}
                <li><button type="button" class="band-button" onclick={()=>zoomBand(band,result!.frequencies)}>{frequencyText(band.from)}–{frequencyText(band.to)} Hz 확대</button>
                  · 기간 B 세기가 기간 A의 {times(10**(band.changeDb/10))} ({band.changeDb.toFixed(1)} dB)</li>
              {/each}
            </ol>
          {:else if channel.bands.length}
            <p class="context">두 기간의 세기 차이가 {MEANINGFUL_DB}dB 이상인 주파수는 없습니다.</p>
          {:else}
            <StatusNotice message="두 기간 모두 계산할 수 있는 주파수 대역이 없어 변화량을 보여 줄 수 없습니다."/>
          {/if}
          </details>
          <details>
            <summary>주파수별 세기 값 보기</summary>
            <div class="table-scroll"><table>
              <caption>주파수 구간별 평균 세기 (최대 60개 표시)</caption>
              <thead><tr><th scope="col">주파수 Hz</th><th scope="col">기간 A</th>
                <th scope="col">기간 B</th></tr></thead>
              <tbody>
                {#each result.frequencies.slice(0,60) as hz,i(i)}
                  <tr><td>{hz.toFixed(1)}</td><td>{fmt(channel.a[i])}</td>
                    <td>{fmt(channel.b[i])}</td></tr>
                {/each}
              </tbody>
            </table></div>
          </details>
        </section>
      {/each}
      </div>
      <SpectrumWaterfall {assetId} {place} onUse={useMeasurement} band={focused} channelId={selectedChannel}/>
      </div>
      <details><summary>비교한 측정과 결과 해석</summary>
        {#if fromSummary}<p class="context">{VIBRATION_SUMMARY_NOTE}</p>{/if}
        <p class="context">기간 A {result.used.a.map(place).join(", ")} · 기간 B {result.used.b.map(place).join(", ")}</p>
        {#if message}<AnalysisMessage {message} showHeadline={false}/>{/if}
      </details>
      {#if acquisition && result.used.b.length}
        {@const last=Math.max(...result.used.b)}
        <p class="continue">기간 B의 마지막 측정({place(last)})으로 이어서 보기
          {#each measurementLinks(assetId,last,{first:acquisition.first,last:acquisition.last,bindingId:acquisition.binding},"spectrum") as item(item.key)}
            <a href={item.href}>{item.label} →</a>
          {/each}</p>
      {/if}
      <CautionNote message="세기가 달라진 주파수는 결함 주파수나 고장 진단이 아닙니다. 경과 시간은 측정 간격으로 환산한 값이며 실제 측정 시각이 아닙니다."/>
      <details>
        <summary>기술 상세</summary>
        <p class="context">Welch PSD · 샘플링 {result.samplingRate}Hz · 세그먼트 {result.segment}개 샘플.
          세기는 PSD를 주파수 구간별로 평균한 값이며, 세기의 단위는 기록된 원본 진폭 단위의 제곱/Hz입니다.
          두 기간 그래프는 채널마다 같은 축을 씁니다. dB 축은 그 채널에서 가장 센 주파수 구간을 0 dB로 두고 -60 dB 아래는 잘라 그립니다. 이 응답은 데이터 출처 ID를 따로 돌려주지 않습니다.
          · 적용 모델 연결 {acquisition.binding}</p>
      </details>
    {/if}
    </div></div>

  {/if}
</section>
<style>
  .spectra{min-width:0}
  summary{cursor:pointer;font-weight:650;color:var(--color-action);padding-block:var(--space-2)}.context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .periods{display:grid;gap:var(--space-4);grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-block:var(--space-5)}
  .spectrum-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-2) var(--space-4);margin-block:var(--space-3)}
  .spectrum-toolbar>div{display:flex;gap:var(--space-1)}.spectrum-toolbar p{margin:0;font-size:var(--font-small);color:var(--color-ink-muted)}
  .spectrum-toolbar button[aria-pressed="true"]{background:var(--color-surface-selected);border-color:var(--color-action);font-weight:650}
  .spectrum-investigation{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-6)}
  .channels{min-width:0}
  .band-choices{display:flex;flex-wrap:wrap;gap:var(--space-1)}
  @media(max-width:1000px){.spectrum-investigation{grid-template-columns:minmax(0,1fr)}}
  /* 나란한 두 채널의 그래프 높이를 맞추려고 첫 칸만 다른 여백을 두지 않는다. */
  .channels>.series{min-width:0;margin:0;padding:0;border:0}
  .series h3{margin:0;font-size:var(--font-section)}.series h4{margin:var(--space-3) 0 var(--space-1);font-size:var(--font-small)}
  .series ol{margin:0;padding-inline-start:var(--space-5);font-size:var(--font-small)}
  .changed-band{fill:var(--color-caution-ink);opacity:.12}
  .band-button{font:inherit;color:var(--color-action);border:0;background:none;text-decoration:underline;cursor:pointer;padding:var(--space-2)}
  svg{display:block;width:100%;height:260px}svg polyline,svg path,svg line{vector-effect:non-scaling-stroke}.axis{stroke:var(--color-border);fill:none;stroke-width:2}
  .grid{stroke:var(--color-border);stroke-width:1}
  .scale{display:flex;gap:var(--space-2);align-items:flex-start;margin-top:var(--space-1);font-size:var(--font-small)}
  .line-a{fill:none;stroke:var(--color-ink-muted);stroke-width:2}
  .line-b{fill:none;stroke:var(--color-action);stroke-width:2;stroke-dasharray:5 4}
  .axis-note,.legend{color:var(--color-ink-muted);font-size:var(--font-small);margin:var(--space-1) 0}
  .peaks{margin:0;font-weight:650}.peaks .sep{color:var(--color-ink-muted);font-weight:400;margin-inline:var(--space-2)}
  .legend{display:flex;flex-wrap:wrap;gap:var(--space-1) var(--space-4)}
  .key{display:inline-block;width:18px;height:0;border-top:2px solid var(--color-ink-muted);vertical-align:middle;margin-inline-end:var(--space-1)}
  .key.b{border-top:2px dashed var(--color-action)}li{overflow-wrap:anywhere}
  .table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}
  th,td{text-align:left;padding:var(--space-2);border-bottom:1px solid var(--color-border)}
  caption{text-align:left;color:var(--color-ink-muted);font-size:var(--font-small)}
  .continue{display:flex;flex-wrap:wrap;gap:var(--space-2) var(--space-4);align-items:baseline;color:var(--color-ink-muted);font-size:var(--font-small)}
</style>
