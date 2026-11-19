<script lang="ts">
  import {loadFeatureProfile, loadFeatureSource} from "../acquisition-profile";
  import {readProfile} from "../comparison";
  import {readAcquisition, readSpectrum, type Spans} from "../spectrum";
  import {departurePeriods, findingLinks} from "../record-findings";
  import {vibrationLinks} from "../vibration-findings";
  import {assetTabUrl,tabSelectionUrl} from "../routes";
  import {historyRelated, rangeEvidence, spectrumEvidence, vibrationRelated, type EvidenceFocus} from "../change-evidence";
  /** 고른 변화에서 여는 분석들. 줄마다 그 분석이 이 변화에서 찾은 사실 한 줄과, 같은 구간으로 여는 링크가 있다.
   * 분석은 모니터링 화면 위 서랍으로 열리고, 닫으면 이 화면으로 돌아온다. */
  let {assetId, focus, model = null, compact=false}: {assetId: string; focus: EvidenceFocus; model?: {text: string; href: string | null} | null;compact?:boolean} = $props();

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
      return {range: own.compare ?? own.previous, related: own.relation?.href ?? own.compare, spectrum: null, signal: own.signal, outlook: own.outlook};
    }
    const change = focus.change, period = spans!;
    const related = change.related[0];
    const own = vibrationLinks(assetId, change);
    return {
      range: own.compare,
      related: related ? url(assetTabUrl(assetId, "change", "relation", "vibration"), {acq_relation_x: change.feature,
        acq_relation_y: related.feature, acq_a_from: period.a.from, acq_a_to: period.a.to, acq_b_from: period.b.from, acq_b_to: period.b.to}) : null,
      spectrum: own.spectrum,
      signal: own.signal, outlook: own.outlook,
    };
  });
  const related = $derived(focus.kind === "history" ? historyRelated(focus.item.related) : vibrationRelated(focus.change.related));

  $effect(() => {
    if(compact)return;
    const current = focus, period = spans;
    const request = new AbortController();
    range = "loading";
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
      spectrum = "loading";
      try {
        const acquisition = await readAcquisition(assetId, request.signal);
        if (!acquisition) { spectrum = null; return; }
        const read = await readSpectrum(assetId, acquisition, period!, request.signal);
        spectrum = spectrumEvidence(read.channels.map(channel => ({label: channel.label, ratio: channel.ratio, shares: channel.shares})));
      } catch { if (!request.signal.aborted) spectrum = "failed"; }
    })();
    return () => request.abort();
  });
  const said = (read: Read, none: string) => read === "loading" ? "계산 중" : read === "failed" ? "결과를 읽지 못함" : read ?? none;
  // 이름과 순서는 분석을 열었을 때의 탭과 같다(들어가는 곳과 도착한 곳을 같은 말로 부른다).
  const rows = $derived([
    {name: "실측 신호", fact: focus.kind === "vibration" ? "변화가 시작된 " + focus.change.from + "번째 측정" : "변화 구간의 원본 값", href: links.signal},
    {name: "기간 비교", fact: said(range, "비교 결과 없음"), href: links.range},
    {name: "신호 관계", fact: related ?? "함께 변한 " + (focus.kind === "vibration" ? "특징" : "신호") + " 없음", href: links.related},
    ...(focus.kind === "vibration" ? [{name: "주파수", fact: said(spectrum, "주파수 결과 없음"), href: links.spectrum}] : []),
    ...(model ? [{name: "모델 반응", fact: model.text, href: model.href}] : []),
    {name: "전망·예상 여유", fact: "이 신호의 앞으로의 추세와 과거 자료 검증", href: links.outlook},
  ]);
</script>

<ul class="entries" class:compact aria-label="분석 열기">
  {#each rows as row (row.name)}
    <li>{#if row.href}<a href={row.href} onclick={event=>{event.currentTarget.href=tabSelectionUrl(event.currentTarget.href,location.href);}}>{row.name} →</a>{:else}<span class="off">{row.name}</span>{/if}{#if !compact}<span class="fact">{row.fact}</span>{/if}</li>
  {/each}
</ul>

<style>
  .entries { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 440px), 1fr)); column-gap: var(--space-6); }
  .entries li { display: grid; grid-template-columns: 7.5rem minmax(0, 1fr); gap: var(--space-3); align-items: baseline; padding: var(--space-2) 0; border-bottom: 1px solid var(--color-border); font-size: var(--font-small); }
  .entries a { font-weight: 650; white-space: nowrap; }
  .off { color: var(--color-ink-muted); }
  .fact { color: var(--color-ink); overflow-wrap: anywhere; word-break: keep-all; }
  .entries.compact{display:flex;flex-wrap:wrap;gap:var(--space-2);padding-block:var(--space-2)}
  .compact li{display:block;border:0;padding:0}.compact a{display:block;border:1px solid var(--color-control-border);border-radius:var(--radius-control);padding:6px 10px;font-size:var(--font-small);text-decoration:none;background:var(--color-surface)}
  .compact a:hover{background:var(--color-surface-selected);border-color:var(--color-action)}
</style>
