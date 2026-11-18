<script lang="ts">
  import {loadFeatureProfile, loadFeatureSource} from "../acquisition-profile";
  import {readProfile} from "../comparison";
  import {readAcquisition, readSpectrum, type Spans} from "../spectrum";
  import {departurePeriods, findingLinks} from "../record-findings";
  import {vibrationLinks} from "../vibration-findings";
  import {plainLabel} from "../change-story";
  import {assetTabUrl} from "../routes";
  import {rangeEvidence, relatedEvidence, spectrumEvidence, type EvidenceFocus} from "../change-evidence";
  /** 대표 변화가 진짜인지 확인한 사실을 한 줄씩. 숫자는 '자세히'로 여는 화면과 같은 계산에서 온다. */
  let {assetId, focus, model}: {assetId: string; focus: EvidenceFocus; model: string | null} = $props();

  type Read = string | null | "loading" | "failed";
  let range: Read = $state("loading");
  let spectrum: Read = $state("loading");

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
  const related = $derived(focus.kind === "history"
    ? relatedEvidence(focus.item.related.filter(row => row.state !== "within")
      .map(row => ({label: row.label, reference: row.reference, current: row.current, unit: row.unit})))
    : relatedEvidence(focus.change.related.map(row => ({label: plainLabel(row.label, row.feature), reference: row.reference,
      current: row.current, unit: row.unit}))));

  $effect(() => {
    const current = focus, period = spans;
    const request = new AbortController();
    range = "loading"; spectrum = current.kind === "vibration" ? "loading" : null;
    void (async () => {
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
    if (current.kind === "vibration") void (async () => {
      try {
        const acquisition = await readAcquisition(assetId, request.signal);
        if (!acquisition) { spectrum = null; return; }
        const read = await readSpectrum(assetId, acquisition, period!, request.signal);
        spectrum = spectrumEvidence(read.channels.map(channel => ({label: channel.label, ratio: channel.ratio, shares: channel.shares})));
      } catch { if (!request.signal.aborted) spectrum = "failed"; }
    })();
    return () => request.abort();
  });
  const modelHref = $derived(focus.kind === "vibration" && focus.record.bindingId
    ? url(assetTabUrl(assetId, "anomaly", "model"), {model_binding: focus.record.bindingId, model_position: focus.change.from})
    : assetTabUrl(assetId, "anomaly", "model"));
</script>

{#snippet line(label: string, read: Read, waiting: string, missed: string, href: string | null)}
  {#if read !== null}
    <li class:waiting={read === "loading" || read === "failed"}>
      <span><strong>{label}</strong>{read === "loading" ? waiting : read === "failed" ? missed : read}</span>
      {#if href}<a href={href}>자세히 →</a>{/if}
    </li>
  {/if}
{/snippet}

<ul class="evidence" aria-label="변화 근거">
  {@render line("범위", range, "계산 중", "확인 실패", links.range)}
  {@render line(focus.kind === "history" ? "함께 변한 신호" : "함께 변한 특징", related, "", "", links.related)}
  {#if focus.kind === "vibration"}{@render line("주파수", spectrum, "계산 중", "확인 실패", links.spectrum)}{/if}
  {@render line("모델", model, "", "", modelHref)}
</ul>

<style>
  .evidence { list-style: none; margin: 0; padding: 0; display: grid; }
  .evidence li { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-2) var(--space-5);
    padding-block: var(--space-2); border-top: 1px solid var(--color-border); overflow-wrap: anywhere; }
  .evidence li span { min-width: 0; line-height: 1.6; }
  .evidence li strong { display: inline-block; min-width: 7.5em; margin-right: var(--space-3); font-size: var(--font-small); color: var(--color-ink-muted); font-weight: 650; }
  .evidence li a { flex: none; font-size: var(--font-small); font-weight: 650; }
  .waiting span { color: var(--color-ink-muted); }
</style>
