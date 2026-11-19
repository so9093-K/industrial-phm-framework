<script lang="ts">
  import ChangeReview from "./ChangeReview.svelte";
  import ChangeReviewArchive from "./ChangeReviewArchive.svelte";
  import VibrationInvestigation from "./VibrationInvestigation.svelte";
  import type {VibrationChange} from "../vibration-findings";
  import TaskDialog from "./TaskDialog.svelte";
  /** inline: 판단 양식을 근거(그래프) 옆에 바로 펼친다. 아니면 버튼으로 연다(좁은 화면). */
  let {assetId, reviewKey, ai = null, inline = false, onCommitted}: {assetId: string; reviewKey: string; ai?: {change: VibrationChange;bindingId:string} | null;
    inline?: boolean; onCommitted?: () => void} = $props();
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
<div class="decision" class:inline aria-label="이 변화로 이어서 할 일">
  {#if inline}{@render review()}{/if}
  {#if ai}<button type="button" class="ui-button" onclick={() => aiOpen = true}>AI 해석</button>{/if}
  {#if !inline}
    <button type="button" class="ui-button" onclick={() => reviewOpen = true}>판단·메모 남기기</button>
    <TaskDialog title="이 변화의 판단·메모" bind:open={reviewOpen}>{@render review()}</TaskDialog>
  {/if}
  {#if ai}
    <TaskDialog bind:open={aiOpen} title="선택한 변화의 AI 해석">
      {#key ai.change.reviewKey}<VibrationInvestigation {assetId} change={ai.change} bindingId={ai.bindingId} active={aiOpen}
        onMemo={text => {draftNote = {sequence: (draftNote?.sequence ?? 0) + 1, text}; aiOpen = false; reviewOpen = !inline;}} />{/key}
    </TaskDialog>
  {/if}
</div>

<style>
  .decision { display: flex; gap: var(--space-2); flex-wrap: wrap; min-width: 0; }
  .decision.inline { display: grid; gap: var(--space-3); }
  .archive summary { cursor: pointer; font-weight: 650; color: var(--color-action); }
</style>
