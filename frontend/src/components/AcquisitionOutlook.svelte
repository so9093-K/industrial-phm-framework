<script lang="ts">
  import ForecastSettings from "./ForecastSettings.svelte";
  import ForecastValidation from "./ForecastValidation.svelte";
  import {savedSettings,rememberSettings} from "../forecast-settings";
  import {onMount} from "svelte";
  import {measure} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {measurementScale} from "../time-axis";
  import StatusNotice from "./StatusNotice.svelte";
  import CautionNote from "./CautionNote.svelte";
  import {reachDuration,reachText} from "../reach";
  import {num} from "../format";
  import {assetTabUrl} from "../routes";
  import OutlookBriefings from "./OutlookBriefings.svelte";
  import ReviewRequest from "./ReviewRequest.svelte";
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
      if(!featureId)featureId=valid[0].id;
      listState="ready";remember();
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      listState="failed";message=cause instanceof Error?cause.message:"획득 특징 목록을 읽지 못했습니다.";
    }
  }
  async function calculate(){
    resultAbort?.abort();
    const request=new AbortController();resultAbort=request;
    resultState="loading";outlook=null;message="";
    try{
      if(!options||!selectedFeature())throw new Error("저장 획득 특징을 먼저 선택하세요.");
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
      message=cause instanceof Error?cause.message:"획득 전망 근거를 확인할 수 없습니다.";
      resultState=cause instanceof AcquisitionVersionMismatch?"mismatch"
        :cause instanceof AcquisitionOutlookUnavailable?"unavailable":"failed";
    }
  }
  function timeBasis(record:AcquisitionProjection):string{
    if(record.timeBasis==="recorded")return "기록된 측정 간격 "+num(record.effectivePeriod)+"초";
    if(record.timeBasis==="assumed")return "가정한 측정 간격 "+num(record.effectivePeriod)+"초 (실제 측정 간격 아님)";
    return "측정 간격 정보 없음 — 측정 횟수로만 계산";
  }
  const formatOffset=(n:number)=>Number.isInteger(n)?String(n):n.toFixed(2);
  const scenarioLabel=(id:string)=>({current:"기본 설정",recent:"최근 구간 중심",responsive:"변화에 민감",linear:"최근 속도 유지"} as Record<string,string>)[id]??id;
  onMount(()=>{void loadOptions();return()=>{listAbort?.abort();resultAbort?.abort();};});
</script>

<section class="ui-panel" aria-labelledby="acq-outlook-title">
  <h2 id="acq-outlook-title">기준 도달 전망</h2>
  <p class="context">진동 특징의 추세를 Prophet으로 예측하고, 사용자가 정한 관리·종료 기준에 몇 번째 측정에서 닿는지 계산합니다. 종료 기준까지 남은 측정은 조건부 잔여수명(RUL)입니다.</p>
  {#if listState==="loading"}
    <StatusNotice message="전망할 수 있는 진동 특징을 불러오고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="전망할 진동 특징을 불러오지 못했습니다" message={message}
      actionLabel="다시 불러오기" onAction={()=>void loadOptions()}/>
  {:else if listState==="empty"||listState==="unavailable"}
    <StatusNotice kind="uncertain" title="전망에 필요한 진동 측정이 부족합니다"
      message="분석된 진동 측정이 20회 이상 있어야 합니다. 이상이 없다는 뜻은 아닙니다."
      actionLabel="진동 특징 비교 보기" actionHref={assetTabUrl(assetId, "change", "compare", "vibration")}/>
  {:else if options}
    <p class="context">데이터 출처 <strong>{options.sourceId}</strong>
      · 측정 #{options.first}~#{options.last} · 분석 {options.count}회
      · {options.recordedPeriod===null?"측정 간격 기록 없음":"기록된 측정 간격 "+num(options.recordedPeriod)+"초"}</p>
    <div class="inputs">
      <label>진동 특징
        <select value={featureId} onchange={e=>{featureId=e.currentTarget.value;invalidate();}}>
          {#each options.features as item (item.id)}
            <option value={item.id} disabled={!item.countForecast}>
              {item.label} · {item.validPoints}회{item.countForecast?"":" (부족)"}
            </option>
          {/each}
        </select>
      </label>
      <label>예측 범위 단위<select value={timeHorizon===null?"count":"time"} onchange={e=>{timeHorizon=e.currentTarget.value==="time"?"1h":null;invalidate();}}><option value="count">측정 횟수</option><option value="time">시간 (측정 간격 필요)</option></select></label>
      {#if timeHorizon!==null}<label>예측 기간<select value={timeHorizon} onchange={e=>{timeHorizon=e.currentTarget.value as Horizon;invalidate();}}>{#each ["1h","24h","7d","30d"] as h}<option value={h}>{HORIZON_LABEL[h as Horizon]}</option>{/each}</select></label>{/if}
      <label>앞으로 볼 측정 횟수 (1~2000)
        <input type="number" min="1" max="2000" step="1" value={countText}
          oninput={e=>{countText=e.currentTarget.value;invalidate();}}/>
      </label>
      <label>측정 간격 가정 (선택 · 초, 1~86400)
        <input type="number" min="1" max="86400" step="any" value={assumedText}
          placeholder={options.recordedPeriod===null?"비우면 측정 횟수로만 계산":"비우면 기록된 간격 사용"}
          oninput={e=>{assumedText=e.currentTarget.value;invalidate();}}/>
      </label>
      <label>기준 방향
        <select value={direction} onchange={e=>{direction=e.currentTarget.value as Direction;invalidate();}}>
          <option value="upper">값이 올라갈 때 (상한)</option><option value="lower">값이 내려갈 때 (하한)</option>
        </select>
      </label>
      <label>관리 기준 (선택)
        <input type="number" step="any" value={managementText}
          oninput={e=>{managementText=e.currentTarget.value;invalidate();}}/>
      </label>
      <label>종료 기준 (선택)
        <input type="number" step="any" value={endText}
          oninput={e=>{endText=e.currentTarget.value;invalidate();}}/>
      </label>
    </div>
    <ForecastSettings value={settings} onChange={value=>{settings=value;customSettings=true;invalidate();}}/>
    <button type="button" class="ui-button ui-button-primary"
      onclick={()=>void calculate()} disabled={available.length===0}>계산하기</button>
    <p class="context">조건을 바꾸면 아래 결과는 지워지고 다시 계산해야 합니다.</p>
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
      {@const current=outlook.scenarios.find(item=>item.id==="current")??outlook.scenarios[0]}
      {@const basis=current&&current.id!=="current"?" · "+scenarioLabel(current.id)+" 기준":""}
      {@const limited=outlook.conditions.management!==null||outlook.conditions.end!==null}
      {@const chart=acquisitionChart(outlook)}
      {@const period=outlook.timeBasis==="ordinal"?null:outlook.effectivePeriod}
      <section class="result" aria-labelledby="acq-result-title">
        <div class="result-head">
          <h3 id="acq-result-title">결과</h3>
          <span class="context">측정 #{outlook.record.last}까지의 데이터로 계산 · {timeBasis(outlook)}</span>
        </div>
        {#if limited}
          <div class="tiles">
            {#if outlook.conditions.management!==null}
              <div><span>관리 기준 {measure(outlook.conditions.management!, outlook.unit)}{basis}</span><strong>{reachText(current?.management,"acquisition")}</strong>
                {#if reachDuration(current?.management,period)}<span>{reachDuration(current?.management,period)}</span>{/if}</div>
            {/if}
            {#if outlook.conditions.end!==null}
              <div><span>조건부 잔여수명(RUL) · 종료 기준 {measure(outlook.conditions.end!, outlook.unit)}{basis}</span><strong>{reachText(current?.end,"acquisition")}</strong>
                {#if reachDuration(current?.end,period)}<span>{reachDuration(current?.end,period)}</span>{/if}</div>
            {/if}
          </div>
        {:else}
          <p class="context">관리·종료 기준을 입력하면 몇 번째 측정에서 닿는지 함께 계산합니다.</p>
        {/if}
        {#if chart}
          {@const axisNote=(period===null?"측정 회차":"기록 시작 후 경과 시간 · "+(outlook.timeBasis==="assumed"?"가정한":"기록된")+" 측정 간격 "+num(period)+"초")+" · 세로선 · 마지막 측정 #"+chart.last}
          <figure class="chart">
            <p class="axis-note">최고 {measure(chart.high, outlook.unit)} · 최저 {measure(chart.low, outlook.unit)}</p>
            <ValueAxis ticks={chart.ticks} height={chart.height} unit={outlook.unit}>
            <svg viewBox={"0 0 "+chart.width+" "+chart.height} preserveAspectRatio="none" role="img"
              aria-label={"저장된 측정 #"+chart.first+"~#"+chart.last+"과 #"+formatOffset(chart.end)+"까지의 예측"}>
              {#each chart.ticks as tick (tick.value)}<line x1="0" x2={chart.width} y1={tick.y} y2={tick.y} class="grid" />{/each}
              {#if chart.band}<path d={chart.band} class="band" />{/if}
              <line x1={chart.lastX} x2={chart.lastX} y1="0" y2={chart.height} class="now" />
              {#if chart.management!==null}<line x1="0" x2={chart.width} y1={chart.management} y2={chart.management} class="management" />{/if}
              {#if chart.endLimit!==null}<line x1="0" x2={chart.width} y1={chart.endLimit} y2={chart.endLimit} class="end" />{/if}
              <path d={chart.history} class="history" />
              <path d={chart.estimate} class="estimate" />
              <path d={"M0 0 V"+chart.height+" H"+chart.width} class="axis" />
            </svg>
            {#snippet footer()}<XAxis lo={chart.first} hi={chart.end} scale={measurementScale(period)}
              note={axisNote} />{/snippet}
            </ValueAxis>
            <figcaption class="legend">
              <span><i class="key history"></i>저장된 측정</span>
              <span><i class="key estimate"></i>추세 예측</span>
              <span><i class="key band"></i>예측 범위</span>
              {#if chart.management!==null}<span><i class="key management"></i>관리 기준 {measure(outlook.conditions.management!, outlook.unit)}</span>{/if}
              {#if chart.endLimit!==null}<span><i class="key end"></i>종료 기준 {measure(outlook.conditions.end!, outlook.unit)}</span>{/if}
            </figcaption>
          </figure>
        {/if}
        {#key outlook.measurementVersion+":"+outlook.dataVersion+":"+outlook.bindingId+":"+outlook.timeBasis}
          <OutlookBriefings projection={outlook} onEvidenceChanged={()=>{
            resultAbort?.abort();
            outlook=null;
            resultState="mismatch";
            message="해설을 확인하는 사이 데이터나 적용 모델, 측정 간격이 바뀌었습니다. 다시 계산하세요.";
          }}/>
          <ReviewRequest projection={outlook} onEvidenceChanged={reason=>{
            resultAbort?.abort();
            outlook=null;
            resultState="mismatch";
            message=reason;
          }}/>
        {/key}
        <ForecastValidation checks={outlook.checks}/>
        <CautionNote message="지금까지의 추세가 이어진다고 가정한 계산이며, 기준은 사용자가 정한 값입니다. 경과 시간은 측정 간격으로 환산한 값이며 실제 날짜가 아닙니다."/>
        <details>
          <summary>앞으로 {num(outlook.horizonCount)}회 측정의 예측값{timeHorizon?" · "+timeHorizon+"를 측정 간격으로 환산":""}</summary>
          <div class="scroll"><table>
            <caption>측정별 특징 예측값 (최대 12개) · 예측 범위는 계산상 범위이며 고장 신뢰구간이 아닙니다</caption>
            <thead><tr><th scope="col">측정 #</th><th scope="col">예측값</th>
              <th scope="col">범위 하한</th><th scope="col">범위 상한</th></tr></thead>
            <tbody>
              {#each outlook.forecast.slice(0,12) as item,i (i)}
                <tr><td>#{formatOffset(item.ordinal)}</td><td>{num(item.estimate)}</td>
                  <td>{num(item.lower)}</td><td>{num(item.upper)}</td></tr>
              {/each}
            </tbody>
          </table></div>
        </details>
        {#if limited}
          <details>
            <summary>계산 방식별 결과 {outlook.scenarios.length}가지</summary>
            <div class="scroll"><table>
              <caption>계산 방식 사이의 차이는 신뢰 구간이 아닙니다 · 기준 도달은 측정 #{outlook.searchUntil}까지 찾음</caption>
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
      </section>
    {/if}
  {/if}
</section>
<style>
  .context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .inputs{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:var(--space-4);margin-block:var(--space-5)}
  label{display:grid;gap:var(--space-2);font-weight:650;font-size:var(--font-small)}
  select,input{width:100%;min-width:0;padding:var(--space-3);border:1px solid var(--color-border);
    border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-ink)}
  .result{border-top:1px solid var(--color-border);margin-top:var(--space-6);padding-top:var(--space-4)}
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
</style>
