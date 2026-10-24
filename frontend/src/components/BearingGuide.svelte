<script lang="ts">
  import {bearingSteps, bearingStep, type DemoJourney} from "../demo-journey";
  let {journey, search, writable=false, returnTo=null}: {journey: DemoJourney; search: string; writable?: boolean;
    returnTo?: string | null} = $props();
  const steps = $derived(bearingSteps(journey));
  const index = $derived(bearingStep(search));
  const step = $derived(index < 0 ? null : steps[index]);
  const selectedAsset = $derived(new URLSearchParams(search).get("monitor_asset"));
  let navigation: HTMLElement | null = $state(null);
  $effect(() => {index; const active = navigation?.querySelector<HTMLElement>('[aria-current="step"]');
    if (navigation && active) navigation.scrollTo({left: Math.max(0, active.offsetLeft - navigation.offsetLeft), behavior: "instant"});});
  function carry(event: MouseEvent) {
    const link=event.currentTarget as HTMLAnchorElement;
    link.href=bearingSteps(journey,location.search)[Number(link.dataset.step)].href;
  }
</script>

<!-- One box carries the example notice and the guide, so a phone reaches the analysis sooner. -->
<aside class="journey" aria-label="베어링 분석 체험 안내">
  <div class="heading"><p class="title">베어링 진동의 변화 조사</p>
    <p class="notice">{journey.dataset === "synthetic" ? "합성 진동 · 실제 모델 계산" : "XJTU-SY 실기록 · 두 모델"} · 별도 작업공간 ·
      {writable ? "변경 내용은 예시에만 저장" : "보기 전용"}{#if returnTo}{" · "}<a href={returnTo}>내 작업공간으로 돌아가기</a>{/if}</p></div>
  <nav aria-label="분석 체험 순서" bind:this={navigation}>
    {#each steps as item, i}<a href={item.href} data-step={i} onclick={carry} onauxclick={carry} oncontextmenu={carry} target="_self" aria-current={index === i ? "step" : undefined}>{item.label}</a>{/each}
  </nav>
  {#if step}
    <div class="current"><div><h2>{step.title}</h2><p>{index===6&&!writable ? "현재 화면은 보기 전용입니다. 저장된 검토를 확인할 수 있으며, 새 판단은 변경 가능한 운영 화면에서 남깁니다." : step.question}</p></div>
      {#if index < steps.length - 1}<a class="ui-button ui-button-primary" href={steps[index + 1].href} data-step={index+1} onclick={carry} onauxclick={carry} oncontextmenu={carry} target="_self">다음: {steps[index + 1].label}</a>
      {:else}<a class="ui-button" href={steps[0].href} target="_self">기록부터 다시 보기</a>{/if}</div>
    {#if selectedAsset && selectedAsset !== journey.assetId}
      <p class="context">다른 설비를 보고 있습니다. <a href={step.href} target="_self">조사 대상 기록으로 돌아가기</a></p>
    {/if}
  {:else}
    <p class="context">조사 단계 밖의 화면입니다. 위의 단계를 눌러 {journey.assetId} 조사로 돌아갈 수 있습니다.</p>
  {/if}
  <details><summary>데이터와 모델은 어떻게 준비했나요?</summary>
    {#if journey.dataset === "xjtu-sy"}<p>데이터셋: XJTU-SY · 조사 대상: {journey.assetId} · 학습에 사용하지 않은 베어링의 과거 실측 기록.</p>{/if}
    <p>{journey.first}~{journey.last}번째 측정 · 수평·수직 진동 2채널 · 기록 간격 1분 · Isolation Forest·LSTM 오토인코더.</p>
    {#if step}<p>{step.evidence}</p>{/if}
    <p>{journey.dataset === "synthetic" ? "직접 생성한 합성 기록과 별도 합성 참조로 학습한 체험용 모델입니다. 실제 설비의 고장이나 현장 모델 성능을 검증한 결과가 아닙니다." : "실기록의 재생이며, 모델 점수만으로 실제 고장 시각이나 원인을 확정할 수 없습니다."}</p>
    <p>선택 범위와 특징을 바꿔 기존 분석 화면에서 다시 계산할 수 있습니다. 상태 전망과 AI 해설은 추가 탐색 기능입니다.</p>
  </details>
</aside>

<style>
  .journey{display:grid;gap:var(--space-3);margin-bottom:var(--space-4);padding:var(--space-4);background:#e8f2f4;border:1px solid #99bdc7;border-radius:var(--radius-panel);color:var(--color-ink);min-width:0}
  .heading{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--space-1) var(--space-3)}
  .current{display:flex;align-items:center;justify-content:space-between;gap:var(--space-4)}
  .title{font-size:1.2rem;font-weight:750}p,h2{margin:0}h2{font-size:1rem;margin-bottom:var(--space-1)}
  .notice,details,.context{font-size:var(--font-small);color:var(--color-ink-muted)}
  nav{display:flex;gap:var(--space-2);overflow-x:auto;padding-bottom:var(--space-1);max-width:100%}nav a{flex:none;padding:var(--space-2) var(--space-3);background:var(--color-surface);border:1px solid #b4cbd2;border-radius:2rem;text-decoration:none}nav a[aria-current]{background:#173544;color:white}
  .current>a{flex-shrink:0}summary{cursor:pointer}details p{margin-top:var(--space-2);overflow-wrap:anywhere}
  @media(max-width:650px){.current{align-items:flex-start;flex-direction:column;gap:var(--space-2)}.journey{padding:var(--space-3)}.title{font-size:1.05rem}}
</style>
