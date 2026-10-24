<script lang="ts">
  import AcquisitionRange from "./AcquisitionRange.svelte";
  import type {AcquisitionTiming} from "../asset-data";
  import {measurementLabel} from "../time-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {yTicks} from "../chart-axis";
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import CautionNote from "./CautionNote.svelte";
  import {readAcquisition,readSpectrum,defaultSpans,validateSpans,
    SpectrumUnavailable,WaveformUnavailable,
    type Acquisition,type Spans,type Spectrum,type SpectrumChannel} from "../spectrum";

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
  let sourceRequest:AbortController|null=null;
  let spectrumRequest:AbortController|null=null;

  const fmt=(value:number)=>value.toExponential(3);
  let decibel=$state(false);
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
    history.replaceState(history.state,"",url);
  }
  function savedSpans(fallback:Spans):Spans {
    const q=new URLSearchParams(location.search);
    const span=(name:"a"|"b")=>({
      from:Number(q.get("spectrum_"+name+"_from")),
      to:Number(q.get("spectrum_"+name+"_to")),
    });
    if(!q.has("spectrum_a_from")||!q.has("spectrum_b_to")
      ||!q.has("spectrum_a_to")||!q.has("spectrum_b_from"))return fallback;
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
      try{spans=savedSpans(defaultSpans(data));}catch(cause:unknown){
        sourceState="unavailable";error=cause instanceof Error?cause.message:"파형 비교 기록이 부족합니다.";return;
      }
      sourceState="ready";remember();await analyze();
    }catch(cause:unknown){
      if(req.signal.aborted)return;
      sourceState="failed";
      error=cause instanceof Error?cause.message:"획득 원본 목록을 조회할 수 없습니다.";
    }
  }
  function change(n:"a"|"b",edge:"from"|"to",input:string){
    if(!spans)return;
    spans={...spans,[n]:{...spans[n],[edge]:Number(input)}};
    spectrumRequest?.abort();result=null;resultState="empty";
  }
  async function analyze(){
    spectrumRequest?.abort();
    const req=new AbortController();spectrumRequest=req;
    result=null;resultState="loading";error="";
    try{
      if(!spans||!acquisition)throw new Error("파형 원본과 획득 구간을 확인하세요.");
      validateSpans(spans);
      const frozen:Spans={a:{...spans.a},b:{...spans.b}};
      const data=await readSpectrum(assetId,acquisition,frozen,req.signal);
      if(req.signal.aborted)return;
      result=data;resultState=data.channels.length?"ready":"empty";remember();
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
  <h2 id="spectra-title">주파수 분석</h2>
  <p class="context">진동 원본 파형을 주파수별 세기로 바꿔 두 기간 A·B를 비교합니다. 어느 주파수에서 세기가 크게 달라졌는지 봅니다.</p>
  {#if sourceState==="loading"}
    <StatusNotice message="진동 원본 파형 목록을 불러오고 있습니다."/>
  {:else if sourceState==="empty"||sourceState==="unavailable"}
    <StatusNotice kind="uncertain" title="주파수를 비교할 원본 파형이 없습니다"
      message={error||"저장된 진동 원본 파형이 없거나 비교할 측정이 부족합니다."}/>
  {:else if sourceState==="failed"}
    <StatusNotice kind="failure" title="원본 파형 목록을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void readSource()}/>
  {:else if acquisition&&spans}
    <p class="context">데이터 출처 <strong>{acquisition.source}</strong>
      · {place(acquisition.first)} ~ {place(acquisition.last)}</p>
    <div class="periods">
      {#each ["a","b"] as label(label)}
        {@const name=label as "a"|"b"}
        <AcquisitionRange name={name} span={spans[name]} first={acquisition.first} last={acquisition.last} {period}
          onChange={(edge, ordinal) => change(name, edge, String(ordinal))} />
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>void analyze()}>
      주파수 비교하기
    </button>
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
      <details><summary>계산에 사용한 측정 보기</summary><p class="context">기간 A {result.used.a.map(place).join(", ")} · 기간 B {result.used.b.map(place).join(", ")}</p></details>
      <label class="scale"><input type="checkbox" bind:checked={decibel}/> 세로축을 dB로 보기 · 세기가 작은 주파수의 변화도 보입니다</label>
      {#each result.channels as channel(channel.id)}
        {@const changed=channel.bands.filter(band=>Math.abs(band.changeDb)>=MEANINGFUL_DB)}
        {@const frequencies=result.frequencies}
        {@const axis=axisFor(channel,decibel)}
        <section class="series">
          <h3>{channel.label} · {channel.id}</h3>
          <p class="axis-note">세로축 · 주파수별 평균 세기 (PSD) · {decibel?"두 기간 중 가장 센 주파수 대비 dB":channel.unit??"단위 미확인"} · 두 기간은 같은 눈금</p>
          <ValueAxis ticks={yTicks(axis.lo,axis.hi,0,180)} height={180} unit={decibel?"dB":null}>
          <svg role="img" viewBox="0 0 800 180" preserveAspectRatio="none"
            aria-label={"주파수별 세기. 기간 A는 실선, 기간 B는 점선입니다. " + result.frequencies[0].toFixed(0) + "Hz부터 " + result.frequencies[result.frequencies.length-1].toFixed(0) + "Hz까지. 정확한 값은 표에 있습니다."}>
            {#each yTicks(axis.lo,axis.hi,0,180) as tick(tick.value)}<line x1="0" x2="800" y1={tick.y} y2={tick.y} class="grid"/>{/each}
            <polyline points={trace(channel.a,axis,result.frequencies)} class="line-a"/>
            <polyline points={trace(channel.b,axis,result.frequencies)} class="line-b"/>
            <path d="M0 0 V180 H800" class="axis"/>
          </svg>
          {#snippet footer()}<XAxis lo={frequencies[0]} hi={frequencies[frequencies.length-1]}
            scale={{kind:"value"}} note="가로축 · 주파수 (Hz)"/>{/snippet}
          </ValueAxis>
          <p class="legend"><span><i class="key a"></i>기간 A (실선)</span><span><i class="key b"></i>기간 B (점선)</span></p>
          {#if changed.length}
            <h4>세기가 크게 달라진 주파수</h4>
            <ol>
              {#each changed as band,i(i)}
                <li>{band.from.toFixed(1)}–{band.to.toFixed(1)}Hz
                  · B/A 세기 변화 {band.changeDb.toFixed(2)}dB</li>
              {/each}
            </ol>
          {:else if channel.bands.length}
            <p class="context">두 기간의 세기 차이가 {MEANINGFUL_DB}dB 이상인 주파수는 없습니다.</p>
          {:else}
            <StatusNotice message="두 기간 모두 계산할 수 있는 주파수 대역이 없어 변화량을 보여 줄 수 없습니다."/>
          {/if}
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
      <CautionNote message="세기가 달라진 주파수는 결함 주파수나 고장 진단이 아닙니다. 경과 시간은 측정 간격으로 환산한 값이며 실제 측정 시각이 아닙니다."/>
      <details>
        <summary>기술 상세</summary>
        <p class="context">Welch PSD · 샘플링 {result.samplingRate}Hz · 세그먼트 {result.segment}개 샘플.
          세기는 PSD를 주파수 구간별로 평균한 값이며, 세기의 단위는 기록된 원본 진폭 단위의 제곱/Hz입니다. 원본 단위가 없으면 단위 미확인으로 표시합니다.
          두 기간 그래프는 채널마다 같은 축을 씁니다. dB 축은 그 채널에서 가장 센 주파수 구간을 0 dB로 두고 -60 dB 아래는 잘라 그립니다. 이 응답은 데이터 출처 ID를 따로 돌려주지 않습니다.
          · 적용 모델 연결 {acquisition.binding}</p>
      </details>
    {/if}
  {/if}
</section>
<style>
  .spectra{min-width:0}
  summary{cursor:pointer;font-weight:650;color:var(--color-action);padding-block:var(--space-2)}.context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .periods{display:grid;gap:var(--space-4);grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-block:var(--space-5)}
  .series{margin-top:var(--space-6);border-top:1px solid var(--color-border);padding-top:var(--space-4)}
  svg{display:block;width:100%;height:180px}svg polyline,svg path,svg line{vector-effect:non-scaling-stroke}.axis{stroke:var(--color-border);fill:none;stroke-width:2}
  .grid{stroke:var(--color-border);stroke-width:1}
  .scale{display:flex;gap:var(--space-2);align-items:center;margin-top:var(--space-3);font-size:var(--font-small)}
  .line-a{fill:none;stroke:var(--color-action);stroke-width:2}
  .line-b{fill:none;stroke:var(--color-ink-muted);stroke-width:2;stroke-dasharray:5 4}
  .axis-note,.legend{color:var(--color-ink-muted);font-size:var(--font-small);margin:var(--space-1) 0}
  .legend{display:flex;flex-wrap:wrap;gap:var(--space-1) var(--space-4)}
  .key{display:inline-block;width:18px;height:0;border-top:2px solid var(--color-action);vertical-align:middle;margin-inline-end:var(--space-1)}
  .key.b{border-top:2px dashed var(--color-ink-muted)}li{overflow-wrap:anywhere}
  .table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}
  th,td{text-align:left;padding:var(--space-2);border-bottom:1px solid var(--color-border)}
  caption{text-align:left;color:var(--color-ink-muted);font-size:var(--font-small)}
</style>
