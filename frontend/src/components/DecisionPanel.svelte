<script lang="ts">
  import ChangeReview from "./ChangeReview.svelte";
  import ChangeReviewArchive from "./ChangeReviewArchive.svelte";
  import TaskDialog from "./TaskDialog.svelte";
  import {untrack} from "svelte";
  /** 판단·메모 남기기. AI 조사의 답을 메모로 옮기면(memo의 순번이 바뀌면) 그 초안으로 연다. */
  let {assetId, reviewKey, memo = null, onCommitted,onInvestigate}: {assetId: string; reviewKey: string;
    memo?: {sequence: number; text: string} | null; onCommitted?: () => void;onInvestigate?:()=>void} = $props();
  let draftNote: {sequence: number; text: string} | null = $state(null);
  let revision = $state(0);
  let archiveOpen = $state(false);
  let reviewOpen = $state(false);
  // 다시 열린 화면에서 예전 메모로 대화상자를 띄우지 않는다: 이 화면이 열린 뒤에 옮긴 메모만 연다.
  let seen = untrack(() => memo?.sequence ?? 0);
  $effect(() => {if (memo && memo.sequence > seen) {seen = memo.sequence; draftNote = memo; reviewOpen = true;}});
</script>

{#snippet review()}
  {#key reviewKey}<ChangeReview {assetId} finding={{reviewKey}} {draftNote} onCommitted={() => {revision++; onCommitted?.();}} />{/key}
  <details class="archive" ontoggle={event => archiveOpen = event.currentTarget.open}>
    <summary>저장된 검토</summary>
    {#if archiveOpen}<ChangeReviewArchive {assetId} {revision} />{/if}
  </details>
{/snippet}
<div class="decision" aria-label="이 변화로 이어서 할 일">
  <button type="button" class="ui-button" onclick={() => {onInvestigate?.();reviewOpen = true;}}>판단·메모 남기기</button>
  <TaskDialog title="이 변화의 판단·메모" bind:open={reviewOpen}>{@render review()}</TaskDialog>
</div>

<style>
  .decision { display: flex; gap: var(--space-2); flex-wrap: wrap; min-width: 0; }
  .archive summary { cursor: pointer; font-weight: 650; color: var(--color-action); }
</style>
