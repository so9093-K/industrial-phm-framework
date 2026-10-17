<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import CautionNote from "./CautionNote.svelte";
  import {reachText} from "../reach";
  import {num} from "../format";
  import {assetTabUrl} from "../routes";
  import OutlookBriefings from "./OutlookBriefings.svelte";
  import ReviewRequest from "./ReviewRequest.svelte";
  import {
    loadOptions, loadPaired, MeasurementVersionMismatch, ProjectionUnavailable,
    type Conditions, type Direction, type Horizon, type Options, type Projection,
  } from "../projections";
  type Props = {assetId: string};
  let {assetId}: Props = $props();
  type State = "loading" | "ready" | "empty" | "unavailable" | "failed" | "unverified";
  let optionsState: State = $state("loading");
  let resultState: State = $state("empty");
  let options: Options | null = $state(null);
  let projection: Projection | null = $state(null);
  let error = $state("");
  const params = new URLSearchParams(location.search);
  let channel = $state(params.get("monitor_channel") ?? "");
  const savedHorizon = params.get("projection_horizon");
  let horizon: Horizon = $state(
    savedHorizon === "24h" || savedHorizon === "7d" || savedHorizon === "30d"
      ? savedHorizon : "1h"
  );
  let management = $state(params.get("projection_management") ?? "");
  let endLimit = $state(params.get("projection_end") ?? "");
  let direction: Direction = $state(params.get("projection_direction") === "lower" ? "lower" : "upper");
  let requestOptions: AbortController | null = null;
  let requestProjection: AbortController | null = null;
  const horizons: Horizon[] = ["1h", "24h", "7d", "30d"];

  function parseLimit(value: string): number | null {
    if (value.trim() === "") return null;
    const n = Number(value);
    if (!Number.isFinite(n)) throw new Error("관리·종료 기준은 유한한 숫자로 입력해야 합니다.");
    return n;
  }
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
    url.searchParams.set("projection_horizon",horizon);
    url.searchParams.set("projection_direction",direction);
    if (management.trim()) url.searchParams.set("projection_management",management);
    else url.searchParams.delete("projection_management");
    if (endLimit.trim()) url.searchParams.set("projection_end",endLimit);
    else url.searchParams.delete("projection_end");
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
    optionsState="loading"; resultState="empty"; options=null; projection=null; error="";
    try {
      const data=await loadOptions(assetId,abort.signal);
      if (abort.signal.aborted) return;
      options=data;
      if (!data.channels.length){optionsState="empty";return;}
      if (!data.channels.includes(channel)) channel=data.channels[0];
      if (data.horizons[horizon] !== null) {
        const allowed = horizons.find(key=>data.horizons[key]===null);
        if (allowed) horizon=allowed;
      }
      optionsState="ready";
      save();
    } catch(cause:unknown) {
      if(abort.signal.aborted)return;
      optionsState="failed";
      error=cause instanceof Error?cause.message:"전망 가능한 측정 목록을 읽지 못했습니다.";
    }
  }
  async function calculate() {
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
      const data=await loadPaired(assetId,channel,horizon,conditions,abort.signal);
      if(abort.signal.aborted)return;
      projection=data;resultState="ready";
    }catch(cause:unknown){
      if(abort.signal.aborted)return;
      resultState=cause instanceof MeasurementVersionMismatch?"unverified"
        :cause instanceof ProjectionUnavailable?"unavailable":"failed";
      error=cause instanceof Error?cause.message:"계산 근거를 확인할 수 없습니다.";
    }
  }
  onMount(()=>{void loadSourceOptions();return ()=>{requestOptions?.abort();requestProjection?.abort();};});
</script>

<section class="ui-panel projection" aria-labelledby="projection-title">
  <h2 id="projection-title">기준 도달 전망</h2>
  <p class="intro">고른 신호가 지금까지의 추세대로 이어질 때 사용자가 정한 기준에 언제 닿는지 계산합니다.</p>
  {#if optionsState === "loading"}
    <StatusNotice message="전망할 수 있는 신호와 기간을 불러오고 있습니다." />
  {:else if optionsState === "failed"}
    <StatusNotice kind="failure" title="전망할 신호를 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void loadSourceOptions()} />
  {:else if optionsState === "empty"}
    <StatusNotice kind="uncertain" title="전망할 시계열 기록이 없습니다"
      message="이 설비에는 저장된 시계열 신호가 없습니다. 이상이 없다는 뜻은 아닙니다."
      actionLabel="신호 보기" actionHref={assetTabUrl(assetId, "signals")} />
  {:else if options}
    <div class="controls">
      <label for="projection-channel">신호
        <select id="projection-channel" value={channel}
          onchange={e=>{channel=e.currentTarget.value;invalidate();}}>
          {#each options.channels as id (id)}<option value={id}>{id}</option>{/each}
        </select>
      </label>
      <label for="projection-horizon">예측 기간
        <select id="projection-horizon" value={horizon}
          onchange={e=>{horizon=e.currentTarget.value as Horizon;invalidate();}}>
          {#each horizons as value (value)}
            <option value={value} disabled={options.horizons[value]!==null}>{value}
              {options.horizons[value]===null?"":" (기록이 짧아 불가)"}</option>
          {/each}
        </select>
      </label>
      <label for="projection-direction">기준 방향
        <select id="projection-direction" value={direction}
          onchange={e=>{direction=e.currentTarget.value as Direction;invalidate();}}>
          <option value="upper">값이 올라갈 때 (상한)</option><option value="lower">값이 내려갈 때 (하한)</option>
        </select>
      </label>
      <label for="projection-management">관리 기준 (선택)
        <input id="projection-management" type="number" step="any"
          value={management} oninput={e=>{management=e.currentTarget.value;invalidate();}}/>
      </label>
      <label for="projection-end">종료 기준 (선택)
        <input id="projection-end" type="number" step="any"
          value={endLimit} oninput={e=>{endLimit=e.currentTarget.value;invalidate();}}/>
      </label>
    </div>
    <button type="button" class="ui-button ui-button-primary"
      onclick={()=>void calculate()} disabled={!horizons.some(key=>options?.horizons[key]===null)}>
      계산하기
    </button>
    <p class="intro">조건을 바꾸면 아래 결과는 지워지고 다시 계산해야 합니다.</p>
    {#if resultState === "loading"}
      <StatusNotice message="전망을 계산하고 있습니다." />
    {:else if resultState === "failed"}
      <StatusNotice kind="failure" title="전망을 계산하지 못했습니다" message={error}
        actionLabel="다시 계산하기" onAction={()=>void calculate()} />
    {:else if resultState === "unverified"}
      <StatusNotice kind="uncertain" title="데이터가 바뀌어 결과를 다시 계산해야 합니다" message={error}
        actionLabel="다시 계산하기" onAction={()=>void calculate()} />
    {:else if resultState === "unavailable"}
      <StatusNotice kind="uncertain" title="이 기간은 전망할 수 없습니다" message={error} />
    {:else if projection}
      {@const current=projection.scenarios.find(item=>item.id==="current")??projection.scenarios[0]}
      {@const basis=current&&current.id!=="current"?" · "+label(current.id)+" 기준":""}
      {@const limited=projection.conditions.management!==null||projection.conditions.end!==null}
      <section class="result" aria-labelledby="projection-result-title">
        <div class="result-head">
          <h3 id="projection-result-title">결과</h3>
          <span class="intro">{clock(projection.record.last)}까지의 기록으로 계산</span>
        </div>
        {#if limited}
          <div class="tiles">
            {#if projection.conditions.management!==null}
              <div><span>관리 기준 {num(projection.conditions.management)}{basis}</span><strong>{reachText(current?.management,"time")}</strong></div>
            {/if}
            {#if projection.conditions.end!==null}
              <div><span>종료 기준 {num(projection.conditions.end)}{basis}</span><strong>{reachText(current?.end,"time")}</strong></div>
            {/if}
          </div>
        {:else}
          <p class="intro">관리·종료 기준을 입력하면 기준에 언제 닿는지 함께 계산합니다.</p>
        {/if}
        {#key projection.measurementVersion+":"+projection.dataVersion+":"+projection.channel}
          <OutlookBriefings {projection} onEvidenceChanged={()=>{
            requestProjection?.abort();
            projection=null;
            resultState="unverified";
            error="해설을 확인하는 사이 데이터가 바뀌었습니다. 다시 계산하세요.";
          }}/>
          <ReviewRequest {projection} onEvidenceChanged={message=>{
            requestProjection?.abort();
            projection=null;
            resultState="unverified";
            error=message;
          }}/>
        {/key}
        <CautionNote message="지금까지의 추세가 이어진다고 가정한 계산입니다. 기준은 사용자가 정한 값이며, 고장 시점이나 남은 수명이 아닙니다." />
        <details>
          <summary>예측값 보기 · {projection.horizon}</summary>
          {#if projection.future.length}
            <div class="scroll"><table>
              <caption>앞으로의 신호 예측값 (최대 8개) · 예측 범위는 계산상 범위이며 고장 신뢰구간이 아닙니다</caption>
              <thead><tr><th scope="col">예측 시각</th><th scope="col">예측값</th>
                <th scope="col">범위 하한</th><th scope="col">범위 상한</th></tr></thead>
              <tbody>
                {#each projection.future.slice(0,8) as value, i (value.at+i)}
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
        <p class="intro"><a href={assetTabUrl(assetId, "signals", null, null, channel)}>이 신호의 원본 측정 보기 →</a></p>
      </section>
    {/if}
  {/if}
</section>

<style>
  .projection { min-width: 0; }
  .intro { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .controls { display: grid; grid-template-columns: repeat(auto-fit,minmax(150px,1fr));
    gap: var(--space-4); margin-block: var(--space-5); }
  label { display: grid; gap: var(--space-2); font-weight: 650; font-size: var(--font-small); }
  select, input { width: 100%; min-width: 0; padding: var(--space-3);
    border: 1px solid var(--color-border); border-radius: var(--radius-control);
    background: var(--color-surface); color: var(--color-ink); }
  .result { border-top: 1px solid var(--color-border); margin-top: var(--space-6); padding-top: var(--space-4); }
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
</style>
