<script lang="ts">
  import {onMount} from "svelte";
  import {askChange,readChangeDiscussion,type ChangeDiscussion} from "../change-investigation";
  import type {VibrationChange} from "../vibration-findings";
  import {readPermission} from "../outlook-briefings";
  let {assetId,change,onMemo}:{assetId:string;change:VibrationChange;onMemo:(text:string)=>void}=$props();
  const questions=["이 변화는 언제부터 얼마나 이어졌나요?","어떤 주파수 성분이 함께 달라졌나요?"];
  let question=$state(""),records:ChangeDiscussion[]=$state([]),error=$state("");
  let writable=$state(false),busy=$state(false),loading=$state(true),remaining=240;
  let request:AbortController|null=null,timer:ReturnType<typeof setTimeout>|null=null;
  const latest=$derived(records[0]??null);
  const waiting=$derived(busy||latest?.status==="pending");
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
    cancel();const pending=new AbortController();request=pending;busy=true;error="";remaining=240;
    try{
      await askChange(assetId,change.reviewKey!,text.trim(),latest?.status==="complete"?latest.id:null,pending.signal);
      if(pending.signal.aborted)return;question="";busy=false;await refresh();
    }catch(cause){if(!pending.signal.aborted){busy=false;error=cause instanceof Error?cause.message:"질문을 보내지 못했습니다.";}}
  }
  onMount(()=>{const permission=new AbortController();void readPermission(permission.signal).then(value=>{if(!permission.signal.aborted)writable=value;}).catch(()=>{});void refresh();return()=>{permission.abort();cancel();};});
</script>
<section class="ui-panel investigation" aria-label="선택한 진동 변화 조사">
  <h2>AI에게 묻기</h2>
  {#if error}<p class="error" role="alert">{error} <button type="button" onclick={()=>void refresh()}>다시 읽기</button></p>{/if}
  {#if waiting}<p role="status">AI가 같은 기간의 특징·주파수 비교 결과를 읽고 답을 쓰고 있습니다.</p>
  {:else if latest?.status==="complete"&&latest.answer}
    <p class="question">질문 · {latest.question}</p>
    <p class="answer">{latest.answer.summary}</p>
    <p class="by">{latest.answer.source==="model"?"계산된 근거만 읽고 쓴 AI 답입니다.":"AI가 답하지 못해 계산된 요약을 보여 드립니다."}</p>
    <button type="button" class="ui-button memo" onclick={()=>onMemo(memo)}>판단 메모에 넣기</button>
  {:else if latest?.status==="failed"}<p>설명을 만들지 못했습니다. 그래프와 원본 측정은 계속 볼 수 있습니다.</p>{/if}
  {#if !loading}<div class="questions">{#each questions.filter(text=>text!==latest?.question) as text(text)}<button type="button" class="suggestion" disabled={!writable||waiting} onclick={()=>void ask(text)}>{text}</button>{/each}</div>{/if}
  <label>{latest?.status==="complete"?"이어서 묻기":"직접 묻기"}<textarea rows="2" maxlength="600" bind:value={question} disabled={!writable||waiting} placeholder="이 변화에서 무엇을 더 확인하면 좋을까요?"></textarea></label>
  <button type="button" class="ui-button ui-button-primary" disabled={!writable||waiting||!question.trim()} onclick={()=>void ask(question)}>질문하기</button>
  {#if !writable}<p class="by">보기 전용에서는 저장된 설명만 볼 수 있습니다.</p>{/if}
</section>
<style>
  .investigation{display:grid;gap:var(--space-3);padding:var(--space-4) var(--space-5);min-width:0}h2{font-size:var(--font-body);margin:0}p{margin:0;font-size:var(--font-small);overflow-wrap:anywhere}.by,.question{color:var(--color-ink-muted)}.answer{font-size:var(--font-body);line-height:1.7}.by{font-size:var(--font-label)}.questions{display:grid;gap:var(--space-2)}.memo{justify-self:start}.suggestion{text-align:left;font:inherit;font-size:var(--font-small);padding:var(--space-2);border:1px solid var(--color-control-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-action);cursor:pointer}.suggestion:disabled{cursor:default;opacity:.6}label{display:grid;gap:var(--space-2);font-size:var(--font-small)}textarea{width:100%;min-width:0;border:1px solid var(--color-control-border);border-radius:var(--radius-control);padding:var(--space-2);font:inherit;background:var(--color-surface);color:var(--color-ink)}.ui-button-primary{justify-self:start}.error{color:var(--color-failure-ink)}
</style>
