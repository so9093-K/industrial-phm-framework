<script lang="ts">
  import ChangeReview from "./ChangeReview.svelte";
  import ChangeReviewArchive from "./ChangeReviewArchive.svelte";
  import ChangeInvestigation from "./ChangeInvestigation.svelte";
  import type {EvidenceFocus} from "../change-evidence";
  import TaskDialog from "./TaskDialog.svelte";
  let {assetId, reviewKey, focus = null, onCommitted,onInvestigate}: {assetId: string; reviewKey: string; focus?: EvidenceFocus | null;
    onCommitted?: () => void;onInvestigate?:()=>void} = $props();
  let draftNote: {sequence: number; text: string} | null = $state(null);
  let revision = $state(0);
  let archiveOpen = $state(false);
  let reviewOpen = $state(false), aiOpen = $state(false);
</script>

{#snippet review()}
  {#key reviewKey}<ChangeReview {assetId} finding={{reviewKey}} {draftNote} onCommitted={() => {revision++; onCommitted?.();}} />{/key}
  <details class="archive" ontoggle={event => archiveOpen = event.currentTarget.open}>
    <summary>저장된 검토</summary>
    {#if archiveOpen}<ChangeReviewArchive {assetId} {revision} />{/if}
  </details>
{/snippet}
<div class="decision" aria-label="이 변화로 이어서 할 일">
  {#if focus}<button type="button" class="ui-button" onclick={() => {onInvestigate?.();aiOpen = true;}}>AI 해석</button>{/if}
  <button type="button" class="ui-button" onclick={() => {onInvestigate?.();reviewOpen = true;}}>판단·메모 남기기</button>
  <TaskDialog title="이 변화의 판단·메모" bind:open={reviewOpen}>{@render review()}</TaskDialog>
  {#if focus}
    <TaskDialog bind:open={aiOpen} title="선택한 변화의 AI 해석">
      {#key reviewKey}<ChangeInvestigation {assetId} {focus} active={aiOpen}
        onMemo={text => {draftNote = {sequence: (draftNote?.sequence ?? 0) + 1, text}; aiOpen = false; reviewOpen = true;}} />{/key}
    </TaskDialog>
  {/if}
</div>

<style>
  .decision { display: flex; gap: var(--space-2); flex-wrap: wrap; min-width: 0; }
  .archive summary { cursor: pointer; font-weight: 650; color: var(--color-action); }
</style>
