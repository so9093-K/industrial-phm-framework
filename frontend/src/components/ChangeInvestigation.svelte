<script lang="ts">
  import {onDestroy,tick,untrack} from "svelte";
  import {investigationOriginUrl} from "../routes";
  import {questionDraft,keepQuestionDraft} from "../question-drafts";
  import {askChange,readChangeDiscussion,investigationLinks,type ChangeDiscussion,type Evidence,type Step} from "../change-investigation";
  import {measure} from "../chart-axis";
  import {clockText,spanText} from "../asset-timeline";
  import type {EvidenceFocus} from "../change-evidence";
  import {currentPlayback} from "../record-playback";
  import {readPermission} from "../outlook-briefings";
  import {OutcomeUnknown} from "../writes";
  /** 조사 화면 오른쪽의 AI 조사 창. 고른 변화 하나에 묶여 그 변화의 측정·비교 결과로만 답한다.
   * '이 변화 조사'로 시작하고, 답마다 서버가 확인한 항목(항목 · 결과)을 먼저 보인 뒤 답을 잇는다.
   * 지난 질문과 답이 위로 쌓이고(이 부분만 스크롤), 입력창은 아래에 고정한다. 답의 근거나 확인한 항목을 가리키면(point)
   * 왼쪽 그래프가 그 선·구간·운전 수준 띠만 남긴다. together는 같은 시기로 함께 그린 변화 수,
   * colorOf는 근거 변화가 그래프에서 쓰는 색. 질문을 시작하면 재생을 멈춘다(onStart). */
  let {assetId,focus,onMemo,onStart,onClose,together=1,colorOf=()=>null,labelOf=()=>null,point=()=>{},active=true,autostart=false,onAutostart}:{assetId:string;focus:EvidenceFocus;onMemo:(text:string)=>void;
    onStart?:()=>void;onClose?:()=>void;together?:number;colorOf?:(reviewKey:string)=>string|null;labelOf?:(reviewKey:string)=>string|null;
    point?:(evidence:Evidence|null)=>void;active?:boolean;
    /** 관제의 'AI 조사'로 들어왔으면 대화가 없을 때 '이 변화 조사'를 바로 보낸다(onAutostart로 한 번만). */
    autostart?:boolean;onAutostart?:()=>void}=$props();
  const change=$derived(focus.kind==="vibration"?focus.change:focus.item);
  const label=$derived(change.label);
  const electrical=$derived(focus.kind==="history"&&(focus.item.unit==="V"||focus.item.unit==="A"));
  const span=$derived(focus.kind==="vibration"?focus.change.from+"–"+focus.change.to+"번째 측정":spanText(Date.parse(focus.item.start),Date.parse(focus.item.end)));
  // 첫 요청: 질문을 고르지 않아도 고른 변화 자체를 조사한다. 대화에는 이름(label)으로 보인다.
  const investigate={label:"이 변화 조사",text:"이 변화를 조사해 기록으로 확인한 것과 아직 모르는 것을 나눠 설명해 주세요."};
  const order={label:"변화 순서",text:"같은 시기에 달라진 항목들이 바뀐 순서와 그 순서로 알 수 있는 것을 설명해 주세요."};
  const steady={label:"변화 시작·지속",text:"변화가 언제 시작됐고 달라진 수준이 이어졌는지 값이 계속 변했는지 설명해 주세요."};
  const questions=$derived(focus.kind==="vibration"
    ?[...(together>1?[order]:[]),{label:"진동·주파수 종합",text:"진동 크기와 주파수 변화를 종합해 알 수 있는 것과 더 확인할 것을 설명해 주세요."},...(together>1?[]:[steady])]
    :[{label:"함께 변한 신호",text:electrical?"선택한 변화와 다른 상전압·전류를 함께 보면 알 수 있는 것을 설명해 주세요.":"선택한 변화와 같은 구간의 다른 신호를 함께 보면 알 수 있는 것을 설명해 주세요."},
      electrical?{label:"운전 조건과 차이",text:"부하(운전 수준)가 바뀌었는지, 같은 운전 수준끼리 비교해도 차이가 남는지 설명해 주세요."}:together>1?order:steady]);
  const draftScope=untrack(()=>"change:"+assetId+":"+change.reviewKey);
  const reviewKey=$derived(change.reviewKey!);
  let question=$state(questionDraft(draftScope)),records:ChangeDiscussion[]=$state([]),error=$state("");
  onDestroy(()=>{keepQuestionDraft(draftScope,question);cancel();write?.abort();point(null);clearInterval(clock);});
  let questionRevision=0;
  let writable=$state(false),busy=$state(false),loading=$state(true),remaining=240;
  let awaitingQuestion:string|null=$state(null);
  let previousIds=new Set<string>();
  let request:AbortController|null=null,write:AbortController|null=null,timer:ReturnType<typeof setTimeout>|null=null;
  const latest=$derived(records[0]??null);
  const waiting=$derived(busy||awaitingQuestion!==null||latest?.status==="pending");
  // 대화는 오래된 것부터. 접수 확인 전의 질문도 보낸 말풍선으로 바로 보인다.
  const thread=$derived([...records].reverse());
  const unsent=$derived(awaitingQuestion!==null&&!records.some(row=>row.question===awaitingQuestion&&!previousIds.has(row.id))?awaitingQuestion:null);
  const asked=$derived(new Set(records.map(row=>row.question)));
  const prompts=$derived(questions.filter(item=>!asked.has(item.text)));
  // 기다린 시간: 첫 답은 모델이 쉬고 있었다면 1분 가까이 걸린다. 멈춘 것과 구분되게 초를 센다.
  let since:number|null=$state(null),now=$state(Date.now());
  const clock=setInterval(()=>{if(waiting)now=Date.now();},1000);
  $effect(()=>{if(waiting&&since===null)untrack(()=>{since=Date.now();now=since;});if(!waiting)since=null;});
  const elapsed=$derived(since!==null?Math.max(0,Math.round((now-since)/1000)):null);
  // 가리키는 근거: 올린 줄이 먼저, 없으면 눌러 고정한 줄. 키는 '종류|답 id|번호'(e: 답의 근거, s: 확인한 항목).
  let hovered:string|null=$state(null),pinned:string|null=$state(null);
  $effect(()=>{const key=hovered??pinned;if(key===null){point(null);return;}
    const [kind,id,index]=key.split("|"),row=records.find(item=>item.id===id);
    point((kind==="s"?row?.steps[Number(index)]?.target:row?.answer?.evidence?.[Number(index)])??null);});
  const said=(text:string)=>text===investigate.text?investigate.label:text;
  const values=(row:{before:number|null;after:number|null;unit:string|null})=>row.before!==null&&row.after!==null?measure(row.before,row.unit,3)+" → "+measure(row.after,row.unit,3):"";
  // 답의 문장(서버의 유효 숫자 세 자리)과 같은 표기.
  const hz=(value:number)=>value.toLocaleString("ko-KR",{maximumSignificantDigits:3});
  const percent=(share:number)=>(share*100).toLocaleString("ko-KR",{maximumFractionDigits:1})+"%";
  const memoOf=(row:ChangeDiscussion)=>row.answer?label+" · "+span+"\n"+row.answer.summary+(row.answer.next_step?"\n"+row.answer.next_step:""):"";
  let copied:string|null=$state(null);
  async function copy(row:ChangeDiscussion){
    try{await navigator.clipboard.writeText(row.answer?.summary??"");copied=row.id;setTimeout(()=>{if(copied===row.id)copied=null;},1500);}catch{ /* 복사를 못 해도 답은 그대로 보인다. */ }
  }
  // 새 말풍선이 생기면 마지막 질문을 창 위쪽에 둔다. 답이 길어도 확인한 항목과 답의 첫 줄부터 읽힌다.
  // 사용자가 위의 답을 읽고 있으면(바닥에서 떨어져 있으면) 그대로 둔다.
  let log:HTMLElement|undefined=$state(),stick=true;
  const atBottom=()=>!log||log.scrollTop+log.clientHeight>=log.scrollHeight-48;
  $effect(()=>{thread.length;unsent;waiting;latest?.status;void tick().then(()=>{
    if(!stick||!log)return;
    const last=[...log.querySelectorAll<HTMLElement>(".me")].at(-1);
    log.scrollTop=last?log.scrollTop+last.getBoundingClientRect().top-log.getBoundingClientRect().top-12:log.scrollHeight;
  });});
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
    onStart?.();stick=true;previousIds=new Set(records.map(row=>row.id));awaitingQuestion=submitted;
    if(question.trim()===submitted)question="";
    cancel();const pending=new AbortController();write=pending;busy=true;error="";remaining=240;
    try{
      await askChange(assetId,reviewKey,submitted,latest?.status==="complete"?latest.id:null,pending.signal,currentPlayback());
      if(pending.signal.aborted)return;
      busy=false;await refresh();
    }catch(cause){if(!pending.signal.aborted){
      if(cause instanceof OutcomeUnknown){busy=false;await refresh();}
      else {awaitingQuestion=null;if(questionRevision===revision&&!question)question=submitted;error=cause instanceof Error?cause.message:"질문을 보내지 못했습니다.";}
    }}
    finally{if(write===pending){write=null;busy=false;}}
  }
  // 이미 조사한 변화면 그 대화를 그대로 보이고, 보기 전용이면 보내지 않는다.
  let autoDone=false;
  $effect(()=>{
    if(!autostart||autoDone||loading)return;
    if(thread.length||awaitingQuestion){autoDone=true;onAutostart?.();return;}
    if(!writable)return;
    autoDone=true;onAutostart?.();untrack(()=>void ask(investigate.text));
  });
  function keydown(event:KeyboardEvent){
    // Enter로 보내고 Shift+Enter는 줄바꿈. 한글을 조합하는 중의 Enter는 글자를 확정할 뿐 보내지 않는다.
    if(event.key!=="Enter"||event.shiftKey||event.isComposing||event.keyCode===229)return;
    event.preventDefault();void ask(question);
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

{#snippet typing(text:string)}
  <p class="typing" role="status"><i></i><i></i><i></i><span>{text}{elapsed!==null&&elapsed>=3?" · "+elapsed+"초":""}</span></p>
{/snippet}

{#snippet waitingBubble()}
  <div class="ai"><span class="avatar" aria-hidden="true">AI</span><div class="body">{@render typing("측정 기록 확인 중")}</div></div>
{/snippet}

<!-- 확인한 항목: 답을 기다리는 동안 펼쳐 두고, 답이 오면 한 줄로 접는다(이어 묻는 질문은 처음부터 접는다). -->
{#snippet work(row:ChangeDiscussion,done:boolean)}
  {#if row.steps.length}
    <details class="work" open={!done&&!row.followUp}>
      <summary><svg class="tick" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg>확인한 항목 {row.steps.length}개</summary>
      <ol>{#each row.steps as step,index(index)}{@const key="s|"+row.id+"|"+index}
        <li style:--i={index}>{@render checkedRow(step,key)}</li>
      {/each}</ol>
    </details>
  {/if}
{/snippet}

{#snippet checkedRow(step:Step,key:string)}
  <button type="button" disabled={!step.target} aria-pressed={step.target?pinned===key:undefined} onpointerenter={()=>{if(step.target)hovered=key;}} onpointerleave={()=>hovered=null}
    onfocus={()=>hovered=key} onblur={()=>hovered=null} onclick={()=>pinned=pinned===key?null:key}>
    <svg class="tick" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg><span>{step.label}</span><b>{step.result}</b>
  </button>
{/snippet}

<section class="chat" aria-label="선택한 변화의 AI 조사">
  <header><div><span class="what"><i class="swatch" style:background={colorOf(reviewKey)??"var(--color-ink-muted)"}></i><b>{labelOf(reviewKey)??label}</b> 변화</span><small>{span}</small></div>
    {#if onClose}<button type="button" class="close" aria-label="AI 조사 닫기" onclick={onClose}><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>{/if}</header>

  <div class="log" bind:this={log} onscroll={()=>stick=atBottom()} aria-live="polite">
    {#if loading}<p class="note">대화를 불러오는 중</p>
    {:else if !thread.length&&!unsent}
      <div class="empty">
        <button type="button" class="start" disabled={!writable} onclick={()=>void ask(investigate.text)}>
          <b>{investigate.label}</b><span>이 변화의 측정·비교 결과를 확인하고, 확인된 것과 아직 모르는 것을 나눠 답합니다.</span></button>
        <div class="follow">{#each prompts as item(item.label)}<button type="button" disabled={!writable} title={item.text} onclick={()=>void ask(item.text)}>{item.label}</button>{/each}</div>
      </div>
    {/if}
    {#each thread as row(row.id)}
      <p class="me">{said(row.question)}</p>
      {#if row.status==="pending"}
        <div class="ai"><span class="avatar" aria-hidden="true">AI</span><div class="body">{@render work(row,false)}{@render typing("답 정리 중")}</div></div>
      {:else if row.status==="complete"&&row.answer}
        {@const evidence=row.answer.evidence??[]}
        {@const next=investigationLinks(assetId,focus,row.answer.actions)}
        <div class="ai"><span class="avatar" aria-hidden="true">AI</span><div class="body">
          {@render work(row,true)}
          <p class="answer">{row.answer.summary}</p>
          {#if row.answer.source==="computed"}<p class="note">AI 응답을 쓰지 못해 계산 결과 요약으로 답했습니다.</p>{/if}
          {#if evidence.length}<ol class="evidence" aria-label="답의 근거">
            {#each evidence as item,index(index)}{@const key="e|"+row.id+"|"+index}
              <li><button type="button" aria-pressed={pinned===key} onpointerenter={()=>hovered=key} onpointerleave={()=>hovered=null}
                onfocus={()=>hovered=key} onblur={()=>hovered=null} onclick={()=>pinned=pinned===key?null:key}>
                <span class="number">{index+1}</span>
                {#if item.kind==="change"}
                  <span class="name"><i class="swatch" style:background={colorOf(item.review_key)??"var(--color-ink-muted)"}></i>{labelOf(item.review_key)??item.label}<b>{values(item)}</b></span><small>{item.where}</small>
                {:else if item.kind==="signal"}
                  <span class="name"><i class="swatch hollow"></i>{item.label}<b>{values(item)}</b></span><small>같은 비교 구간 · 그래프에 없는 신호</small>
                {:else if item.kind==="operation"&&item.levels&&item.a&&item.b}
                  <span class="name"><i class="swatch level"></i>{item.label}</span>
                  <!-- 비교 구간과 변화 구간의 운전 수준 비중. 진하기는 그래프 아래 운전 수준 띠와 같다(진할수록 높은 전류, 빈 칸은 정지). -->
                  {#each [["비교 구간",item.a],["변화 구간",item.b]] as [name,shares] (name)}
                    <span class="mix"><small>{name}</small><span class="stack" title={item.levels.map((level,i)=>level+" "+percent((shares as number[])[i])).join(", ")}>
                      {#each shares as number[] as share,i(i)}{#if share>0}<i class:stop={i===0} style:width={share*100+"%"} style:opacity={i===0?1:.18+.72*i/Math.max(1,item.levels.length-1)}>{share>=.15?percent(share):""}</i>{/if}{/each}
                    </span></span>
                  {/each}
                {:else if item.kind==="operation"&&item.levels&&item.runs}
                  {@const runs=item.runs}{@const levels=item.levels}{@const start=Date.parse(runs[0].from)}{@const total=Date.parse(runs.at(-1)!.to)-start}
                  <span class="name"><i class="swatch level"></i>{item.label}</span>
                  <!-- 변화 앞뒤의 운전 수준: 그래프 아래 띠와 같은 진하기. 경계 시각은 포인터를 올리면 보인다. -->
                  <span class="flow" title={item.detail}>{#each runs as run,i(i)}<i class:stop={run.level===0} style:width={(Date.parse(run.to)-Date.parse(run.from))/total*100+"%"}
                    style:opacity={run.level===0?1:.18+.72*run.level/Math.max(1,levels.length-1)}></i>{/each}</span>
                  <small class="ends"><span>{clockText(start).replace(/\(.\)/,"")}</span><span>{clockText(Date.parse(runs.at(-1)!.to)).replace(/\(.\)/,"")}</span></small>
                {:else if item.kind==="operation"}
                  <span class="name"><i class="swatch level"></i>{item.label}</span><small>{item.detail}</small>
                {:else}
                  <span class="name"><i class="swatch hollow"></i>{item.label} {hz(item.from_hz)}–{hz(item.to_hz)} Hz<b>{percent(item.a)} → {percent(item.b)}</b></span>
                  <span class="bars" aria-hidden="true"><i style:width={item.a*100+"%"}></i><i style:width={item.b*100+"%"}></i></span>
                {/if}
              </button></li>
            {/each}
          </ol>{/if}
          {#if row.answer.next_step}<p class="next-step">{row.answer.next_step}</p>{/if}
          {#if next.length}<div class="next">{#each next as item(item.key)}<a href={item.href} onclick={event=>event.currentTarget.href=investigationOriginUrl(event.currentTarget.href,location.href)}>{item.label} →</a>{/each}</div>{/if}
          <div class="tools">
            <button type="button" onclick={()=>onMemo(memoOf(row))}>판단 메모로</button>
            <button type="button" onclick={()=>void copy(row)}>{copied===row.id?"복사됨":"복사"}</button>
          </div>
        </div></div>
      {:else}
        <div class="ai"><span class="avatar" aria-hidden="true">AI</span><div class="body">{@render work(row,true)}<p class="note">설명을 만들지 못했습니다. 그래프와 원본 측정은 계속 볼 수 있습니다.</p></div></div>
      {/if}
    {/each}
    {#if unsent}<p class="me">{said(unsent)}</p>{@render waitingBubble()}{/if}
    {#if error}<p class="error" role="alert">{error} <button type="button" onclick={()=>void refresh()}>다시 읽기</button></p>{/if}
  </div>

  <footer>
    {#if thread.length&&prompts.length}<div class="follow">{#each prompts as item(item.label)}<button type="button" disabled={!writable||waiting} onclick={()=>void ask(item.text)}>{item.label}</button>{/each}</div>{/if}
    <div class="composer" class:disabled={!writable}>
      <textarea rows="1" maxlength="600" aria-label="질문" bind:value={question} oninput={()=>questionRevision++} onfocus={()=>onStart?.()} onkeydown={keydown}
        disabled={!writable} placeholder={!writable?"보기 전용에서는 저장된 대화만 볼 수 있습니다":waiting?"답변을 기다리는 동안 다음 질문을 쓸 수 있습니다":"이 변화에 대해 질문"}></textarea>
      <button type="button" class="send" aria-label="질문 보내기" disabled={!writable||loading||waiting||!question.trim()} onclick={()=>void ask(question)}>
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
  .flow{display:flex;height:12px;border-radius:2px;overflow:hidden}
  .flow i{display:block;height:100%;background:var(--color-ink)}.flow i.stop{background:none;box-shadow:inset 0 0 0 1px var(--color-border)}
  .ends{display:flex;justify-content:space-between}
  .what{display:flex;align-items:center;gap:7px;font-size:var(--font-small)}
  header small{padding-left:19px;font-size:var(--font-label);color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .log{overflow-y:auto;min-height:0;padding:14px;display:flex;flex-direction:column;gap:12px;overscroll-behavior:contain}
  p{margin:0;font-size:var(--font-small);overflow-wrap:anywhere}
  .note{color:var(--color-ink-muted);font-size:var(--font-label);line-height:1.5}
  .empty{display:grid;gap:10px;margin-top:auto}
  .start{display:grid;gap:3px;text-align:left;padding:11px 13px;border:1px solid var(--color-action);border-radius:10px;background:var(--color-surface-selected);font:inherit;cursor:pointer;color:var(--color-ink)}
  .start:hover:not(:disabled){box-shadow:0 0 0 3px rgb(37 99 235 / .12)}
  .start:disabled{border-color:var(--color-border);background:var(--color-surface);cursor:default}
  .start b{font-size:var(--font-small);color:var(--color-action)}.start span{font-size:var(--font-label);color:var(--color-ink-muted);line-height:1.45}
  .work{border:1px solid var(--color-border);border-radius:8px;background:#f7f9fa}
  .work summary{display:flex;align-items:center;gap:6px;padding:5px 10px;font-size:var(--font-label);color:var(--color-ink-muted);cursor:pointer;list-style:none;user-select:none}
  .work summary::-webkit-details-marker{display:none}
  .work summary::after{content:"";margin-left:auto;width:5px;height:5px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:translateY(-2px) rotate(45deg)}
  .work[open] summary::after{transform:translateY(1px) rotate(-135deg)}
  .work ol{display:grid;gap:1px;margin:0;padding:0 4px 5px;list-style:none}
  .work li{animation:rise .24s both;animation-delay:calc(var(--i) * 70ms)}
  @keyframes rise{from{opacity:0;transform:translateY(3px)}}
  @media (prefers-reduced-motion:reduce){.work li{animation:none}}
  .work li button{display:grid;grid-template-columns:12px minmax(0,auto) minmax(0,1fr);align-items:baseline;gap:6px;width:100%;padding:4px 6px;border:0;border-radius:5px;background:none;font:inherit;font-size:var(--font-label);text-align:left;color:var(--color-ink)}
  .work li button:disabled{cursor:default;color:var(--color-ink)}
  .work li button:not(:disabled){cursor:pointer}
  .work li button:not(:disabled):hover,.work li button:focus-visible,.work li button[aria-pressed="true"]{background:var(--color-surface-selected)}
  .work li b{justify-self:end;text-align:right;font-weight:600;font-variant-numeric:tabular-nums}
  .tick{flex:none;width:12px;height:12px;align-self:center;fill:none;stroke:var(--color-ink-muted);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
  .me{align-self:flex-end;max-width:85%;padding:8px 12px;border-radius:14px 14px 4px 14px;background:var(--color-surface-selected);line-height:1.5}
  .ai{display:grid;grid-template-columns:24px minmax(0,1fr);gap:8px;align-items:start}
  .avatar{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--color-action);color:#fff;font-size:10px;font-weight:700;letter-spacing:.02em}
  .body{display:grid;gap:8px;min-width:0;padding-top:2px}
  .answer{line-height:1.7;color:var(--color-ink)}
  .next-step{color:var(--color-ink-muted);line-height:1.55}
  .typing{display:flex;align-items:center;gap:4px;color:var(--color-ink-muted);font-size:var(--font-label);min-height:24px}
  .typing i{width:5px;height:5px;border-radius:50%;background:var(--color-ink-muted);animation:blink 1.2s infinite ease-in-out}
  .typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s}.typing span{margin-left:6px}
  @keyframes blink{0%,80%,100%{opacity:.25}40%{opacity:1}}
  @media (prefers-reduced-motion:reduce){.typing i{animation:none;opacity:.6}}
  .evidence{display:grid;gap:2px;margin:0;padding:0;list-style:none}
  .evidence{border-left:2px solid var(--color-border);padding-left:6px}
  .evidence button{display:grid;grid-template-columns:18px minmax(0,1fr);column-gap:6px;row-gap:3px;width:100%;padding:6px 8px 6px 4px;border:0;border-radius:6px;background:none;text-align:left;font:inherit;color:var(--color-ink);cursor:pointer}
  .evidence button:hover,.evidence button:focus-visible,.evidence button[aria-pressed="true"]{background:var(--color-surface-selected)}
  .evidence button>*:not(.number){grid-column:2}
  .number{grid-row:1;display:grid;place-items:center;width:16px;height:16px;border-radius:50%;background:var(--color-border);font-size:10px;font-weight:700;color:var(--color-ink)}
  .name{display:flex;align-items:center;gap:6px;font-size:var(--font-small);min-width:0}
  .name b{margin-left:auto;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}
  .evidence small{font-size:var(--font-label);color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .swatch{flex:none;display:inline-block;width:12px;height:3px;border-radius:2px}
  .swatch.hollow{height:8px;width:8px;margin:0 2px;border-radius:50%;border:1.5px solid var(--color-ink-muted);box-sizing:border-box}
  .swatch.level{height:10px;background:var(--color-ink);opacity:.6}
  .bars{display:grid;gap:2px}.bars i{display:block;height:4px;border-radius:2px;background:var(--color-ink-muted)}.bars i+i{background:var(--color-series-1)}
  .mix{display:grid;grid-template-columns:52px minmax(0,1fr);align-items:center;gap:6px}
  .stack{display:flex;height:14px;border-radius:2px;overflow:hidden;background:var(--color-surface)}
  .stack i{display:block;height:100%;background:var(--color-ink);color:#fff;font-size:10px;font-style:normal;line-height:14px;text-align:center;overflow:hidden;white-space:nowrap}
  .stack i.stop{background:none;box-shadow:inset 0 0 0 1px var(--color-border);color:var(--color-ink-muted)}
  .next{display:flex;flex-direction:column;gap:4px}
  .next a{font-size:var(--font-small);font-weight:650;color:var(--color-action);text-decoration:none}.next a:hover{text-decoration:underline}
  .tools{display:flex;gap:4px}
  .tools button{border:1px solid var(--color-border);border-radius:6px;background:var(--color-surface);padding:3px 8px;font:inherit;font-size:var(--font-label);color:var(--color-ink-muted);cursor:pointer}
  .tools button:hover{color:var(--color-action);border-color:var(--color-action)}
  .error{color:var(--color-failure-ink);font-size:var(--font-label)}
  .error button{border:0;background:none;padding:0;font:inherit;color:var(--color-action);text-decoration:underline;cursor:pointer}
  footer{display:grid;gap:8px;padding:10px 12px 12px;border-top:1px solid var(--color-border)}
  .follow{display:flex;flex-wrap:wrap;gap:6px}
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
