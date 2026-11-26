<script lang="ts">
  import {onDestroy,tick,untrack} from "svelte";
  import type {AnalysisReadout} from "../analysis-readout.svelte";
  import {askChange,newChangeConversation,readChangeDiscussion,withConversation,STARTERS,LOAD_QUESTION,type ChangeDiscussion,type Pointed} from "../change-investigation";
  import {spanText} from "../date-format";
  import {answerParts,freshLink} from "../answer-text";
  import {changeAnalyses, changeFollowup, type EvidenceFocus} from "../change-evidence";
  import {investigationOriginUrl} from "../routes";
  import type {PlaybackScope} from "../record-playback";
  import {readPermission} from "../outlook-briefings";
  import {OutcomeUnknown} from "../writes";
  import ChangeLoadComparison from "./ChangeLoadComparison.svelte";
  /** 조사 화면 오른쪽의 AI 조사 창. 고른 변화 하나를 두고 대화하고, AI는 화면에 보이는 데이터를 읽고 사람에게 말하듯 답한다.
   * 지난 질문과 답이 위로 쌓이고(이 부분만 스크롤), 입력창은 아래에 고정한다. colorOf·labelOf는
   * 머리줄에 이 특이사항을 그래프와 같은 색·이름으로 보이는 데 쓴다.
   * 질문을 시작하면 재생을 멈춘다(onStart). */
  let {assetId,focus,scope,onMemo,onStart,onClose,colorOf=()=>null,labelOf=()=>null,pointed=null,onUnpoint,carried=null,view=null,viewTitle=null,readout=null}:{assetId:string;focus:EvidenceFocus;scope:PlaybackScope|null;onMemo?:(text:string)=>void;
    onStart?:()=>void;onClose?:()=>void;colorOf?:(reviewKey:string)=>string|null;labelOf?:(reviewKey:string)=>string|null;
    /** 그래프에서 짚은 측정·시각: 질문과 함께 보낸다. */
    pointed?:Pointed|null;onUnpoint?:()=>void;
    /** 분석 화면으로 이어 온 대화(주소의 chat)와, 지금 물은 분석 화면(compare·spectrum…). */
    carried?:string|null;view?:string|null;viewTitle?:string|null;readout?:AnalysisReadout|null}=$props();
  const change=$derived(focus.kind==="vibration"?focus.change:focus.item);
  const label=$derived(change.label);
  const span=$derived(focus.kind==="vibration"?focus.change.from+"–"+focus.change.to+"번째 측정":spanText(Date.parse(focus.item.start),Date.parse(focus.item.end)));
  const incoming=untrack(()=>carried);
  const conversation=incoming??newChangeConversation();
  let restoring=$state(incoming!==null);
  const ready=$derived(!restoring&&(!view||readout!==null));
  const reviewKey=$derived(change.reviewKey!);
  const followup=$derived(changeFollowup(assetId,focus,scope!==null));
  // AI가 답과 함께 여는 분석 화면(분석 이름 → 이 변화의 신호·기간으로 연 링크).
  const analyses=$derived(changeAnalyses(assetId,focus));
  const compareLoad=$derived(focus.kind==="history"&&focus.item.unit==="V"&&focus.item.band!=null);
  let question=$state(""),records:ChangeDiscussion[]=$state([]),error=$state("");
  onDestroy(()=>{cancel();write?.abort();clearInterval(clock);});
  let questionRevision=0;
  let writable=$state(false),busy=$state(false),remaining=240;
  let awaitingQuestion:string|null=$state(null);
  let previousIds=new Set<string>();
  let request:AbortController|null=null,write:AbortController|null=null,timer:ReturnType<typeof setTimeout>|null=null;
  const latest=$derived(records[0]??null);
  const waiting=$derived(busy||awaitingQuestion!==null||latest?.status==="pending");
  // 대화는 오래된 것부터. 접수 확인 전의 질문도 보낸 말풍선으로 바로 보인다.
  const thread=$derived([...records].reverse());
  // 화면 결과가 준비되기 전(이어 온 대화를 읽거나 분석을 그리는 중)에 보낸 질문은 들고 있다가 준비되면 보낸다.
  // 전에는 그동안 누른 Enter가 아무 일도 하지 않아, 질문이 입력칸에 남은 채 묻혔다.
  let held:string|null=$state(null);
  const unsent=$derived(held??(awaitingQuestion!==null&&!records.some(row=>row.question===awaitingQuestion&&!previousIds.has(row.id))?awaitingQuestion:null));
  // 기다린 시간: 첫 답은 모델이 쉬고 있었다면 1분 가까이 걸린다. 멈춘 것과 구분되게 초를 센다.
  let since:number|null=$state(null),now=$state(Date.now());
  const clock=setInterval(()=>{if(waiting)now=Date.now();},1000);
  $effect(()=>{if(waiting&&since===null)untrack(()=>{since=Date.now();now=since;});if(!waiting)since=null;});
  const elapsed=$derived(since!==null?Math.max(0,Math.round((now-since)/1000)):null);
  const memoOf=(row:ChangeDiscussion)=>row.answer?label+" · "+span+"\n"+row.answer.summary:"";
  let copied:string|null=$state(null);
  async function copy(row:ChangeDiscussion){
    try{await navigator.clipboard.writeText(row.answer?.summary??"");copied=row.id;setTimeout(()=>{if(copied===row.id)copied=null;},1500);}catch{ /* 복사를 못 해도 답은 그대로 보인다. */ }
  }
  // 새 말풍선이 생기면 마지막 질문을 창 위쪽에 둔다. 답이 길어도 첫 줄부터 읽힌다.
  // 사용자가 위의 답을 읽고 있으면(바닥에서 떨어져 있으면) 그대로 둔다.
  let log:HTMLElement|undefined=$state(),stick=true;
  const atBottom=()=>!log||log.scrollTop+log.clientHeight>=log.scrollHeight-48;
  $effect(()=>{thread.length;unsent;waiting;latest?.status;latest?.comparison?.status;void tick().then(()=>{
    if(!stick||!log)return;
    const last=[...log.querySelectorAll<HTMLElement>(".me")].at(-1);
    log.scrollTop=last?log.scrollTop+last.getBoundingClientRect().top-log.getBoundingClientRect().top-12:log.scrollHeight;
  });});
  function cancel(){request?.abort();if(timer!==null)clearTimeout(timer);timer=null;}
  async function refresh(){
    cancel();const pending=new AbortController();request=pending;
    try {
      const read=await readChangeDiscussion(assetId,reviewKey,conversation,pending.signal,scope);
      if(pending.signal.aborted)return;records=read;restoring=false;
      if(awaitingQuestion&&read.some(row=>row.question===awaitingQuestion&&!previousIds.has(row.id)))awaitingQuestion=null;
      error="";
      if(awaitingQuestion||read[0]?.status==="pending"){
        if(remaining-->0)timer=setTimeout(()=>void refresh(),1500);
        else {awaitingQuestion=null;error="접수·생성 상태를 확인하지 못했습니다. 다시 읽어 확인하세요.";}
      }
    }catch(cause){
      if(pending.signal.aborted)return;
      // 답을 기다리는 중의 읽기 실패는 다시 읽는다(멈추면 끝난 답이 '답 정리 중'으로 남았다).
      if((awaitingQuestion||records[0]?.status==="pending")&&remaining-->0){timer=setTimeout(()=>void refresh(),1500);return;}
      error=cause instanceof Error?cause.message:"답변을 불러오지 못했습니다.";
    }
  }
  async function ask(text:string,runComparison=false){
    if(!writable||waiting||!text.trim())return;
    if(!ready){held=text.trim();if(question.trim()===held)question="";stick=true;return;}
    const revision=questionRevision;const submitted=text.trim();
    onStart?.();stick=true;previousIds=new Set(records.map(row=>row.id));awaitingQuestion=submitted;
    if(question.trim()===submitted)question="";
    cancel();const pending=new AbortController();write=pending;busy=true;error="";remaining=240;
    try{
      await askChange(assetId,reviewKey,conversation,submitted,records.find(row => row.status === "complete" && row.answer)?.id ?? null,pending.signal,scope,runComparison,pointed,view,readout);
      if(pending.signal.aborted)return;
      busy=false;await refresh();
    }catch(cause){if(!pending.signal.aborted){
      if(cause instanceof OutcomeUnknown){busy=false;await refresh();}
      else {awaitingQuestion=null;if(questionRevision===revision&&!question)question=submitted;error=cause instanceof Error?cause.message:"질문을 보내지 못했습니다.";}
    }}
    finally{if(write===pending){write=null;busy=false;}}
  }
  $effect(()=>{if(ready&&held!==null&&!waiting)untrack(()=>{const text=held!;held=null;void ask(text);});});
  // 분석 화면으로 이어 온 대화는 지난 질문과 답부터 보인다.
  if(incoming)void refresh();
  function keydown(event:KeyboardEvent){
    // Enter로 보내고 Shift+Enter는 줄바꿈. 한글을 조합하는 중의 Enter는 글자를 확정할 뿐 보내지 않는다.
    if(event.key!=="Enter"||event.shiftKey||event.isComposing||event.keyCode===229)return;
    event.preventDefault();void ask(question);
  }
  $effect(()=>{
    const permission=new AbortController();
    void readPermission(permission.signal).then(value=>{if(!permission.signal.aborted)writable=value;}).catch(()=>{});
    return()=>{permission.abort();cancel();};
  });
</script>

{#snippet typing(text:string)}
  <p class="typing" role="status"><i></i><i></i><i></i><span>{text}{elapsed!==null&&elapsed>=3?" · "+elapsed+"초":""}</span></p>
{/snippet}

{#snippet waitingBubble(text:string)}
  <div class="ai"><span class="avatar" aria-hidden="true">AI</span><div class="body">{@render typing(text)}</div></div>
{/snippet}

<section class="chat" aria-label="선택한 변화의 AI 조사">
  <header><div>
    {#if viewTitle}<span class="what"><b>AI 조사</b></span><small class="view-title">{viewTitle}</small>
    {:else}<span class="what"><i class="swatch" style:background={colorOf(reviewKey)??"var(--color-ink-muted)"}></i><b>{labelOf(reviewKey)??label}</b> 특이사항</span><small>{span}</small>{/if}
    </div>
    {#if onClose}<button type="button" class="close" aria-label="AI 조사 닫기" onclick={onClose}><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>{/if}</header>

  <div class="log" bind:this={log} onscroll={()=>stick=atBottom()} aria-live="polite">
    {#each thread as row,index(row.id)}
      <p class="me">{row.question}{#if row.pointed}<small>{row.pointed}에서</small>{/if}</p>
      <div class="ai"><span class="avatar" aria-hidden="true">AI</span><div class="body">
        {#if row.status==="complete"&&row.answer}<p class="answer">{#each answerParts(row.answer.summary) as part,at(at)}{#if part.value}<b>{part.text}</b>{:else}{part.text}{/if}{/each}</p>{/if}
        {#if row.comparison}<ChangeLoadComparison {assetId} {conversation} result={row.comparison}/>{/if}
        {#if row.status==="complete"&&row.analysis&&analyses[row.analysis]&&freshLink(thread,index)}
          <a class="followup" href={withConversation(investigationOriginUrl(analyses[row.analysis].href,location.href),conversation)} onclick={onStart}>{analyses[row.analysis].label} →</a>{/if}
        {#if row.status==="complete"&&row.answer}
          <div class="tools">
            {#if onMemo}<button type="button" onclick={()=>onMemo(memoOf(row))}>판단 메모로</button>{/if}
            <button type="button" onclick={()=>void copy(row)}>{copied===row.id?"복사됨":"복사"}</button>
          </div>
        {:else if row.status==="pending"}{@render typing("답 정리 중")}
        {:else}<p class="note">답을 만들지 못했습니다. 다시 물어 주세요.</p>{/if}
      </div></div>
    {/each}
    {#if unsent}<p class="me">{unsent}</p>{@render waitingBubble(held!==null?"화면 결과를 읽는 중":"측정 기록 확인 중")}{/if}
    {#if error}<p class="error" role="alert">{error} {#if restoring || awaitingQuestion || latest?.status === "pending"}<button type="button" onclick={()=>{remaining=240;void refresh();}}>다시 확인</button>{/if}</p>{/if}
  </div>

  <footer>
    {#if !thread.length&&!unsent&&writable&&ready}<div class="follow">{#if compareLoad&&!view}<button type="button" onclick={()=>void ask(LOAD_QUESTION,true)}>{LOAD_QUESTION}</button>{/if}
      {#each view ? ["이 화면에서 무엇이 달라졌나요?"] : STARTERS as text(text)}<button type="button" onclick={()=>void ask(text)}>{text}</button>{/each}</div>
    {:else if !view&&latest?.status==="complete"&&latest.comparison?.status!=="ready"&&!latest.analysis&&followup&&!waiting}
      <a class="followup" href={withConversation(investigationOriginUrl(followup.href,location.href),conversation)} onclick={onStart}>{followup.label} →</a>
    {/if}
    {#if pointed&&writable}<p class="pointed">그래프에서 짚은 곳 · <b>{pointed.label}</b>
      {#if onUnpoint}<button type="button" aria-label="짚은 곳 지우기" onclick={onUnpoint}>×</button>{/if}</p>{/if}
    <div class="composer" class:disabled={!writable}>
      <textarea rows="1" maxlength="600" aria-label="질문" bind:value={question} oninput={()=>questionRevision++} onfocus={()=>onStart?.()} onkeydown={keydown}
        disabled={!writable} placeholder={!writable?"보기 전용":waiting?"답변을 기다리는 동안 다음 질문을 쓸 수 있습니다":restoring?"대화를 불러오는 중":view?"이 화면의 결과에 대해 질문":pointed?"짚은 곳에 대해 질문":"이 특이사항에 대해 질문"}></textarea>
      <button type="button" class="send" aria-label="질문 보내기" disabled={!writable||waiting||!question.trim()} onclick={()=>void ask(question)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5"/></svg></button>
    </div>
  </footer>
</section>

<style>
  .chat{display:grid;grid-template-rows:auto minmax(0,1fr) auto;height:100%;min-height:0;min-width:0;border:1px solid var(--color-border);border-radius:10px;background:var(--color-surface);overflow:hidden}
  header{display:flex;align-items:start;justify-content:space-between;gap:8px;padding:10px 10px 10px 14px;border-bottom:1px solid var(--color-border);background:#f7f9fa}
  header>div{display:grid;gap:2px;min-width:0}
  .close{display:grid;place-items:center;width:28px;height:28px;border:0;border-radius:6px;background:none;color:var(--color-ink-muted);cursor:pointer}
  .close:hover{background:var(--color-surface-selected);color:var(--color-ink)}
  .close svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round}
  .what{display:flex;align-items:center;gap:7px;font-size:var(--font-small)}
  header small{padding-left:19px;font-size:var(--font-label);color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  header .view-title{padding-left:0}
  .log{overflow-y:auto;min-height:0;padding:14px;display:flex;flex-direction:column;gap:12px;overscroll-behavior:contain}
  p{margin:0;font-size:var(--font-small);overflow-wrap:anywhere}
  .note{color:var(--color-ink-muted);font-size:var(--font-label);line-height:1.5}
  .me{align-self:flex-end;max-width:85%;padding:8px 12px;border-radius:14px 14px 4px 14px;background:var(--color-surface-selected);line-height:1.5}
  .ai{display:grid;grid-template-columns:24px minmax(0,1fr);gap:8px;align-items:start}
  .avatar{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--color-action);color:#fff;font-size:10px;font-weight:700;letter-spacing:.02em}
  .body{display:grid;gap:8px;min-width:0;padding-top:2px}
  .answer{line-height:1.7;white-space:pre-wrap;color:var(--color-ink)}
  .answer b{font-weight:700;font-variant-numeric:tabular-nums}
  .typing{display:flex;align-items:center;gap:4px;color:var(--color-ink-muted);font-size:var(--font-label);min-height:24px}
  .typing i{width:5px;height:5px;border-radius:50%;background:var(--color-ink-muted);animation:blink 1.2s infinite ease-in-out}
  .typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s}.typing span{margin-left:6px}
  @keyframes blink{0%,80%,100%{opacity:.25}40%{opacity:1}}
  @media (prefers-reduced-motion:reduce){.typing i{animation:none;opacity:.6}}
  .swatch{flex:none;display:inline-block;width:12px;height:3px;border-radius:2px}
  .tools{display:flex;gap:4px}
  .tools button{border:1px solid var(--color-border);border-radius:6px;background:var(--color-surface);padding:3px 8px;font:inherit;font-size:var(--font-label);color:var(--color-ink-muted);cursor:pointer}
  .tools button:hover{color:var(--color-action);border-color:var(--color-action)}
  .error{color:var(--color-failure-ink);font-size:var(--font-label)}
  .error button{border:0;background:none;padding:0;font:inherit;color:var(--color-action);text-decoration:underline;cursor:pointer}
  footer{display:grid;gap:8px;padding:10px 12px 12px;border-top:1px solid var(--color-border)}
  .follow{display:flex;flex-wrap:wrap;gap:6px}
  .followup{justify-self:start;padding-block:4px;color:var(--color-action);font-size:var(--font-small);font-weight:650}
  .me small{display:block;margin-top:2px;font-size:var(--font-label);color:var(--color-ink-muted)}
  .pointed{display:flex;align-items:center;gap:4px;margin:0;font-size:var(--font-label);color:var(--color-ink-muted)}.pointed b{color:var(--color-ink)}
  .pointed button{border:0;background:none;padding:0 4px;font:inherit;font-size:14px;line-height:1;color:var(--color-ink-muted);cursor:pointer}
  .follow button{font:inherit;font-size:var(--font-label);padding:4px 10px;border:1px solid var(--color-control-border);border-radius:999px;background:var(--color-surface);color:var(--color-action);cursor:pointer}
  .follow button:disabled{cursor:default;opacity:.55}
  .composer{display:grid;grid-template-columns:minmax(0,1fr) 32px;align-items:end;gap:6px;padding:6px 6px 6px 12px;border:1px solid var(--color-control-border);border-radius:12px;background:var(--color-surface)}
  .composer:focus-within{border-color:var(--color-action);box-shadow:0 0 0 3px rgb(37 99 235 / .12)}
  .composer.disabled{background:#f4f6f8}
  textarea{border:0;outline:0;resize:none;padding:5px 0;font:inherit;font-size:var(--font-small);line-height:1.5;background:transparent;color:var(--color-ink);field-sizing:content;min-height:1.5em;max-height:8em;overflow-y:auto}
  .send{display:grid;place-items:center;width:32px;height:32px;border:0;border-radius:50%;background:var(--color-action);cursor:pointer}
  .send svg{width:16px;height:16px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
  .send:disabled{background:var(--color-border);cursor:default}
</style>
