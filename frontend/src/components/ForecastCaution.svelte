<script lang="ts">
  import {measure} from "../chart-axis";
  import {apartFromStart,worseThanPersistence,type ForecastFit} from "../forecast-fit";
  import type {Backtest} from "../forecast-settings";

  /** The forecast's one caution on the outlook screen: what was last measured against where the
   * forecast starts, then how the forecast fared on the past. The measurement comes first. */
  let {fit,start,checks=[],unit,lastLabel,href=null}:{fit:ForecastFit|null;
    start:{estimate:number;lower:number|null;upper:number|null}|undefined;checks?:Backtest[];unit:string|null;
    lastLabel:string;href?:string|null}=$props();
  const worse=$derived(worseThanPersistence(checks[0]));
  // 마지막 측정이 예측 시작 범위보다 멀고, 과거에도 단순 지속보다 오차가 컸을 때만 '따라가지 못한다'고 말한다.
  // 과거에 단순 지속보다 나았던 예측(전압처럼 오르내리는 값)은 마지막 값을 쫓지 않는 것이 맞다.
  const apart=$derived(worse&&fit!==null&&apartFromStart(fit.observed,start));
</script>
{#if apart||worse}
  <p class="forecast-caution" role="status">
    {#if fit && apart}<strong>{lastLabel} {measure(fit.observed,unit)} · 예측 시작 {measure(fit.modeled,unit)}</strong> — 예측이 최근 측정을 따라가지 못합니다.{" "}{/if}
    {#if worse}{apart?"과거 기록에서도 ":""}마지막 값이 그대로 이어진다고 볼 때보다 예측 오차가 컸습니다.{/if}
    {#if href}<a href={href}>최근 측정의 변화 보기 →</a>{/if}
  </p>
{/if}
<style>
  .forecast-caution{padding:var(--space-3);border-inline-start:3px solid var(--color-caution-ink);background:var(--color-uncertain-surface);color:var(--color-caution-ink);line-height:1.6;overflow-wrap:anywhere;margin:0}
</style>
