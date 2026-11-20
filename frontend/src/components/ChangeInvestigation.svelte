<script lang="ts">
  import {onDestroy,untrack} from "svelte";
  import {investigationOriginUrl} from "../routes";
  import {questionDraft,keepQuestionDraft} from "../question-drafts";
  import {askChange,readChangeDiscussion,investigationLinks,type ChangeDiscussion} from "../change-investigation";
  import type {EvidenceFocus} from "../change-evidence";
  import {currentPlayback} from "../record-playback";
  import {readPermission} from "../outlook-briefings";
  import {OutcomeUnknown} from "../writes";
  let {assetId,focus,onMemo,active=true}:{assetId:string;focus:EvidenceFocus;onMemo:(text:string)=>void;active?:boolean}=$props();
  const change=$derived(focus.kind==="vibration"?focus.change:focus.item);
  const label=$derived(change.label);
  const electrical=$derived(focus.kind==="history"&&(focus.item.unit==="V"||focus.item.unit==="A"));
  const span=$derived(focus.kind==="vibration"?focus.change.from+"–"+focus.change.to+"번째 측정":new Date(focus.item.start).toLocaleString("ko-KR")+" — "+new Date(focus.item.end).toLocaleString("ko-KR"));
  const questions=$derived(focus.kind==="vibration"?[{label:"진동·주파수 종합",text:"진동 크기와 주파수 변화를 종합해 알 수 있는 것과 더 확인할 것을 설명해 주세요."},{label:"변화 시작·지속",text:"변화가 언제 시작됐고 달라진 수준이 이어졌는지 값이 계속 변했는지 설명해 주세요."}]:[{label:"함께 변한 신호",text:electrical?"선택한 변화와 다른 상전압·전류를 함께 보면 무엇을 알 수 있나요?":"선택한 변화와 같은 구간의 다른 신호를 함께 보면 무엇을 알 수 있나요?"},{label:electrical?"운전 조건과 차이":"변화 시작·지속",text:electrical?"전류 수준을 고려했을 때도 차이가 남는지, 이 결과로 어디까지 설명할 수 있나요?":"변화가 언제 시작됐고 달라진 수준이 이어졌는지 값이 계속 변했는지 설명해 주세요."}]);
  const draftScope=untrack(()=>"change:"+assetId+":"+change.reviewKey);
  const reviewKey=$derived(change.reviewKey!);
  let question=$state(questionDraft(draftScope)),records:ChangeDiscussion[]=$state([]),error=$state("");
  onDestroy(()=>{keepQuestionDraft(draftScope,question);cancel();write?.abort();});
  let questionRevision=0;
  let writable=$state(false),busy=$state(false),loading=$state(true),remaining=240;
  let awaitingQuestion:string|null=$state(null);
  let previousIds=new Set<string>();
  let request:AbortController|null=null,write:AbortController|null=null,timer:ReturnType<typeof setTimeout>|null=null;
  const latest=$derived(records[0]??null);
  const waiting=$derived(busy||awaitingQuestion!==null||latest?.status==="pending");
  const next=$derived(latest?.answer?investigationLinks(assetId,focus,latest.answer.actions):[]);
  const memo=$derived(latest?.answer ? label+" · "+span+"\n"+latest.answer.summary+(latest.answer.next_step?"\n"+latest.answer.next_step:"") : "");
  function cancel(){request?.abort();if(timer!==null)clearTimeout(timer);timer=null;}
  async function refresh(){
    if(!active)return;
    cancel();const pending=new AbortController();request=pending;
    try {
      const read=await readChangeDiscussion(assetId,reviewKey,pending.signal,currentPlayback());
      if(pending.signal.aborted)return;records=read;loading=false;
      if(awaitingQuestion&&read.some(row=>row.question===awaitingQuestion&&!previousIds.has(row.id)))awaitingQuestion=null;
      error=awaitingQuestion?"질문 접수 여부를 다시 확인하고 있습니다.":"";
      if(awaitingQuestion||read[0]?.status==="pending"){
        if(remaining-->0)timer=setTimeout(()=>void refresh(),1500);
        else {awaitingQuestion=null;error="접수·생성 상태를 확인하지 못했습니다. 다시 읽어 확인하세요.";}
      }
    }catch(cause){if(!pending.signal.aborted){loading=false;error=cause instanceof Error?cause.message:"조사 조회 실패";}}
  }
  async function ask(text:string){
    if(!writable||loading||waiting||!text.trim())return;
    const revision=questionRevision;const submitted=text.trim();
    previousIds=new Set(records.map(row=>row.id));awaitingQuestion=submitted;
    cancel();const pending=new AbortController();write=pending;busy=true;error="";remaining=240;
    try{
      await askChange(assetId,reviewKey,submitted,latest?.status==="complete"?latest.id:null,pending.signal,currentPlayback());
      if(pending.signal.aborted)return;
      if(questionRevision===revision&&question.trim()===submitted)question="";
      busy=false;await refresh();
    }catch(cause){if(!pending.signal.aborted){
      if(cause instanceof OutcomeUnknown){busy=false;await refresh();}
      else {awaitingQuestion=null;error=cause instanceof Error?cause.message:"질문을 보내지 못했습니다.";}
    }}
    finally{if(write===pending){write=null;busy=false;}}
  }
  $effect(()=>{
    // Hiding stops reads, but must not cancel a question before the server accepts it.
    if(!active){cancel();return;}
    const permission=new AbortController();
    void readPermission(permission.signal).then(value=>{if(!permission.signal.aborted)writable=value;}).catch(()=>{});
    remaining=240;untrack(()=>void refresh());
    return()=>{permission.abort();cancel();};
  });
</script>
<section class="ui-panel investigation" aria-label="선택한 변화에 AI 질문">
  <p class="question">{label} · {span}</p>
  {#if error}<p class="error" role="alert">{error} <button type="button" onclick={()=>void refresh()}>다시 읽기</button></p>{/if}
  {#if waiting}<p role="status">AI 해설 작성 중 · 선택한 구간의 측정·비교 결과 사용</p>
  {:else if latest?.status==="complete"&&latest.answer}
    <p class="question">질문 · {latest.question}</p>
    <p class="answer">{latest.answer.summary}</p>
    {#if latest.answer.next_step}<p class="next-step">{latest.answer.next_step}</p>{/if}
    <p class="by">{latest.answer.source==="model"?"AI 해석 · 선택한 측정과 분석 결과 사용":"계산 결과 요약 · AI 응답을 사용하지 못했습니다"}</p>
    {#if next.length}<div class="next" aria-label="질문에 이어서 살펴볼 분석">{#each next as item(item.key)}<a class="ui-button" href={item.href} onclick={event=>event.currentTarget.href=investigationOriginUrl(event.currentTarget.href,location.href)}>{item.label} →</a>{/each}</div>{/if}
    <button type="button" class="ui-button memo" onclick={()=>onMemo(memo)}>판단 메모에 넣기</button>
  {:else if latest?.status==="failed"}<p>설명을 만들지 못했습니다. 그래프와 원본 측정은 계속 볼 수 있습니다.</p>{/if}
  {#if !loading}<div class="questions">{#each questions.filter(item=>item.text!==latest?.question) as item(item.label)}<button type="button" class="suggestion" disabled={!writable||waiting} onclick={()=>void ask(item.text)}>{item.label}</button>{/each}</div>{/if}
  <label>{latest?.status==="complete"?"추가 질문":"질문"}<textarea rows="2" maxlength="600" bind:value={question} oninput={()=>questionRevision++} disabled={!writable} placeholder={waiting?"답변을 기다리는 동안 다음 질문을 작성할 수 있습니다.":"이 변화에서 더 알아볼 내용을 입력하세요."}></textarea></label>
  <button type="button" class="ui-button ui-button-primary" disabled={!writable||loading||waiting||!question.trim()} onclick={()=>void ask(question)}>질문하기</button>
  {#if !writable}<p class="by">보기 전용에서는 저장된 설명만 볼 수 있습니다.</p>{/if}
</section>
<style>
  .next{display:flex;flex-wrap:wrap;gap:var(--space-2)}
  .investigation{display:grid;gap:var(--space-3);padding:var(--space-4) var(--space-5);min-width:0}p{margin:0;font-size:var(--font-small);overflow-wrap:anywhere}.by,.question{color:var(--color-ink-muted)}.answer{font-size:var(--font-body);line-height:1.7}.by{font-size:var(--font-label)}.questions{display:flex;flex-wrap:wrap;gap:var(--space-2)}.memo{justify-self:start}.suggestion{text-align:left;font:inherit;font-size:var(--font-small);padding:var(--space-2);border:1px solid var(--color-control-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-action);cursor:pointer}.suggestion:disabled{cursor:default;opacity:.6}label{display:grid;gap:var(--space-2);font-size:var(--font-small)}textarea{width:100%;min-width:0;border:1px solid var(--color-control-border);border-radius:var(--radius-control);padding:var(--space-2);font:inherit;background:var(--color-surface);color:var(--color-ink)}.ui-button-primary{justify-self:start}.error{color:var(--color-failure-ink)}
</style>
