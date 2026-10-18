<script lang="ts">
  import {onMount} from "svelte";
  import {steps,currentStep} from "./guide";
  let {search}: {search:string} = $props();
  const index = $derived(currentStep(search));
  const step = $derived(steps[index]);
  let unavailable = $state(false);
  onMount(()=>{
    const notice=()=>unavailable=true;
    const clear=()=>unavailable=false;
    window.addEventListener("showcase-unavailable",notice);
    window.addEventListener("popstate",clear);
    return ()=>{window.removeEventListener("showcase-unavailable",notice);window.removeEventListener("popstate",clear);};
  });
  $effect(()=>{search;unavailable=false;});
</script>

<aside class="guide" aria-label="제품 체험 안내">
  <div class="intro"><div><p class="eyebrow">Industrial PHM · Guided demo</p>
    <h1>측정의 변화에서 검토할 근거까지</h1></div><span class="badge">합성 기록 · 보기 전용 체험</span></div>
  <!-- A prepared link reloads its complete selection, including limits and settings. -->
  <nav aria-label="체험 순서">{#each steps as item,i}<a href={item.href} target="_self" aria-current={i===index?"step":undefined}>{item.label}</a>{/each}</nav>
  <div class="step"><div><h2>{step.title}</h2><p>{step.question}</p></div>
    {#if index<steps.length-1}<a class="ui-button ui-button-primary" href={steps[index+1].href} target="_self">다음: {steps[index+1].label}</a>{:else}<a class="ui-button" href={steps[0].href} target="_self">처음부터 둘러보기</a>{/if}</div>
  {#if unavailable}<p class="unavailable" role="status">이 조건은 체험 스냅샷에 없습니다. 준비된 결과로 돌아가려면 <a href={step.href} target="_self">현재 체험 단계 다시 열기</a>를 누르세요. 다른 조건의 결과로 대신하지 않습니다.</p>{/if}
  <details><summary>이 단계의 근거 · 시연 데이터 안내</summary><p>{step.evidence}</p><p>2026-10-01 00:00~03:59 UTC, 1분 간격 240행씩 만든 두 CSV입니다. 저장된 측정·비교·전망·검토 결과를 둘러볼 수 있습니다. 실제 계측·고장 데이터가 아니며 모델 성능·현장 적합성·AI 품질을 입증하지 않습니다.</p>
    <p><a href="./scenario/manifest.json" target="_blank" rel="noopener">생성 조건과 입력 해시</a> · <a href="./scenario/demo-pump-change.csv" download>변화 기록 CSV</a> · <a href="./scenario/demo-pump-stable.csv" download>일정한 기록 CSV</a></p></details>
</aside>

<style>
  .guide{max-width:1500px;margin:0 auto 1rem;padding:1rem 1.25rem;background:#e8f2f4;border:1px solid #99bdc7;border-radius:1rem;color:#173544;}
  .intro,.step{display:flex;justify-content:space-between;gap:1.5rem;align-items:center;}
  .eyebrow{font-size:.8rem;letter-spacing:.1em;text-transform:uppercase;margin:0;color:#386777;}
  h1{font-size:1.25rem;margin:.1rem 0;}h2{font-size:1rem;margin:0;}p{margin:.2rem 0;}
  nav{display:flex;gap:.5rem;flex-wrap:wrap;margin:.6rem 0;}
  nav a{border-radius:2rem;padding:.4rem .85rem;background:#fff;text-decoration:none;border:1px solid #b4cbd2;}
  nav a[aria-current]{background:#173544;color:#fff;}.badge{font-size:.8rem;white-space:nowrap;}
  .step>.ui-button{flex-shrink:0;}details{font-size:.85rem;color:#365565;margin-top:.5rem;}summary{cursor:pointer;}
  .unavailable{background:#fff8eb;padding:.8rem;}
  @media(max-width:650px){.guide{margin:.75rem;padding:1rem;}.intro,.step{align-items:flex-start;flex-direction:column;gap:.6rem;}h1{font-size:1.3rem;}}
</style>
