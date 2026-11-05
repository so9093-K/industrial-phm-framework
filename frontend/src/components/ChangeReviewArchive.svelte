<script lang="ts">
  import {readChangeReviews, type ChangeCapture} from "../change-reviews";
  import {findingText, findingLinks} from "../record-findings";
  import {readableSourceId} from "../operations-status";
  import {onMount} from "svelte";
  import ChangeReview from "./ChangeReview.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  let {assetId, revision=0}:{assetId:string;revision?:number}=$props();
  let captures:ChangeCapture[]=$state([]), next:string|null=$state(null), busy=$state(false), error=$state("");
  let request:AbortController|null=null;
  let opened:Record<string,boolean>=$state({});
  const clock=(value:string)=>new Date(value).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"});
  async function load(more=false){request?.abort();const req=new AbortController();request=req;busy=true;error="";
    try{const page=await readChangeReviews(assetId,req.signal,more&&next?{before_id:next}:{});if(req.signal.aborted)return;captures=more?[...captures,...page.captures]:page.captures;next=page.next;}
    catch(cause){if(!req.signal.aborted)error=cause instanceof Error?cause.message:"검토 목록 조회 실패";}
    finally{if(request===req)busy=false;}
  }
  $effect(()=>{void revision;void load();});
  onMount(()=>()=>request?.abort());
</script>
{#if error}<StatusNotice kind="failure" message={error} actionLabel="저장 검토 다시 읽기" onAction={()=>void load()} />{/if}
{#if !busy&&!error&&!captures.length}<p>저장한 주요 변화 검토가 없습니다.</p>{/if}
{#each captures as capture(capture.id)}
  {@const finding=capture.finding}
  {@const text=findingText(finding,finding.bucketSeconds??null)}
  {@const links=findingLinks(assetId,finding,finding.baseline,finding.bucketSeconds??null)}
  <details ontoggle={event=>opened={...opened,[capture.id]:event.currentTarget.open}}><summary>{finding.label} · {text.what} · {capture.review.status==="closed"?"종료":capture.review.status==="acknowledged"?"확인함":"검토 대기"}</summary>
    <p>{text.when} · {finding.context?readableSourceId(finding.context.sourceId):""} · {finding.context?.pointId??"측정 위치 미지정"}</p>
    {#if finding.baseline}<p>비교 기준 · {clock(finding.baseline.from)} ~ {clock(finding.baseline.to)}</p>{/if}
    <p>{#if links.signal}<a href={links.signal}>당시 구간의 원본 신호 →</a>{/if} {#if links.compare}<a href={links.compare}>당시 기준과 비교 →</a>{/if}</p>
    {#if opened[capture.id]}<ChangeReview {assetId} {finding} saved={capture} />{/if}
  </details>
{/each}
{#if busy}<p role="status">저장한 변화 검토를 읽고 있습니다.</p>{/if}
{#if next}<button type="button" class="ui-button" disabled={busy} onclick={()=>void load(true)}>이전 검토 더 보기</button>{/if}
<style>details{margin-block:var(--space-3);padding:var(--space-3);border:1px solid var(--color-border);border-radius:var(--radius-control)}summary,p{overflow-wrap:anywhere}a{margin-inline-end:var(--space-3)}</style>
