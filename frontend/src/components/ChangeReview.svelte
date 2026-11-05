<script lang="ts">
  import {onMount} from "svelte";
  import {captureChange, readChangeReviews, reviewChange, type ChangeCapture} from "../change-reviews";
  import type {FoundInterval} from "../record-findings";
  import {readPermission} from "../outlook-briefings";
  import ReviewActions from "./ReviewActions.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  let {assetId, finding, saved = null, onSaved = () => {}}: {assetId:string;finding:FoundInterval;saved?:ChangeCapture|null;onSaved?:(capture:ChangeCapture)=>void} = $props();
  let capture:ChangeCapture|null = $state(null);
  let writable = $state(false);
  let readState:"loading"|"ready"|"failed" = $state("loading");
  let error = $state("");
  let request:AbortController|null = null;
  async function load() {
    request?.abort(); const req = new AbortController(); request=req; readState="loading";
    try {
      const page = await readChangeReviews(assetId,req.signal,saved ? {capture_id:saved.id} : {finding_id:finding.reviewKey!});
      if(req.signal.aborted)return;
      capture=page.captures[0]??null; readState="ready";
      if(capture)onSaved(capture);
    } catch(cause) {if(!req.signal.aborted){readState="failed";error=cause instanceof Error?cause.message:"검토 기록 조회 실패";}}
  }
  async function reload(signal:AbortSignal):Promise<boolean> {
    if(!capture)return false;
    try { const page=await readChangeReviews(assetId,signal,{capture_id:capture.id}); if(signal.aborted)return false;capture=page.captures[0];onSaved(capture);return true; } catch{return false;}
  }
  onMount(()=>{const req=new AbortController();void readPermission(req.signal).then(value=>{if(!req.signal.aborted)writable=value;}).catch(()=>{});void load();return()=>{req.abort();request?.abort();};});
</script>
{#if readState === "loading"}<StatusNotice message="이 변화의 저장된 검토를 확인하고 있습니다." />
{:else if readState === "failed"}<StatusNotice kind="failure" message={error} actionLabel="검토 다시 읽기" onAction={()=>void load()} />
{:else}
  <p class="context">이 변화와 비교 기준을 함께 보존합니다. 새 측정이 들어온 뒤에도 ‘저장한 주요 변화 검토’에서 이어서 볼 수 있습니다.</p>
  <ReviewActions id={capture?.id ?? finding.reviewKey!} status={capture?.review.status ?? "open"} events={capture?.review.events ?? []}
    {writable} confirmLabel="판단 저장" closeQuestion="이 변화의 검토를 종료할까요? 종료하면 기록을 더 남길 수 없습니다." {reload}
    submit={async(action,note,eventId,signal,decision)=>{
      if(!capture){const id=await captureChange(assetId,finding,signal);const page=await readChangeReviews(assetId,signal,{capture_id:id});capture=page.captures[0];}
      await reviewChange(assetId,capture,action,note,eventId,signal,decision);
    }} />
{/if}
<style>.context{font-size:var(--font-small);color:var(--color-ink-muted);overflow-wrap:anywhere}</style>
