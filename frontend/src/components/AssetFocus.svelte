<script lang="ts">
  import type {Asset} from "../monitor";
  import {flowLabel} from "../monitor";
  import {bandName, changeValue, focusChange, findingLinks, findingSpan} from "../record-findings";
  import {changeSentence,changeHeadline} from "../change-story";
  import ChangeNumbers from "./ChangeNumbers.svelte";
  import RecordStrip from "./RecordStrip.svelte";
  import type {OverviewRow} from "../asset-overview";
  import type {Note} from "../monitor-attention";
  import {assetTabUrl} from "../routes";
  import ChangeInterval from "./ChangeInterval.svelte";
  import OverviewTrace from "./OverviewTrace.svelte";
  import {vibrationLinks} from "../vibration-findings";
  import {measurementLabel} from "../time-axis";
  import LatestMeasurement from "./LatestMeasurement.svelte";

  let {asset, name, read, observed, href, note, countText, onRetry, reasonHref, onReasons}: {
    asset: Asset; name: string; read: OverviewRow | "loading" | "failed" | undefined;
    observed: (at: string | null) => string; href: string; note?: Note; countText: string;
    onRetry: () => void; reasonHref: string | null; onReasons: () => void;
  } = $props();
  const row = $derived(typeof read === "object" ? read : null);
  const interval = $derived(row?.historyInterval ?? null);
  const chartInterval=$derived(interval?focusChange(interval):null);
  const vibration = $derived(row?.vibrationInterval ?? null);
  const vibrationTrace = $derived(vibration ? {
    label:vibration.change.label, unit:vibration.change.unit, axis:"acquisition" as const,
    periodSeconds:vibration.periodSeconds, latest:null,
    trace:vibration.change.trace.map(point=>({x:point.at,value:point.value,join:point.join})),
  } : null);
  const condition=$derived(interval?.band!=null && row?.operation && interval.operation?.key===row.operation.key ? bandName(row.operation.names,interval.band) : null);
  const date=$derived(asset.lastObservedAt ? new Date(asset.lastObservedAt).toLocaleDateString("ko-KR",{timeZone:"Asia/Seoul",year:"numeric",month:"numeric",day:"numeric"}) : null);
  const links = $derived(vibration ? vibrationLinks(asset.assetId,vibration.change) : interval ? findingLinks(asset.assetId, interval, interval.baseline, interval.bucketSeconds ?? null, interval.context?.record) : null);
  const signals = $derived(assetTabUrl(asset.assetId, "signals"));
  // 설비 요약과 같은 문장으로 말한다: 무엇이, 언제부터 얼마 동안, 무엇과 견줘 어땠는지.
  const story = $derived.by((): string | null => {
    if (interval) return changeSentence(interval, findingSpan(interval),
      interval.band != null && row?.operation && interval.operation?.key === row.operation.key ? bandName(row.operation.names, interval.band) : null);
    if (vibration) {
      const change = vibration.change, place = (at: number) => measurementLabel(at, vibration.periodSeconds);
      return changeSentence(change, place(change.from) + "부터 " + place(change.to) + "까지 " + (change.to - change.from + 1) + "회 동안");
    }
    return null;
  });
</script>

<article class="focus" aria-label={name + " 기록 요약"}>
  <header class="identity">
    <h3><a {href}>{name}</a></h3>
    <p><span class="record-kind">{asset.flow === "stored-history" ? "과거 저장 기록" : flowLabel(asset.flow)}</span>
      <span title={asset.lastObservedAt?observed(asset.lastObservedAt):undefined}>{asset.lastObservedAt ? "마지막 측정 " + date : asset.lastPosition != null ? "마지막 " + asset.lastPosition + "번째 측정" : "측정 시각 정보 없음"}</span></p>
  </header>
  {#if row?.finding}<LatestMeasurement main={row.main}/>{/if}
  {#if !row}
    <div class="pending">
      <div role="status"><h4>{read === "failed" ? "주요 변화를 불러오지 못했습니다" : "기록에서 달라진 값을 확인하고 있습니다"}</h4>
        <p>{read === "failed" ? "분석 요약을 읽지 못했습니다. 신호 기록은 직접 열어 볼 수 있습니다." : "기다리는 동안 신호 기록을 먼저 살펴볼 수 있습니다."}</p></div>
      <div class="actions"><a class="ui-button ui-button-primary" href={signals}>신호 기록 보기 →</a>
        {#if read === "failed"}<button type="button" class="ui-button" onclick={onRetry}>변화 다시 확인</button>{/if}
        <a {href}>설비 분석 열기 →</a></div>
    </div>
  {:else if row.finding}
    {@const found = row.finding}
    <div class="finding-layout" class:no-trend={!interval?.trace?.length && !vibrationTrace?.trace.length}>
      <div class="insight">
        <p class="eyebrow">기록에서 찾은 주요 변화</p>
        <h4>{changeHeadline(interval??vibration?.change??{...found,kind:found.kind==="level-change"?"level-change":"departure"})}</h4>
        <p class="change-when">{interval?findingSpan(interval):vibration?measurementLabel(vibration.change.from,vibration.periodSeconds)+"부터 "+measurementLabel(vibration.change.to,vibration.periodSeconds)+"까지":""}</p>
        {#if condition}<p class="change-condition">같은 운전 수준끼리 비교 · {condition}</p>{/if}
        <ChangeNumbers facts={interval ?? vibration?.change ?? {...found, kind: found.kind === "level-change" ? "level-change" : "departure"}}
          fallback={found.direction === "up" ? "높아진 구간 발견" : "낮아진 구간 발견"} />
        <div class="actions">
          {#if links?.signal}<a class="ui-button ui-button-primary" href={links.signal}>변화 구간 조사하기 →</a>
          {:else}<a class="ui-button ui-button-primary" {href}>변화 자세히 보기 →</a>{/if}
          <a {href}>설비 분석 열기 →</a>
        </div>
      </div>
      {#if interval?.trace?.length}<div class="change-trend"><ChangeInterval finding={chartInterval!} height={176} focus/></div>
      {:else if vibrationTrace}<div class="change-trend"><OverviewTrace main={vibrationTrace} range={vibration!.change} height={176}/></div>{/if}
    </div>
  {:else}
    <div class="quiet">
      <h4>{row.judged ? "기록 초반과 비교해 크게 달라진 구간을 찾지 못했습니다" : "아직 표시할 변화 분석 결과가 없습니다"}</h4>
      {#if row.main}<p>{row.main.label}{#if row.main.latest} · 마지막 저장값 <strong>{changeValue(row.main.latest.value, row.main.unit)}</strong>{/if}</p>
        <OverviewTrace main={row.main}/>
      {/if}
      <div class="actions"><a class="ui-button ui-button-primary" href={signals}>신호 기록 보기 →</a><a {href}>설비 분석 열기 →</a></div>
    </div>
  {/if}
  {#if story}<details class="finding-basis"><summary>비교 조건·전체 기록 보기</summary><p>{story}</p>
    {#if interval}<RecordStrip finding={chartInterval!} {condition} height={90}/>{/if}
    {#if row?.copied}<p class="data-issue">신호 {row.copied}개는 변화 비교에서 제외했습니다. <a {href}>해당 기록 확인 →</a></p>{/if}
  </details>{/if}
  {#if row?.copied && !story}<p class="data-issue">데이터 확인 필요 · 신호 {row.copied}개는 변화 판단에서 제외했습니다. <a {href}>해당 기록 확인 →</a></p>{/if}
  {#if note && (!row?.finding || note.kind !== "departure")}<p class="additional"><strong>{note.label}</strong> · <a href={note.href}>{note.action} →</a></p>{/if}
  <details class="checks"><summary>추가 확인 항목 · {countText}</summary>
    {#if note}<p>{note.label} · {note.detail}</p>{/if}
    {#if reasonHref}<a href={reasonHref} onclick={onReasons}>확인 항목 모두 보기 →</a>{:else}<a {href}>설비에서 확인하기 →</a>{/if}
  </details>
</article>

<style>
  .focus{min-width:0}.identity{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:var(--space-2) var(--space-6);margin-block:var(--space-4)}
  h3{font-size:1.4rem;margin:0}h3 a{color:var(--color-ink);text-decoration:none}h3 a:hover{text-decoration:underline}.identity p{display:flex;flex-wrap:wrap;gap:var(--space-2);font-size:var(--font-small);color:var(--color-ink-muted);margin:0}
  .record-kind{padding:2px var(--space-2);border-radius:var(--radius-control);background:var(--color-surface-selected);font-weight:650}
  .finding-layout{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:var(--space-8);align-items:start;min-height:200px;padding-block:var(--space-4);border-top:1px solid var(--color-border)}
  .finding-layout.no-trend{grid-template-columns:minmax(0,1fr)}
  .insight,.pending,.quiet{min-width:0}.eyebrow{font-size:var(--font-small);color:var(--color-ink-muted);margin:0 0 var(--space-2)}h4{font-size:1.4rem;line-height:1.35;margin:0 0 var(--space-3);overflow-wrap:anywhere}
  p{overflow-wrap:anywhere}
  .actions{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-3) var(--space-5);margin-top:var(--space-5)}.actions a{font-weight:650}
  .pending,.quiet{min-height:240px;padding-block:var(--space-6);border-top:1px solid var(--color-border)}.pending{display:flex;flex-direction:column;justify-content:center}.pending p{color:var(--color-ink-muted)}
  .change-trend{min-width:0;display:grid;gap:var(--space-3)}
  .change-when,.change-condition{font-size:var(--font-small);color:var(--color-ink-muted);margin:var(--space-2) 0}.finding-basis{font-size:var(--font-small);color:var(--color-ink-muted);margin-top:var(--space-2)}.finding-basis summary{cursor:pointer;padding-block:var(--space-2)}.finding-basis p{margin-block:var(--space-2)}
  .data-issue{color:var(--color-caution-ink);font-size:var(--font-small)}.additional{margin-top:var(--space-4);padding-top:var(--space-3);border-top:1px solid var(--color-border)}
  .checks{margin-top:var(--space-4);font-size:var(--font-small);color:var(--color-ink-muted)}.checks summary{cursor:pointer;padding-block:var(--space-2)}.checks p{margin-block:var(--space-2)}
  @media(max-width:800px){.finding-layout{grid-template-columns:1fr;gap:var(--space-3)}.identity{align-items:start}.identity p{display:grid}.pending,.quiet{min-height:220px}}
</style>
