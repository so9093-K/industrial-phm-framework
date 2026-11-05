<script lang="ts">
  import RangeCompare from "./RangeCompare.svelte";
  import {assetTabUrl, systemUrl} from "../routes";
  import AnalysisMessage from "./AnalysisMessage.svelte";
  import {historyPeriodMessage, type NextStep} from "../analysis-messages";
  import {comparisonWindows, focusFrom, focusParams, windowParams} from "../signal-selection";
  import { defaultChannel } from "../monitor-attention";
  import {onMount} from "svelte";
  import {readSourceNames, sourceLabel} from "../operations-status";
  import {readSignalNames,signalName,type SignalNames} from "../history";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import {ORIGIN_TEXT, periodOrigin, type PeriodOrigin} from "../signal-selection";
  // What one source's two periods show, first: what changed, how plain it is, where to look next.
  function told(read: ProfileResult, row: ProfileSeries) {
    const a = row.periods.a, b = row.periods.b, qa = a.quantiles;
    const next: NextStep[] = [];
    for (const view of comparisonWindows(read.periods)) {
      const url = new URL(assetTabUrl(assetId, "signals", null, null, row.channel), location.origin);
      for (const [key, value] of Object.entries({...windowParams(view.window, view.pick), ...focusParams({source:row.source, point:row.point, interpretation:row.interpretation})})) url.searchParams.set(key, value);
      next.push({label: view.label, href: url.pathname + url.search});
    }
    const low = a.lowCurrent !== null && b.lowCurrent !== null ? {a: a.lowCurrent, b: b.lowCurrent} : null;
    if (low && electrical) next.push({label: "3상 평균 전류와 상별 값을 부하·불평형에서 보기", href: assetTabUrl(assetId, "change", "electrical")});
    return historyPeriodMessage({
      unit: row.unit ?? names?.get(row.channel)?.unit ?? null,
      a: {usable: a.usable, median: a.median, low: qa?.[0] ?? null, high: qa?.[4] ?? null},
      b: {usable: b.usable, median: b.median},
      outsideCount: row.outsideCount, outsidePercent: row.outsidePercent, medianChangePercent: row.medianChangePercent,
      onset: null, means: {a: a.mean, b: b.mean}, aMiddle: qa ? {low: qa[1], high: qa[3]} : null, lowCurrent: low,
    }, next);
  }
  import {
    defaultPeriods, readProfile, readSources, validatePeriods, NoHistoryError,
    type Periods, type ProfileResult, type ProfileSeries, type SourceHistory,
  } from "../comparison";

  /** electrical: whether R·S·T roles resolve for this asset, so 부하·불평형 can actually run. */
  type Props = {assetId: string; electrical?: boolean};
  let {assetId, electrical = false}: Props = $props();
  let sources_: Map<string, string> = $state(new Map());
  $effect(() => { void readSourceNames().then((value) => sources_ = value); });
  let names: SignalNames = $state(new Map());
  $effect(() => { const asset = assetId; void readSignalNames(asset).then((value) => { if (asset === assetId) names = value; }); });
  type State = "loading" | "ready" | "edited" | "empty" | "failed" | "unavailable";
  let sourceState: State = $state("loading");
  let compareState: State = $state("loading");
  let sources: SourceHistory | null = $state(null);
  let focus = $state(focusFrom(new URLSearchParams(location.search)));
  let selected = $state(new URLSearchParams(location.search).get("monitor_channel") ?? "");
  let periods: Periods | null = $state(null);
  // Periods handed over from a span picked on the signal chart; said on screen until edited.
  let handedOver: PeriodOrigin | null = $state(periodOrigin(location.search));
  const HOUR = 3600000;
  const QUICK: {label: string; length: number}[] = [
    {label: "1시간", length: HOUR}, {label: "24시간", length: 24 * HOUR}, {label: "7일", length: 7 * 24 * HOUR},
  ];
  let result: ProfileResult | null = $state(null);
  let error = $state("");
  // Keep invalid *draft fields* separate from valid periods used by server queries.
  // Fixing one field must not clear an error in another.
  let invalidFields: Record<string, string> = $state({});
  const formError = $derived(Object.values(invalidFields)[0] ?? "");
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
    new Date(Date.parse(iso) + 9 * 3600000).toISOString().slice(0, 19).replace("T", " ");

  function loadPeriodUrl(fallback: Periods): Periods {
    const params = new URLSearchParams(location.search);
    const read = (key: string) => {
      const span = params.get(key)?.split("~");
      return span && span.length === 2 ? {from:span[0],to:span[1]} : null;
    };
    const a = read("compare_a"), b = read("compare_b");
    if (!a || !b) {handedOver = null; return fallback;}
    try {validatePeriods({a,b}); return {a,b};} catch {handedOver = null; return fallback;}
  }
  /** The last stretch of the record (B) against the same length right before it (A). */
  function quick(length: number) {
    if (!sources) return;
    const last = Date.parse(sources.to) + 1000;
    const iso = (ms: number) => new Date(ms).toISOString();
    periods = {a: {from: iso(last - 2 * length), to: iso(last - length)}, b: {from: iso(last - length), to: iso(last)}};
    invalidFields = {}; handedOver = null;
    remember();
    void compare();
  }
  // Offered when the record holds both stretches; a shortfall of up to 2% (a 2-day file ending a
  // minute early) is allowed and said below the periods instead of hiding the choice.
  const fits = (length: number) => !!sources && Date.parse(sources.to) - Date.parse(sources.from) + 1000 >= 1.98 * length;
  const beforeRecord = $derived.by(() => {
    const current: Periods | null = periods, held: SourceHistory | null = sources;
    if (!current || !held) return 0;
    return Math.max(0, Date.parse(held.from) - Date.parse(current.a.from));
  });
  function remember() {
    if (!periods) return;
    const url = new URL(location.href);
    url.searchParams.delete("record_key");
    url.searchParams.set("monitor_range","window");
    url.searchParams.set("monitor_from",periods.b.from);
    url.searchParams.set("monitor_to",periods.b.to);
    url.searchParams.set("monitor_pick",periods.b.from+"~"+periods.b.to);
    url.searchParams.set("monitor_asset", assetId);
    url.searchParams.set("monitor_channel", selected);
    for(const key of ["monitor_source","monitor_point","monitor_interpretation"]) url.searchParams.delete(key);
    if(focus) for(const [key,value] of Object.entries(focusParams(focus))) url.searchParams.set(key,value);
    url.searchParams.set("compare_a", periods.a.from + "~" + periods.a.to);
    url.searchParams.set("compare_b", periods.b.from + "~" + periods.b.to);
    if (!handedOver) url.searchParams.delete("compare_origin");
    history.replaceState(history.state, "", url);
  }
  async function loadSources() {
    sourceAbort?.abort();
    profileAbort?.abort();
    const request = new AbortController(); sourceAbort = request;
    sourceState = "loading"; compareState = "loading"; sources = null; result = null; error = "";
    invalidFields = {};
    try {
      const data = await readSources(assetId, request.signal);
      if (request.signal.aborted) return;
      sources = data;
      if (!data.channels.length) {sourceState = "empty"; return;}
      if (!data.channels.includes(selected)) selected = await defaultChannel(assetId, data.channels, request.signal);
      if (request.signal.aborted) return;
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
    selected = id; if(focus) focus = {...focus, interpretation: undefined};
    remember();
    if (!formError) void compare();
  }
  function changePeriod(which: "a" | "b", edge: "from" | "to", value: string) {
    if (!periods) return;
    // Once the form differs, a previously computed result is no longer evidence
    // for the current selection. Abort even a still-running request.
    profileAbort?.abort();
    result = null;
    compareState = "edited";
    error = "";
    handedOver = null;
    const key = which + "." + edge;
    try {
      const parsed = isoKst(value);
      periods = {...periods, [which]: {...periods[which], [edge]:parsed}};
      const remaining = {...invalidFields};
      delete remaining[key];
      invalidFields = remaining;
      // The URL owns the user's selection, not the last server-calculated result.
      // A reload must recover the selected interval even before recalculation.
      remember();
    } catch (cause: unknown) {
      invalidFields = {
        ...invalidFields,
        [key]: cause instanceof Error ? cause.message : "구간 입력을 확인하세요.",
      };
    }
  }
  async function compare() {
    // A partly entered datetime has no valid server query; never reuse old periods.
    if (formError) return;
    profileAbort?.abort();
    const request = new AbortController(); profileAbort = request;
    compareState = "loading"; result = null; error = "";
    if (!periods) return;
    try {
      validatePeriods(periods);
      const expected: Periods = {a: {...periods.a}, b: {...periods.b}};
      const data = await readProfile(assetId, selected, expected, request.signal);
      if (request.signal.aborted) return;
      result = {...data, series: data.series.filter(row => !focus || (row.source === focus.source && (focus.point === undefined || row.point === focus.point) && (!focus.interpretation || row.interpretation === focus.interpretation)))}; compareState = result.series.length ? "ready" : "empty"; remember();
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
  <h2 id="comparison-title">두 기간 비교</h2>
  <p class="context">고른 신호를 두 기간(A·B)으로 나눠 대표값·결측·품질을 비교합니다. 데이터 출처나 측정 위치가 다르면 따로 보여 줍니다.</p>
  {#if sourceState === "loading"}
    <StatusNotice message="비교할 수 있는 신호를 불러오고 있습니다." />
  {:else if sourceState === "failed"}
    <StatusNotice kind="failure" title="신호 목록을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={() => void loadSources()} />
  {:else if sourceState === "unavailable" || sourceState === "empty"}
    <StatusNotice kind="uncertain" title="비교할 시계열 기록이 없습니다"
      message="이 설비에는 저장된 시계열 기록이 없습니다."
      actionLabel="데이터 연결 확인하기" actionHref={systemUrl("connections")} />
  {:else if sources && periods}
    <details class="conditions" open={compareState !== "ready"}>
      <summary>비교 조건 확인·변경 · {signalName(names, selected)}</summary>
    <div class="controls">
      <label for="compare-channel">신호
        <select id="compare-channel" value={selected}
          onchange={e => selectChannel(e.currentTarget.value)}>
          {#each sources.channels as id (id)}<option value={id}>{signalName(names,id)}</option>{/each}
        </select>
      </label>
    </div>
    {#if QUICK.some((item) => fits(item.length))}
      <div class="quick" role="group" aria-label="빠른 기간 선택">
        <span>마지막 기록까지 · 바로 앞 같은 길이와 비교</span>
        {#each QUICK.filter((item) => fits(item.length)) as item (item.label)}
          <button type="button" class="ui-button" onclick={() => quick(item.length)}>최근 {item.label}</button>
        {/each}
      </div>
    {/if}
    {#if handedOver}
      <p class="handed">{ORIGIN_TEXT[handedOver]}</p>
    {/if}
    {#if beforeRecord > 0}
      <p class="context">기간 A의 앞 {beforeRecord >= 3600000 ? (beforeRecord / 3600000).toFixed(1) + "시간" : Math.ceil(beforeRecord / 60000) + "분"}은 기록이 시작되기 전이라 측정이 없습니다. 표의 측정 수로 두 기간의 양을 확인하세요.</p>
    {/if}
    <div class="ranges">
      {#each ["a", "b"] as key (key)}
        {@const name = key as "a" | "b"}
        <fieldset>
          <legend>기간 {name.toUpperCase()} · {name === "a" ? "비교 기준" : "살펴볼 기간"}</legend>
          <label>시작 (KST)
            <input type="datetime-local" value={kst(periods[name].from)}
              oninput={e => changePeriod(name, "from", e.currentTarget.value)} />
          </label>
          <label>종료 (KST)
            <input type="datetime-local" value={kst(periods[name].to)}
              oninput={e => changePeriod(name, "to", e.currentTarget.value)} />
          </label>
        </fieldset>
      {/each}
    </div>
    <button class="ui-button ui-button-primary" type="button" disabled={!!formError}
      onclick={() => void compare()}>비교하기</button>
    {#if formError}<StatusNotice kind="failure" message={formError}/>{/if}
    </details>
    {#if compareState === "loading"}
      <StatusNotice message="두 기간의 측정값과 품질을 불러오고 있습니다." />
    {:else if compareState === "failed"}
      <StatusNotice kind="failure" title="두 기간 비교를 불러오지 못했습니다" message={error}
        actionLabel="같은 조건으로 다시 불러오기" onAction={() => void compare()} />
    {:else if compareState === "edited"}
      <StatusNotice kind="uncertain" title="비교 조건이 변경되었습니다"
        message="이전 조건의 분석 결과는 숨겼습니다. 새 기간으로 비교하기를 눌러 다시 계산하세요." />
    {:else if compareState === "unavailable"}
      <StatusNotice kind="uncertain" title="비교할 기록이 없습니다"
        message="이 설비에는 비교할 시계열 기록이 없습니다." />
    {:else if compareState === "empty"}
      <StatusNotice title="고른 기간에 측정이 없습니다"
        message="두 기간 모두 이 신호의 저장 측정이 없습니다. 기간이나 신호를 바꿔 보세요." />
    {:else if result}
      {#each result.series as row (row.key)}
        {@const unit = row.unit ?? names?.get(row.channel)?.unit ?? null}
        {@const message = told(result, row)}
        <section class="series" aria-label={"데이터 출처 " + row.source}>
          <h3>{signalName(names, row.channel)}{unit ? " (" + unit + ")" : ""} · 기간 비교 결과</h3>
          <p class="context">데이터 출처 {sourceLabel(sources_, row.source, result.series.map((each) => each.source))}{row.point ? " · 측정 위치 " + row.point : " · 측정 위치 미지정"}</p>
          {#if message}<AnalysisMessage {message}
            basis={"A (기준) " + showTime(result.periods.a.from) + " ~ " + showTime(result.periods.a.to)
              + " / B (비교) " + showTime(result.periods.b.from) + " ~ " + showTime(result.periods.b.to) + " (KST)"}
            boundary="기간 A의 5–95% 범위와 기간 B의 측정값을 비교합니다." />
          {:else}<StatusNotice kind="uncertain" title="두 기간의 차이를 해석할 값이 부족합니다"
            message="한쪽 기간의 유효 측정이 부족해 대표값을 비교할 수 없습니다. 아래에서 기간별 측정 수와 품질을 확인하세요." />{/if}
          {#if row.periods.a.quantiles && row.periods.b.quantiles}<p class="context">값의 퍼짐 · 가운데 50% 범위의 폭
            {num(row.periods.a.quantiles[3]-row.periods.a.quantiles[1])} → {num(row.periods.b.quantiles[3]-row.periods.b.quantiles[1])}{unit?" "+unit:""} (A → B)</p>{/if}
          <RangeCompare a={row.periods.a.quantiles} b={row.periods.b.quantiles} {unit} label={signalName(names, row.channel)} />
          <details class="statistics">
            <summary>기간별 수치와 데이터 품질</summary>
          <p class="context">데이터 출처 {sourceLabel(sources_, row.source, result.series.map((each) => each.source))}{row.point ? " · 측정 위치 " + row.point : ""}{unit ? " · 단위 " + unit : ""}</p>
          {#if row.medianChange !== null}
            <p class="headline">중앙값 변화(B − A) <strong>{num(row.medianChange)}{unit ? " " + unit : ""}</strong>
              {#if row.outsidePercent !== null}<span> · B의 값 중 A의 평소 범위 밖 {row.outsidePercent.toFixed(1)}%</span>{/if}
            </p>
          {/if}
          <div class="table-wrap">
            <table>
              <caption>이 출처·측정 위치의 기간별 통계 (개별 측정값 아님)</caption>
              <thead><tr><th scope="col">항목</th><th scope="col">기간 A</th><th scope="col">기간 B</th></tr></thead>
              <tbody>
                <tr><th scope="row">측정 수</th><td>{row.periods.a.observations}</td><td>{row.periods.b.observations}</td></tr>
                <tr><th scope="row">유효 측정</th><td>{row.periods.a.usable}</td><td>{row.periods.b.usable}</td></tr>
                <tr><th scope="row">중앙값</th><td>{num(row.periods.a.median)}</td><td>{num(row.periods.b.median)}</td></tr>
                <tr><th scope="row">평균</th><td>{num(row.periods.a.mean)}</td><td>{num(row.periods.b.mean)}</td></tr>
                {#if row.periods.a.lowCurrent !== null && row.periods.b.lowCurrent !== null}
                  <tr><th scope="row">전류 1 A 미만인 측정</th><td>{row.periods.a.lowCurrent}</td><td>{row.periods.b.lowCurrent}</td></tr>
                {/if}
                <tr><th scope="row">결측</th><td>{row.periods.a.missing ?? "미확인"}</td><td>{row.periods.b.missing ?? "미확인"}</td></tr>
                <tr><th scope="row">품질 문제</th><td>{row.periods.a.nonGood ?? "미확인"}</td><td>{row.periods.b.nonGood ?? "미확인"}</td></tr>
                <tr><th scope="row">값 충돌</th><td>{row.periods.a.conflict ?? "미확인"}</td><td>{row.periods.b.conflict ?? "미확인"}</td></tr>
              </tbody>
            </table>
          </div>
          </details>
          <details>
            <summary>기술 상세</summary>
            <p class="context">측정 의미 ID {row.interpretation} · ‘평소 범위 밖’은 기간 A의 분위수 범위를 벗어난 B 값의 비율입니다.</p>
          </details>
        </section>
      {/each}
    {/if}
  {/if}
</section>

<style>
  .compare { min-width: 0; }
  .conditions { margin-block: var(--space-4); padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  summary { cursor: pointer; font-weight: 650; padding-block: var(--space-2); overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .controls { margin-block: var(--space-4); }
  label { display: grid; gap: var(--space-2); font-weight: 600; }
  select, input { min-width: 0; width: 100%; padding: var(--space-3); color: var(--color-ink);
    background: var(--color-surface); border: 1px solid var(--color-border);
    border-radius: var(--radius-control); }
  .quick { display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center; }
  .quick span { color: var(--color-ink-muted); font-size: var(--font-small); margin-right: var(--space-2); }
  .handed { margin: var(--space-4) 0 0; padding: var(--space-3); border-left: 4px solid var(--color-focus);
    background: var(--color-surface-selected); overflow-wrap: anywhere; }
  .ranges { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); margin-block: var(--space-4); }
  fieldset { border: 1px solid var(--color-border); border-radius: var(--radius-panel); min-width: 0; display: grid; gap: var(--space-3); }
  legend { font-weight: 700; }
  .series { border-top: 1px solid var(--color-border); padding-top: var(--space-4); margin-top: var(--space-6); }
  h3 { overflow-wrap: anywhere; }
  .headline { font-size: var(--font-section); overflow-wrap: anywhere; }
  .headline span { font-size: var(--font-small); color: var(--color-ink-muted); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; margin-block: var(--space-3); }
  caption { text-align: left; font-size: var(--font-small); color: var(--color-ink-muted); }
  th, td { text-align: left; padding: var(--space-2); border-bottom: 1px solid var(--color-border); }
</style>
