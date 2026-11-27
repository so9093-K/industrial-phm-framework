<script lang="ts">
  import {dateTime as showTime, kstInput as kst, kstInstant as isoKst} from "../date-format";
  import {exposeAnalysis} from "../analysis-readout.svelte";
  import {observationSnapshot} from "../observation-context";
  import AnalysisControls from "./AnalysisControls.svelte";
  import SourceIdentity from "./SourceIdentity.svelte";
  import ComparisonValues from "./ComparisonValues.svelte";
  import RangeCompare from "./RangeCompare.svelte";
  import {systemUrl} from "../routes";
  import {countShare} from "../analysis-messages";
  import {rangeEvidence} from "../change-evidence";
  import {focusFrom, focusParams} from "../signal-selection";
  import {comparisonDefault, defaultChannel, readSummary} from "../summary-defaults";
  import {onMount} from "svelte";
  import {readSourceNames, sourceLabel} from "../operations-status";
  import {readSignalNames,signalName,type SignalNames} from "../history";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import {ORIGIN_TEXT, periodNames, periodOrigin, type PeriodOrigin} from "../signal-selection";
  import {
    defaultPeriods, readProfile, readSources, validatePeriods, NoHistoryError,
    type CompareOperation, type Periods, type ProfileResult, type ProfileSeries, type SourceHistory,
  } from "../comparison";
  import {bandName, bandRange, percent} from "../record-findings";

  type Props = {assetId: string};
  let {assetId}: Props = $props();
  let sources_: Map<string, string> = $state(new Map());
  $effect(() => { void readSourceNames().then((value) => sources_ = value); });
  let names_: SignalNames = $state(new Map());
  $effect(() => { const asset = assetId; void readSignalNames(asset).then((value) => { if (asset === assetId) names_ = value; }); });
  type State = "loading" | "ready" | "edited" | "empty" | "failed" | "unavailable";
  let sourceState: State = $state("loading");
  let compareState: State = $state("loading");
  let sources: SourceHistory | null = $state(null);
  let focus = $state(focusFrom(new URLSearchParams(location.search)));
  let selected = $state(new URLSearchParams(location.search).get("monitor_channel") ?? "");
  // The operating level to compare within; null compares every value.
  const levelParam = new URLSearchParams(location.search).get("compare_level");
  let level: number | null = $state(levelParam !== null && /^\d+$/.test(levelParam) ? Number(levelParam) : null);
  let operation: CompareOperation | null = $state(null);
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

  // 모니터링에서 같은 변화로 열었으면 중심 화면과 같은 이름을 쓴다. 기간을 직접 고치면 A·B로 돌아간다.
  const names = $derived(periodNames(handedOver));
  /** 한 출처의 두 기간: 기간 A 값의 90% 범위 밖 측정 수, 전류가 낮았던 측정 비율이 크게 다를 때 그 차이.
   * 초기와 견준 배수는 관제·조사 화면의 '지금' 값 하나로만 말한다. 여기서 중앙값의 배수를 더하면 같은 변화에 배수가 둘이 된다. */
  function facts(row: ProfileSeries, unit: string | null) {
    const a = row.periods.a, b = row.periods.b, qa = a.quantiles;
    const condition = level !== null && operation ? bandName(operation.names, level) : null;
    const outside = rangeEvidence({usable: b.usable, outside: row.outsideCount, low: qa?.[0] ?? null, high: qa?.[4] ?? null,
      unit, percent: row.outsidePercent}, names);
    // 측정 수 기준 비율이다. 두 기간에서 10%p 넘게 다르면 값 차이에 운전 여부 차이가 섞였을 수 있다.
    const low = a.lowCurrent !== null && b.lowCurrent !== null && a.usable && b.usable
      && Math.abs(a.lowCurrent / a.usable - b.lowCurrent / b.usable) >= 0.1
      ? "전류 1 A 미만 측정 · " + names.a + " " + countShare(a.lowCurrent, a.usable) + " · " + names.b + " " + countShare(b.lowCurrent, b.usable) : null;
    return {condition, outside, low};
  }

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
    if (level === null) url.searchParams.delete("compare_level"); else url.searchParams.set("compare_level", String(level));
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
      // 기간을 받지 않고 탭으로 열었으면 상태 요약의 대표 변화와 같은 기준(신호·운전 수준·기간)으로 시작한다.
      // 그래야 요약이 '높았습니다'라고 한 변화를 이 화면이 다른 기준으로 '비슷합니다'라고 하지 않는다.
      const asked = new URLSearchParams(location.search);
      let start: ReturnType<typeof comparisonDefault> = null;
      if (!asked.has("compare_a") || !asked.has("compare_b")) {
        const found = await readSummary(assetId, request.signal);
        if (request.signal.aborted) return;
        start = found ? comparisonDefault(found, data.channels) : null;
        if (start && selected && data.channels.includes(selected) && selected !== start.channel) start = null;
      }
      if (start) {
        selected = start.channel; if (!focus) focus = start.focus;
        if (levelParam === null) level = start.level;
        handedOver = "summary";
      } else if (!data.channels.includes(selected)) selected = await defaultChannel(assetId, data.channels, request.signal);
      if (request.signal.aborted) return;
      sourceState = "ready";
      periods = start ? start.periods : loadPeriodUrl(defaultPeriods(data.from, data.to));
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
      const source = operation ?? (focus ? {sourceId: focus.source, pointId: focus.point ?? null} : null);
      const data = await readProfile(assetId, selected, expected, request.signal,
        level === null ? null : {band: level, sourceId: source?.sourceId, pointId: source?.pointId},
        observationSnapshot(new URLSearchParams(location.search),assetId));
      if (request.signal.aborted) return;
      operation = data.operation;
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

  exposeAnalysis(() => {
    if (compareState !== "ready" || !result?.series.length) return null;
    const compared = result;
    return {
      "비교 신호": signalName(names_, compared.channel),
      [names.a]: showTime(compared.periods.a.from) + " ~ " + showTime(compared.periods.a.to) + " KST",
      [names.b]: showTime(compared.periods.b.from) + " ~ " + showTime(compared.periods.b.to) + " KST",
      ...Object.fromEntries(compared.series.slice(0, 2).map((row, index) => {
        const unit = row.unit ?? names_.get(row.channel)?.unit ?? null;
        const {a, b} = row.periods;
        const {condition} = facts(row, unit);
        const source = sourceLabel(sources_, row.source, compared.series.map((series) => series.source));
        const number = (value: number | null) => value === null ? "측정 없음" : num(value) + (unit ? " " + unit : "");
        return [`측정 중앙값 ${index + 1}`, `${source}${row.point ? " · " + row.point : ""} · ${number(a.median)} → ${number(b.median)} (유효 측정 ${a.usable} · ${b.usable}개)${condition ? " · " + condition : ""}`];
      })),
    };
  });
</script>

{#snippet conditions(close:()=>void)}
  {#if sources&&periods}
    <section class="conditions">

    <div class="controls">
      <label for="compare-channel">신호
        <select id="compare-channel" value={selected}
          onchange={e => {if(!formError)close();selectChannel(e.currentTarget.value);}}>
          {#each sources.channels as id (id)}<option value={id}>{signalName(names_,id)}</option>{/each}
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
      onclick={() => {close();void compare();}}>비교하기</button>
    {#if formError}<StatusNotice kind="failure" message={formError}/>{/if}
    {#if operation}{@const shown = operation}
        <label>비교할 값
          <select value={level === null ? "" : String(level)} disabled={!!formError}
            onchange={(event) => { const value = event.currentTarget.value; level = value === "" ? null : Number(value); remember(); void compare(); }}>
            <option value="">모든 운전 상태의 값</option>
            {#each [0, ...shown.names.levels.map((_, index) => index + 1)] as band (band)}<option value={String(band)}>{bandName(shown.names, band)} 중의 값만</option>{/each}
          </select>
        </label>
    {/if}
    </section>
  {/if}
{/snippet}

<section class="ui-panel compare" aria-labelledby="comparison-title">
  <h2 class="visually-hidden" id="comparison-title">두 기간 비교</h2>
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
    <div class="analysis-workspace"><header class="analysis-result-head"><div><h3>{signalName(names_,selected)}</h3><p>{names.a} · {showTime(periods.a.from)} ~ {showTime(periods.a.to)} / {names.b} · {showTime(periods.b.from)} ~ {showTime(periods.b.to)}</p></div><AnalysisControls title="비교 대상·기간"
     >{#snippet children(close)}{#if periods}

    {#if focus}<p class="context">선택한 데이터 출처{focus.point?" · 측정 위치 "+focus.point:""}의 기록을 비교합니다.</p>
      {#if compareState!=="empty"}<button type="button" class="ui-button" disabled={!!formError}
        onclick={()=>{focus=null;remember();close();void compare();}}>다른 출처의 기록 보기</button>{/if}{/if}
    <div class="period-summary" role="group" aria-label="현재 비교 기간">
      <p><strong>{names.a} · {handedOver === "summary" ? "기록 처음 30%" : "비교 기준"}</strong><span>{showTime(periods.a.from)} ~ {showTime(periods.a.to)} (KST)</span></p>
      <p><strong>{names.b}{handedOver === "summary" ? "" : " · 살펴볼 구간"}</strong><span>{showTime(periods.b.from)} ~ {showTime(periods.b.to)} (KST)</span></p>
    </div>

    {#if handedOver && handedOver !== "summary"}
      <p class="handed">{ORIGIN_TEXT[handedOver]}</p>
    {/if}
    {#if beforeRecord > 0}
      <p class="context">{names.a}의 앞 {beforeRecord >= 3600000 ? (beforeRecord / 3600000).toFixed(1) + "시간" : Math.ceil(beforeRecord / 60000) + "분"}은 기록이 시작되기 전이라 측정이 없습니다. 표의 측정 수로 두 기간의 양을 확인하세요.</p>
    {/if}
    {#if operation}{@const shown = operation}
        <p class="context">{level === null ? "운전 상태가 다른 값도 함께 비교합니다. 두 기간의 운전 상태 비율이 다르면 같은 상태의 값끼리 비교해야 합니다."
          : bandName(shown.names, level) + " 중에 측정된 값끼리 비교합니다."}</p>
    {/if}
    {@render conditions(close)}
    {/if}{/snippet}</AnalysisControls></header>
    <div class="analysis-body">
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
      <StatusNotice title={focus?"선택한 출처에 비교할 측정이 없습니다":"고른 기간에 측정이 없습니다"}
        message={focus?"고른 신호와 A/B 기간에 맞는 기록이 없습니다. 다른 출처의 기록을 확인하거나 기간·신호를 바꿔 다시 비교하세요.":"두 기간 모두 이 신호의 저장 측정이 없습니다. 기간이나 신호를 바꿔 다시 비교하세요."} />
      {#if focus}<button type="button" class="ui-button" onclick={()=>{focus=null;remember();void compare();}}>다른 출처의 기록 보기</button>{/if}
    {:else if result}
      {#each result.series as row (row.key)}
        {@const unit = row.unit ?? names_.get(row.channel)?.unit ?? null}
        {@const told = facts(row, unit)}
        <section class="series" aria-label={"데이터 출처 " + row.source}>
          {#if result.series.length > 1}<SourceIdentity id={row.source} name={sources_?.get(row.source)} pointId={row.point} interpretationId={row.interpretation} among={result.series.map(each=>each.source)}/>{/if}
          {#if row.periods.a.median !== null && row.periods.b.median !== null}
            <ComparisonValues caption={told.condition ? told.condition+" 중 측정의 중앙값" : "측정 중앙값"} {names}
              a={num(row.periods.a.median)+(unit?" "+unit:"")} b={num(row.periods.b.median)+(unit?" "+unit:"")}/>
            {#if told.outside}<p class="fact">{told.outside}</p>{/if}
            {#if told.low}<p class="fact">{told.low}</p>{/if}
          {:else}<StatusNotice kind="uncertain" title="두 기간의 차이를 계산할 값이 부족합니다" message="기간별 측정 수와 품질을 확인하세요."/>{/if}
          <RangeCompare a={row.periods.a.quantiles} b={row.periods.b.quantiles} histogram={row.histogram} {unit} label={signalName(names_, row.channel)} names={names} />
          <details class="statistics">
            <summary>기간별 수치와 데이터 품질</summary>
          {#if result.series.length === 1}<SourceIdentity id={row.source} name={sources_?.get(row.source)} pointId={row.point} interpretationId={row.interpretation}/>{/if}
          <div class="table-wrap">
            <table>
              <caption>이 출처·측정 위치의 기간별 통계 (개별 측정값 아님)</caption>
              <thead><tr><th scope="col">항목</th><th scope="col">{names.a}</th><th scope="col">{names.b}</th></tr></thead>
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
            <p class="context">측정 의미 ID {row.interpretation} · ‘90% 범위’는 {names.a} 값의 5~95% 범위입니다. {names.a} 값도 약 10%는 이 범위 밖에 있고, {names.a}가 정상 운전이었다는 뜻은 아닙니다.</p>
          </details>
        </section>
      {/each}
    {/if}
    {#if operation && compareState === "ready"}
      {@const shown = operation}
      <details class="operation-distribution"><summary>두 기간의 운전 수준별 비율</summary>
        <section class="operation" aria-labelledby="compare-operation">
          <h3 id="compare-operation">운전 수준 <small>{shown.label} 기준</small></h3>
        <div class="table"><table>
          <thead><tr><th scope="col">운전 수준</th><th scope="col">전류</th><th scope="col">{names.a}</th><th scope="col">{names.b}</th></tr></thead>
          <tbody>{#each [0, ...shown.names.levels.map((_, index) => index + 1)] as band (band)}
            <tr><th scope="row">{bandName(shown.names, band)}</th><td>{bandRange(shown.names, band)}</td>
              <td>{shown.shares.a ? percent(shown.shares.a[band]) : "측정 없음"}</td><td>{shown.shares.b ? percent(shown.shares.b[band]) : "측정 없음"}</td></tr>
          {/each}</tbody>
        </table></div>
        </section>
      </details>
    {/if}
    </div></div>

  {/if}
</section>

<style>
  .fact{margin:0;line-height:1.6}
  .period-summary{font-size:var(--font-small)}.period-summary p{margin:0}.period-summary span{display:block}
  .compare { min-width: 0; }
  .period-summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,16rem),1fr)); gap:var(--space-3); margin-block:var(--space-3); }
  .period-summary p { display:grid; gap:var(--space-1); margin:0; overflow-wrap:anywhere; }
  .period-summary span { color:var(--color-ink-muted); font-size:var(--font-small); }
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
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; margin-block: var(--space-3); }
  caption { text-align: left; font-size: var(--font-small); color: var(--color-ink-muted); }
  th, td { text-align: left; padding: var(--space-2); border-bottom: 1px solid var(--color-border); }
  .operation { display: grid; gap: var(--space-2); margin: var(--space-3) 0; padding: var(--space-3) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  .operation h3 { margin: 0; font-size: var(--font-body); }
  .operation h3 small { font-weight: 400; color: var(--color-ink-muted); font-size: var(--font-small); }
  .operation .table { overflow-x: auto; }
  .operation table { border-collapse: collapse; font-size: var(--font-small); font-variant-numeric: tabular-nums; }
  .operation th, .operation td { padding: var(--space-1) var(--space-2) var(--space-1) 0; text-align: right; white-space: nowrap; }
  .operation th:first-child, .operation td:nth-child(2) { text-align: left; }
  .operation thead th { color: var(--color-ink-muted); font-weight: 400; }
</style>
