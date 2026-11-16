<script lang="ts">
  import OverviewTrace from "./OverviewTrace.svelte";
  import {onMount} from "svelte";
  import {measurementLabel} from "../time-axis";
  import {CHANGE_REASON, changeValue} from "../record-findings";
  import {readVibrationFindings, vibrationLinks, type VibrationChange, type VibrationFindings} from "../vibration-findings";
  import {assetTabUrl} from "../routes";

  /** What the whole acquisition record held: up to three feature changes, by acquisition. */
  let {assetId}: {assetId: string} = $props();
  let found: VibrationFindings | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  onMount(() => {
    const request = new AbortController();
    void readVibrationFindings(assetId, request.signal).then(value => { found = value; loadState = "ready"; })
      .catch(() => { if (!request.signal.aborted) loadState = "failed"; });
    return () => request.abort();
  });
  const place = (at: number) => measurementLabel(at, found?.periodSeconds);
  let expanded:Record<string,boolean>=$state({});

</script>

{#if loadState === "loading"}
  <p class="context">진동 측정 전체를 처음 30%와 비교하고 있습니다.</p>
{:else if loadState === "failed"}
  <p class="context">진동 측정에서 찾은 변화를 불러오지 못했습니다. <a href={assetTabUrl(assetId, "signals", null, "vibration")}>진동 특징 추이 보기 →</a></p>
{:else if found && found.first !== null && found.last !== null}
  {@const record = found}
  <section class="vibration" aria-labelledby="vibration-title">
    <h3 id="vibration-title">진동 주요 변화 <small>{place(record.first!)} ~ {place(record.last!)}</small></h3>
    {#if record.intervals.length}
      <ul class="found">
        {#each record.intervals as change,index (change.feature + change.from)}
          {@const links = vibrationLinks(assetId, change)}
          <li class:secondary={index>0} id={index===0?"primary-change":"vibration-change-"+index}>
            {#if index===0||expanded[change.feature]}
            <h4>{change.label} · {change.kind === "level-change" ? "일정하던 기준보다 " : "기준보다 "}{change.direction === "up" ? "높음" : "낮음"}</h4>
            <strong class="change-values">{#if change.reference !== null && change.typical !== null}{changeValue(change.reference, null)} → {changeValue(change.typical, change.unit)}{:else}가장 {change.direction === "up" ? "높을" : "낮을"} 때 {changeValue(change.value, change.unit)}{/if}</strong>
            <p class="when">{place(change.from)} ~ {place(change.to)} · {change.to - change.from + 1}회{change.reason ? " · " + CHANGE_REASON[change.reason] : ""}</p>
            {#if change.related.length}<p class="when">함께 달라진 특징 · {change.related.map(other => other.label + " " + changeValue(other.reference, null) + " → " + changeValue(other.current, other.unit)).join(" · ")}</p>{/if}
            {#if change.effectDistance != null}<p class="when">대표값 차이 · 기준 구간의 변동 폭 대비 {change.effectDistance.toLocaleString("ko-KR",{maximumSignificantDigits:3})}배</p>{/if}
            <OverviewTrace main={{label:change.label,unit:change.unit,axis:"acquisition",periodSeconds:record.periodSeconds,latest:null,trace:change.trace.map(point=>({x:point.at,value:point.value,join:point.join}))}} range={change} height={220}/>
            <p class="links"><a class="ui-button ui-button-primary" href={links.signal}>변화가 시작된 측정 보기 →</a>
              <a href={links.compare}>처음 30%와 비교 →</a></p>
            <p class="context small">비교 기준 · 처음 30% · {place(change.baseline.from)} ~ {place(change.baseline.to)}</p>
            {:else}<div class="additional"><button type="button" onclick={()=>expanded={...expanded,[change.feature]:true}}><strong>{change.label}</strong> · {change.reference!=null&&change.typical!=null?changeValue(change.reference,null)+" → "+changeValue(change.typical,change.unit):changeValue(change.value,change.unit)}</button><a href={links.signal}>구간 조사 →</a></div>{/if}
          </li>
        {/each}
      </ul>
    {:else if record.judged}
      <p class="context">진동 특징 {record.judged}개에서 처음 30%와 견줘 크게 달라진 구간을 찾지 못했습니다. <a href={assetTabUrl(assetId, "signals", null, "vibration")}>진동 특징 추이 보기 →</a></p>
    {/if}
  </section>
{/if}

<style>
  .vibration { display: grid; gap: var(--space-2); margin-bottom: var(--space-3); }
  h3 { margin: 0; font-size: var(--font-body); }
  h3 small { font-weight: 400; color: var(--color-ink-muted); font-size: var(--font-small); }
  .found { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
  .found > li { display: grid; gap: var(--space-1); padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-control); overflow-wrap: anywhere; }
  h4 { margin: 0; font-size: var(--font-body); font-weight: 650; }
  .change-values { font-size: clamp(1.25rem, 3vw, 1.65rem); line-height: 1.4; }
  .when, .context { margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); }
  .found>li.secondary{padding:var(--space-3) var(--space-4);background:transparent}.additional{display:flex;justify-content:space-between;gap:var(--space-3);align-items:center;flex-wrap:wrap}.additional button{border:0;background:none;padding:0;text-align:left;font:inherit;color:var(--color-ink)}
  .links { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3); margin: var(--space-2) 0 0; }
  .small { font-size: var(--font-small); }
</style>
