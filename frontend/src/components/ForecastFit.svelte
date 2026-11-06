<script lang="ts">
  import {outsideRecentRange,worseThanPersistence,type ForecastFit} from "../forecast-fit";
  import type {Backtest} from "../forecast-settings";
  import {elapsedText} from "../time-axis";
  import {num} from "../format";
  import {measure} from "../chart-axis";
  let {fit,checks=[],unit,axis="time",showValues=true,requestedCount=null,effectivePeriod=null}:{fit:ForecastFit|null;checks?:Backtest[];unit:string|null;axis?:"time"|"acquisition";showValues?:boolean;requestedCount?:number|null;effectivePeriod?:number|null}=$props();
  const amount=(value:number)=>num(value)+(unit?" "+unit:"");
  const check=$derived(checks[0]);
  const checkedCount=$derived(check?.hiddenSeconds!==undefined&&effectivePeriod!==null&&effectivePeriod>0?check.hiddenSeconds/effectivePeriod:null);
</script>
{#if fit}
<section class="fit" aria-label="예측 시작값과 검증 상태">
  {#if showValues}<dl><div><dt>{axis==="time"?"마지막 구간 평균":"마지막 측정 특징값"}</dt><dd>{amount(fit.observed)}</dd></div>
    <div><dt>모델 예측 시작값</dt><dd>{amount(fit.modeled)}</dd></div>
    <div><dt>시작값 차이</dt><dd>{fit.gap>0?"+":""}{amount(fit.gap)}</dd></div></dl>{/if}

  {#if outsideRecentRange(fit)}<p class="caution">최근 표시 구간의 평균값 범위는 {amount(fit.recentLow!)}~{amount(fit.recentHigh!)}이며, 모델 시작값은 이 범위 밖에 있습니다.</p>{/if}
  {#if worseThanPersistence(check)}
    <p class="caution" role="status"><strong>이 모델의 예측으로 추세 판단을 보류하세요.</strong> 같은 과거 구간에서 모델 평균 오차 {measure(check!.error,unit)}, 마지막 값이 계속된다고 가정한 예측의 오차 {measure(check!.naive,unit)}로 모델의 오차가 더 컸습니다.</p>
  {:else if !check}<p class="caution">과거 검증 결과가 없어 이번 예측의 정확도를 확인하지 못했습니다.</p>{/if}
  {#if fit.bucketSeconds}<p>입력값은 약 {elapsedText(fit.bucketSeconds)} 단위의 평균입니다.{fit.points!==null?" 학습에 사용한 평균값 "+fit.points+"개.":""}</p>{/if}
  {#if axis==="acquisition" && requestedCount!==null && check}
    <p>요청한 예측 범위 {num(requestedCount)}회 · 과거 검증 {check.points}개 측정값{checkedCount!==null?", 약 "+num(checkedCount)+"회 구간":""}.</p>
    {#if checkedCount!==null && Math.abs(checkedCount-requestedCount)>1e-6}<p>과거 검증 범위가 요청한 예측 횟수와 다릅니다. 요청한 {num(requestedCount)}회 앞 예측의 성능을 직접 확인한 결과와 구분해 읽으세요.</p>{/if}
  {:else if check?.hiddenSeconds!==undefined && check?.requestedSeconds!==undefined && Math.abs(check.hiddenSeconds-check.requestedSeconds)>1}
    <p>과거 검증은 {check.points}개 값에 걸친 약 {elapsedText(check.hiddenSeconds)} 구간입니다. 요청한 예측 기간 {elapsedText(check.requestedSeconds)}을 직접 확인한 결과와 구분해 읽으세요.</p>
  {/if}
  <details><summary>학습·검증 조건</summary>
    <p>세로 연결선은 마지막 구간 평균과 모델 시작값의 차이입니다. 최근 구간의 범위는 예측 기간의 두 배 구간에서 비교합니다.</p>
  {#if check?.baselineValue!==undefined}<p>비교에 사용한 단순 예측은 검증을 시작하기 직전의 {amount(check.baselineValue)}을 그대로 유지한 결과입니다.</p>{/if}
  {#if fit.intervalWidth!==null}<p class="small">음영은 모델이 계산한 {Math.round(fit.intervalWidth*100)}% 예측 범위입니다. 실제 적중률은 과거 검증에서 확인합니다.</p>{/if}
  </details>
</section>
{/if}
<style>
  .fit{margin-block:var(--space-4);padding:var(--space-3);border:1px solid var(--color-border);border-radius:var(--radius-control);min-width:0}
  dl{display:flex;flex-wrap:wrap;gap:var(--space-3);margin:0}dl div{flex:1;min-width:110px}dt,.small{font-size:var(--font-small);color:var(--color-ink-muted)}dd{margin:var(--space-1) 0 0;font-weight:650}
  summary{cursor:pointer;color:var(--color-action);font-weight:650;padding-block:var(--space-2);font-size:var(--font-small)}
  p{font-size:var(--font-small);color:var(--color-ink-muted);overflow-wrap:anywhere}.caution{border-left:3px solid var(--color-caution-ink);padding:var(--space-2);background:var(--color-uncertain-surface)}
</style>
