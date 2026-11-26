<script lang="ts">
  import type {EvidenceFocus} from "../change-evidence";
  import {readSpectrum, type Acquisition, type Spectrum, type Spans} from "../spectrum";
  import {aroundBand, comparisonBand, relativePower} from "../frequency-view";
  import {measure} from "../chart-axis";
  import FrequencyPlot from "./FrequencyPlot.svelte";

  let {focus, assetId, selected = null, onClear}: {focus: EvidenceFocus; assetId: string; selected?: number | null; onClear?: () => void} = $props();
  const rows = $derived(focus.kind === "history" ? focus.item.related : focus.change.related);
  const condition = $derived(focus.kind === "history" ? focus.condition : null);
  const input = $derived.by((): {source: Acquisition; spans: Spans; channel: string; asset: string} | null => {
    if (focus.kind !== "vibration" || !focus.record.sourceId || !focus.record.bindingId) return null;
    const first = focus.record.first ?? 1, last = focus.record.last ?? focus.change.to;
    return {
      asset: assetId,
      source: {source: focus.record.sourceId, binding: focus.record.bindingId, first, last, count: last - first + 1},
      spans: {a: focus.change.baseline, b: {from: focus.change.from, to: focus.change.to}},
      channel: focus.change.feature.slice(8, focus.change.feature.lastIndexOf(".")),
    };
  });
  let average = $state<Spectrum | null>(null);
  let measurement = $state<Spectrum | null>(null);
  let averageFailed = $state(false);
  let measurementFailed = $state(false);
  $effect(() => {
    const current = input;
    average = null;
    averageFailed = false;
    if (!current) return;
    const request = new AbortController();
    void readSpectrum(current.asset, current.source, current.spans, request.signal)
      .then(result => { if (!request.signal.aborted) average = result; })
      .catch(() => { if (!request.signal.aborted) averageFailed = true; });
    return () => request.abort();
  });
  $effect(() => {
    const current = input, ordinal = selected;
    measurement = null;
    measurementFailed = false;
    if (!current || ordinal === null || ordinal < current.source.first || ordinal > current.source.last) return;
    const request = new AbortController();
    const timer = setTimeout(() => {
      void readSpectrum(current.asset, current.source, {a: current.spans.a, b: {from: ordinal, to: ordinal}}, request.signal)
        .then(result => { if (!request.signal.aborted) measurement = result; })
        .catch(() => { if (!request.signal.aborted) measurementFailed = true; });
    }, 160);
    return () => { clearTimeout(timer); request.abort(); };
  });
  const averageChannel = $derived(average?.channels.find(row => row.id === input?.channel));
  const changedBand = $derived(averageChannel ? comparisonBand(averageChannel) : null);
  const shown = $derived(selected === null ? average : measurement);
  const spectrum = $derived(shown?.channels.find(row => row.id === input?.channel));
  const domain = $derived(shown ? changedBand ? aroundBand(changedBand, shown.samplingRate / 2) : {from: 0, to: shown.samplingRate / 2} : null);
  const series = $derived.by(() => {
    if (!spectrum) return [];
    const reference = Math.max(...spectrum.a, ...spectrum.b);
    return [
      {label: "초기 평균", values: relativePower(spectrum.a, reference)},
      {label: selected === null ? "특이사항 구간 평균" : selected + "번째 측정", values: relativePower(spectrum.b, reference), comparison: true},
    ];
  });
  const label = (row: typeof rows[number]) => row.label;
  // 기록 끝까지 이어지는 진동 변화는 위에서 '지금' 값으로 말한다. 함께 달라진 특징도 같은 때의 값을
  // 보인다. 구간 대표값을 두면 수평이 지금 7.27 g인데 '3.23 g'로 읽혔다.
  const ongoing = $derived(focus.kind === "vibration" && focus.record.last !== null && focus.change.to >= focus.record.last);
  const after = (row: typeof rows[number]) => ongoing && "latest" in row && row.latest !== null ? row.latest : row.current;
</script>
<aside class="context" aria-label="선택한 변화의 관련 관측">
  <h3>{focus.kind === "history" ? "같은 구간의 다른 신호" : "함께 달라진 진동 특징"}</h3>
  {#if condition}<p class="condition">{condition}인 측정끼리 비교</p>{/if}
  {#if rows.length}
    <!-- 한 줄에 이름과 비교 구간 → 변화 구간. 그림은 왼쪽 그래프가 맡는다. -->
    <dl>{#each rows.slice(0, focus.kind==="vibration"?1:3) as row(label(row))}<div class="fact">
      <dt>{row.label}</dt><dd><span>{measure(row.reference,row.unit,3)}</span><i aria-hidden="true">→</i><strong>{measure(after(row),row.unit,3)}</strong></dd>
    </div>{/each}</dl>
  {:else}<p>함께 비교할 신호가 이 기록에 없습니다.</p>{/if}
  {#if focus.kind === "vibration" && input}
    <section class="spectrum-preview" aria-label="선택한 진동의 주파수">
      <header>
        <h3>{selected === null ? "초기와 달라진 주파수" : selected + "번째 측정의 주파수"}</h3>
        {#if selected !== null && onClear}<button type="button" onclick={onClear}>구간 평균 보기</button>{/if}
      </header>
      {#if shown && domain && series.length}
        <FrequencyPlot frequencies={shown.frequencies} {series} {domain} band={changedBand} height={110}
          label={"초기 평균과 " + series[1].label + "의 주파수 비교"}/>
        {#if selected === null && changedBand}
          <p class="band-share">강조 대역의 에너지 비중 <strong>{measure(changedBand.a * 100, "%", 3)} → {measure(changedBand.b * 100, "%", 3)}</strong></p>
        {/if}
        <p class="spectrum-key"><span><i></i>{series[0].label}</span><span><i class="comparison"></i>{series[1].label}</span></p>
      {:else}
        <div class="spectrum-status" role="status" aria-busy={!(selected === null ? averageFailed || !!average : measurementFailed || !!measurement)}>
          {selected === null
            ? averageFailed || average ? "이 구간의 주파수를 표시할 수 없습니다." : "두 구간의 주파수를 비교하고 있습니다."
            : measurementFailed || measurement ? "선택한 측정의 주파수를 표시할 수 없습니다." : "선택한 측정의 주파수를 불러오고 있습니다."}
        </div>
      {/if}
    </section>
  {/if}
</aside>
<style>
  .context { min-width:0; display:grid; align-content:start; gap:8px; }
  h3 { margin:0; font-size:var(--font-small); }
  p { margin:0; color:var(--color-ink-muted); font-size:var(--font-small); }
  .condition { font-size:var(--font-label); }
  dl { display:grid; gap:6px; margin:0; }
  .fact { display:flex; align-items:baseline; justify-content:space-between; gap:8px; }
  dt { font-size:var(--font-small); }
  dd { display:flex; align-items:baseline; gap:6px; margin:0; font-size:var(--font-small); font-variant-numeric:tabular-nums; white-space:nowrap; }
  dd > span,dd > i { color:var(--color-ink-muted); font-style:normal; }
  .spectrum-preview { display:grid; gap:7px; border-top:1px solid var(--color-border); padding-top:10px; --frequency-gutter:28px; }
  .spectrum-preview header { display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap; gap:4px 8px; }
  .spectrum-preview button { border:0; background:none; padding:0; font:inherit; font-size:var(--font-label); color:var(--color-action); cursor:pointer; }
  .spectrum-preview button:hover { text-decoration:underline; }
  .band-share { font-size:var(--font-label); }
  .spectrum-key { display:flex; flex-wrap:wrap; gap:4px 10px; font-size:var(--font-label); }
  .spectrum-key span { display:inline-flex; align-items:center; gap:5px; }
  .spectrum-key i { width:12px; border-top:2px solid var(--color-ink-muted); }
  .spectrum-key i.comparison { border-top:2px dashed var(--color-action); }
  .spectrum-status { display:grid; place-items:center; min-height:155px; color:var(--color-ink-muted); font-size:var(--font-label); }
</style>
