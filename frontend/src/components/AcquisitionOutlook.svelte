<script lang="ts">
  import AnalysisControls from "./AnalysisControls.svelte";
  import TaskDialog from "./TaskDialog.svelte";
  let validationOpen = $state(false);
  import SignalEvolution from "./SignalEvolution.svelte";
  import {preferredFeature} from "../acquisition-profile";
  import ForecastFit from "./ForecastFit.svelte";
  import {worseThanPersistence} from "../forecast-fit";
  import ForecastSettings from "./ForecastSettings.svelte";
  import ForecastValidation from "./ForecastValidation.svelte";
  import AnalysisMessage from "./AnalysisMessage.svelte";
  import {outlookMessage, forecastMessage} from "../analysis-messages";
  import {featureTrendHref} from "../measurement-links";
  import {savedSettings,rememberSettings} from "../forecast-settings";
  import {onMount} from "svelte";
  import {measure} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {elapsedText,measurementScale} from "../time-axis";
  import StatusNotice from "./StatusNotice.svelte";
  import {reachDuration,reachText} from "../reach";
  import {num} from "../format";
  import {assetTabUrl} from "../routes";
  import OutlookBriefingPanel from "./OutlookBriefingPanel.svelte";
  import ReviewRequest from "./ReviewRequest.svelte";
  let reviewSelection: string | null = $state(null);
  import {
    loadAcquisitionOptions,loadAcquisitionPair,acquisitionChart,
    AcquisitionVersionMismatch,AcquisitionOutlookUnavailable,
    type AcquisitionOptions,type AcquisitionProjection,type AcquisitionFeature,
  } from "../acquisition-outlook";
  import {HORIZON_LABEL,type Conditions,type Direction,type Horizon} from "../projections";

  let {assetId}:{assetId:string}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed"|"mismatch";
  let listState:State=$state("loading");
  let resultState:State=$state("empty");
  let options:AcquisitionOptions|null=$state(null);
  let outlook:AcquisitionProjection|null=$state(null);
  let includeLimits=$state(false);
  let message=$state("");
  const params=new URLSearchParams(location.search);
  let settings=$state(savedSettings(params));
  let customSettings=$state([...params.keys()].some(key=>/^forecast_(prior|range|training|seasonality|backtest)$/.test(key)));
  let featureId=$state(params.get("acq_forecast_feature")??"");
  let timeHorizon:Horizon|null=$state(params.get("acq_forecast_unit")==="time" ? (params.get("acq_forecast_horizon")??"1h") as Horizon : null);
  let countText=$state(params.get("acq_forecast_count")??"30");
  let assumedText=$state(params.get("acq_assumed_period")??"");
  let managementText=$state(params.get("acq_management")??"");
  let endText=$state(params.get("acq_end")??"");
  let direction:Direction=$state(params.get("acq_direction")==="lower"?"lower":"upper");
  const criteriaPending=$derived.by(()=>{const current:AcquisitionProjection|null=outlook;return current!==null&&(current.conditions.direction!==direction
    ||current.conditions.management!==(managementText.trim()?Number(managementText):null)
    ||current.conditions.end!==(endText.trim()?Number(endText):null));});
  let listAbort:AbortController|null=null;
  let resultAbort:AbortController|null=null;
  const available=$derived.by(():AcquisitionFeature[]=>
    options?options.features.filter((item:AcquisitionFeature)=>item.countForecast):[]);
  function floatOrNull(text:string):number|null{
    if(text.trim()==="")return null;
    const number=Number(text);
    if(!Number.isFinite(number))throw new Error("유한한 숫자로 기준·간격을 입력하세요.");
    return number;
  }
  function selectedFeature():AcquisitionFeature|undefined {
    return options?.features.find(f=>f.id===featureId);
  }
  function remember(){
    const url=new URL(location.href);
    url.searchParams.set("monitor_asset",assetId);
    const values={
      acq_forecast_unit:timeHorizon===null?"count":"time",acq_forecast_horizon:timeHorizon??"",
      acq_forecast_feature:featureId,acq_forecast_count:countText,
      acq_assumed_period:assumedText,acq_direction:direction,
      acq_management:managementText,acq_end:endText,
    };
    for(const [key,value] of Object.entries(values)){
      if(value.trim())url.searchParams.set(key,value);
      else url.searchParams.delete(key);
    }
    if(customSettings)rememberSettings(url,settings);
    history.replaceState(history.state,"",url);
  }
  function invalidate(){
    resultAbort?.abort();outlook=null;resultState="empty";message="";
    remember();
  }
  async function loadOptions(){
    listAbort?.abort();resultAbort?.abort();
    const request=new AbortController();listAbort=request;
    listState="loading";resultState="empty";options=null;outlook=null;message="";
    try{
      const next=await loadAcquisitionOptions(assetId,request.signal);
      if(request.signal.aborted)return;
      if(!next){listState="empty";return;}
      options=next;
      const valid=next.features.filter(f=>f.countForecast);
      if(!valid.length){listState="unavailable";return;}
      if(featureId&&!valid.some(f=>f.id===featureId))throw new Error("고른 진동 특징이 이 데이터 출처에 없거나 전망할 수 없습니다.");
      // Opens on RMS like the other vibration screens, so one feature is followed from trend to outlook.
      if(!featureId)featureId=preferredFeature(valid)!.id;
      if (!params.has("acq_forecast_count")) countText=String(Math.min(30,Math.max(1,Math.floor(selectedFeature()!.validPoints/2))));
      listState="ready";remember();await calculate();
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      listState="failed";message=cause instanceof Error?cause.message:"측정 특징 목록을 읽지 못했습니다.";
    }
  }
  async function calculate(){
    resultAbort?.abort();
    const request=new AbortController();resultAbort=request;
    resultState="loading";outlook=null;message="";
    try{
      if(!options||!selectedFeature())throw new Error("전망을 계산할 진동 특징을 먼저 선택하세요.");
      const count=Number(countText);
      const assumed=floatOrNull(assumedText);
      const conditions:Conditions={direction,management:floatOrNull(managementText),
        end:floatOrNull(endText)};
      remember();
      const data=await loadAcquisitionPair(options,featureId,count,assumed,conditions,request.signal,customSettings?settings:undefined,timeHorizon);
      if(request.signal.aborted)return;
      outlook=data;resultState="ready";
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      message=cause instanceof Error?cause.message:"진동 전망을 계산할 기록을 확인할 수 없습니다.";
      resultState=cause instanceof AcquisitionVersionMismatch?"mismatch"
        :cause instanceof AcquisitionOutlookUnavailable?"unavailable":"failed";
    }
  }
  function timeBasis(record:AcquisitionProjection):string{
    if(record.timeBasis==="recorded")return "기록된 측정 간격 "+elapsedText(record.effectivePeriod);
    if(record.timeBasis==="assumed")return "가정한 측정 간격 "+elapsedText(record.effectivePeriod)+" (실제 측정 간격 아님)";
    return "측정 간격 정보 없음 — 측정 횟수로만 계산";
  }
  const formatOffset=(n:number)=>Number.isInteger(n)?String(n):n.toFixed(2);
  const scenarioLabel=(id:string)=>({current:"기본 설정",recent:"최근 구간 중심",responsive:"변화에 민감",linear:"최근 속도 유지"} as Record<string,string>)[id]??id;
  onMount(()=>{void loadOptions();return()=>{listAbort?.abort();resultAbort?.abort();};});
</script>

<section class="ui-panel" aria-labelledby="acq-outlook-title">
  <h2 class="visually-hidden" id="acq-outlook-title">추세·기준 도달 전망</h2>
  {#if listState==="loading"}
    <StatusNotice message="전망할 수 있는 진동 특징을 불러오고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="전망할 진동 특징을 불러오지 못했습니다" message={message}
      actionLabel="다시 불러오기" onAction={()=>void loadOptions()}/>
  {:else if listState==="empty"||listState==="unavailable"}
    <StatusNotice kind="uncertain" title="전망에 필요한 진동 측정이 부족합니다"
      message="분석된 진동 측정이 20회 이상 있어야 합니다."
      actionLabel="진동 특징 비교 보기" actionHref={assetTabUrl(assetId, "change", "compare", "vibration")}/>
  {:else if options}
    <div class="analysis-workspace forecast-workspace"><div class="forecast-controls">
    <div class="inputs">
      <label>진동 신호
        <select value={featureId} onchange={e=>{featureId=e.currentTarget.value;managementText="";endText="";invalidate();void calculate();}}>
          {#each options.features as item (item.id)}
            <option value={item.id} disabled={!item.countForecast}>
              {item.label} · {item.validPoints}회{item.countForecast?"":" (부족)"}
            </option>
          {/each}
        </select>
      </label>

      <label>예측 범위 단위<select value={timeHorizon===null?"count":"time"} onchange={e=>{timeHorizon=e.currentTarget.value==="time"?"1h":null;invalidate();}}><option value="count">측정 횟수</option><option value="time">시간 (측정 간격 필요)</option></select></label>
      {#if timeHorizon!==null}<label>예측 기간<select value={timeHorizon} onchange={e=>{timeHorizon=e.currentTarget.value as Horizon;invalidate();}}>{#each ["1h","24h","7d","30d"] as h}<option value={h}>{HORIZON_LABEL[h as Horizon]}</option>{/each}</select></label>{/if}
      {#if timeHorizon===null}<label>앞으로 볼 측정 횟수 (1~2000)
        <input type="number" min="1" max="2000" step="1" value={countText}
          oninput={e=>{countText=e.currentTarget.value;invalidate();}}/>
      </label>{/if}
      <button type="button" class="ui-button ui-button-primary"
        onclick={()=>void calculate()} disabled={available.length===0}>계산하기</button>
    </div>

    <AnalysisControls title="고급 설정">{#snippet children(close)}{#if options}
    <details class="interval-assumption" open={assumedText.trim()!==""||(timeHorizon!==null&&options.recordedPeriod===null)}>
      <summary>측정 간격 가정 (선택)</summary><label>측정 간격 가정 (선택 · 초, 1~86400)
        <input type="number" min="1" max="86400" step="any" value={assumedText}
          placeholder={options.recordedPeriod===null?"비우면 측정 횟수로만 계산":"비우면 기록된 간격 사용"}
          oninput={e=>{assumedText=e.currentTarget.value;invalidate();}}/>
      </label></details>
    <ForecastSettings value={settings} expanded={customSettings} onChange={value=>{settings=value;customSettings=true;invalidate();}}/>
    <button type="button" class="ui-button ui-button-primary" disabled={available.length===0} onclick={()=>{close();void calculate();}}>적용하고 계산하기</button>
    {/if}{/snippet}</AnalysisControls>
    </div>

    <div class="analysis-body">
    {#if resultState==="loading"}
      <StatusNotice message="전망을 계산하고 있습니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="전망을 계산하지 못했습니다" message={message}
        actionLabel="다시 계산하기" onAction={()=>void calculate()}/>
    {:else if resultState==="mismatch"}
      <StatusNotice kind="uncertain" title="데이터가 바뀌어 결과를 다시 계산해야 합니다" message={message}
        actionLabel="진동 특징 목록 다시 불러오기" onAction={()=>void loadOptions()}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="이 조건으로는 전망할 수 없습니다" message={message}/>
    {:else if outlook}
      {@const displayFeature=outlook.featureId}
      {@const limited=outlook.conditions.management!==null||outlook.conditions.end!==null}
      {@const chart=acquisitionChart(outlook,includeLimits)}
      {@const period=outlook.timeBasis==="ordinal"?null:outlook.effectivePeriod}
      {@const worse=worseThanPersistence(outlook.checks?.[0])}
      {@const told=outlookMessage({axis:"acquisition",period,unit:outlook.unit,conditions:outlook.conditions,
        scenarios:outlook.scenarios,checks:outlook.reachChecks??[]},
        [{label:"다음 측정이 기준에 다가가는지 특징 추이에서 보기",href:featureTrendHref(outlook.assetId,outlook.featureId)}]) ?? forecastMessage({last:outlook.history.at(-1)?.value??null,start:outlook.forecast[0].estimate,end:outlook.forecast.at(-1)!,unit:outlook.unit,
          horizon:formatOffset(outlook.forecast.at(-1)!.ordinal)+"번째 측정",checks:outlook.checks??[]})}
      <section class="result" aria-labelledby="acq-result-title">
        <div class="result-head">
          <h3 id="acq-result-title">추세 전망</h3>
          <span class="context">마지막 실측 · {outlook.record.last}번째 측정 · {timeBasis(outlook)}</span>
        </div>
        {#if worse}
          <p class="forecast-caution" role="status"><strong>이 모델의 예측으로 추세 판단을 보류하세요.</strong> <a href={featureTrendHref(outlook.assetId,outlook.featureId)}>최근 실제 측정의 변화부터 보기 →</a>{#if told && !limited}{" "}<span class="outlook-summary">{told.headline}</span>{/if}</p>
        {/if}
        {#if told && !worse && !limited}<p class="result-statement outlook-summary">{told.headline}</p>{/if}
        {#if chart}
          {@const axisNote=(period===null?"측정 회차":"기록 시작 후 경과 시간 · "+(outlook.timeBasis==="assumed"?"가정한":"기록된")+" 측정 간격 "+elapsedText(period))+" · 세로선은 마지막 "+chart.last+"번째 측정"}
          {#if limited}<label class="axis-toggle"><input type="checkbox" bind:checked={includeLimits} /> 기준선까지 세로축에 포함</label>{/if}
          {#if outlook.conditions.management!==null&&chart.management===null}<p class="context">관리 기준 {measure(outlook.conditions.management,outlook.unit)} · 현재 그래프 범위 밖</p>{/if}
          {#if outlook.conditions.end!==null&&chart.endLimit===null}<p class="context">종료 기준 {measure(outlook.conditions.end,outlook.unit)} · 현재 그래프 범위 밖</p>{/if}
          <figure class="chart" class:unreliable={worse}>
            <p class="axis-note">최고 {measure(chart.high, outlook.unit)} · 최저 {measure(chart.low, outlook.unit)}</p>
            <ValueAxis ticks={chart.ticks} height={chart.height} unit={outlook.unit}>
            <svg viewBox={"0 0 "+chart.width+" "+chart.height} preserveAspectRatio="none" role="img"
              aria-label={"저장된 "+chart.first+"~"+chart.last+"번째 측정과 "+formatOffset(chart.end)+"번째 측정까지의 예측"}>
              {#each chart.ticks as tick (tick.value)}<line x1="0" x2={chart.width} y1={tick.y} y2={tick.y} class="grid" />{/each}
              {#if chart.band}<path d={chart.band} class="band" />{/if}
              <line x1={chart.lastX} x2={chart.lastX} y1="0" y2={chart.height} class="now" />
              {#if chart.management!==null}<line x1="0" x2={chart.width} y1={chart.management} y2={chart.management} class="management" />{/if}
              {#if chart.endLimit!==null}<line x1="0" x2={chart.width} y1={chart.endLimit} y2={chart.endLimit} class="end" />{/if}
              {#if chart.fitted}<path d={chart.fitted} class="fitted" />{/if}
              {#if chart.gap}<line x1={chart.gap.x} x2={chart.gap.x} y1={chart.gap.observed} y2={chart.gap.modeled} class="fit-gap" />{/if}
              <path d={chart.history} class="history" />
              <path d={chart.estimate} class="estimate" />
              <path d={"M0 0 V"+chart.height+" H"+chart.width} class="axis" />
            </svg>
            {#snippet footer()}<XAxis lo={chart.first} hi={chart.end} scale={measurementScale(period)}
              note={axisNote} />{/snippet}
            </ValueAxis>
            <figcaption class="legend">
              <span><i class="key history"></i>저장된 측정</span>
              {#if chart.fitted}<span><i class="key fitted"></i>모델이 학습한 값</span>{/if}
              <span><i class="key estimate"></i>추세 예측</span>
              <span><i class="key band"></i>예측 범위</span>
              {#if chart.management!==null}<span><i class="key management"></i>관리 기준 {measure(outlook.conditions.management!, outlook.unit)}</span>{/if}
              {#if chart.endLimit!==null}<span><i class="key end"></i>종료 기준 {measure(outlook.conditions.end!, outlook.unit)}</span>{/if}
            </figcaption>
          </figure>
        {/if}
        {#if outlook.evolution}<SignalEvolution data={outlook.evolution} unit={outlook.unit}/>{/if}
        <button type="button" class="ui-button" onclick={()=>validationOpen=true}>예측 시작값·과거 검증 보기</button>
        <TaskDialog bind:open={validationOpen} title="전망 해석·과거 검증">
        {#if told}<AnalysisMessage message={told} showHeadline={false}
          subject={options.features.find(item=>item.id===displayFeature)?.label ?? displayFeature}
          basis={outlook.record.last + "번째 측정까지의 기록 · " + timeBasis(outlook)}
          boundary="예상 여유의 시작은 기록 마지막 측정입니다." />{/if}
        <ForecastFit showValues={limited} fit={outlook.fit??null} checks={outlook.checks} unit={outlook.unit} axis="acquisition"
          requestedCount={timeHorizon===null?outlook.horizonCount:null} effectivePeriod={outlook.effectivePeriod} />
        <ForecastValidation checks={outlook.checks}/>
        <details>
          <summary>앞으로 {num(outlook.horizonCount)}회 측정의 예측값{timeHorizon?" · "+timeHorizon+"를 측정 간격으로 환산":""}</summary>
          <div class="scroll"><table>
            <caption>측정별 특징 예측값 (최대 12개) · 예측 범위는 계산상 범위이며 고장 신뢰구간이 아닙니다</caption>
            <thead><tr><th scope="col">측정</th><th scope="col">예측값</th>
              <th scope="col">범위 하한</th><th scope="col">범위 상한</th></tr></thead>
            <tbody>
              {#each outlook.forecast.slice(0,12) as item,i (i)}
                <tr><td>{formatOffset(item.ordinal)}번째</td><td>{num(item.estimate)}</td>
                  <td>{num(item.lower)}</td><td>{num(item.upper)}</td></tr>
              {/each}
            </tbody>
          </table></div>
        </details>
        {#if limited}
          <details>
            <summary>계산 방식별 결과 {outlook.scenarios.length}가지</summary>
            <div class="scroll"><table>
              <caption>계산 방식 사이의 차이는 신뢰 구간이 아닙니다 · 기준 도달은 {outlook.searchUntil}번째 측정까지 찾음</caption>
              <thead><tr><th scope="col">계산 방식</th>
                {#if outlook.conditions.management!==null}<th scope="col">관리 기준</th>{/if}
                {#if outlook.conditions.end!==null}<th scope="col">종료 기준</th>{/if}
              </tr></thead>
              <tbody>
                {#each outlook.scenarios as row (row.id)}
                  <tr><th scope="row">{scenarioLabel(row.id)}</th>
                    {#if outlook.conditions.management!==null}<td>{reachText(row.management,"acquisition")}</td>{/if}
                    {#if outlook.conditions.end!==null}<td>{reachText(row.end,"acquisition")}</td>{/if}
                  </tr>
                {/each}
              </tbody>
            </table></div>
          </details>
        {/if}
        <details>
          <summary>기술 상세</summary>
          <dl>
            <dt>데이터 출처 · 적용 모델</dt><dd>{outlook.sourceId} · {outlook.bindingId}</dd>
            <dt>사용한 측정</dt><dd>#{outlook.record.first}~#{outlook.record.last} · {outlook.record.points}회</dd>
            <dt>측정 간격 근거 (time_basis)</dt><dd>{outlook.timeBasis} · {num(outlook.effectivePeriod)}초</dd>
            <dt>예측·기준 탐색 범위</dt><dd>예측 {outlook.horizonCount}회 · 기준 탐색 {outlook.searchCount}회 (최대 #{outlook.searchUntil})</dd>
            <dt>계산 데이터 버전 (measurement_version)</dt><dd>{outlook.measurementVersion}</dd>
            <dt>해설 근거 버전 (data_version)</dt><dd>{outlook.dataVersion}</dd>
          </dl>
        </details>
        </TaskDialog>
        {#key outlook.measurementVersion+":"+outlook.dataVersion+":"+outlook.bindingId+":"+outlook.timeBasis}
          <OutlookBriefingPanel projection={outlook} onEvidenceChanged={()=>{
            resultAbort?.abort();
            outlook=null;
            resultState="mismatch";
            message="해설을 확인하는 사이 데이터나 적용 모델, 측정 간격이 바뀌었습니다. 다시 계산하세요.";
          }}/>
          <details class="optional-review" ontoggle={(event)=>reviewSelection=event.currentTarget.open && outlook ? outlook.measurementVersion+":"+outlook.dataVersion+":"+outlook.bindingId+":"+outlook.timeBasis : null}><summary>검토 기록에 남기기 (선택)</summary>
            {#if reviewSelection === outlook.measurementVersion+":"+outlook.dataVersion+":"+outlook.bindingId+":"+outlook.timeBasis}<ReviewRequest projection={outlook} onEvidenceChanged={reason=>{
            resultAbort?.abort();
            outlook=null;
            resultState="mismatch";
            message=reason;
          }}/>{/if}
          </details>
        {/key}
      </section>
    {:else}
      <p class="context">진동 특징과 예측 범위를 고르고 계산하기를 누르면 전망을 표시합니다.</p>
    {/if}
    </div>
    <aside class="forecast-inspector" aria-label="기준 도달·예상 여유">
      <h3 class="inspector-title">기준 도달·예상 여유</h3>

    {#if outlook}
      {@const current=outlook.scenarios.find(item=>item.id==="current")??outlook.scenarios[0]}
      {@const basis=current&&current.id!=="current"?" · "+scenarioLabel(current.id)+" 기준":""}
      {@const period=outlook.timeBasis==="ordinal"?null:outlook.effectivePeriod}
      {@const limited=outlook.conditions.management!==null||outlook.conditions.end!==null}
      {@const worse=worseThanPersistence(outlook.checks?.[0])}
      {#if criteriaPending}<p class="criteria-pending" role="status">입력한 기준은 아직 적용하지 않았습니다.</p>{/if}
        {#if limited && !worse}
          <div class="tiles">
            {#if outlook.conditions.management!==null}
              <div><span>관리 기준 {measure(outlook.conditions.management!, outlook.unit)}{basis}</span><strong>{reachText(current?.management,"acquisition")}</strong>
                {#if reachDuration(current?.management,period)}<span>{reachDuration(current?.management,period)}</span>{/if}</div>
            {/if}
            {#if outlook.conditions.end!==null}
              <div><span>종료 기준 {measure(outlook.conditions.end!, outlook.unit)}까지 예상 여유{basis}</span><strong>{reachText(current?.end,"acquisition")}</strong>
                {#if reachDuration(current?.end,period)}<span>{reachDuration(current?.end,period)}</span>{/if}
                <span>입력한 종료 기준까지의 조건부 예측입니다. 설비의 실제 잔여수명은 아닙니다.</span></div>
            {/if}
          </div>
        {/if}
    {/if}

    <form class="criteria" onsubmit={event=>{event.preventDefault();void calculate();}}>
      <div class="criteria-title"><strong>기준값 입력</strong><span>선택 사항</span></div>
      <div class="inputs">      <label>기준 방향
        <select value={direction} onchange={e=>{direction=e.currentTarget.value as Direction;remember();}}>
          <option value="upper">값이 올라갈 때 (상한)</option><option value="lower">값이 내려갈 때 (하한)</option>
        </select>
      </label>
      <label>관리 기준{outlook?.unit?" ("+outlook.unit+")":""}
        <input type="number" step="any" value={managementText}
          oninput={e=>{managementText=e.currentTarget.value;remember();}}/>
      </label>
      <label>종료 기준{outlook?.unit?" ("+outlook.unit+")":""}
        <input type="number" step="any" value={endText}
          oninput={e=>{endText=e.currentTarget.value;remember();}}/>
      </label>
      <button type="submit" class="ui-button" aria-busy={resultState==="loading"} disabled={available.length===0||resultState==="loading"}>{resultState==="loading"?"계산 중…":"기준 적용"}</button></div>
    </form>
    </aside>
    </div>
  {/if}
</section>
<style>
  .forecast-workspace{grid-template-columns:minmax(0,1fr);gap:var(--space-3)}
  .criteria{display:grid;gap:var(--space-2);padding:var(--space-3);background:var(--color-surface-selected);border-radius:var(--radius-control)}
  .criteria-title{display:flex;flex-wrap:wrap;gap:var(--space-2) var(--space-4);align-items:baseline;font-size:var(--font-small)}
  .criteria-title span{font-size:var(--font-label);color:var(--color-ink-muted)}
  .criteria .inputs{grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:var(--space-2);margin:0}
  .criteria label{gap:4px;font-size:var(--font-label)}.criteria input,.criteria select{padding:var(--space-2)}
  @media(max-width:600px){.criteria .inputs{grid-template-columns:repeat(2,minmax(0,1fr))}}
  .forecast-controls{grid-column:1/-1;grid-row:1;display:flex;align-items:end;flex-wrap:wrap;gap:var(--space-3);border-bottom:1px solid var(--color-border);padding-bottom:var(--space-3)}
  .forecast-controls>div{flex:1;display:flex;flex-wrap:wrap;align-items:end;margin:0;gap:var(--space-2)}.forecast-controls .inputs label{flex:1;min-width:100px}.forecast-controls .inputs label:first-child{flex:1.4;min-width:140px}.forecast-controls .inputs button{flex:none;padding:var(--space-2);min-height:40px}
  .forecast-controls :global(.analysis-controls){flex:none;margin:0}
  .chart.unreliable .estimate{stroke:var(--color-ink-muted)}.chart.unreliable .band{fill:var(--color-ink-muted);opacity:.08}

  .forecast-caution{padding:var(--space-3);border-inline-start:3px solid var(--color-caution-ink);background:var(--color-uncertain-surface);color:var(--color-caution-ink);line-height:1.6;overflow-wrap:anywhere}

  .inputs>button{align-self:end;min-height:44px}
  .chart .fitted{fill:none;stroke:#8366a5;stroke-width:1.5;stroke-dasharray:2 3}
  .chart .fit-gap{stroke:var(--color-caution-ink);stroke-width:2;stroke-dasharray:3 3}
  .key.fitted{border-color:#8366a5;border-top-style:dotted}
  .axis-toggle{display:flex;align-items:center;gap:var(--space-2);margin-top:var(--space-3);font-size:var(--font-small);color:var(--color-ink-muted)}
  .axis-toggle input{width:auto;min-height:20px;margin:0;padding:0;flex:none}
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-3); }
  .context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .inputs{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:var(--space-4);margin-block:var(--space-5)}
  label{display:grid;gap:var(--space-2);font-weight:650;font-size:var(--font-small)}
  select,input{width:100%;min-width:0;padding:var(--space-3);border:1px solid var(--color-border);
    border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-ink)}
  .result{min-width:0}
  .result-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:var(--space-2);align-items:baseline}
  .result-head h3{margin:0}
  .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:var(--space-3);margin-top:var(--space-4)}
  .tiles div{border:1px solid var(--color-border);border-radius:var(--radius-control);padding:var(--space-4);display:grid;gap:var(--space-1)}
  .tiles span{color:var(--color-ink-muted);font-size:var(--font-small)}.tiles strong{font-size:var(--font-section)}
  .chart{margin:var(--space-4) 0;min-width:0}
  .chart svg{display:block;width:100%;height:220px;}
  .chart path,.chart line{vector-effect:non-scaling-stroke}
  .chart .axis{fill:none;stroke:var(--color-border);stroke-width:2}
  .chart .history{fill:none;stroke:var(--color-ink);stroke-width:1.5}
  .chart .estimate{fill:none;stroke:var(--color-action);stroke-width:2;stroke-dasharray:6 4}
  .chart .band{fill:var(--color-action);opacity:.14;stroke:none}
  .chart .now{stroke:var(--color-border);stroke-width:1}
  .chart .management{stroke:var(--color-caution-ink);stroke-width:1.5;stroke-dasharray:3 3}
  .chart .end{stroke:var(--color-failure-ink);stroke-width:1.5;stroke-dasharray:3 3}
  .axis-note,.legend{color:var(--color-ink-muted);font-size:var(--font-small);margin:0}
  .legend{display:flex;flex-wrap:wrap;gap:var(--space-1) var(--space-4);margin-top:var(--space-2)}
  .key{display:inline-block;width:16px;height:0;border-top:2px solid;vertical-align:middle;margin-inline-end:var(--space-1)}
  .key.history{border-color:var(--color-ink)}
  .key.estimate{border-color:var(--color-action);border-top-style:dashed}
  .key.band{height:10px;border:0;background:var(--color-action);opacity:.2}
  .key.management{border-color:var(--color-caution-ink);border-top-style:dashed}
  .key.end{border-color:var(--color-failure-ink);border-top-style:dashed}
  summary{cursor:pointer;font-weight:650;color:var(--color-action);padding-block:var(--space-3)}
  dl{overflow-wrap:anywhere}dt{font-weight:700}dd{margin:var(--space-1) 0 var(--space-3)}
  .scroll{max-width:100%;overflow-x:auto}
  table{border-collapse:collapse;width:100%}th,td{padding:var(--space-2);text-align:left;border-bottom:1px solid var(--color-border)}
  caption{text-align:left;color:var(--color-ink-muted)}dd{overflow-wrap:anywhere}
  .grid{stroke:var(--color-border);stroke-width:1;opacity:.7;vector-effect:non-scaling-stroke}

  .forecast-workspace{grid-template-columns:minmax(0,1fr) 260px;gap:var(--space-5)}
  .forecast-workspace>.analysis-body{grid-column:1;grid-row:2;min-width:0}
  .forecast-inspector{grid-column:2;grid-row:2;align-self:start;display:grid;gap:var(--space-3);border-left:1px solid var(--color-border);padding-left:var(--space-4);min-width:0}
  .forecast-inspector .criteria{padding:0;background:none}.forecast-inspector .criteria .inputs{grid-template-columns:minmax(0,1fr);gap:var(--space-3)}
  .forecast-inspector .tiles{grid-template-columns:minmax(0,1fr)}
  .criteria-pending{font-size:var(--font-small);color:var(--color-caution-ink);margin:0}
  @media(max-width:1000px){.forecast-workspace{grid-template-columns:minmax(0,1fr)}.forecast-inspector{grid-column:1;grid-row:3;border-left:0;border-top:1px solid var(--color-border);padding:var(--space-4) 0 0}.forecast-inspector .criteria .inputs{grid-template-columns:repeat(2,minmax(0,1fr))}}

  .inspector-title{margin:0;font-size:var(--font-section)}
  .forecast-inspector .tiles{margin:0;gap:var(--space-3)}.forecast-inspector .tiles>div{border:0;border-bottom:1px solid var(--color-border);border-radius:0;padding:0 0 var(--space-3)}
</style>
