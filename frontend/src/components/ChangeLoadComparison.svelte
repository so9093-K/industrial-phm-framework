<script lang="ts">
  import {withConversation, type LoadComparison} from "../change-investigation";
  import {assetTabUrl,investigationOriginUrl} from "../routes";
  import {focusParams,periodParams} from "../signal-selection";
  import {measure} from "../chart-axis";
  import RangeCompare from "./RangeCompare.svelte";

  let {assetId, result, conversation, origin}: {assetId: string; result: LoadComparison; conversation: string; origin?: string} = $props();
  const periods = ["a","b"] as const;
  const names = {a:"초기",b:"변화 구간"};
  function detail(row:Extract<LoadComparison,{status:"ready"}>):string {
    const url = new URL(assetTabUrl(assetId,"change","compare","history",row.series.channel),location.origin);
    const params = {
      ...periodParams(row.periods,"summary"),
      ...focusParams({source:row.series.source,point:row.series.point,interpretation:row.series.interpretation}),
      compare_level:String(row.level), observation_asset:assetId, observation_snapshot:String(row.snapshot),
    };
    for(const [key,value] of Object.entries(params))url.searchParams.set(key,value);
    if(row.until)url.searchParams.set("record_until",row.until);
    const current = origin ? new URL(origin, location.origin).href : location.href;
    return withConversation(investigationOriginUrl(url.href, current), conversation);
  }
</script>

{#if result.status === "ready"}
  <section class="comparison" aria-label="같은 전류 범위의 전압 비교">
    <header>
      <p>전류 {measure(result.current.low,"A",4)} 이상{result.current.high === null ? "" : ", "+measure(result.current.high,"A",4)+" 미만"}</p>
      <h4>{result.series.channel} 중앙값</h4>
    </header>
    <dl>
      {#each periods as period (period)}
        <div><dt>{names[period]}</dt><dd>{measure(result.series.periods[period].median!,result.series.unit,4)}</dd>
          <dd class="count">{result.series.periods[period].usable.toLocaleString("ko-KR")}회 측정</dd></div>
      {/each}
    </dl>
    <RangeCompare a={result.series.periods.a.quantiles} b={result.series.periods.b.quantiles} histogram={result.series.histogram}
      unit={result.series.unit} label={result.series.channel} {names} compact/>
    <a href={detail(result)}>기간 비교 열기 →</a>
  </section>
{:else}
  <p class="unavailable">{result.status === "failed" ? "전압 비교를 불러오지 못했습니다." : "같은 전류 범위에서 비교할 두 구간의 측정이 부족합니다."}</p>
{/if}

<style>
  .comparison{display:grid;gap:8px;min-width:0;padding:12px;border:1px solid var(--color-border);border-radius:8px;background:var(--color-surface);white-space:normal}
  header,p,h4,dl,dd{margin:0}
  header p,dt,.unavailable{color:var(--color-ink-muted);font-size:var(--font-label)}
  h4{font-size:var(--font-small);font-weight:650}
  dl{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline}
  dl>div+div{border-left:1px solid var(--color-border);padding-left:16px}
  dd{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
  dl>div+div dd,a{color:var(--color-action)}
  dl dd.count{color:var(--color-ink-muted);font-size:var(--font-label);font-weight:400}
  a{justify-self:end;font-size:var(--font-label);font-weight:650}
  .comparison :global(.ranges){margin:2px 0 0}
</style>
