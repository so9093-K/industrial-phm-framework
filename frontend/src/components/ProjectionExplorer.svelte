<script lang="ts">
  import SignalEvolution from "./SignalEvolution.svelte";
  import AnalysisControls from "./AnalysisControls.svelte";
  import TaskDialog from "./TaskDialog.svelte";
  let validationOpen = $state(false);
  let criteriaOpen = $state(false);
  import SourceIdentity from "./SourceIdentity.svelte";
  import {focusFrom,focusParams,type SourceFocus} from "../signal-selection";
  import {recordParams} from "../record-context";
  import {readableSourceId} from "../operations-status";
  import ForecastFit from "./ForecastFit.svelte";
  import ForecastCaution from "./ForecastCaution.svelte";
  import {worseThanPersistence} from "../forecast-fit";
  import ForecastSettings from "./ForecastSettings.svelte";
  import ForecastValidation from "./ForecastValidation.svelte";
  import AnalysisMessage from "./AnalysisMessage.svelte";
  import {outlookMessage, forecastMessage} from "../analysis-messages";
  import {savedSettings,rememberSettings} from "../forecast-settings";
  import {defaultSignal} from "../summary-defaults";
  import {onMount} from "svelte";
  import {measure} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {readSignalNames,signalName,type SignalNames} from "../history";
  import StatusNotice from "./StatusNotice.svelte";
  import {reachText} from "../reach";
  import {num} from "../format";
  import {assetTabUrl} from "../routes";
  import OutlookBriefingPanel from "./OutlookBriefingPanel.svelte";
  import OutlookChart from "./OutlookChart.svelte";
  import {crossedSince,investigatedChange,limitSuggestions,reachAt,reachSummary} from "../outlook-view";
  import {clockText} from "../asset-timeline";
  import ReviewRequest from "./ReviewRequest.svelte";
  let reviewSelection: string | null = $state(null);
  import {
    HORIZON_LABEL, loadOptions, loadPaired, MeasurementVersionMismatch, ProjectionUnavailable, spreadRows, steadyRange, suggestedHorizon,
    type Conditions, type Direction, type Horizon, type Options, type Projection,
  } from "../projections";
  type Props = {assetId: string};
  let {assetId}: Props = $props();
  let names: SignalNames = $state(new Map());
  $effect(() => { const asset = assetId; void readSignalNames(asset).then((value) => { if (asset === assetId) names = value; }); });
  type State = "loading" | "ready" | "empty" | "unavailable" | "failed" | "unverified";
  let optionsState: State = $state("loading");
  let resultState: State = $state("empty");
  let options: Options | null = $state(null);
  let projection: Projection | null = $state(null);
  let error = $state("");
  let horizonNotice = $state("");
  let selectionLoading = $state(false);
  let selectionReady = $state(false);
  const params = new URLSearchParams(location.search);
  let focus:SourceFocus|null=$state(focusFrom(params));
  let selectedRecord=$state(params.get("record_key")??"");
  let settings=$state(savedSettings(params));
  let customSettings=$state([...params.keys()].some(key=>/^forecast_(prior|range|training|seasonality|backtest)$/.test(key)));
  let channel = $state(params.get("monitor_channel") ?? "");
  const savedHorizon = params.get("projection_horizon");
  let horizon: Horizon = $state(
    savedHorizon === "24h" || savedHorizon === "7d" || savedHorizon === "30d"
      ? savedHorizon : "1h"
  );
  // Until a horizon is chosen, the forecast reaches as far as the selected record suits.
  let horizonChosen = Boolean(savedHorizon);
  let management = $state(params.get("projection_management") ?? "");
  let endLimit = $state(params.get("projection_end") ?? "");
  let direction: Direction = $state(params.get("projection_direction") === "lower" ? "lower" : "upper");
  let requestOptions: AbortController | null = null;
  let requestProjection: AbortController | null = null;
  const horizons: Horizon[] = ["1h", "24h", "7d", "30d"];

  function signalHref():string {
    const url=new URL(assetTabUrl(assetId,"signals",null,null,channel),location.origin);
    const record=options?.records?.find(row=>row.key===projection?.recordKey);
    for(const [key,value] of Object.entries(record?recordParams(record):focus?focusParams(focus):{}))url.searchParams.set(key,value);
    return url.pathname+url.search;
  }
  const appliedCriteria = $derived.by(() => {
    const current: Projection | null = projection;
    return current !== null && (current.conditions.management !== null || current.conditions.end !== null);
  });
  const criteriaPending=$derived.by(()=>{const current:Projection|null=projection;return current!==null&&(current.conditions.direction!==direction
    ||current.conditions.management!==(management.trim()?Number(management):null)
    ||current.conditions.end!==(endLimit.trim()?Number(endLimit):null));});
  function parseLimit(value: string): number | null {
    if (value.trim() === "") return null;
    const n = Number(value);
    if (!Number.isFinite(n)) throw new Error("관리·종료 기준은 유한한 숫자로 입력해야 합니다.");
    return n;
  }
  // 처음 수준과 처음 범위: 관제·조사 화면의 회색 점선·띠와 같은 뜻으로 전망 그래프에도 그린다.
  const baseline=$derived.by(()=>{const shown:Projection|null=projection,evolution=shown?.evolution;return evolution?{median:evolution.baselineMedian,low:evolution.baselineRange?.low??null,high:evolution.baselineRange?.high??null}:null;});
  const suggestions=$derived.by(()=>{const shown:Projection|null=projection;
    return shown?limitSuggestions(shown.unit??names.get(shown.channel)?.unit??null,baseline,signalName(names,shown.channel)):[];});
  /** 예측 범위 폭은 표본 탓에 칸마다 들쭉날쭉하다. 그래프에는 고른 폭(steadyRange)으로 그린다. */
  function steadyFuture(shown:Projection){
    const steady=steadyRange(shown.future);
    return shown.future.map((row,i)=>({x:Date.parse(row.at),estimate:row.estimate,lower:steady[i]?.lower??null,upper:steady[i]?.upper??null}));
  }
  function suggest(value:number,toward:Direction){direction=toward;management=String(value);save();void calculate();}
  const clock = (at: string): string =>
    new Date(at).toLocaleString("ko-KR", {timeZone:"Asia/Seoul"});
  function label(id: string): string {
    return ({current:"기본 설정", recent:"최근 구간 중심", responsive:"변화에 민감",
      linear:"최근 속도 유지"} as Record<string,string>)[id] ?? id;
  }
  function save() {
    const url=new URL(location.href);
    url.searchParams.set("monitor_asset",assetId);
    url.searchParams.set("monitor_channel",channel);
    if(selectedRecord)url.searchParams.set("record_key",selectedRecord);else url.searchParams.delete("record_key");
    for(const key of ["monitor_source","monitor_point","monitor_interpretation"])url.searchParams.delete(key);
    if(focus)for(const [key,value] of Object.entries(focusParams(focus)))url.searchParams.set(key,value);
    url.searchParams.set("projection_horizon",horizon);
    url.searchParams.set("projection_direction",direction);
    if (management.trim()) url.searchParams.set("projection_management",management);
    else url.searchParams.delete("projection_management");
    if (endLimit.trim()) url.searchParams.set("projection_end",endLimit);
    else url.searchParams.delete("projection_end");
    if(customSettings)rememberSettings(url,settings);
    history.replaceState(history.state,"",url);
  }
  function invalidate() {
    requestProjection?.abort();
    resultState = "empty";
    projection = null;
    error = "";
    save();
  }
  async function loadSourceOptions() {
    requestOptions?.abort();
    requestProjection?.abort();
    const abort=new AbortController(); requestOptions=abort;
    optionsState="loading"; resultState="empty"; options=null; projection=null; error=""; horizonNotice="";
    try {
      const data=await loadOptions(assetId,abort.signal);
      if (abort.signal.aborted) return;
      options=data;
      if (!data.channels.length){optionsState="empty";return;}
      if(channel&&!data.channels.includes(channel))throw new Error("고른 신호가 이 설비에 없습니다.");
      if(!channel){
        // The change the summary leads with, in its own record; else the main signal.
        const picked=await defaultSignal(assetId,data.channels,abort.signal);
        if (abort.signal.aborted) return;
        channel=picked.channel;
        if(!selectedRecord&&!focus&&picked.context)selectedRecord=picked.context.key;
      }
      if (abort.signal.aborted) return;
      optionsState="ready";
      await loadSelectedOptions(true,Boolean(savedHorizon));
    } catch(cause:unknown) {
      if(abort.signal.aborted)return;
      optionsState="failed";
      error=cause instanceof Error?cause.message:"전망 가능한 측정 목록을 읽지 못했습니다.";
    }
  }
  async function loadSelectedOptions(autoCalculate:boolean,bookmarked=false):Promise<void> {
    requestOptions?.abort();
    requestProjection?.abort();
    const abort=new AbortController();requestOptions=abort;
    selectionLoading=true;selectionReady=false;resultState="empty";projection=null;error="";horizonNotice="";
    try {
      const data=await loadOptions(assetId,abort.signal,{channel,trainingPoints:settings.trainingPoints,recordKey:selectedRecord||undefined,focus:selectedRecord?null:focus});
      if(abort.signal.aborted)return;
      options=data;selectionReady=true;selectedRecord=data.recordKey??"";
      const chosen=data.records?.find(row=>row.key===selectedRecord);
      if(chosen)focus={source:chosen.sourceId,point:chosen.pointId,interpretation:chosen.interpretationId};
      if(!horizonChosen)horizon=suggestedHorizon(data.horizons,chosen?(Date.parse(chosen.record.to)-Date.parse(chosen.record.from))/1000:null)??horizon;
      if (data.horizons[horizon] !== null) {
        const allowed = horizons.find(key=>data.horizons[key]===null);
        if (!allowed) {
          resultState="unavailable";
          error="선택한 신호와 학습 범위로 전망할 수 있는 예측 기간이 없습니다.";
          return;
        }
        horizonNotice=(bookmarked?"저장된":"선택한")+" 예측 기간 "+HORIZON_LABEL[horizon]
          +"은 선택한 신호와 학습 범위가 지원하지 않아 "+HORIZON_LABEL[allowed]+"으로 변경했습니다.";
        horizon=allowed;
      }
      save();
      selectionLoading=false;
      if (autoCalculate) await calculate();
    } catch(cause:unknown) {
      if(abort.signal.aborted)return;
      resultState="failed";
      error=cause instanceof Error?cause.message:"선택한 신호의 예측 가능 기간을 읽지 못했습니다.";
    } finally {
      if(!abort.signal.aborted)selectionLoading=false;
    }
  }
  async function calculate():Promise<void> {
    if(!selectionReady){await loadSelectedOptions(true);return;}
    requestProjection?.abort();
    const abort=new AbortController();requestProjection=abort;
    resultState="loading";projection=null;error="";
    try{
      if(!options?.channels.includes(channel)) throw new Error("선택한 신호의 정보가 없습니다.");
      if(options.horizons[horizon]!==null) throw new ProjectionUnavailable(
        "해당 예측 기간은 저장 이력의 길이·지원 범위 때문에 계산할 수 없습니다."
      );
      const conditions:Conditions={direction,management:parseLimit(management),end:parseLimit(endLimit)};
      save();
      const data=await loadPaired(assetId,channel,horizon,conditions,abort.signal,customSettings?settings:undefined, selectedRecord||undefined);
      if(abort.signal.aborted)return;
      projection=data;resultState="ready";
    }catch(cause:unknown){
      if(abort.signal.aborted)return;
      resultState=cause instanceof MeasurementVersionMismatch?"unverified"
        :cause instanceof ProjectionUnavailable?"unavailable":"failed";
      error=cause instanceof Error?cause.message:"계산 근거를 확인할 수 없습니다.";
    }
  }
  onMount(()=>{
    void loadSourceOptions();
    return ()=>{requestOptions?.abort();requestProjection?.abort();};
  });
</script>

<section class="ui-panel projection" aria-labelledby="projection-title">
  <h2 class="visually-hidden" id="projection-title">추세·기준 도달 전망</h2>
  {#if optionsState === "loading"}
    <StatusNotice message="전망할 수 있는 신호와 기간을 불러오고 있습니다." />
  {:else if optionsState === "failed"}
    <StatusNotice kind="failure" title="전망할 신호를 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void loadSourceOptions()} />
  {:else if optionsState === "empty"}
    <StatusNotice kind="uncertain" title="전망할 시계열 기록이 없습니다"
      message="이 설비에는 저장된 시계열 신호가 없습니다."
      actionLabel="신호 보기" actionHref={assetTabUrl(assetId, "signals")} />
  {:else if options!==null}
    <div class="analysis-workspace forecast-workspace" class:has-criteria={appliedCriteria}><div class="forecast-controls">
    <div class="controls">
      <label for="projection-channel">신호
        <select id="projection-channel" value={channel}
          onchange={e=>{channel=e.currentTarget.value;selectedRecord="";if(focus)focus={...focus,interpretation:undefined};invalidate();void loadSelectedOptions(true);}}>
          {#each options.channels as id (id)}<option value={id}>{signalName(names,id)}</option>{/each}
        </select>
      </label>
      {#if options.records && options.records.length>1}<label for="projection-record">분석할 기록
        <select id="projection-record" value={selectedRecord} onchange={event=>{selectedRecord=event.currentTarget.value;focus=null;invalidate();void loadSelectedOptions(true);}}>
          {#each options.records as record (record.key)}<option value={record.key}>{readableSourceId(record.sourceId)} · {record.pointId??"측정 위치 미지정"} · {record.meaningLabel??"측정 항목 미지정"}{record.unit?" · "+record.unit:""} · {clock(record.record.from)} ~ {clock(record.record.to)}</option>{/each}
        </select>
      </label>{/if}
      <label for="projection-horizon">예측 기간
        <select id="projection-horizon" value={horizon} disabled={selectionLoading||!selectionReady}
          onchange={e=>{horizon=e.currentTarget.value as Horizon;horizonChosen=true;horizonNotice="";invalidate();void calculate();}}>
          {#each horizons as value (value)}
            <option value={value} disabled={options.horizons[value]!==null}>{HORIZON_LABEL[value]}
              {options.horizons[value]===null?"":" (기록이 짧아 불가)"}</option>
          {/each}
        </select>
      </label>
      <button type="button" class="ui-button ui-button-primary"
        onclick={()=>void calculate()} disabled={selectionLoading||!selectionReady||!horizons.some(key=>options?.horizons[key]===null)}>
        계산하기
      </button>
    </div>

    <AnalysisControls title="모델 설정">{#snippet children(close)}{#if options}
    <ForecastSettings value={settings} expanded={customSettings} onChange={value=>{const changed=settings.trainingPoints!==value.trainingPoints;settings=value;customSettings=true;invalidate();if(changed)void loadSelectedOptions(false);}}/>
    <p class="purpose">조건을 바꾸면 결과는 지워지고 다시 계산해야 합니다.</p>

    <button type="button" class="ui-button ui-button-primary" disabled={selectionLoading||!selectionReady||!horizons.some(key=>options?.horizons[key]===null)} onclick={()=>{close();void calculate();}}>적용하고 계산하기</button>

    {/if}{/snippet}</AnalysisControls>
      <button type="button" class="ui-button criteria-button" onclick={() => criteriaOpen = true}>도달 기준 설정</button>
    </div>
    <div class="analysis-body">
    {#if horizonNotice}<p class="intro" role="status">{horizonNotice}</p>{/if}
    {#if selectionLoading}<StatusNotice message="선택한 신호와 학습 범위의 예측 가능 기간을 확인하고 있습니다." />{/if}
    {#if resultState === "loading"}
      <StatusNotice message="전망을 계산하고 있습니다." />
    {:else if resultState === "failed"}
      <StatusNotice kind="failure" title="전망을 계산하지 못했습니다" message={error}
        actionLabel="다시 계산하기" onAction={()=>void calculate()} />
      {#if selectedRecord||focus}<button type="button" class="ui-button" onclick={()=>{selectedRecord="";focus=null;save();void loadSelectedOptions(true);}}>이 신호의 다른 기록 선택</button>{/if}
    {:else if resultState === "unverified"}
      <StatusNotice kind="uncertain" title="데이터가 바뀌어 결과를 다시 계산해야 합니다" message={error}
        actionLabel="다시 계산하기" onAction={()=>void calculate()} />
    {:else if resultState === "unavailable"}
      <StatusNotice kind="uncertain" title="이 기간은 전망할 수 없습니다" message={error} />
    {:else if projection}
      {@const limited=projection.conditions.management!==null||projection.conditions.end!==null}
      {@const chart=projection.future.length>0}
      {@const current=projection.scenarios.find(item=>item.id==="current")??projection.scenarios[0]}
      {@const worse=worseThanPersistence(projection.checks?.[0])}
      {@const told=outlookMessage({axis:"time",period:null,
        unit:projection.unit ?? names.get(projection.channel)?.unit ?? null,conditions:projection.conditions,
        scenarios:projection.scenarios,checks:projection.reachChecks??[]}) ?? forecastMessage({
          last:projection.history?.at(-1)?.value??null,start:projection.future[0].estimate,end:projection.future.at(-1)!,unit:projection.unit??names.get(projection.channel)?.unit??null,
          horizon:clock(projection.future.at(-1)!.at),checks:projection.checks??[]})}
      <section class="result" aria-labelledby="projection-result-title">
        <div class="result-head">
          <h3 id="projection-result-title">{signalName(names, projection.channel)} · 앞으로 {HORIZON_LABEL[projection.horizon]} 전망</h3>
          <span class="intro">마지막 측정 {clockText(Date.parse(projection.record.last))}</span>
        </div>
        <ForecastCaution fit={projection.fit??null} start={projection.future[0]} checks={projection.checks} unit={projection.unit} lastLabel="마지막 구간 평균"/>
        {#if chart}
          <OutlookChart history={(projection.history??[]).map(row=>({x:Date.parse(row.at),value:row.value}))}
            future={steadyFuture(projection)}
            last={Date.parse(projection.record.last)} {baseline} change={investigatedChange(location.search,"history",projection.recordKey)}
            limits={{management:projection.conditions.management,end:projection.conditions.end}} direction={projection.conditions.direction}
            reach={{management:reachAt(current?.management,Date.parse(projection.record.last),"time"),end:reachAt(current?.end,Date.parse(projection.record.last),"time")}}
            unit={projection.unit??names.get(projection.channel)?.unit??null} scale={{kind:"clock"}} place={clockText} unreliable={worse}/>
        {/if}
        {#if projection.evolution}<SignalEvolution data={projection.evolution} unit={projection.unit}/>{/if}
        <button type="button" class="ui-button" onclick={() => validationOpen = true}>예측 설명</button>
        <TaskDialog bind:open={validationOpen} title="전망 해석·과거 검증">
          <SourceIdentity id={projection.sourceId} pointId={projection.pointId} among={options.records?.map(row=>row.sourceId)??[]}/>
        {#if told}<AnalysisMessage message={told} showHeadline={false}
          subject={signalName(names, projection.channel)}
          basis={clock(projection.record.last) + "까지의 기록 · " + HORIZON_LABEL[projection.horizon] + " 앞까지 계산"}
          boundary="예상 여유의 시작은 기록 마지막 측정 시점입니다." />{/if}
        <ForecastFit showValues={limited} fit={projection.fit??null} checks={projection.checks} unit={projection.unit} />
        <ForecastValidation checks={projection.checks}/>
        <details>
          <summary>예측값 표 · {HORIZON_LABEL[projection.horizon]}</summary>
          {#if projection.future.length}
            <div class="scroll"><table>
              <caption>예측 기간 전체에서 고르게 고른 8개 · 예측 범위는 계산상 범위이며 고장 신뢰구간이 아닙니다</caption>
              <thead><tr><th scope="col">예측 시각</th><th scope="col">예측값</th>
                <th scope="col">범위 하한</th><th scope="col">범위 상한</th></tr></thead>
              <tbody>
                {#each spreadRows(projection.future) as value, i (value.at+i)}
                  <tr><td>{clock(value.at)}</td><td>{num(value.estimate)}</td>
                    <td>{num(value.lower)}</td><td>{num(value.upper)}</td></tr>
                {/each}
              </tbody>
            </table></div>
          {:else}
            <p class="intro">예측값을 받지 못했습니다.</p>
          {/if}
        </details>
        {#if limited}
          <details>
            <summary>계산 방식별 결과 {projection.scenarios.length}가지</summary>
            {#if projection.scenarios.length}
              <div class="scroll"><table>
                <caption>계산 방식 사이의 차이는 신뢰 구간이 아닙니다</caption>
                <thead><tr><th scope="col">계산 방식</th>
                  {#if projection.conditions.management!==null}<th scope="col">관리 기준</th>{/if}
                  {#if projection.conditions.end!==null}<th scope="col">종료 기준</th>{/if}
                </tr></thead>
                <tbody>
                  {#each projection.scenarios as scenario (scenario.id)}
                    <tr><th scope="row">{label(scenario.id)}</th>
                      {#if projection.conditions.management!==null}<td>{reachText(scenario.management,"time")}</td>{/if}
                      {#if projection.conditions.end!==null}<td>{reachText(scenario.end,"time")}</td>{/if}
                    </tr>
                  {/each}
                </tbody>
              </table></div>
            {:else}
              <p class="intro">기준에 대한 계산 결과를 받지 못했습니다.</p>
            {/if}
          </details>
        {/if}
        <details>
          <summary>기술 상세</summary>
          <dl>
            <dt>데이터 출처 · 측정 위치 · 단위</dt><dd>{projection.sourceId} · {projection.pointId ?? "미확인"} · {projection.unit ?? "미확인"}</dd>
            <dt>사용한 기록</dt><dd>{clock(projection.record.first)} ~ {clock(projection.record.last)} · {projection.record.points}개</dd>
            <dt>계산 데이터 버전 (measurement_version)</dt><dd>{projection.measurementVersion}</dd>
            <dt>해설 근거 버전 (data_version)</dt><dd>{projection.dataVersion}</dd>
          </dl>
        </details>
        </TaskDialog>
        {#key projection.measurementVersion+":"+projection.dataVersion+":"+projection.channel}
          <OutlookBriefingPanel {projection} onEvidenceChanged={()=>{
            requestProjection?.abort();
            projection=null;
            resultState="unverified";
            error="해설을 확인하는 사이 데이터가 바뀌었습니다. 다시 계산하세요.";
          }}/>
          <details class="optional-review" ontoggle={(event)=>reviewSelection=event.currentTarget.open && projection ? projection.measurementVersion+":"+projection.dataVersion+":"+projection.channel : null}><summary>검토 기록에 남기기 (선택)</summary>
            {#if reviewSelection === projection.measurementVersion+":"+projection.dataVersion+":"+projection.channel}<ReviewRequest {projection} onEvidenceChanged={message=>{
            requestProjection?.abort();
            projection=null;
            resultState="unverified";
            error=message;
          }}/>{/if}
          </details>
        {/key}
        <p class="intro"><a href={signalHref()}>이 신호의 원본 측정 보기 →</a></p>
      </section>
    {:else if !selectionLoading}
      <p class="intro">신호와 예측 기간을 고르고 계산하기를 누르면 전망을 표시합니다.</p>
    {/if}
    </div>
    {#if appliedCriteria}<aside class="forecast-inspector" aria-label="기준 도달·예상 여유">
      <h3 class="inspector-title">기준 도달·예상 여유</h3>

      {#if projection}
        {@const current=projection.scenarios.find(item=>item.id==="current")??projection.scenarios[0]}
        {@const basis=current&&current.id!=="current"?" · "+label(current.id)+" 기준":""}
        {@const limited=projection.conditions.management!==null||projection.conditions.end!==null}
        {@const worse=worseThanPersistence(projection.checks?.[0])}
        {#if criteriaPending}<p class="criteria-pending" role="status">입력한 기준은 아직 적용하지 않았습니다.</p>{/if}
        {#if limited}
          {@const lastAt=Date.parse(projection.record.last)}
          {@const shown=(projection.history??[]).map(row=>({x:Date.parse(row.at),value:row.value}))}
          <div class="tiles">
            {#each [["management","관리 기준",projection.conditions.management,current?.management],["end","종료 기준",projection.conditions.end,current?.end]] as const as [key,name,value,reach] (key)}
              {#if value!==null}{@const told=reachSummary(reach,"time",null,clockText,lastAt,reach?.state==="already"?crossedSince(shown,value,projection.conditions.direction):null)}
                <div><span>{name} {measure(value, (projection.unit ?? names.get(projection.channel)?.unit ?? null))}{basis}</span><strong>{told.headline}</strong>
                  {#if told.detail}<span>{told.detail}</span>{/if}
                  {#if worse&&reach?.state!=="already"}<span class="caveat">예측 오차가 커서 참고로만 봅니다.</span>{/if}
                  {#if key==="end"}<span>입력한 종료 기준까지의 조건부 예측입니다. 설비의 실제 잔여수명은 아닙니다.</span>{/if}</div>
              {/if}
            {/each}
          </div>
        {/if}
      {/if}
    </aside>{/if}
    <TaskDialog bind:open={criteriaOpen} title="도달 기준 설정">
      {#if suggestions.length}<div class="suggest" aria-label="기준 제안"><p>기준 제안 · 누르면 바로 적용</p>
        {#each suggestions as item (item.label)}<button type="button" class="chip" title={item.source} aria-pressed={projection?.conditions.management===item.value&&projection?.conditions.direction===item.direction}
          onclick={() => { criteriaOpen = false; suggest(item.value, item.direction); }}>{item.label}</button>{/each}</div>{/if}
      <form class="criteria" onsubmit={event=>{event.preventDefault(); criteriaOpen = false; void calculate();}}>
        <p>기준값 직접 입력</p>
      <div class="controls">      <label for="projection-direction">기준 방향
        <select id="projection-direction" value={direction}
          onchange={e=>{direction=e.currentTarget.value as Direction;save();}}>
          <option value="upper">값이 올라갈 때 (상한)</option><option value="lower">값이 내려갈 때 (하한)</option>
        </select>
      </label>
      <label for="projection-management">관리 기준 ({(projection?.unit??names.get(channel)?.unit)?(projection?.unit??names.get(channel)?.unit)+" · ":""}선택)
        <input id="projection-management" type="number" step="any"
          value={management} oninput={e=>{management=e.currentTarget.value;save();}}/>
      </label>
      <label for="projection-end">종료 기준 ({(projection?.unit??names.get(channel)?.unit)?(projection?.unit??names.get(channel)?.unit)+" · ":""}선택)
        <input id="projection-end" type="number" step="any"
          value={endLimit} oninput={e=>{endLimit=e.currentTarget.value;save();}}/>
      </label>
      </div>
        <button type="submit" class="ui-button ui-button-primary" aria-busy={resultState==="loading"} disabled={selectionLoading||!selectionReady||resultState==="loading"}>{resultState==="loading"?"계산 중…":"기준 적용"}</button>
      </form>
    </TaskDialog>
    </div>
  {/if}
</section>

<style>
  .forecast-workspace{grid-template-columns:minmax(0,1fr);gap:var(--space-5)}
  .forecast-workspace.has-criteria{grid-template-columns:minmax(0,1fr) 260px}
  .forecast-controls{grid-column:1/-1;grid-row:1;display:flex;align-items:end;flex-wrap:wrap;gap:var(--space-3);border-bottom:1px solid var(--color-border);padding-bottom:var(--space-3)}
  .forecast-controls>.controls{flex:1 1 500px;min-width:0;display:flex;flex-wrap:wrap;align-items:end;margin:0;gap:var(--space-3)}
  .forecast-controls>.controls>label{flex:1 1 160px;min-width:0}.forecast-controls>.controls>label:first-child{flex:1.3 1 240px}.forecast-controls>.controls>button{flex:none}
  .forecast-controls :global(.analysis-controls){flex:none;margin:0}
  .criteria-button{min-height:40px}


  .controls>button{align-self:end;min-height:44px}
  .projection { min-width: 0; }
  .intro { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-3); }
  .controls { display: grid; grid-template-columns: repeat(auto-fit,minmax(150px,1fr));
    gap: var(--space-4); margin-block: var(--space-5); }
  label { display: grid; gap: var(--space-2); font-weight: 650; font-size: var(--font-small); }
  select, input { width: 100%; min-width: 0; padding: var(--space-3);
    border: 1px solid var(--color-border); border-radius: var(--radius-control);
    background: var(--color-surface); color: var(--color-ink); }
  .result { min-width: 0; }
  h3 { font-size: var(--font-section); margin: 0; }
  .result-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2); align-items: baseline; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-3); margin-top: var(--space-4); }
  .tiles div { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-4); display: grid; gap: var(--space-1); }
  .tiles span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .tiles strong { font-size: var(--font-section); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-3); }
  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; margin-top: var(--space-4); }
  caption { text-align: left; color: var(--color-ink-muted); font-size: var(--font-small); }
  th, td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--color-border); }
  dl { overflow-wrap: anywhere; }
  dt { font-weight: 700; }
  dd { margin: var(--space-1) 0 var(--space-3); }

  .forecast-workspace>.analysis-body{grid-column:1;grid-row:2;min-width:0}
  .forecast-inspector{grid-column:2;grid-row:2;align-self:start;display:grid;gap:var(--space-3);border-left:1px solid var(--color-border);padding-left:var(--space-4);min-width:0}
  .criteria{display:grid;gap:var(--space-3)}.criteria p,.criteria-pending{font-size:var(--font-small);margin:0;color:var(--color-ink-muted)}
  .criteria .controls{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--space-3);margin:0}.criteria input,.criteria select{padding:var(--space-2)}
  .forecast-inspector .tiles{grid-template-columns:minmax(0,1fr)}.criteria-pending{color:var(--color-caution-ink)}
  @media(max-width:1000px){.forecast-workspace.has-criteria{grid-template-columns:minmax(0,1fr)}.forecast-inspector{grid-column:1;grid-row:3;border-left:0;border-top:1px solid var(--color-border);padding:var(--space-4) 0 0}.criteria .controls{grid-template-columns:repeat(2,minmax(0,1fr))}}

  .inspector-title{margin:0;font-size:var(--font-section)}
  .tiles .caveat{color:var(--color-caution-ink)}
  .suggest{display:flex;flex-wrap:wrap;gap:6px}.suggest p{flex-basis:100%;margin:0;font-size:var(--font-small);color:var(--color-ink-muted)}
  .chip{font:inherit;font-size:var(--font-label);padding:4px 10px;border:1px solid var(--color-control-border);border-radius:999px;background:var(--color-surface);color:var(--color-action);cursor:pointer}
  .chip[aria-pressed="true"]{background:var(--color-surface-selected);border-color:var(--color-action);font-weight:650}
  .forecast-inspector .tiles{margin:0;gap:var(--space-3)}.forecast-inspector .tiles>div{border:0;border-bottom:1px solid var(--color-border);border-radius:0;padding:0 0 var(--space-3)}
</style>
