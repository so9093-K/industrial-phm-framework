<script lang="ts">
  import {onMount} from "svelte";
  import {askChange,readChangeDiscussion,type ChangeDiscussion,type ChangeAction} from "../change-investigation";
  import {vibrationLinks,type VibrationChange} from "../vibration-findings";
  import {assetTabUrl} from "../routes";
  import {readPermission} from "../outlook-briefings";
  let {assetId,change,bindingId,onMemo}:{assetId:string;change:VibrationChange;bindingId:string;onMemo:(text:string)=>void}=$props();
  const questions=["이 변화가 일시적인가요, 이어지는 상태인가요?","어떤 주파수 성분이 함께 달라졌나요?"];
  let question=$state(""),records:ChangeDiscussion[]=$state([]),error=$state(""),message=$state("");
  let writable=$state(false),busy=$state(false),loading=$state(true),remaining=240;
  let request:AbortController|null=null,timer:ReturnType<typeof setTimeout>|null=null;
  const latest=$derived(records[0]??null);
  const waiting=$derived(busy||latest?.status==="pending");
  const links=$derived.by(()=>{
    const base=vibrationLinks(assetId,change);
    const url=(href:string,params:Record<string,string|number>)=>{const u=new URL(href,location.origin);for(const [k,v] of Object.entries(params))u.searchParams.set(k,String(v));return u.pathname+u.search;};
    return {
      compare:{label:"같은 기간의 특징 변화 보기",href:base.compare},
      spectrum:{label:"같은 기간의 주파수 변화 보기",href:url(assetTabUrl(assetId,"change","spectrum"),{spectrum_a_from:change.baseline.from,spectrum_a_to:change.baseline.to,spectrum_b_from:change.from,spectrum_b_to:change.to})},
      onset:{label:"변화가 시작된 측정의 원본 보기",href:url(assetTabUrl(assetId,"anomaly","model"),{model_binding:bindingId,model_position:change.from})+"#selected-model-input"},
      model:{label:"변화 시작 측정의 모델 결과 보기",href:url(assetTabUrl(assetId,"anomaly","model"),{model_binding:bindingId,model_position:change.from})},
    } satisfies Record<ChangeAction,{label:string;href:string}>;
  });
  const memo=$derived(latest?.answer ? change.label+" · 기준 "+change.baseline.from+"~"+change.baseline.to+"회, 변화 "+change.from+"~"+change.to+"회\n"+latest.answer.summary : "");
  function cancel(){request?.abort();if(timer!==null)clearTimeout(timer);timer=null;}
  async function refresh(){
    cancel();const pending=new AbortController();request=pending;
    try {
      const read=await readChangeDiscussion(assetId,change.reviewKey!,pending.signal);
      if(pending.signal.aborted)return;records=read;loading=false;error="";
      if(read[0]?.status==="pending"&&remaining-->0)timer=setTimeout(()=>void refresh(),1500);
    }catch(cause){if(!pending.signal.aborted){loading=false;error=cause instanceof Error?cause.message:"조사 조회 실패";}}
  }
  async function ask(text:string){
    if(!writable||waiting||!text.trim())return;
    cancel();const pending=new AbortController();request=pending;busy=true;error="";message="";remaining=240;
    try{
      await askChange(assetId,change.reviewKey!,text.trim(),latest?.status==="complete"?latest.id:null,pending.signal);
      if(pending.signal.aborted)return;question="";busy=false;await refresh();
    }catch(cause){if(!pending.signal.aborted){busy=false;error=cause instanceof Error?cause.message:"질문을 보내지 못했습니다.";}}
  }
  async function copy(){try{await navigator.clipboard.writeText(memo);message="조사 요약을 복사했습니다.";}catch{message="복사하지 못했습니다. 설명 문장을 선택해 복사하세요.";}}
  onMount(()=>{const permission=new AbortController();void readPermission(permission.signal).then(value=>{if(!permission.signal.aborted)writable=value;}).catch(()=>{});void refresh();return()=>{permission.abort();cancel();};});
</script>
<section class="ui-panel investigation" aria-label="선택한 진동 변화 조사">
  <h2>이 변화를 함께 살펴보기</h2>
  <p class="basis">{change.label} · {change.from}~{change.to}회<br/>기준 {change.baseline.from}~{change.baseline.to}회와 비교</p>
  {#if error}<p class="error" role="alert">{error} <button type="button" onclick={()=>void refresh()}>다시 읽기</button></p>{/if}
  {#if waiting}<p role="status">선택한 변화와 같은 기간의 특징·주파수 결과를 함께 살펴보고 있습니다.</p>
  {:else if latest?.status==="complete"&&latest.answer}
    <p class="question">질문 · {latest.question}</p>
    <p class="answer">{latest.answer.summary}</p>
    <p class="by">{latest.answer.source==="model"?"AI가 계산된 분석 결과를 함께 읽은 설명입니다.":"AI 설명을 완성하지 못해 계산된 변화 요약을 표시합니다."}</p>
    <nav aria-label="설명에서 이어서 조사">{#each latest.answer.actions as action(action)}<a href={links[action].href}>{links[action].label} →</a>{/each}</nav>
    <div class="actions"><button type="button" class="ui-button" onclick={()=>onMemo(memo)}>판단·메모로 옮기기</button><button type="button" class="copy" onclick={()=>void copy()}>요약 복사</button></div>
  {:else if latest?.status==="failed"}<p>설명을 만들지 못했습니다. 그래프와 원본 측정은 계속 볼 수 있습니다.</p>{/if}
  {#if !loading}<div class="questions">{#each questions as text(text)}<button type="button" class="suggestion" disabled={!writable||waiting} onclick={()=>void ask(text)}>{text}</button>{/each}</div>{/if}
  <label>{latest?.status==="complete"?"이어서 질문하기":"이 기록에서 궁금한 점"}<textarea rows="2" maxlength="600" bind:value={question} disabled={!writable||waiting} placeholder="이 변화에서 무엇을 더 확인하면 좋을까요?"></textarea></label>
  <button type="button" class="ui-button ui-button-primary" disabled={!writable||waiting||!question.trim()} onclick={()=>void ask(question)}>질문하기</button>
  {#if !writable}<p class="by">보기 전용에서는 저장된 설명만 볼 수 있습니다.</p>{/if}
  {#if message}<p role="status">{message}</p>{/if}
</section>
<style>
  .investigation{display:grid;gap:var(--space-3);padding:var(--space-4) var(--space-5);min-width:0}h2{font-size:var(--font-body);margin:0}p{margin:0;font-size:var(--font-small);overflow-wrap:anywhere}.basis,.by,.question{color:var(--color-ink-muted)}.answer{font-size:var(--font-body);line-height:1.7}.by{font-size:var(--font-label)}nav,.questions{display:grid;gap:var(--space-2)}nav a{font-size:var(--font-small);font-weight:650}.suggestion{text-align:left;font:inherit;font-size:var(--font-small);padding:var(--space-2);border:1px solid var(--color-control-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-action);cursor:pointer}.suggestion:disabled{cursor:default;opacity:.6}label{display:grid;gap:var(--space-2);font-size:var(--font-small)}textarea{width:100%;min-width:0;border:1px solid var(--color-control-border);border-radius:var(--radius-control);padding:var(--space-2);font:inherit;background:var(--color-surface);color:var(--color-ink)}.ui-button-primary{justify-self:start}.actions{display:flex;flex-wrap:wrap;gap:var(--space-2)}.copy{font:inherit;font-size:var(--font-small);color:var(--color-action);border:0;background:none;cursor:pointer}.error{color:var(--color-failure-ink)}
</style>
