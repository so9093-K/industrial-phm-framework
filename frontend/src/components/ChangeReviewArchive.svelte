<script lang="ts">
  import {changeCaptureCaption,readChangeReviews, type ChangeCapture} from "../change-reviews";
  import {onMount} from "svelte";
  import ChangeCaptureDetail from "./ChangeCaptureDetail.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  let {assetId, revision=0}:{assetId:string;revision?:number}=$props();
  let captures:ChangeCapture[]=$state([]), next:string|null=$state(null), busy=$state(false), error=$state("");
  let request:AbortController|null=null;
  let opened:Record<string,boolean>=$state({});
  async function load(more=false){request?.abort();const req=new AbortController();request=req;busy=true;error="";
    try{const page=await readChangeReviews(assetId,req.signal,more&&next?{before_id:next}:{});if(req.signal.aborted)return;const incoming=page.captures.map(row=>{
        const known=captures.find(previous=>previous.id===row.id);
        return known&&known.review.events.length>row.review.events.length?known:row;
      });
      captures=more?[...captures,...incoming]:incoming;next=page.next;}
    catch(cause){if(!req.signal.aborted)error=cause instanceof Error?cause.message:"검토 목록 조회 실패";}
    finally{if(request===req)busy=false;}
  }
  $effect(()=>{void revision;void load();});
  onMount(()=>()=>request?.abort());
</script>
{#if error}<StatusNotice kind="failure" message={error} actionLabel="저장 검토 다시 읽기" onAction={()=>void load()} />{/if}
{#if !busy&&!error&&!captures.length}<p>저장한 특이사항 검토가 없습니다.</p>{/if}
{#each captures as capture(capture.id)}
  {@const finding=capture.finding}
  <details ontoggle={event=>opened={...opened,[capture.id]:event.currentTarget.open}}><summary>{finding.label} · {changeCaptureCaption(capture)} · {capture.review.status==="closed"?"종료":capture.review.status==="acknowledged"?"확인함":"검토 대기"}</summary>
    {#if opened[capture.id]}<ChangeCaptureDetail {assetId} {capture} onUpdated={updated=>captures=captures.map(row=>row.id===updated.id&&updated.review.events.length>=row.review.events.length?updated:row)} />{/if}
  </details>
{/each}
{#if busy}<p role="status">저장한 특이사항 검토를 읽고 있습니다.</p>{/if}
{#if next}<button type="button" class="ui-button" disabled={busy} onclick={()=>void load(true)}>이전 검토 더 보기</button>{/if}
<style>details{margin-block:var(--space-3);padding:var(--space-3);border:1px solid var(--color-border);border-radius:var(--radius-control)}summary,p{overflow-wrap:anywhere}</style>
