<script lang="ts">
  import {onMount} from "svelte";
  import type {Projection} from "../projections";
  import StatusNotice from "./StatusNotice.svelte";
  import {
    assertCurrentVersion,readBriefings,readPermission,requestBriefing,
    BriefingEvidenceChanged,type Briefing,
  } from "../outlook-briefings";
  type Props={projection:Projection;onEvidenceChanged:()=>void};
  let {projection,onEvidenceChanged}:Props=$props();
  type State="loading"|"ready"|"failed"|"changed";
  let briefingState:State=$state("loading");
  let error=$state("");
  let records:Briefing[]=$state([]);
  let writable=$state(false);
  let requesting=$state(false);
  let question=$state("이 설비의 상태와 기준까지 남은 여유를 설명해 주세요.");
  let request:AbortController|null=null;
  let timer:ReturnType<typeof setTimeout>|null=null;
  let remaining=20;
  const checkedSource=(record:Briefing):string=>
    record.answer?.source==="computed"?"서버 계산 요약":
    record.answer?.source==="model-trimmed"?"AI 문장 일부 근거 검증 수정":
    record.answer?.source==="model"?"근거 검증된 AI 설명":"생성 방식 미확인";
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
  async function ask(){
    if(!writable||requesting||!readyVersion)return;
    cancel();
    const pending=new AbortController();request=pending;requesting=true;
    briefingState="loading";error="";records=[];remaining=20;
    try{
      await requestBriefing(projection,question,pending.signal);
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
  <h3 id="briefings-heading">버전 일치 AI 브리핑</h3>
  <p class="context">이 설명은 선택한 저장 측정·이상 탐지 근거 버전에서만 유효합니다.
    서버가 다시 계산한 `data_version`이 바뀌면 설명과 이전 전망을 모두 폐기합니다.
    AI 설명은 고장 판정이나 정비 지시가 아닙니다.</p>
  <label>AI에게 물을 질문 (최대 600자)
    <input maxlength="600" value={question} disabled={!writable||requesting||!readyVersion}
      oninput={event=>question=event.currentTarget.value}/>
  </label>
  <div class="actions">
    <button type="button" class="ui-button ui-button-primary"
      onclick={()=>void ask()} disabled={!writable||requesting||!question.trim()||!readyVersion}>
      AI 브리핑 요청
    </button>
    <button type="button" class="ui-button" onclick={()=>{remaining=20;void refresh();}}
      disabled={requesting||!readyVersion}>저장된 브리핑 다시 확인</button>
  </div>
  {#if !writable}
    <StatusNotice kind="uncertain" message="AI 질문은 supervisor가 연결된 쓰기 권한 세션에서만 요청할 수 있습니다. 저장된 브리핑은 읽을 수 있습니다."/>
  {/if}
  {#if requesting}
    <StatusNotice message="서버 권한과 최신 분석 버전을 다시 확인하고 AI 브리핑을 요청합니다."/>
  {:else if briefingState==="loading"}
    <StatusNotice message="저장 전망의 계산 버전을 재검증하고 AI 브리핑 상태를 조회하고 있습니다."/>
  {:else if briefingState==="failed"}
    <StatusNotice kind="failure" title="AI 브리핑 확인 실패" message={error}
      actionLabel="버전 다시 확인" onAction={()=>{remaining=20;void refresh();}}/>
  {:else if briefingState==="changed"}
    <StatusNotice kind="uncertain" title="기존 전망·AI 설명 무효화" message={error}/>
  {:else if records.length===0}
    <StatusNotice message="이 설정과 분석 근거 버전으로 저장된 AI 브리핑은 없습니다."/>
  {:else}
    {#each records as item (item.id)}
      <article class="record">
        <h4>{item.question}</h4>
        <p class="context">요청 {new Date(item.requestedAt).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"})}
          · {item.status==="pending"?"계산 중":item.status==="failed"?"생성 실패":"근거 확인된 설명"}</p>
        {#if item.status==="pending"}
          <StatusNotice message="서버가 설명을 처리하고 있습니다. 동일한 버전으로 결과를 다시 조회합니다."/>
        {:else if item.status==="failed"}
          <StatusNotice kind="uncertain" message="이 질문의 AI 설명을 생성하지 못했습니다. 기존 수치 전망을 대신하지 않습니다."/>
        {:else if item.answer}
          <p class="summary">{item.answer.summary}</p>
          {#if item.answer.points.length}
            <ul>
              {#each item.answer.points as point,i (i)}
                <li>{point.text}
                  <span class="context"> · 사용한 사실 {point.evidence.map(k=>item.answer!.evidence[k].label).join(", ")}</span>
                </li>
              {/each}
            </ul>
          {/if}
          <details>
            <summary>AI 설명이 실제로 사용한 서버 계산 근거</summary>
            <dl>
              {#each Object.entries(item.answer.evidence) as [key,fact] (key)}
                <dt>{fact.label}</dt><dd>{fact.text}</dd>
              {/each}
            </dl>
          </details>
          <p class="context">{checkedSource(item)} · 모델 {item.model??"모델명 없음"}</p>
        {/if}
      </article>
    {/each}
  {/if}
</section>
<style>
  .briefings{border-top:1px solid var(--color-border);margin-top:var(--space-6);padding-top:var(--space-4)}
  .context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  label{display:grid;gap:var(--space-2);font-weight:650}
  input{width:100%;min-width:0;border:1px solid var(--color-border);border-radius:var(--radius-control);
    padding:var(--space-3);background:var(--color-surface);color:var(--color-ink)}
  .actions{display:flex;flex-wrap:wrap;gap:var(--space-3);margin-top:var(--space-3)}
  .record{border-top:1px solid var(--color-border);padding-block:var(--space-3)}
  .summary{font-weight:650;overflow-wrap:anywhere}
  dd{margin:0 0 var(--space-3);overflow-wrap:anywhere}
</style>
