<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {
    defaultPeriods, readProfile, readSources, validatePeriods, NoHistoryError,
    type Periods, type ProfileResult, type SourceHistory,
  } from "../comparison";

  type Props = {assetId: string};
  let {assetId}: Props = $props();
  type State = "loading" | "ready" | "empty" | "failed" | "unavailable";
  let sourceState: State = $state("loading");
  let compareState: State = $state("loading");
  let sources: SourceHistory | null = $state(null);
  let selected = $state(new URLSearchParams(location.search).get("monitor_channel") ?? "");
  let periods: Periods | null = $state(null);
  let result: ProfileResult | null = $state(null);
  let error = $state("");
  let formError = $state("");
  let sourceAbort: AbortController | null = null;
  let profileAbort: AbortController | null = null;

  const kst = (iso: string): string =>
    new Date(Date.parse(iso) + 9 * 3600000).toISOString().slice(0, 16);
  const isoKst = (input: string): string => {
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(input)
        || !Number.isFinite(Date.parse(input + ":00+09:00")))
      throw new Error("구간 시각은 KST 날짜와 시각으로 지정하세요.");
    return input + ":00+09:00";
  };
  const showTime = (iso: string): string =>
    new Date(iso).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});

  function loadPeriodUrl(fallback: Periods): Periods {
    const params = new URLSearchParams(location.search);
    const read = (key: string) => {
      const span = params.get(key)?.split("~");
      return span && span.length === 2 ? {from:span[0],to:span[1]} : null;
    };
    const a = read("compare_a"), b = read("compare_b");
    if (!a || !b) return fallback;
    try {validatePeriods({a,b}); return {a,b};} catch {return fallback;}
  }
  function remember() {
    if (!periods) return;
    const url = new URL(location.href);
    url.searchParams.set("monitor_asset", assetId);
    url.searchParams.set("monitor_channel", selected);
    url.searchParams.set("compare_a", periods.a.from + "~" + periods.a.to);
    url.searchParams.set("compare_b", periods.b.from + "~" + periods.b.to);
    history.replaceState(history.state, "", url);
  }
  async function loadSources() {
    sourceAbort?.abort();
    profileAbort?.abort();
    const request = new AbortController(); sourceAbort = request;
    sourceState = "loading"; compareState = "loading"; sources = null; result = null; error = "";
    try {
      const data = await readSources(assetId, request.signal);
      if (request.signal.aborted) return;
      sources = data;
      if (!data.channels.length) {sourceState = "empty"; return;}
      if (!data.channels.includes(selected)) selected = data.channels[0];
      sourceState = "ready";
      periods = loadPeriodUrl(defaultPeriods(data.from, data.to));
      remember();
      await compare();
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      sourceState = cause instanceof NoHistoryError ? "unavailable" : "failed";
      error = cause instanceof Error ? cause.message : "비교할 측정 목록을 조회하지 못했습니다.";
    }
  }
  function selectChannel(id: string) {
    if (!sources?.channels.includes(id)) return;
    selected = id; remember(); void compare();
  }
  function changePeriod(which: "a" | "b", edge: "from" | "to", value: string) {
    if (!periods) return;
    try {
      periods = {...periods, [which]: {...periods[which], [edge]:isoKst(value)}};
      formError = "";
    } catch (cause: unknown) {
      formError = cause instanceof Error ? cause.message : "구간 입력을 확인하세요.";
    }
  }
  async function compare() {
    profileAbort?.abort();
    const request = new AbortController(); profileAbort = request;
    compareState = "loading"; result = null; error = ""; formError = "";
    if (!periods) return;
    try {
      validatePeriods(periods);
      const expected = structuredClone(periods);
      const data = await readProfile(assetId, selected, expected, request.signal);
      if (request.signal.aborted) return;
      result = data; compareState = data.series.length ? "ready" : "empty"; remember();
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      compareState = cause instanceof NoHistoryError ? "unavailable" : "failed";
      error = cause instanceof Error ? cause.message : "두 기간의 분석 결과를 읽지 못했습니다.";
    }
  }
  onMount(() => {
    void loadSources();
    return () => {sourceAbort?.abort(); profileAbort?.abort();};
  });
</script>

<section class="ui-panel compare" aria-labelledby="comparison-title">
  <h2 id="comparison-title">구간 A와 B의 측정 사실 비교</h2>
  <p class="context">설비 <strong>{assetId}</strong> · 저장된 원본 측정에 기반한 서버 집계입니다.</p>
  <p class="context">A는 사용자가 고른 비교 기준이며 정상 운전이나 고장 전 기준으로 검증된 기간이 아닙니다. 출처·측정점·단위·측정 의미가 다른 기록은 별도로 표시합니다.</p>
  {#if sourceState === "loading"}
    <StatusNotice message="비교 가능한 저장 측정을 확인합니다." />
  {:else if sourceState === "failed"}
    <StatusNotice kind="failure" title="저장 측정 조회 실패" message={error}
      actionLabel="다시 조회" onAction={() => void loadSources()} />
  {:else if sourceState === "unavailable" || sourceState === "empty"}
    <StatusNotice kind="uncertain" title="비교할 저장 이력이 없습니다"
      message="해당 설비의 저장 측정 이력이 조회되지 않습니다. 정상 설비라는 뜻이 아닙니다."
      actionLabel="데이터 연결 확인" actionHref="/web/#connect" />
  {:else if sources && periods}
    <div class="controls">
      <label for="compare-channel">비교할 측정 신호
        <select id="compare-channel" value={selected}
          onchange={e => selectChannel(e.currentTarget.value)}>
          {#each sources.channels as id (id)}<option value={id}>{id}</option>{/each}
        </select>
      </label>
    </div>
    <div class="ranges">
      {#each ["a", "b"] as key (key)}
        {@const name = key as "a" | "b"}
        <fieldset>
          <legend>구간 {name.toUpperCase()} · {name === "a" ? "비교 기준" : "살펴볼 구간"}</legend>
          <label>시작 (KST)
            <input type="datetime-local" value={kst(periods[name].from)}
              onchange={e => changePeriod(name, "from", e.currentTarget.value)} />
          </label>
          <label>종료 (KST)
            <input type="datetime-local" value={kst(periods[name].to)}
              onchange={e => changePeriod(name, "to", e.currentTarget.value)} />
          </label>
        </fieldset>
      {/each}
    </div>
    <button class="ui-button ui-button-primary" type="button"
      onclick={() => void compare()}>이 조건으로 비교</button>
    {#if formError}<StatusNotice kind="failure" message={formError}/>{/if}
    {#if compareState === "loading"}
      <StatusNotice message="두 기간의 저장 측정과 품질을 조회합니다." />
    {:else if compareState === "failed"}
      <StatusNotice kind="failure" title="구간 비교 조회 실패" message={error}
        actionLabel="같은 조건 재조회" onAction={() => void compare()} />
    {:else if compareState === "unavailable"}
      <StatusNotice kind="uncertain" title="비교 자료가 없습니다"
        message="선택한 설비에 비교 가능한 이력이 없습니다. 조회 실패와 정상 판정이 아닙니다." />
    {:else if compareState === "empty"}
      <StatusNotice title="선택한 구간에 측정이 없습니다"
        message="두 구간에 해당 신호의 저장 측정이 없습니다. 구간과 신호를 바꿔 확인하세요." />
    {:else if result}
      <p class="context">구간 A: {showTime(result.periods.a.from)} ~ {showTime(result.periods.a.to)}
        · 구간 B: {showTime(result.periods.b.from)} ~ {showTime(result.periods.b.to)}</p>
      {#each result.series as row (row.key)}
        <section class="series" aria-label={"측정 출처 " + row.source}>
          <h3>{row.channel} · {row.source}</h3>
          <p class="context">측정 지점 {row.point ?? "미확인"} · 의미 ID {row.interpretation}
            · 단위 {row.unit ?? "미확인"}</p>
          <div class="table-wrap">
            <table>
              <caption>해당 출처·측정점·의미에 한정된 구간 통계 (원본 개별 측정 아님)</caption>
              <thead><tr><th scope="col">항목</th><th scope="col">구간 A</th><th scope="col">구간 B</th></tr></thead>
              <tbody>
                <tr><th scope="row">관측 수</th><td>{row.periods.a.observations}</td><td>{row.periods.b.observations}</td></tr>
                <tr><th scope="row">유효 측정</th><td>{row.periods.a.usable}</td><td>{row.periods.b.usable}</td></tr>
                <tr><th scope="row">중앙값</th><td>{row.periods.a.median ?? "미산출"}</td><td>{row.periods.b.median ?? "미산출"}</td></tr>
                <tr><th scope="row">평균</th><td>{row.periods.a.mean ?? "미산출"}</td><td>{row.periods.b.mean ?? "미산출"}</td></tr>
                <tr><th scope="row">결측</th><td>{row.periods.a.missing ?? "미확인"}</td><td>{row.periods.b.missing ?? "미확인"}</td></tr>
                <tr><th scope="row">품질 문제</th><td>{row.periods.a.nonGood ?? "미확인"}</td><td>{row.periods.b.nonGood ?? "미확인"}</td></tr>
                <tr><th scope="row">충돌</th><td>{row.periods.a.conflict ?? "미확인"}</td><td>{row.periods.b.conflict ?? "미확인"}</td></tr>
              </tbody>
            </table>
          </div>
          {#if row.medianChange !== null}
            <p class="context">중앙값 변화(B − A): <strong>{row.medianChange} {row.unit ?? "(단위 미확인)"}</strong>.
              {#if row.outsidePercent !== null} B의 값 중 A 구간 분위수 범위 밖: {row.outsidePercent.toFixed(1)}%{/if}
            </p>
          {:else}
            <StatusNotice kind="uncertain" message="두 구간을 비교할 대표값이 충분하지 않습니다. 0으로 대체하지 않습니다." />
          {/if}
        </section>
      {/each}
    {/if}
  {/if}
</section>

<style>
  .compare { min-width: 0; }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .controls { margin-block: var(--space-4); }
  label { display: grid; gap: var(--space-2); font-weight: 600; }
  select, input { min-width: 0; width: 100%; padding: var(--space-3); color: var(--color-ink);
    background: var(--color-surface); border: 1px solid var(--color-border);
    border-radius: var(--radius-control); }
  .ranges { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); margin-block: var(--space-4); }
  fieldset { border: 1px solid var(--color-border); border-radius: var(--radius-panel); min-width: 0; display: grid; gap: var(--space-3); }
  legend { font-weight: 700; }
  .series { border-top: 1px solid var(--color-border); padding-top: var(--space-4); margin-top: var(--space-6); }
  h3 { overflow-wrap: anywhere; }
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; margin-block: var(--space-3); }
  caption { text-align: left; font-size: var(--font-small); color: var(--color-ink-muted); }
  th, td { text-align: left; padding: var(--space-2); border-bottom: 1px solid var(--color-border); }
</style>
