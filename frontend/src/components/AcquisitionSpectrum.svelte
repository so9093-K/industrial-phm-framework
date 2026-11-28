<script lang="ts">
  import {exposeAnalysis, type AnalysisReadout} from "../analysis-readout.svelte";
  import {onMount,untrack} from "svelte";
  import AnalysisControls from "./AnalysisControls.svelte";
  import AcquisitionRange from "./AcquisitionRange.svelte";
  import SourceIdentity from "./SourceIdentity.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import SpectrumWaterfall from "./SpectrumWaterfall.svelte";
  import FrequencyPlot from "./FrequencyPlot.svelte";
  import type {AcquisitionTiming} from "../asset-data";
  import {measurementLabel} from "../time-axis";
  import {measurementLinks} from "../measurement-links";
  import {measure} from "../chart-axis";
  import {aroundBand,comparisonBand,frequencyLabel,relativePower,type FrequencyRange} from "../frequency-view";
  import {readWaterfall,type Waterfall} from "../waterfall";
  import {readAcquisition,readSpectrum,defaultSpans,validateSpans,peakSummary,frequencyText,
    SpectrumUnavailable,WaveformUnavailable,type Acquisition,type Spans,type Spectrum} from "../spectrum";
  import {handedSpans,isHanded,readVibrationSummary,vibrationDefault,VIBRATION_SUMMARY_NOTE} from "../summary-defaults";
  import {periodNames} from "../signal-selection";
  import {toward} from "../change-story";

  let {assetId,timing=null,selectedPosition=null,onPosition}:{assetId:string;timing?:AcquisitionTiming|null;selectedPosition?:number|null;onPosition?:(at:number)=>void}=$props();
  type State="loading"|"ready"|"empty"|"failed"|"unavailable"|"missing-waveform";
  let sourceState:State=$state("loading"),resultState:State=$state("empty");
  let acquisition:Acquisition|null=$state(null),spans:Spans|null=$state(null),result:Spectrum|null=$state(null);
  let waterfall:Waterfall|null=$state(null),mapState:State=$state("loading");
  let error=$state(""),selectionNotice=$state(""),fromSummary=$state(false);
  // 특이사항에서 넘어온 기간이면 다른 화면과 같은 '초기'·'특이사항 구간', 직접 고치면 '기간 A'·'기간 B'.
  const handed=handedSpans(location.search);
  const names=$derived(periodNames(fromSummary||isHanded(spans,handed)?"summary":null));
  const query=new URLSearchParams(location.search);
  const savedNumber=(key:string)=>{const value=Number(query.get(key)??NaN);return Number.isFinite(value)?value:null;};
  const savedFrom=savedNumber("spectrum_hz_from"),savedTo=savedNumber("spectrum_hz_to");
  let focused:FrequencyRange|null=$state(savedFrom!==null&&savedTo!==null&&savedFrom>=0&&savedTo>savedFrom?{from:savedFrom,to:savedTo}:null);
  let initialZoom=!(savedFrom!==null&&savedTo!==null&&savedFrom>=0&&savedTo>savedFrom)&&query.get("spectrum_hz")!=="all";
  let selectedChannel=$state(query.get("spectrum_channel")??"");
  let bandFrom:number|null=$state(savedNumber("spectrum_band"));
  let selected:number|null=$state(savedNumber("spectrum_measurement"));
  let viewMode:"compare"|"measurement"=$state(query.get("spectrum_view")==="measurement"?"measurement":"compare");
  let decibel=$state(query.get("spectrum_scale")!=="linear");
  const PERIODS=["a","b"] as const;
  const period=$derived.by(()=>{const current:Acquisition|null=acquisition;return timing&&current?.source===timing.sourceId?timing.periodSeconds:null;});
  const place=(at:number)=>measurementLabel(at,period);
  const channel=$derived.by(()=>{const current:Spectrum|null=result;return current?.channels.find(row=>row.id===selectedChannel)??null;});
  const band=$derived(channel?comparisonBand(channel,bandFrom):null);
  const domain=$derived.by(()=>{const current:Spectrum|null=result;return focused??{from:0,to:current?current.samplingRate/2:1};});
  const mapChannel=$derived.by(()=>{const current:Waterfall|null=waterfall;return current?.channels.find(row=>row.id===selectedChannel)??null;});
  const rowIndex=$derived.by(()=>{const current:Waterfall|null=waterfall;return selected===null?-1:current?.acquisitions.indexOf(selected)??-1;});
  const individual=$derived(rowIndex>=0?mapChannel?.decibels[rowIndex]??null:null);
  const top=$derived(channel?Math.max(...channel.a,...channel.b,1e-16):1);
  const plotSeries=$derived(viewMode==="measurement"
    ?individual?[{label:"선택 측정 "+selected+"회",values:individual}]:[]
    :channel?[{label:names.a,values:decibel?relativePower(channel.a,top):channel.a},
      {label:names.b,values:decibel?relativePower(channel.b,top):channel.b,comparison:true}]:[]);
  const linked=$derived.by(()=>{const current:Acquisition|null=acquisition;return current&&selected!==null?measurementLinks(assetId,selected,{first:current.first,last:current.last,bindingId:current.binding},"spectrum"):[];});
  let sourceRequest:AbortController|null=null,spectrumRequest:AbortController|null=null,mapRequest:AbortController|null=null;
  $effect(()=>{
    const at=selectedPosition,available=waterfall;
    if(at===null||!available?.acquisitions.includes(at))return;
    untrack(()=>{if(selected!==at){selected=at;remember();}});
  });

  function remember(){
    if(!spans)return;
    const url=new URL(location.href);url.searchParams.set("monitor_asset",assetId);
    for(const n of ["a","b"] as const)for(const edge of ["from","to"] as const)url.searchParams.set("spectrum_"+n+"_"+edge,String(spans[n][edge]));
    for(const [key,value] of [["spectrum_hz_from",focused?.from],["spectrum_hz_to",focused?.to],
      ["spectrum_channel",selectedChannel||undefined],["spectrum_band",band?.from],
      ["spectrum_measurement",selected??undefined],["spectrum_view",viewMode],["spectrum_scale",decibel?"db":"linear"]] as const){
      if(value===undefined)url.searchParams.delete(key);else url.searchParams.set(key,String(value));
    }
    if(focused)url.searchParams.delete("spectrum_hz");else url.searchParams.set("spectrum_hz","all");
    history.replaceState(history.state,"",url);
  }
  function savedSpans(fallback:Spans):Spans{
    const prefix=query.has("spectrum_a_from")?"spectrum_":query.has("feature_a_from")?"feature_":"acq_";
    if(!["a_from","a_to","b_from","b_to"].every(key=>query.has(prefix+key)))return fallback;
    const saved={a:{from:Number(query.get(prefix+"a_from")),to:Number(query.get(prefix+"a_to"))},
      b:{from:Number(query.get(prefix+"b_from")),to:Number(query.get(prefix+"b_to"))}};
    try{validateSpans(saved);return saved;}catch{return fallback;}
  }
  async function loadMap(){
    mapRequest?.abort();const req=new AbortController();mapRequest=req;mapState="loading";
    try{
      const read=await readWaterfall(assetId,req.signal);if(req.signal.aborted)return;
      waterfall=read;mapState=read.acquisitions.length?"ready":"empty";
      if(selected===null||!read.acquisitions.includes(selected)){
        if(selected!==null)selectionNotice="저장한 측정이 표시 목록에 없어 마지막 표시 측정을 선택했습니다.";
        selected=read.acquisitions.at(-1)??null;
      }
      remember();
    }catch{if(!req.signal.aborted){waterfall=null;mapState="failed";}}
  }
  async function readSource(){
    sourceRequest?.abort();spectrumRequest?.abort();mapRequest?.abort();
    const req=new AbortController();sourceRequest=req;sourceState="loading";resultState="empty";acquisition=null;result=null;waterfall=null;error="";
    try{
      const read=await readAcquisition(assetId,req.signal);if(req.signal.aborted)return;
      if(!read){sourceState="empty";return;}acquisition=read;
      const chosen=["spectrum_a_from","feature_a_from","acq_a_from"].some(key=>query.has(key));
      const found=!chosen?await readVibrationSummary(assetId,req.signal):null;if(req.signal.aborted)return;
      const summary=found&&found.intervals[0]?vibrationDefault(found,read.binding,[found.intervals[0].feature]):null;
      fromSummary=summary!==null;
      try{spans=summary?summary.spans:savedSpans(defaultSpans(read));}catch(cause:unknown){
        sourceState="unavailable";error=cause instanceof Error?cause.message:"파형 비교 기록이 부족합니다.";return;
      }
      sourceState="ready";void loadMap();await analyze();
    }catch(cause:unknown){if(!req.signal.aborted){sourceState="failed";error=cause instanceof Error?cause.message:"원본 파형 목록을 조회하지 못했습니다.";}}
  }
  function change(n:"a"|"b",edge:"from"|"to",value:number){
    if(!spans)return;spans={...spans,[n]:{...spans[n],[edge]:value}};
    spectrumRequest?.abort();result=null;resultState="empty";selectionNotice="";fromSummary=false;
  }
  function useMeasurement(n:"a"|"b"){
    if(!spans||!acquisition||selected===null)return;
    spans={...spans,[n]:{from:selected,to:selected}};fromSummary=false;viewMode="compare";
    selectionNotice="기간 "+n.toUpperCase()+"를 "+place(selected)+" 한 측정으로 바꿨습니다. 반대 기간은 유지했습니다.";
    remember();void analyze();
  }
  function chooseMeasurement(ordinal:number){selected=ordinal;viewMode="measurement";remember();onPosition?.(ordinal);}
  function zoomBand(){if(band&&result){focused=aroundBand(band,result.samplingRate/2);remember();}}
  function chooseBand(value:number){bandFrom=value;if(focused)zoomBand();remember();}
  function chooseChannel(id:string){selectedChannel=id;if(focused)zoomBand();remember();}
  function chooseView(mode:"compare"|"measurement"){viewMode=mode;remember();}
  async function analyze(){
    spectrumRequest?.abort();const req=new AbortController();spectrumRequest=req;
    result=null;resultState="loading";error="";
    try{
      if(!spans||!acquisition)throw new Error("원본 파형과 비교 기간을 확인하세요.");validateSpans(spans);
      const frozen:Spans={a:{...spans.a},b:{...spans.b}};
      const read=await readSpectrum(assetId,acquisition,frozen,req.signal);if(req.signal.aborted)return;
      if(!read.channels.some(row=>row.id===selectedChannel))selectedChannel=read.channels[0]?.id??"";
      if(focused){
        focused={from:Math.max(0,focused.from),to:Math.min(read.samplingRate/2,focused.to)};
        if(focused.to<=focused.from||read.frequencies.filter(hz=>focused!.from<=hz&&hz<=focused!.to).length<2){focused=null;selectionNotice="저장한 대역에 표시할 주파수가 부족해 전체 주파수를 표시합니다.";}
      }
      result=read;resultState=read.channels.length?"ready":"empty";
      if(initialZoom){initialZoom=false;if(band&&Math.abs(band.b-band.a)>=.1)zoomBand();}
      remember();
    }catch(cause:unknown){
      if(req.signal.aborted)return;error=cause instanceof Error?cause.message:"주파수 분석을 불러오지 못했습니다.";
      resultState=cause instanceof SpectrumUnavailable?"unavailable":cause instanceof WaveformUnavailable?"missing-waveform":"failed";
    }
  }
  onMount(()=>{void readSource();return()=>{sourceRequest?.abort();spectrumRequest?.abort();mapRequest?.abort();};});

  exposeAnalysis((): AnalysisReadout | null => {
    if (viewMode === "measurement") {
      if (selected === null || !waterfall || !individual || !mapChannel || mapState !== "ready") return null;
      let peak = -1;
      for (const [index, hz] of waterfall.frequencies.entries()) {
        if (hz > 0 && hz >= domain.from && hz <= domain.to && (peak === -1 || individual[index] > individual[peak]))
          peak = index;
      }
      return {
        "선택한 파형": mapChannel.label + " · " + place(selected),
        "표시 대역": frequencyLabel(domain.from) + "–" + frequencyLabel(domain.to) + " Hz",
        "표시 대역 최대 성분": peak < 0 ? "측정 없음" : frequencyLabel(waterfall.frequencies[peak]) + " Hz",
      };
    }
    if (resultState !== "ready" || !result || !spans || !channel) return null;
    return {
      "비교한 방향": channel.label,
      "조회 범위": `${names.a} ${spans.a.from}–${spans.a.to}번째, ${names.b} ${spans.b.from}–${spans.b.to}번째 측정`,
      "파형 수": `${names.a} ${result.used.a.length}회, ${names.b} ${result.used.b.length}회 평균`,
      ...(band ? {[`${frequencyLabel(band.from)}–${frequencyLabel(band.to)} Hz가 차지하는 비중`]: `${names.a} ${measure(band.a * 100, "%")} → ${names.b} ${measure(band.b * 100, "%")}`} : {}),
    };
  });
</script>

<section class="ui-panel spectra" aria-labelledby="spectra-title">
  <h2 class="visually-hidden" id="spectra-title">주파수 분석</h2>
  {#if sourceState==="loading"}<StatusNotice message="진동 원본 파형 목록을 불러오고 있습니다."/>
  {:else if sourceState==="empty"||sourceState==="unavailable"}<StatusNotice kind="uncertain" title="주파수를 비교할 원본 파형이 없습니다" message={error||"저장된 원본 파형이 없거나 비교할 측정이 부족합니다."}/>
  {:else if sourceState==="failed"}<StatusNotice kind="failure" title="원본 파형 목록을 불러오지 못했습니다" message={error} actionLabel="다시 불러오기" onAction={()=>void readSource()}/>
  {:else if acquisition&&spans}
    {#if viewMode==="compare"||resultState!=="ready"}<div class="spectrum-heading">
      <!-- 크기는 RMS 화면들이 말한다. 이 화면은 어느 주파수에서 커졌는지를 먼저 보인다. -->
      {#if result&&channel&&band}
      <div class="spectrum-facts band-share" aria-label={channel.label+" 기간 비교 결과"}>
        <p><strong>{frequencyLabel(band.from)}–{frequencyLabel(band.to)} Hz</strong><span>{channel.label} 에너지에서 이 대역이 차지하는 비중</span></p>
        {#each PERIODS as name(name)}<div class={"share-row "+name}>
          <b>{names[name]}</b><span class="track"><i style:width={band[name]*100+"%"}></i></span><strong>{measure(band[name]*100,null)}%</strong>
        </div>{/each}
      </div>{/if}
      <div class="period-controls"><p>{names.a} · {spans.a.from}–{spans.a.to}회 / {names.b} · {spans.b.from}–{spans.b.to}회</p><AnalysisControls title="비교 기간">
      {#snippet children(close)}{#if acquisition&&spans}
        <div class="periods">{#each PERIODS as name(name)}
          <AcquisitionRange {name} span={spans[name]} first={acquisition.first} last={acquisition.last} {period} onChange={(edge,value)=>change(name,edge,value)}/>
        {/each}</div>
        <button type="button" class="ui-button ui-button-primary" onclick={()=>{close();void analyze();}}>주파수 비교하기</button>
      {/if}{/snippet}
      </AnalysisControls></div>
    </div>{/if}
    {#if resultState==="loading"}<StatusNotice message="원본 파형의 주파수별 세기를 계산하고 있습니다."/>
    {:else if resultState==="failed"}<StatusNotice kind="failure" title="주파수 분석을 불러오지 못했습니다" message={error} actionLabel="같은 측정으로 다시 불러오기" onAction={()=>void analyze()}/>
    {:else if resultState==="missing-waveform"||resultState==="unavailable"}<StatusNotice kind="uncertain" title="고른 측정의 원본 파형을 확인할 수 없습니다" message={error}/>
    {:else if resultState==="empty"}<StatusNotice message="두 기간을 고르고 주파수 비교하기를 누르세요."/>
    {:else if result&&channel}
      <div class="spectrum-toolbar">
        <div class="button-group" role="group" aria-label="주파수 조사 방식">
          <button class="ui-button" type="button" aria-pressed={viewMode==="compare"} onclick={()=>chooseView("compare")}>기간 비교</button>
          <button class="ui-button" type="button" aria-pressed={viewMode==="measurement"} onclick={()=>chooseView("measurement")}>측정 조사</button>
        </div>
        {#if result.channels.length>1}<div class="button-group" role="group" aria-label="진동 방향">
          {#each result.channels as item(item.id)}<button class="ui-button" type="button" aria-pressed={selectedChannel===item.id} onclick={()=>chooseChannel(item.id)}>{item.label}</button>{/each}
        </div>{/if}
        {#if band}<label>주파수 범위 <select aria-label="살펴볼 주파수 대역" value={focused?band.from:"all"} onchange={event=>{if(event.currentTarget.value==="all"){focused=null;remember();}else{chooseBand(Number(event.currentTarget.value));zoomBand();remember();}}}>
          <option value="all">전체 주파수</option>
          {#each channel.shares as share(share.from)}<option value={share.from}>{frequencyLabel(share.from)}–{frequencyLabel(share.to)} Hz</option>{/each}
        </select></label>{/if}
      </div>
      {#if selectionNotice}<p class="selection-notice" role="status">{selectionNotice}</p>{/if}
      <div class="spectrum-investigation" class:measurement-view={viewMode==="measurement"}>
        <section class="spectrum-curve" aria-label={viewMode==="measurement"?"선택 측정의 스펙트럼":"두 기간의 평균 스펙트럼"}>
          <h3>{viewMode==="measurement"?(selected===null?"측정을 고르세요":selected+"회에서 보이는 주파수"):"두 기간의 평균 스펙트럼"}</h3>
          {#if plotSeries.length}
            <FrequencyPlot frequencies={viewMode==="measurement"?waterfall!.frequencies:result.frequencies} series={plotSeries} {domain} {band}
              height={viewMode==="measurement"?240:150} floor={viewMode==="measurement"||decibel?-60:0}
              ceiling={viewMode==="measurement"||decibel?0:top*1.05} unit={viewMode==="measurement"||decibel?"dB":channel.unit??"진폭²/Hz"}
              label={viewMode==="measurement"?place(selected!)+"의 주파수별 세기. 시간별 지도와 같은 dB 기준입니다.":channel.label+"의 평균 스펙트럼. "+names.a+" 실선, "+names.b+" 점선. 두 기간은 같은 기준입니다."}/>
            <p class="spectrum-key">{#if viewMode==="measurement"}전체 표시 측정의 최대 세기 = 0 dB
              {:else}<span><i></i>{names.a} 평균</span><span><i class="b"></i>{names.b} 평균</span>
                <label class="scale"><input type="checkbox" checked={decibel} onchange={event=>{decibel=event.currentTarget.checked;remember();}}/> dB</label>
                <span>{decibel?"두 기간 전체의 최대 세기 = 0 dB":"원본 진폭의 제곱/Hz"}</span>{/if}</p>
          {:else}<StatusNotice message={mapState==="loading"?"선택한 측정의 주파수를 불러오고 있습니다.":"이 측정의 주파수 지도를 표시할 수 없습니다. 기간 비교는 계속 사용할 수 있습니다."}/>{/if}
        </section>
        {#if waterfall&&mapChannel&&waterfall.acquisitions.length}
          <SpectrumWaterfall data={waterfall} channel={mapChannel} {domain} {band} {selected} onSelect={chooseMeasurement} {place} height={viewMode==="measurement"?240:115}/>
        {:else}<section class="map-status" aria-label="측정별 주파수 지도">
          {#if mapState==="loading"}<StatusNotice message="측정별 주파수 지도를 불러오고 있습니다."/>
          {:else if mapState==="failed"}<StatusNotice kind="failure" title="측정별 주파수 지도를 불러오지 못했습니다" message="두 기간의 평균 스펙트럼은 계속 볼 수 있습니다." actionLabel="지도 다시 불러오기" onAction={()=>void loadMap()}/>
          {:else}<StatusNotice message="표시할 측정별 주파수 지도가 없습니다."/>{/if}
        </section>{/if}
      </div>
      {#if waterfall&&waterfall.acquisitions.length}
        <div class="measurement-actions" role="group" aria-label="선택한 측정으로 주파수 비교">
          <label>측정 <select aria-label="선택 측정" value={selected??""} onchange={event=>chooseMeasurement(Number(event.currentTarget.value))}>
            {#each waterfall.acquisitions as ordinal(ordinal)}<option value={ordinal}>{ordinal}회</option>{/each}
          </select></label>
          {#if linked.find(link=>link.key==="model")}<a href={linked.find(link=>link.key==="model")!.href}>원본 파형·모델 보기 →</a>{/if}
          <details class="use-measurement"><summary>이 측정으로 비교</summary><div>
            <span>{names.a} · {spans.a.from}–{spans.a.to}회 / {names.b} · {spans.b.from}–{spans.b.to}회</span>
            <button class="ui-button" type="button" onclick={()=>useMeasurement("a")}>{toward(names.a)} 사용</button>
            <button class="ui-button" type="button" onclick={()=>useMeasurement("b")}>{toward(names.b)} 사용</button>
          </div></details>
          <output aria-live="polite" class="visually-hidden">{selected!==null?place(selected)+" 선택":""}</output>
        </div>
      {/if}
      <details class="analysis-details"><summary>계산 조건·상세 수치</summary>
        <SourceIdentity id={acquisition.source}/>
        {#if fromSummary||isHanded(spans,handed)}<p>{VIBRATION_SUMMARY_NOTE}</p>{/if}
        <p>{names.a} {result.used.a.length}회, {names.b} {result.used.b.length}회 파형의 평균입니다. 변화 대역이 고장 원인을 뜻하지는 않습니다.</p>
        <p>시간별 지도와 선택 측정은 표시된 모든 측정 중 해당 방향의 최대 세기를 0 dB로 둡니다. 평균 스펙트럼은 두 기간 평균의 최대 세기를 기준으로 하므로 두 그림의 dB 값을 직접 비교하지 않습니다. −60 dB 아래는 잘라 표시합니다.</p>
        <p>{names.a}: {result.used.a.map(place).join(", ")}<br/>{names.b}: {result.used.b.map(place).join(", ")}</p>
        <h4>가장 센 주파수</h4><p>{names.a} · {peakSummary(result.frequencies,channel.a)}<br/>{names.b} · {peakSummary(result.frequencies,channel.b)}</p>
        <p>표시 주파수와 피크는 인접 주파수를 묶은 평균값입니다.</p>
        {#if channel.bands.length}<div class="table-scroll"><table><caption>세기가 달라진 대역 · {names.b}의 대역 에너지를 {names.a} 대비 dB로 표시</caption>
          <thead><tr><th scope="col">대역 Hz</th><th scope="col">변화 dB</th></tr></thead><tbody>
            {#each channel.bands as changed(changed.from)}<tr><td>{frequencyText(changed.from)}–{frequencyText(changed.to)}</td><td>{measure(changed.changeDb,"dB")}</td></tr>{/each}
          </tbody></table></div>{/if}
        <div class="table-scroll"><table><caption>평균 스펙트럼 ({channel.unit??"원본 진폭²/Hz"}) · 선택 범위의 앞 60개 주파수</caption>
          <thead><tr><th scope="col">Hz</th><th scope="col">{names.a}</th><th scope="col">{names.b}</th></tr></thead><tbody>
          {#each result.frequencies.flatMap((hz,i)=>hz>=domain.from&&hz<=domain.to?[{hz,i}]:[]).slice(0,60) as item(item.i)}
            <tr><td>{frequencyText(item.hz)}</td><td>{channel.a[item.i].toExponential(3)}</td><td>{channel.b[item.i].toExponential(3)}</td></tr>
          {/each}</tbody></table></div>
        <p>Welch PSD · 샘플링 {result.samplingRate} Hz · 세그먼트 {result.segment}개 샘플. 세기 단위는 원본 진폭 단위의 제곱/Hz입니다.</p>
      </details>
    {/if}
  {/if}
</section>
<style>
  .spectra{min-width:0;--frequency-gutter:4.25rem;padding:var(--space-4) var(--space-5)}
  .periods{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:var(--space-4)}
  .spectrum-heading{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-3) var(--space-6);margin-bottom:var(--space-3)}
  .spectrum-facts{flex:1 1 500px;display:grid;gap:var(--space-1);align-items:start;max-width:760px}
  .period-controls{margin-left:auto;max-width:100%;display:grid;justify-items:end;gap:var(--space-1)}.period-controls p{margin:0;font-size:var(--font-label);color:var(--color-ink-muted)}
  .period-controls :global(.analysis-controls>button){padding:var(--space-2) var(--space-3);font-size:var(--font-small)}
  .spectrum-facts>p{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px var(--space-3);margin:0 0 var(--space-1)}
  .spectrum-facts>p strong{font-size:var(--font-section);font-variant-numeric:tabular-nums}
  .spectrum-facts>p span{color:var(--color-ink-muted);font-size:var(--font-small)}
  .share-row{display:grid;grid-template-columns:7.5rem minmax(0,1fr) 3.8rem;align-items:center;gap:var(--space-2);font-size:var(--font-small)}
  .share-row strong{text-align:right;font-variant-numeric:tabular-nums}.track{height:9px;background:var(--color-surface-selected);border-radius:3px;overflow:hidden}
  .track i{display:block;height:100%;background:var(--color-ink-muted)}.b .track i{background:var(--color-action)}
  .spectrum-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-2) var(--space-4);padding-block:var(--space-3);border-block:1px solid var(--color-border);margin-bottom:var(--space-4)}
  .button-group{display:flex;gap:var(--space-1)}
  label{display:flex;align-items:center;gap:var(--space-2);font-size:var(--font-small);min-width:0}
  .spectra select,.spectra button{font-size:var(--font-small)}.spectra button.ui-button{padding:var(--space-2) var(--space-3);min-height:40px}.spectrum-toolbar label{margin-left:auto}.spectrum-toolbar select{max-width:17rem}
  .spectrum-investigation{display:grid;gap:var(--space-4);min-width:0}.spectrum-curve{min-width:0}
  .spectrum-curve h3{font-size:var(--font-small);margin:0 0 var(--space-2);font-weight:650}
  .measurement-view{grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-6)}.measurement-view .spectrum-curve{grid-column:2;grid-row:1}
  .measurement-view :global(.waterfall),.measurement-view .map-status{grid-column:1;grid-row:1}
  .spectrum-key{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-1) var(--space-4);font-size:var(--font-label);color:var(--color-ink-muted);margin:var(--space-1) 0 0;min-height:24px}
  .spectrum-key i{display:inline-block;width:18px;border-top:2px solid var(--color-ink-muted);margin-right:var(--space-1);vertical-align:middle}.spectrum-key i.b{border-top:2px dashed var(--color-action)}
  .scale{font-size:var(--font-label)}.scale input{margin:0}.measurement-actions{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-2) var(--space-4);margin-top:var(--space-4);font-size:var(--font-small)}
  .measurement-actions a{margin-right:auto}.use-measurement>div{display:flex;flex-wrap:wrap;gap:var(--space-2);margin-top:var(--space-2)}
  summary{cursor:pointer;color:var(--color-action);font-size:var(--font-small)}.analysis-details{margin-top:var(--space-3);font-size:var(--font-small);color:var(--color-ink-muted)}
  .analysis-details h4{color:var(--color-ink);margin-bottom:var(--space-1)}.selection-notice{font-size:var(--font-small);margin-block:var(--space-2);color:var(--color-action)}
  .table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}caption{text-align:left}th,td{text-align:left;padding:var(--space-2);border-bottom:1px solid var(--color-border)}
  @media(max-width:800px){.measurement-view{grid-template-columns:minmax(0,1fr)}.measurement-view .spectrum-curve{grid-column:1;grid-row:2}.measurement-view :global(.waterfall){grid-row:1}.spectrum-toolbar label{margin-left:0}}
  @media(max-width:480px){.spectrum-facts{grid-template-columns:minmax(0,1fr);gap:var(--space-3)}.spectrum-toolbar select{max-width:100%}.period-controls{margin-left:0}.period-controls :global(.analysis-controls){align-items:flex-start}}
</style>
