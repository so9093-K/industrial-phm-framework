<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import CautionNote from "./CautionNote.svelte";
  import {readAcquisition,readSpectrum,defaultSpans,validateSpans,
    SpectrumUnavailable,WaveformUnavailable,
    type Acquisition,type Spans,type Spectrum,type SpectrumChannel} from "../spectrum";

  let {assetId}:{assetId:string}=$props();
  type State="loading"|"ready"|"empty"|"failed"|"unavailable"|"missing-waveform";
  let sourceState:State=$state("loading");
  let resultState:State=$state("empty");
  let acquisition:Acquisition|null=$state(null);
  let spans:Spans|null=$state(null);
  let result:Spectrum|null=$state(null);
  let error=$state("");
  let sourceRequest:AbortController|null=null;
  let spectrumRequest:AbortController|null=null;

  const fmt=(value:number)=>value.toExponential(3);
  function trace(values:number[],channel:SpectrumChannel,frequencies:number[]):string {
    const top=Math.max(...channel.a,...channel.b,1e-16);
    const lo=frequencies[0], hi=frequencies[frequencies.length-1];
    return values.map((n,i)=>{
      const x=24+590*(frequencies[i]-lo)/Math.max(hi-lo,1e-12);
      const y=113-91*n/top;
      return x.toFixed(1)+","+y.toFixed(1);
    }).join(" ");
  }
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
    <p class="context">데이터 출처 <strong>{acquisition.source}</strong> · 적용 모델 {acquisition.binding}
      · 측정 #{acquisition.first} ~ #{acquisition.last}</p>
    <div class="periods">
      {#each ["a","b"] as label(label)}
        {@const name=label as "a"|"b"}
        <fieldset>
          <legend>기간 {name.toUpperCase()} · 측정 순서</legend>
          <label>처음 측정 # <input type="number" min={acquisition.first} max={acquisition.last} step="1"
            value={spans[name].from} onchange={e=>change(name,"from",e.currentTarget.value)}/></label>
          <label>마지막 측정 # <input type="number" min={acquisition.first} max={acquisition.last} step="1"
            value={spans[name].to} onchange={e=>change(name,"to",e.currentTarget.value)}/></label>
        </fieldset>
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
      <p class="context">기간 A 측정 #{result.used.a.join(", #")} · 기간 B 측정 #{result.used.b.join(", #")}</p>
      {#each result.channels as channel(channel.id)}
        <section class="series">
          <h3>{channel.label} · {channel.id}</h3>
          <svg role="img" viewBox="0 0 640 145"
            aria-label="주파수별 세기. 기간 A는 진한 선, B는 밝은 선입니다. 정확한 값은 표에 있습니다.">
            <path d="M24 20 V120 H614" class="axis"/>
            <polyline points={trace(channel.a,channel,result.frequencies)} class="line-a"/>
            <polyline points={trace(channel.b,channel,result.frequencies)} class="line-b"/>
            <text x="34" y="138" class="legend">기간 A: 진한 선 · 기간 B: 밝은 선</text>
          </svg>
          {#if channel.bands.length}
            <h4>세기가 크게 달라진 주파수</h4>
            <ol>
              {#each channel.bands as band,i(i)}
                <li>{band.from.toFixed(1)}–{band.to.toFixed(1)}Hz
                  · B/A 세기 변화 {band.changeDb.toFixed(2)}dB</li>
              {/each}
            </ol>
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
      <CautionNote message="세기가 달라진 주파수는 결함 주파수나 고장 진단이 아닙니다. 측정 순서는 실제 날짜나 일정한 시간 간격이 아닙니다."/>
      <details>
        <summary>기술 상세</summary>
        <p class="context">Welch PSD · 샘플링 {result.samplingRate}Hz · 세그먼트 {result.segment}개 샘플.
          세기는 PSD를 주파수 구간별로 평균한 값이며, 원본 물리 단위가 확인되지 않아 단위를 붙이지 않습니다.
          두 기간 그래프는 채널마다 같은 선형 축을 씁니다. 이 응답은 데이터 출처 ID를 따로 돌려주지 않습니다.</p>
      </details>
    {/if}
  {/if}
</section>
<style>
  .spectra{min-width:0}
  summary{cursor:pointer;font-weight:650;color:var(--color-action);padding-block:var(--space-2)}.context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .periods{display:grid;gap:var(--space-4);grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-block:var(--space-5)}
  label{display:grid;gap:var(--space-2);font-weight:650}
  input{width:100%;min-width:0;border:1px solid var(--color-border);border-radius:var(--radius-control);
    color:var(--color-ink);background:var(--color-surface);padding:var(--space-3)}
  fieldset{min-width:0;border:1px solid var(--color-border);border-radius:var(--radius-panel);display:grid;gap:var(--space-3)}
  .series{margin-top:var(--space-6);border-top:1px solid var(--color-border);padding-top:var(--space-4)}
  svg{display:block;width:100%;height:auto}.axis{stroke:var(--color-border);fill:none}
  .line-a{fill:none;stroke:var(--color-action);stroke-width:2}
  .line-b{fill:none;stroke:var(--color-ink-muted);stroke-width:2;stroke-dasharray:4 3}
  .legend{font-size:12px;fill:var(--color-ink)}li{overflow-wrap:anywhere}
  .table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}
  th,td{text-align:left;padding:var(--space-2);border-bottom:1px solid var(--color-border)}
  caption{text-align:left;color:var(--color-ink-muted);font-size:var(--font-small)}
</style>
