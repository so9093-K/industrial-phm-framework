<script lang="ts">
  import AnalysisControls from "./AnalysisControls.svelte";
  import TaskDialog from "./TaskDialog.svelte";
  let validationOpen = $state(false);
  let criteriaOpen = $state(false);
  import SignalEvolution from "./SignalEvolution.svelte";
  import {preferredFeature} from "../acquisition-profile";
  import ForecastFit from "./ForecastFit.svelte";
  import ForecastCaution from "./ForecastCaution.svelte";
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
  import {reachText} from "../reach";
  import {num} from "../format";
  import {assetTabUrl} from "../routes";
  import OutlookBriefingPanel from "./OutlookBriefingPanel.svelte";
  import OutlookChart from "./OutlookChart.svelte";
  import {crossedSince,investigatedChange,limitSuggestions,measuredPaceReach,reachAt,reachSummary,reachReading} from "../outlook-view";
  import ReviewRequest from "./ReviewRequest.svelte";
  let reviewSelection: string | null = $state(null);
  import {
    loadAcquisitionOptions,loadAcquisitionPair,
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
  const appliedCriteria = $derived.by(() => {
    const current: AcquisitionProjection | null = outlook;
    return current !== null && (current.conditions.management !== null || current.conditions.end !== null);
  });
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
  /** '72번째 측정 · 1시간 11분'(기록된 간격이 있으면 경과 시간도). */
  const place=(at:number,period:number|null)=>Math.round(at)+"번째 측정"+(period!==null?" · "+elapsedText((Math.round(at)-1)*period):"");
  const baseline=$derived.by(()=>{const shown:AcquisitionProjection|null=outlook,evolution=shown?.evolution;return evolution?{median:evolution.baselineMedian,low:evolution.baselineRange?.low??null,high:evolution.baselineRange?.high??null}:null;});
  const suggestions=$derived.by(()=>{const shown:AcquisitionProjection|null=outlook;
    return shown?limitSuggestions(shown.unit,baseline,options?.features.find(item=>item.id===shown.featureId)?.label??"",shown.history.at(-1)?.value??null,true):[];});
  function suggest(value:number,toward:Direction){direction=toward;managementText=String(value);remember();void calculate();}
  const formatOffset=(n:number)=>Number.isInteger(n)?String(n):n.toFixed(2);
  const paceLabel=(record:AcquisitionProjection)=>"최근 "+(record.evolution?.ratePoints??"")+"회 속도 유지";
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


      {#if timeHorizon!==null}<label>예측 기간<select value={timeHorizon} onchange={e=>{timeHorizon=e.currentTarget.value as Horizon;invalidate();void calculate();}}>{#each ["1h","24h","7d","30d"] as h}<option value={h}>{HORIZON_LABEL[h as Horizon]}</option>{/each}</select></label>{/if}
      {#if timeHorizon===null}<label>앞으로 볼 측정 횟수 (1~2000)
        <input type="number" min="1" max="2000" step="1" value={countText}
          oninput={e=>{countText=e.currentTarget.value;invalidate();}}/>
      </label>{/if}
      {#if timeHorizon === null && resultState === "empty"}<button type="button" class="ui-button ui-button-primary"
        onclick={()=>void calculate()} disabled={available.length===0}>계산하기</button>{/if}
    </div>

    <AnalysisControls title="고급 설정">{#snippet children(close)}{#if options}
      <label>예측 범위 단위<select value={timeHorizon===null?"count":"time"} onchange={e=>{timeHorizon=e.currentTarget.value==="time"?"1h":null;invalidate();void calculate();}}><option value="count">측정 횟수</option><option value="time">시간 (측정 간격 필요)</option></select></label>
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
      {@const chart=outlook.forecast.length>0}
      {@const period=outlook.timeBasis==="ordinal"?null:outlook.effectivePeriod}
      {@const worse=worseThanPersistence(outlook.checks?.[0])}
      {@const ahead={management:reachReading(outlook.scenarios,"management",worse),end:reachReading(outlook.scenarios,"end",worse)}}
      {@const told=outlookMessage({axis:"acquisition",period,unit:outlook.unit,conditions:outlook.conditions,
        scenarios:outlook.scenarios,checks:outlook.reachChecks??[]},
        [{label:"다음 측정이 기준에 다가가는지 특징 추이에서 보기",href:featureTrendHref(outlook.assetId,outlook.featureId)}]) ?? forecastMessage({last:outlook.history.at(-1)?.value??null,start:outlook.forecast[0].estimate,end:outlook.forecast.at(-1)!,unit:outlook.unit,
          horizon:formatOffset(outlook.forecast.at(-1)!.ordinal)+"번째 측정",checks:outlook.checks??[]})}
      <section class="result" aria-labelledby="acq-result-title">
        <div class="result-head">
          <h3 id="acq-result-title">{options.features.find(item=>item.id===displayFeature)?.label ?? displayFeature} · 앞으로 {timeHorizon === null ? num(outlook.horizonCount)+"회" : HORIZON_LABEL[timeHorizon]} 전망</h3>
          <span class="context">마지막 측정 {place(outlook.record.last,period)} · {timeBasis(outlook)}</span>
        </div>
        <ForecastCaution fit={outlook.fit??null} start={outlook.forecast[0]} checks={outlook.checks} unit={outlook.unit} lastLabel="마지막 측정"
          href={featureTrendHref(outlook.assetId,outlook.featureId)}/>
        {#if chart}
          <OutlookChart history={outlook.history.map(row=>({x:row.ordinal,value:row.value}))}
            future={outlook.forecast.map(row=>({x:row.ordinal,estimate:row.estimate,lower:row.lower,upper:row.upper}))}
            last={outlook.record.last} {baseline} change={investigatedChange(location.search,"vibration",outlook.featureId)}
            limits={{management:outlook.conditions.management,end:outlook.conditions.end}} direction={outlook.conditions.direction}
            reach={{management:reachAt(ahead.management?.management,outlook.record.last,"acquisition"),end:reachAt(ahead.end?.end,outlook.record.last,"acquisition")}}
            pace={outlook.evolution&&(ahead.management?.id==="linear"||ahead.end?.id==="linear")?{rate:outlook.evolution.rate,label:paceLabel(outlook)}:null}
            unit={outlook.unit} scale={measurementScale(period)} place={at=>place(at,period)} unreliable={worse}/>
        {/if}
        {#if outlook.evolution}<SignalEvolution data={outlook.evolution} unit={outlook.unit}/>{/if}
        <button type="button" class="ui-button" onclick={() => validationOpen = true}>예측 설명</button>
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
      {@const period=outlook.timeBasis==="ordinal"?null:outlook.effectivePeriod}
      {@const limited=outlook.conditions.management!==null||outlook.conditions.end!==null}
      {@const worse=worseThanPersistence(outlook.checks?.[0])}
      {@const example=suggestions.find(item=>item.label.startsWith("지금의 2배"))}
      {@const last=outlook.history.at(-1)?.value}
      {@const pace=example&&outlook.evolution&&last!==undefined
        ? measuredPaceReach(last,outlook.evolution.rate,example.value,example.direction) : null}
      {#if criteriaPending}<p class="criteria-pending" role="status">입력한 기준은 아직 적용하지 않았습니다.</p>{/if}
        {#if limited}
          {@const shown=outlook.history.map(row=>({x:row.ordinal,value:row.value}))}
          <div class="tiles">
            {#each [["management","관리 기준",outlook.conditions.management],["end","종료 기준",outlook.conditions.end]] as const as [key,name,value] (key)}
              {#if value!==null}
                {@const reading=reachReading(outlook.scenarios,key,worse)}{@const reach=reading?.[key]}{@const paced=reading?.id==="linear"}
                {@const basis=reading&&!paced&&reading.id!=="current"?" · "+scenarioLabel(reading.id)+" 기준":""}
                {@const told=reachSummary(reach,"acquisition",period,at=>place(at,period),outlook.record.last,reach?.state==="already"?crossedSince(shown,value,outlook.conditions.direction):null,paced?"기준 도달":undefined)}
                <div><span>{name} {measure(value, outlook.unit)}{basis}</span>
                  {#if paced}<span class="pace-basis">{paceLabel(outlook)} 시</span>{/if}
                  <strong>{told.headline}</strong>
                  {#if told.detail}<span>{told.detail}</span>{/if}
                  {#if worse&&!paced&&reach?.state!=="already"}<span class="caveat">예측 오차가 커서 참고로만 봅니다.</span>{/if}
                  {#if key==="end"}<span>입력한 종료 기준까지의 조건부 예측입니다. 설비의 실제 잔여수명은 아닙니다.</span>{/if}</div>
              {/if}
            {/each}
          </div>
        {:else if example && pace}
          {@const told=reachSummary(pace,"acquisition",period,at=>place(at,period),outlook.record.last,null)}
          <div class="tiles"><div>
            <span>예시 기준 {measure(example.value,outlook.unit)} · 마지막 값의 2배</span>
            <strong>{told.headline}</strong>
            <span>{paceLabel(outlook)} 시</span>
          </div></div>
        {/if}
    {/if}
      {#if suggestions.length}<div class="suggest" aria-label="기준 제안"><p>{appliedCriteria?"다른 기준":"기준을 고르면 바로 계산합니다"}</p>
      {#each suggestions as item (item.label)}<button type="button" class="chip" title={item.source} aria-pressed={outlook?.conditions.management===item.value&&outlook?.conditions.direction===item.direction}
        onclick={() => suggest(item.value, item.direction)}>{item.label}</button>{/each}</div>{/if}
      <button type="button" class="ui-button criteria-button" disabled={!outlook} onclick={() => criteriaOpen = true}>기준값 직접 입력</button>
    </aside>
    <TaskDialog bind:open={criteriaOpen} title="기준값 직접 입력">
    <form class="criteria" onsubmit={event=>{event.preventDefault(); criteriaOpen = false; void calculate();}}>
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
      <button type="submit" class="ui-button ui-button-primary" aria-busy={resultState==="loading"} disabled={available.length===0||resultState==="loading"}>{resultState==="loading"?"계산 중…":"기준 적용"}</button></div>
    </form>
    </TaskDialog>
    </div>
  {/if}
</section>
<style>
  .criteria{display:grid;gap:var(--space-2);padding:var(--space-3);background:var(--color-surface-selected);border-radius:var(--radius-control)}
  .pace-basis{font-weight:650;color:var(--color-action)}
  .criteria .inputs{grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:var(--space-2);margin:0}
  .criteria label{gap:4px;font-size:var(--font-label)}.criteria input,.criteria select{padding:var(--space-2)}
  @media(max-width:600px){.criteria .inputs{grid-template-columns:repeat(2,minmax(0,1fr))}}
  .forecast-controls{grid-column:1/-1;grid-row:1;display:flex;align-items:end;flex-wrap:wrap;gap:var(--space-3);border-bottom:1px solid var(--color-border);padding-bottom:var(--space-3)}
  .forecast-controls>div{flex:1;display:flex;flex-wrap:wrap;align-items:end;margin:0;gap:var(--space-2)}.forecast-controls .inputs label{flex:1;min-width:100px}.forecast-controls .inputs label:first-child{flex:1.4;min-width:140px}.forecast-controls .inputs button{flex:none;padding:var(--space-2);min-height:40px}
  .forecast-controls :global(.analysis-controls){flex:none;margin:0}
  .criteria-button{min-height:40px;justify-self:start}


  .inputs>button{align-self:end;min-height:44px}
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
  summary{cursor:pointer;font-weight:650;color:var(--color-action);padding-block:var(--space-3)}
  dl{overflow-wrap:anywhere}dt{font-weight:700}dd{margin:var(--space-1) 0 var(--space-3)}
  .scroll{max-width:100%;overflow-x:auto}
  table{border-collapse:collapse;width:100%}th,td{padding:var(--space-2);text-align:left;border-bottom:1px solid var(--color-border)}
  caption{text-align:left;color:var(--color-ink-muted)}dd{overflow-wrap:anywhere}

  .forecast-workspace{grid-template-columns:minmax(0,1fr) 260px;gap:var(--space-5)}
  .forecast-workspace>.analysis-body{grid-column:1;grid-row:2;min-width:0}
  .forecast-inspector{grid-column:2;grid-row:2;align-self:start;display:grid;gap:var(--space-3);border-left:1px solid var(--color-border);padding-left:var(--space-4);min-width:0}
  .forecast-inspector .tiles{grid-template-columns:minmax(0,1fr)}
  .criteria-pending{font-size:var(--font-small);color:var(--color-caution-ink);margin:0}
  @media(max-width:1000px){.forecast-workspace{grid-template-columns:minmax(0,1fr)}.forecast-inspector{grid-column:1;grid-row:3;border-left:0;border-top:1px solid var(--color-border);padding:var(--space-4) 0 0}.criteria .inputs{grid-template-columns:repeat(2,minmax(0,1fr))}}

  .inspector-title{margin:0;font-size:var(--font-section)}
  .tiles .caveat{color:var(--color-caution-ink)}
  .suggest{display:flex;flex-wrap:wrap;gap:6px}.suggest p{flex-basis:100%;margin:0;font-size:var(--font-small);color:var(--color-ink-muted)}
  .chip{font:inherit;font-size:var(--font-label);padding:4px 10px;border:1px solid var(--color-control-border);border-radius:999px;background:var(--color-surface);color:var(--color-action);cursor:pointer}
  .chip[aria-pressed="true"]{background:var(--color-surface-selected);border-color:var(--color-action);font-weight:650}
  .forecast-inspector .tiles{margin:0;gap:var(--space-3)}.forecast-inspector .tiles>div{border:0;border-bottom:1px solid var(--color-border);border-radius:0;padding:0 0 var(--space-3)}
</style>
