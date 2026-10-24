<script lang="ts">
  import {onMount} from "svelte";
  import type {BriefingProjection} from "../outlook-briefings";
  import StatusNotice from "./StatusNotice.svelte";
  import {
    assertCurrentVersion,readBriefings,readPermission,requestBriefing,
    BriefingEvidenceChanged,type Briefing,
  } from "../outlook-briefings";
  type Props={projection:BriefingProjection;onEvidenceChanged:()=>void};
  let {projection,onEvidenceChanged}:Props=$props();
  type State="loading"|"ready"|"failed"|"changed";
  let briefingState:State=$state("loading");
  let error=$state("");
  let records:Briefing[]=$state([]);
  let writable=$state(false);
  let requesting=$state(false);
  const DEFAULT_QUESTION="이 설비의 상태와 기준까지 남은 여유를 설명해 주세요.";
  let question=$state("");
  let request:AbortController|null=null;
  let timer:ReturnType<typeof setTimeout>|null=null;
  let remaining=20;
  const checkedSource=(record:Briefing):string=>
    record.answer?.source==="computed"?"계산 결과 요약(AI 미사용)":
    record.answer?.source==="model-trimmed"?"AI 해설 · 근거 없는 문장 제외":
    record.answer?.source==="model"?"AI 해설":"만든 방식 미확인";
  const latest=$derived(records.find(item=>item.status==="complete"&&item.answer)??null);
  const waiting=$derived(records.some(item=>item.status==="pending"));
  const earlier=$derived(records.filter(item=>item!==latest));
  const clock=(at:string)=>new Date(at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"});
  const readyVersion=$derived(/^[a-f0-9]{64}$/.test(projection.dataVersion) && !!projection.outlookSettings);
  function cancel(){
    request?.abort();
    if(timer!==null)clearTimeout(timer);
    timer=null;
  }
  async function refresh(){
    cancel();
    const pending=new AbortController();request=pending;
    briefingState="loading";error="";records=[];
    try{
      await assertCurrentVersion(projection,pending.signal);
      if(pending.signal.aborted)return;
      const results=await readBriefings(projection,pending.signal);
      await assertCurrentVersion(projection,pending.signal);
      if(pending.signal.aborted)return;
      records=results;briefingState="ready";
      if(results.some(x=>x.status==="pending")&&remaining>0){
        remaining--;
        timer=setTimeout(()=>void refresh(),1500);
      }
    }catch(cause:unknown){
      if(pending.signal.aborted)return;
      error=cause instanceof Error?cause.message:"AI 브리핑 버전을 검증할 수 없습니다.";
      briefingState=cause instanceof BriefingEvidenceChanged?"changed":"failed";
      if(briefingState==="changed")onEvidenceChanged();
    }
  }
  async function ask(text:string){
    if(!writable||requesting||!readyVersion||!text.trim())return;
    cancel();
    const pending=new AbortController();request=pending;requesting=true;
    briefingState="loading";error="";records=[];remaining=20;
    try{
      await requestBriefing(projection,text,pending.signal);
      question="";
      if(pending.signal.aborted)return;
      requesting=false;
      await refresh();
    }catch(cause:unknown){
      if(pending.signal.aborted)return;
      requesting=false;
      error=cause instanceof Error?cause.message:"AI 브리핑 요청 실패";
      briefingState=cause instanceof BriefingEvidenceChanged?"changed":"failed";
      if(briefingState==="changed")onEvidenceChanged();
    }
  }
  onMount(()=>{
    if(!readyVersion){briefingState="failed";error="설명 근거 버전이나 계산 설정을 확인할 수 없어 AI 설명을 조회하지 않았습니다.";return;}
    const permissionRequest=new AbortController();
    void readPermission(permissionRequest.signal).then(allowed=>{
      if(!permissionRequest.signal.aborted)writable=allowed;
    }).catch(()=>{if(!permissionRequest.signal.aborted)writable=false;});
    void refresh();
    return()=>{permissionRequest.abort();cancel();};
  });
</script>

<section class="briefings" aria-labelledby="briefings-heading">
  <div class="head">
    <h3 id="briefings-heading">AI 해설</h3>
    {#if latest}
      <!-- A computed summary used no model, so naming the configured one would mislead. -->
      <span class="meta">{checkedSource(latest)}{latest.answer?.source==="computed"?"":" · "+(latest.model??"모델명 없음")} · {clock(latest.requestedAt)}</span>
    {/if}
  </div>
  <p class="context">마지막 기록 {typeof projection.record.last === "number" ? "#"+projection.record.last : clock(projection.record.last)+" (KST)"} 시점의 상태와 전망에 대한 해설입니다. 기준까지의 여유는 이 기록 이후로 계산합니다.</p>
  {#if requesting}
    <StatusNotice message="해설을 요청하고 있습니다. 계산 결과가 그사이 바뀌지 않았는지 다시 확인합니다."/>
  {:else if briefingState==="loading"}
    <StatusNotice message="이 결과에 대한 해설을 확인하고 있습니다."/>
  {:else if briefingState==="failed"}
    <StatusNotice kind="failure" title="해설을 확인하지 못했습니다" message={error}
      actionLabel="다시 확인" onAction={()=>{remaining=20;void refresh();}}/>
  {:else if briefingState==="changed"}
    <StatusNotice kind="uncertain" title="결과가 바뀌어 이전 해설을 숨겼습니다" message={error}/>
  {:else if latest&&latest.answer}
    {#if waiting}
      <StatusNotice message="새 질문의 해설을 만들고 있습니다. 아래는 앞서 완료한 해설입니다."/>
    {/if}
    <p class="context">질문 · {latest.question}</p>
    <p class="summary">{latest.answer.summary}</p>
    {#if latest.answer.modelUnavailable && writable}
      <p class="context">AI 서버가 응답하지 않아 계산 결과로 썼습니다.
        <button type="button" class="ui-button" disabled={requesting || waiting} onclick={() => {if (latest) void ask(latest.question);}}>AI로 다시 만들기</button></p>
    {/if}
    {#if latest.answer.points.length}
      <ul>
        {#each latest.answer.points as point,i (i)}
          <li>{point.text}
            <span class="context"> · 근거 {point.evidence.map(k=>latest.answer!.evidence[k].label).join(", ")}</span>
          </li>
        {/each}
      </ul>
    {/if}
    <details>
      <summary>해설에 쓴 계산 사실</summary>
      <dl>
        {#each Object.entries(latest.answer.evidence) as [key,fact] (key)}
          <dt>{fact.label}</dt><dd>{fact.text}</dd>
        {/each}
      </dl>
    </details>
  {:else if waiting}
    <StatusNotice message="해설을 만들고 있습니다. 잠시 후 자동으로 다시 확인합니다."/>
  {:else}
    <p class="context">아직 이 결과에 대한 해설이 없습니다.</p>
    {#if writable}
      <button type="button" class="ui-button ui-button-primary" disabled={!readyVersion}
        onclick={()=>void ask(DEFAULT_QUESTION)}>해설 만들기</button>
    {/if}
  {/if}
  {#if !writable}
    <p class="context">보기 전용이라 해설을 만들 수 없습니다. 운영을 시작하면 만들 수 있습니다.</p>
  {/if}
  <details class="ask">
    <summary>직접 질문하기</summary>
    <label>AI에게 물을 질문 (최대 600자)
      <input maxlength="600" value={question} disabled={!writable||requesting||!readyVersion}
        placeholder={DEFAULT_QUESTION} oninput={event=>question=event.currentTarget.value}/>
    </label>
    <div class="actions">
      <button type="button" class="ui-button ui-button-primary"
        onclick={()=>void ask(question)} disabled={!writable||requesting||!question.trim()||!readyVersion}>
        질문 보내기
      </button>
      <button type="button" class="ui-button" onclick={()=>{remaining=20;void refresh();}}
        disabled={requesting||!readyVersion}>해설 다시 확인</button>
    </div>
    {#each earlier as item (item.id)}
      <article class="record">
        <h4>{item.question}</h4>
        <p class="context">{clock(item.requestedAt)} · {item.status==="pending"?"만드는 중":item.status==="failed"?"만들지 못함":checkedSource(item)}</p>
        {#if item.status==="complete"&&item.answer}<p>{item.answer.summary}</p>{/if}
      </article>
    {/each}
  </details>
</section>
<style>
  .briefings{border:2px solid var(--color-action);border-radius:var(--radius-panel);margin-top:var(--space-4);padding:var(--space-4) var(--space-5)}
  .head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:var(--space-2) var(--space-4);align-items:baseline}
  .head h3{margin:0}
  .meta{font-size:var(--font-small);color:var(--color-ink-muted)}
  summary{cursor:pointer;font-weight:650;color:var(--color-action);padding-block:var(--space-2)}
  .ask{margin-top:var(--space-3)}
  .context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  label{display:grid;gap:var(--space-2);font-weight:650}
  input{width:100%;min-width:0;border:1px solid var(--color-border);border-radius:var(--radius-control);
    padding:var(--space-3);background:var(--color-surface);color:var(--color-ink)}
  .actions{display:flex;flex-wrap:wrap;gap:var(--space-3);margin-top:var(--space-3)}
  .record{border-top:1px solid var(--color-border);padding-block:var(--space-3)}
  .summary{font-weight:650;overflow-wrap:anywhere}
  dd{margin:0 0 var(--space-3);overflow-wrap:anywhere}
</style>
