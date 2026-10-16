<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
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
  function offset(value: number | null): string {
    return value === null ? "기준 기간 내 도달값 없음" : value <= 0
      ? "이미 도달 또는 기준 도달 시점" : "마지막 관측 후 약 " + (value / 3600).toFixed(1) + "시간";
  }
  function label(id: string): string {
    return ({current:"현재 설정", recent:"최근 구간 중심", responsive:"변화점 민감",
      linear:"최근 변화속도 유지"} as Record<string,string>)[id] ?? id;
  }
  function limitState(state: string, expected: number | null): string {
    if (state === "already") return "이미 설정한 기준 도달";
    if (state === "expected") return offset(expected);
    if (state === "possible") return "불확실성 범위에서 도달 가능";
    return "제한된 계산 범위에서 예상 도달 시점 없음";
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
  <h2 id="projection-title">조건부 기준 도달과 측정 변화 전망</h2>
  <p class="intro">미래 신호 예측은 저장 기록에 학습한 추세를 연장한 값으로, 물리 고장 시점이나 확정된 잔여수명이 아닙니다. 사용자가 입력한 관리·종료 기준은 고장 인증 기준이 아닙니다.</p>
  {#if optionsState === "loading"}
    <StatusNotice message="선택 설비의 예측 가능한 신호·기간을 조회합니다." />
  {:else if optionsState === "failed"}
    <StatusNotice kind="failure" title="예측 선택지 조회 실패" message={error}
      actionLabel="다시 조회" onAction={()=>void loadSourceOptions()} />
  {:else if optionsState === "empty"}
    <StatusNotice kind="uncertain" title="전망할 저장 측정이 없습니다"
      message="해당 설비에 저장된 이력 신호가 없습니다. 설비가 정상이라는 의미가 아닙니다."
      actionLabel="저장 신호 조사" actionHref={"/web-next/?view=signals&monitor_asset="+encodeURIComponent(assetId)} />
  {:else if options}
    <div class="controls">
      <label for="projection-channel">측정 신호
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
              {options.horizons[value]===null?"":" (자료·지원 조건 부족)"}</option>
          {/each}
        </select>
      </label>
      <label for="projection-direction">기준 도달 방향
        <select id="projection-direction" value={direction}
          onchange={e=>{direction=e.currentTarget.value as Direction;invalidate();}}>
          <option value="upper">상한 이상</option><option value="lower">하한 이하</option>
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
      같은 측정 버전으로 전망 계산
    </button>
    <p class="intro">분석은 요청 시 다시 계산되며 자동 저장하지 않습니다. 입력 조건이나 선택 신호를 바꾸면 이전 결과를 폐기합니다.</p>
    {#if resultState === "loading"}
      <StatusNotice message="예측과 조건부 전망을 같은 저장 측정 근거에 대해 계산합니다." />
    {:else if resultState === "failed"}
      <StatusNotice kind="failure" title="전망 근거 검증 실패" message={error}
        actionLabel="다시 계산" onAction={()=>void calculate()} />
    {:else if resultState === "unverified"}
      <StatusNotice kind="uncertain" title="측정 버전 불일치로 결합 보류" message={error}
        actionLabel="다시 조회" onAction={()=>void calculate()} />
    {:else if resultState === "unavailable"}
      <StatusNotice kind="uncertain" title="이 기간의 예측 지원 불가" message={error} />
    {:else if projection}
      <p class="intro">관측 출처 <strong>{projection.sourceId}</strong> · 측정점
        {projection.pointId ?? "미확인"} · 단위 {projection.unit ?? "미확인"}</p>
      <p class="intro">원본 기록 {clock(projection.record.first)} ~ {clock(projection.record.last)}
        · 분석 사용 유효 시점 {projection.record.points}개</p>
      <details>
        <summary>측정 버전·설명 데이터 버전 확인</summary>
        <dl>
          <dt>공통 측정 버전</dt><dd>{projection.measurementVersion}</dd>
          <dt>AI 설명용 근거 버전 (AI 호출 없음)</dt><dd>{projection.dataVersion}</dd>
        </dl>
      </details>
      <section class="result">
        <h3>예측 신호값 · {projection.horizon}</h3>
        <p class="intro">오차 범위는 모델 가정에 따른 계산 구간이며 현장 검증이나 고장 신뢰구간이 아닙니다.</p>
        {#if projection.future.length}
          <div class="scroll"><table>
            <caption>서버가 계산한 미래 신호 예측값 (최대 8개 예시)</caption>
            <thead><tr><th scope="col">예측 시점</th><th scope="col">예측값</th>
              <th scope="col">계산 하한</th><th scope="col">계산 상한</th></tr></thead>
            <tbody>
              {#each projection.future.slice(0,8) as value, i (value.at+i)}
                <tr><td>{clock(value.at)}</td><td>{value.estimate}</td>
                  <td>{value.lower??"미산출"}</td><td>{value.upper??"미산출"}</td></tr>
              {/each}
            </tbody>
          </table></div>
        {:else}
          <StatusNotice kind="uncertain" message="반환된 미래 시점의 수치를 확인할 수 없습니다." />
        {/if}
      </section>
      {#if projection.conditions.management!==null || projection.conditions.end!==null}
        <section class="result">
          <h3>사용자가 지정한 기준까지의 조건부 전망</h3>
          <p class="intro">도달 시점은 마지막 기록 기준 계산 시간입니다. 검증된 물리 고장 시점이 아니며, 시나리오 차이는 신뢰구간이 아닙니다.</p>
          {#if projection.scenarios.length}
            <div class="scroll"><table>
              <caption>서버 소유 예측 모델 설정별 도달 상태</caption>
              <thead><tr><th scope="col">계산 방식</th>
                {#if projection.conditions.management!==null}<th scope="col">관리 기준 도달</th>{/if}
                {#if projection.conditions.end!==null}<th scope="col">종료 기준 도달</th>{/if}
              </tr></thead>
              <tbody>
                {#each projection.scenarios as scenario (scenario.id)}
                  <tr><th scope="row">{label(scenario.id)}</th>
                    {#if projection.conditions.management!==null}
                      <td>{scenario.management?limitState(scenario.management.state,scenario.management.expected):"미산출"}</td>
                    {/if}
                    {#if projection.conditions.end!==null}
                      <td>{scenario.end?limitState(scenario.end.state,scenario.end.expected):"미산출"}</td>
                    {/if}
                  </tr>
                {/each}
              </tbody>
            </table></div>
          {:else}
            <StatusNotice kind="uncertain" message="입력 기준에 대한 시나리오 결과가 없습니다." />
          {/if}
        </section>
      {:else}
        <StatusNotice message="관리·종료 기준을 입력하면 조건부 기준 도달 전망을 함께 계산할 수 있습니다." />
      {/if}
      <p class="intro"><a href={"/web-next/?view=signals&monitor_asset="+encodeURIComponent(assetId)
        +"&monitor_channel="+encodeURIComponent(channel)}>원본 측정·출처·품질 다시 확인 →</a></p>
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
  h3 { font-size: var(--font-section); }
  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; margin-top: var(--space-4); }
  caption { text-align: left; color: var(--color-ink-muted); font-size: var(--font-small); }
  th, td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--color-border); }
  dl { overflow-wrap: anywhere; }
  dt { font-weight: 700; }
  dd { margin: var(--space-1) 0 var(--space-3); }
</style>
