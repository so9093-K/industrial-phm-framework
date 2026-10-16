<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {assetTabUrl} from "../routes";
  import OutlookBriefings from "./OutlookBriefings.svelte";
  import {
    loadAcquisitionOptions,loadAcquisitionPair,
    AcquisitionVersionMismatch,AcquisitionOutlookUnavailable,
    type AcquisitionOptions,type AcquisitionProjection,type AcquisitionFeature,
  } from "../acquisition-outlook";
  import type {Conditions,Direction} from "../projections";

  let {assetId}:{assetId:string}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed"|"mismatch";
  let listState:State=$state("loading");
  let resultState:State=$state("empty");
  let options:AcquisitionOptions|null=$state(null);
  let outlook:AcquisitionProjection|null=$state(null);
  let message=$state("");
  const params=new URLSearchParams(location.search);
  let featureId=$state(params.get("acq_forecast_feature")??"");
  let countText=$state(params.get("acq_forecast_count")??"5");
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
      acq_forecast_feature:featureId,acq_forecast_count:countText,
      acq_assumed_period:assumedText,acq_direction:direction,
      acq_management:managementText,acq_end:endText,
    };
    for(const [key,value] of Object.entries(values)){
      if(value.trim())url.searchParams.set(key,value);
      else url.searchParams.delete(key);
    }
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
      if(!valid.some(f=>f.id===featureId))featureId=valid[0].id;
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
      const data=await loadAcquisitionPair(options,featureId,count,assumed,conditions,request.signal);
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
    if(record.timeBasis==="recorded")return "수집 메타데이터에 기록된 획득 간격";
    if(record.timeBasis==="assumed")return "사용자가 가정한 획득 간격";
    return "획득 순번만 확인 가능 (시간 간격 미기록)";
  }
  function reachState(state:string,offset:number|null):string{
    if(state==="already")return "마지막 획득 시 기준에 도달";
    if(state==="expected")return offset===null?"도달 횟수 미산출":`추가 ${offset}회 획득 시 도달 예상`;
    if(state==="possible")return "예측 범위에서만 도달 가능 (중심값 도달 아님)";
    return "설정된 계산 범위 내 예상 도달 없음";
  }
  const formatOffset=(n:number)=>Number.isInteger(n)?String(n):n.toFixed(2);
  onMount(()=>{void loadOptions();return()=>{listAbort?.abort();resultAbort?.abort();};});
</script>

<section class="ui-panel" aria-labelledby="acq-outlook-title">
  <h2 id="acq-outlook-title">획득 특징의 조건부 전망</h2>
  <p class="context">저장된 파형의 <strong>획득 순번(ordinal)</strong>을 기준으로 특징값의
    미래 범위와 사용자가 설정한 기준까지의 여유를 계산합니다. 획득 순번·간격·실제 측정 시각은
    서로 다릅니다. 가정한 간격은 수집된 시각이나 실제 사용 수명을 의미하지 않습니다.</p>
  {#if listState==="loading"}
    <StatusNotice message="저장된 획득 특징과 기록된 시간 간격을 조회하고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="획득 전망 목록 조회 실패" message={message}
      actionLabel="다시 조회" onAction={()=>void loadOptions()}/>
  {:else if listState==="empty"||listState==="unavailable"}
    <StatusNotice kind="uncertain" title="획득 특징 전망의 입력 근거 부족"
      message="유효한 모델 분석 획득 특징이 최소 20개 필요합니다. 데이터가 없거나 계산할 수 없는 상태는 설비 정상 판정이 아닙니다."
      actionLabel="획득 특징 분석 확인" actionHref={assetTabUrl(assetId, "change", "compare", "vibration")}/>
  {:else if options}
    <p class="context">원본 <strong>{options.sourceId}</strong> · binding <strong>{options.bindingId}</strong>
      · 획득 #{options.first}~#{options.last} · 저장 분석 {options.count}회</p>
    <p class="context">수집 메타데이터의 간격:
      {options.recordedPeriod===null?"기록 없음":options.recordedPeriod+"초 / 획득"}
      (획득의 실제 UTC 시각을 나타내지 않음)</p>
    <div class="inputs">
      <label>저장 획득 특징
        <select value={featureId} onchange={e=>{featureId=e.currentTarget.value;invalidate();}}>
          {#each options.features as item (item.id)}
            <option value={item.id} disabled={!item.countForecast}>
              {item.label} · {item.id} · 유효 {item.validPoints}회{item.countForecast?"":" (부족)"}
            </option>
          {/each}
        </select>
      </label>
      <label>미래 추가 획득 횟수 (1~2000)
        <input type="number" min="1" max="2000" step="1" value={countText}
          oninput={e=>{countText=e.currentTarget.value;invalidate();}}/>
      </label>
      <label>가정한 획득 간격 (선택 · 초/회, 1~86400)
        <input type="number" min="1" max="86400" step="any" value={assumedText}
          placeholder={options.recordedPeriod===null?"없으면 획득 횟수만 계산":"비우면 기록된 간격 사용"}
          oninput={e=>{assumedText=e.currentTarget.value;invalidate();}}/>
      </label>
      <label>기준 도달 방향
        <select value={direction} onchange={e=>{direction=e.currentTarget.value as Direction;invalidate();}}>
          <option value="upper">상한 이상</option><option value="lower">하한 이하</option>
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
    <button type="button" class="ui-button ui-button-primary"
      onclick={()=>void calculate()} disabled={available.length===0}>같은 획득 근거로 전망 계산</button>
    <p class="context">서버 계산은 요청 시 실행하며 저장하지 않습니다. 선택한 특징·횟수·간격·조건을
      바꾸면 이전 결과를 즉시 폐기합니다. AI 요청은 명시적으로 저장하며 사람 검토 기록은 이 화면에서 작성하지 않습니다.</p>
    {#if resultState==="loading"}
      <StatusNotice message="동일 출처·binding·측정 버전의 획득 전망 두 계산을 검증 중입니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="획득 전망 근거 확인 실패" message={message}
        actionLabel="같은 조건 재계산" onAction={()=>void calculate()}/>
    {:else if resultState==="mismatch"}
      <StatusNotice kind="uncertain" title="획득 전망 근거 불일치" message={message}
        actionLabel="원본 목록 다시 조회" onAction={()=>void loadOptions()}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="이 획득 조건에서는 예측 지원 불가" message={message}/>
    {:else if outlook}
      <section class="result">
        <h3>서버에 검증된 획득 전망 근거</h3>
        <p class="context">{timeBasis(outlook)} · 계산 축: 획득 회차
          · 예측 추가 {outlook.horizonCount}회 · 유효 입력 {outlook.record.points}회</p>
        <p class="context">입력 획득 #{outlook.record.first}~#{outlook.record.last}
          · 출처 {outlook.sourceId} · binding {outlook.bindingId}</p>
        <p class="context">시간 간격 표기는 {outlook.timeBasis==="assumed"?"사용자가 가정한 ":
          outlook.timeBasis==="recorded"?"저장 출처 메타데이터에서 읽은 ":"산출용 내부 "} 
          {outlook.effectivePeriod}초/회이며 실제 이벤트 시각을 복원한 값이 아닙니다.</p>
        <details>
          <summary>정확한 측정 버전·AI 설명 근거 버전</summary>
          <dl>
            <dt>공통 획득 측정 버전</dt><dd>{outlook.measurementVersion}</dd>
            <dt>이상 탐지 포함 설명 근거 버전</dt><dd>{outlook.dataVersion}</dd>
          </dl>
        </details>
        <p class="context">특징값 예측 범위: 추가 {outlook.horizonCount}회.
          조건부 기준 도달 탐색 범위: 마지막 관측 #{outlook.record.last} 이후
          추가 {outlook.searchCount}회 (최대 #{outlook.searchUntil})입니다.
          두 계산의 탐색 범위는 서로 다를 수 있습니다.</p>
        <h3>추가 획득 회차별 예상 특징값</h3>
        <p class="context">서버 Prophet 추세 계산값입니다. 예측 범위는 고장 신뢰구간이 아닙니다.</p>
        <div class="scroll"><table>
          <caption>예측 회차는 실제 날짜·시각이 아닌 상대적인 획득 순번입니다</caption>
          <thead><tr><th scope="col">획득 #</th><th scope="col">특징 예상</th>
            <th scope="col">계산 하한</th><th scope="col">계산 상한</th></tr></thead>
          <tbody>
            {#each outlook.forecast.slice(0,12) as item,i (i)}
              <tr><td>#{formatOffset(item.ordinal)}</td><td>{item.estimate}</td>
                <td>{item.lower??"미산출"}</td><td>{item.upper??"미산출"}</td></tr>
            {/each}
          </tbody>
        </table></div>
        {#if outlook.conditions.management!==null||outlook.conditions.end!==null}
          <h3>사용자가 지정한 기준 도달 · 추가 획득 횟수</h3>
          <div class="scroll"><table>
            <caption>추가 획득 횟수는 예측값이며 기계 잔여수명·교체 시점이 아닙니다</caption>
            <thead><tr><th scope="col">시나리오</th>
              {#if outlook.conditions.management!==null}<th scope="col">관리 기준</th>{/if}
              {#if outlook.conditions.end!==null}<th scope="col">종료 기준</th>{/if}
            </tr></thead>
            <tbody>
              {#each outlook.scenarios as row (row.id)}
                <tr><th scope="row">{row.id}</th>
                  {#if outlook.conditions.management!==null}
                    <td>{row.management?reachState(row.management.state,row.management.expected):"미산출"}</td>
                  {/if}
                  {#if outlook.conditions.end!==null}
                    <td>{row.end?reachState(row.end.state,row.end.expected):"미산출"}</td>
                  {/if}
                </tr>
              {/each}
            </tbody>
          </table></div>
        {:else}
          <StatusNotice message="관리·종료 기준을 선택하면 해당 기준까지의 획득 횟수 전망을 함께 계산합니다."/>
        {/if}
      </section>
      {#key outlook.measurementVersion+":"+outlook.dataVersion+":"+outlook.bindingId+":"+outlook.timeBasis}
        <OutlookBriefings projection={outlook} onEvidenceChanged={()=>{
          resultAbort?.abort();
          outlook=null;
          resultState="mismatch";
          message="AI 근거 재검증 중 출처·binding·버전·간격이 변경됐습니다. 획득 원본을 다시 조회하세요.";
        }}/>
      {/key}
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
  .scroll{max-width:100%;overflow-x:auto}
  table{border-collapse:collapse;width:100%}th,td{padding:var(--space-2);text-align:left;border-bottom:1px solid var(--color-border)}
  caption{text-align:left;color:var(--color-ink-muted)}dd{overflow-wrap:anywhere}
</style>
