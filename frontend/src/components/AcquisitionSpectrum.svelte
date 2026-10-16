<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
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
  <h2 id="spectra-title">원본 획득 파형의 주파수 에너지 비교</h2>
  <p class="context">설비 <strong>{assetId}</strong> · 획득 회차(ordinal)의 원본 파형만 사용합니다.
    이 회차는 실제 날짜·시간 간격이 아닙니다. 파워 변화는 결함 주파수나 고장 진단이 아닙니다.</p>
  {#if sourceState==="loading"}
    <StatusNotice message="원본 획득 파형 목록을 확인하고 있습니다."/>
  {:else if sourceState==="empty"||sourceState==="unavailable"}
    <StatusNotice kind="uncertain" title="스펙트럼 비교 근거가 없습니다"
      message={error||"저장된 획득 원본 파형이 없거나 비교할 회차가 부족합니다."}/>
  {:else if sourceState==="failed"}
    <StatusNotice kind="failure" title="원본 목록 조회 실패" message={error}
      actionLabel="다시 조회" onAction={()=>void readSource()}/>
  {:else if acquisition&&spans}
    <p class="context">서버가 제공한 획득 출처 <strong>{acquisition.source}</strong>
      · binding {acquisition.binding} · 전체 회차 {acquisition.first} ~ {acquisition.last}</p>
    <p class="context">이 API 응답은 획득 source ID를 다시 반환하지 않습니다.
      선택 출처와 완전한 원본 identity 일치는 서버의 검증된 저장 경계를 따릅니다.</p>
    <div class="periods">
      {#each ["a","b"] as label(label)}
        {@const name=label as "a"|"b"}
        <fieldset>
          <legend>비교 구간 {name.toUpperCase()} · 획득 회차</legend>
          <label>시작 회차 <input type="number" min={acquisition.first} max={acquisition.last} step="1"
            value={spans[name].from} onchange={e=>change(name,"from",e.currentTarget.value)}/></label>
          <label>끝 회차 <input type="number" min={acquisition.first} max={acquisition.last} step="1"
            value={spans[name].to} onchange={e=>change(name,"to",e.currentTarget.value)}/></label>
        </fieldset>
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>void analyze()}>
      원본 파형 PSD 비교
    </button>
    {#if resultState==="loading"}
      <StatusNotice message="검증된 원본 파형의 Welch PSD를 서버에서 계산하고 있습니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="PSD 조회 실패" message={error}
        actionLabel="같은 회차 재조회" onAction={()=>void analyze()}/>
    {:else if resultState==="missing-waveform"}
      <StatusNotice kind="uncertain" title="원본 파형 확인 불가" message={error}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="해당 회차의 원본 자료가 없습니다" message={error}/>
    {:else if resultState==="empty"}
      <StatusNotice message="회차와 원본 파형을 선택해 분석 결과를 확인합니다."/>
    {:else if result}
      <p class="context">서버 Welch PSD · 샘플링 {result.samplingRate}Hz
        · 세그먼트 {result.segment}개 샘플 · 구간 A에 사용한 획득 회차
        {result.used.a.join(", ")} · B에 사용한 회차 {result.used.b.join(", ")}</p>
      <p class="context">파워 값은 서버의 Welch PSD를 주파수 버킷별로 평균한 수치입니다.
        원본 물리 단위가 확인되지 않아 물리량 단위를 표시하지 않습니다.
        A/B 그래프는 각 채널 내 동일한 선형 스케일을 사용합니다.</p>
      {#each result.channels as channel(channel.id)}
        <section class="series">
          <h3>{channel.label} · {channel.id}</h3>
          <svg role="img" viewBox="0 0 640 145"
            aria-label="선형 파워 스펙트럼. 구간 A는 진한 선, B는 밝은 선이며 정확한 수치는 표를 참조하세요.">
            <path d="M24 20 V120 H614" class="axis"/>
            <polyline points={trace(channel.a,channel,result.frequencies)} class="line-a"/>
            <polyline points={trace(channel.b,channel,result.frequencies)} class="line-b"/>
            <text x="34" y="138" class="legend">구간 A: 진한 선 · 구간 B: 밝은 선</text>
          </svg>
          {#if channel.bands.length}
            <h4>파워 변화가 큰 주파수 대역</h4>
            <ol>
              {#each channel.bands as band,i(i)}
                <li>{band.from.toFixed(1)}–{band.to.toFixed(1)}Hz
                  · B/A 파워 변화 {band.changeDb.toFixed(2)}dB</li>
              {/each}
            </ol>
          {:else}
            <StatusNotice message="서버가 계산 가능한 양 구간의 파워 변화 대역을 반환하지 않았습니다."/>
          {/if}
          <details>
            <summary>주파수별 파워 수치 확인</summary>
            <div class="table-scroll"><table>
              <caption>동일 주파수 버킷의 PSD 집계값 (최대 60개 표시)</caption>
              <thead><tr><th scope="col">주파수 Hz</th><th scope="col">구간 A</th>
                <th scope="col">구간 B</th></tr></thead>
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
    {/if}
  {/if}
</section>
<style>
  .spectra{min-width:0}.context{color:var(--color-ink-muted);overflow-wrap:anywhere}
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
