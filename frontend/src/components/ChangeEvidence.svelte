<script lang="ts">
  import {loadFeatureProfile, loadFeatureSource} from "../acquisition-profile";
  import {readProfile} from "../comparison";
  import {readAcquisition, readSpectrum, type Spans} from "../spectrum";
  import {departurePeriods, findingLinks} from "../record-findings";
  import {vibrationLinks} from "../vibration-findings";
  import {assetTabUrl} from "../routes";
  import {historyRelated, rangeEvidence, spectrumEvidence, vibrationRelated, type EvidenceFocus} from "../change-evidence";
  /** 대표 변화가 진짜인지 확인한 사실을 한 줄씩. 숫자는 '자세히'로 여는 화면과 같은 계산에서 온다. */
  let {assetId, focus, model, modelDestination = null, modelState="ready"}: {assetId: string; focus: EvidenceFocus; model: string | null;modelDestination?:string|null;modelState?:"loading"|"ready"|"failed"} = $props();

  type Read = string | null | "loading" | "failed";
  let range: Read = $state("loading");
  let spectrum: Read = $state("loading");
  type Question = "range" | "related" | "spectrum" | "model";
  let selected: Question | null = $state(null);
  const questions = $derived([
    {key:"range" as const,label:"값의 수준이 달라졌나요?",action:"두 기간 비교하기"},
    {key:"related" as const,label:"함께 달라진 신호는?",action:"신호 관계 살펴보기"},
    ...(focus.kind === "vibration" ? [{key:"spectrum" as const,label:"어떤 주파수가 달라졌나요?",action:"주파수 변화 조사하기"}] : []),
    {key:"model" as const,label:"같은 구간의 모델 반응은?",action:"이 구간의 모델 결과 살펴보기"},
  ]);

  const url = (href: string, params: Record<string, string | number>) => {
    const target = new URL(href, location.origin);
    for (const [key, value] of Object.entries(params)) target.searchParams.set(key, String(value));
    return target.pathname + target.search;
  };
  const spans = $derived.by((): Spans | null => focus.kind === "vibration"
    ? {a: {...focus.change.baseline}, b: {from: focus.change.from, to: focus.change.to}} : null);
  const links = $derived.by(() => {
    if (focus.kind === "history") {
      const own = findingLinks(assetId, focus.item, focus.record.baseline, focus.record.bucketSeconds, focus.record.record);
      return {range: own.compare ?? own.previous, related: own.relation?.href ?? own.compare, spectrum: null};
    }
    const change = focus.change, period = spans!;
    const related = change.related[0];
    return {
      range: vibrationLinks(assetId, change).compare,
      related: related ? url(assetTabUrl(assetId, "change", "relation", "vibration"), {acq_relation_x: change.feature,
        acq_relation_y: related.feature, acq_a_from: period.a.from, acq_a_to: period.a.to, acq_b_from: period.b.from, acq_b_to: period.b.to}) : null,
      spectrum: url(assetTabUrl(assetId, "change", "spectrum"), {spectrum_a_from: period.a.from, spectrum_a_to: period.a.to,
        spectrum_b_from: period.b.from, spectrum_b_to: period.b.to}),
    };
  });
  const related = $derived(focus.kind === "history" ? historyRelated(focus.item.related) : vibrationRelated(focus.change.related));

  $effect(() => {
    const current = focus, period = spans;
    const question = selected;
    const request = new AbortController();
    if (question === "range") void (async () => {
      try {
        if (current.kind === "history") {
          const item = current.item, periods = departurePeriods(item, current.record.baseline, current.record.bucketSeconds);
          if (!periods) { range = null; return; }
          const level = item.band != null ? {band: item.band, sourceId: item.context?.sourceId, pointId: item.context?.pointId ?? null} : null;
          const read = await readProfile(assetId, item.channel, periods, request.signal, level);
          // 같은 출처·위치·측정 의미의 기록만 읽는다.
          const own = read.series.find(row => item.context ? row.source === item.context.sourceId
            && (row.point ?? null) === (item.context.pointId ?? null) && row.interpretation === item.context.interpretationId : true);
          range = own ? rangeEvidence({usable: own.periods.b.usable, outside: own.outsideCount, low: own.periods.a.quantiles?.[0] ?? null,
            high: own.periods.a.quantiles?.[4] ?? null, unit: own.unit ?? item.unit, condition: current.condition,
            percent: own.outsidePercent}) : null;
        } else {
          const source = await loadFeatureSource(assetId, request.signal);
          if (!source || source.bindingId !== current.record.bindingId) { range = null; return; }
          const read = await loadFeatureProfile(assetId, source, current.change.feature, period!, request.signal);
          range = rangeEvidence({usable: read.b.usable, outside: read.outsideCount, low: read.a.quantiles?.[0] ?? null,
            high: read.a.quantiles?.[4] ?? null, unit: read.unit ?? current.change.unit, condition: null});
        }
      } catch { if (!request.signal.aborted) range = "failed"; }
    })();
    if (question === "spectrum" && current.kind === "vibration") void (async () => {
      try {
        const acquisition = await readAcquisition(assetId, request.signal);
        if (!acquisition) { spectrum = null; return; }
        const read = await readSpectrum(assetId, acquisition, period!, request.signal);
        spectrum = spectrumEvidence(read.channels.map(channel => ({label: channel.label, ratio: channel.ratio, shares: channel.shares})));
      } catch { if (!request.signal.aborted) spectrum = "failed"; }
    })();
    return () => request.abort();
  });
  const modelHref = $derived(modelDestination ?? (focus.kind === "vibration" && focus.record.bindingId
    ? url(assetTabUrl(assetId, "anomaly", "model"), {model_binding: focus.record.bindingId, model_position: focus.change.from})
    : null));
  const answer = $derived(selected === "range" ? range : selected === "related" ? related : selected === "spectrum" ? spectrum : modelState!=="ready"?modelState:model);
  const href = $derived(selected === "range" ? links.range : selected === "related" ? links.related : selected === "spectrum" ? links.spectrum : modelHref);
</script>

<div class="questions" role="group" aria-label="이 변화에서 더 알아볼 것">
  {#each questions as question (question.key)}
    <button type="button" aria-pressed={selected === question.key} onclick={() => selected = selected === question.key ? null : question.key}>{question.label}</button>
  {/each}
</div>
{#if selected}
  <section class="answer" aria-label={questions.find(row => row.key === selected)?.label}>
    <p role="status">{answer === "loading" ? "선택한 구간을 비교하고 있습니다." : answer === "failed" ? "비교 결과를 불러오지 못했습니다. 분석 화면에서 다시 확인할 수 있습니다."
      : answer ?? (selected === "related" ? "이 구간에서 함께 달라진 신호를 찾지 못했습니다." : selected==="model"?"이 구간을 분석한 모델 결과가 없습니다.":"이 구간의 비교 결과가 아직 없습니다.")}</p>
    {#if href}<a class="ui-button" {href}>{questions.find(row => row.key === selected)?.action} →</a>{/if}
  </section>
{/if}

<style>
  .questions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
  .questions button { font: inherit; font-size: var(--font-small); padding: var(--space-2) var(--space-3); cursor: pointer; border: 1px solid var(--color-control-border); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-action); }
  .questions button[aria-pressed="true"] { background: var(--color-surface-selected); border-color: var(--color-action); font-weight: 650; }
  .answer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3); border-left: 3px solid var(--color-action); background: var(--color-surface-selected); margin-top: var(--space-2); }
  .answer p { flex: 1; min-width: min(100%, 300px); margin: 0; overflow-wrap: anywhere; line-height: 1.6; }
</style>
