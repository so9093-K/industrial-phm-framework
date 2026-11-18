<script lang="ts">
  import ChangeReview from "./ChangeReview.svelte";
  import ChangeReviewArchive from "./ChangeReviewArchive.svelte";
  import VibrationInvestigation from "./VibrationInvestigation.svelte";
  import type {VibrationChange} from "../vibration-findings";
  /** 판단하는 곳 하나: 이 변화의 판단·메모, AI에게 묻기, 이 설비의 이전 검토. */
  let {assetId, reviewKey, ai = null}: {assetId: string; reviewKey: string; ai?: {change: VibrationChange} | null} = $props();
  let draftNote: {sequence: number; text: string} | null = $state(null);
  let revision = $state(0);
  let archiveOpen = $state(false);
</script>

<aside class="decision" aria-label="이 변화의 판단">
  <section class="ui-panel" aria-labelledby="decision-title">
    <h2 id="decision-title">이 변화를 어떻게 할까요?</h2>
    {#key reviewKey}<ChangeReview {assetId} finding={{reviewKey}} {draftNote} onCommitted={() => revision++} />{/key}
  </section>
  {#if ai}
    {#key ai.change.reviewKey}<VibrationInvestigation {assetId} change={ai.change}
      onMemo={text => {draftNote = {sequence: (draftNote?.sequence ?? 0) + 1, text};}} />{/key}
  {/if}
  <details class="ui-panel archive" ontoggle={event => archiveOpen = event.currentTarget.open}>
    <summary>이 설비의 저장한 검토</summary>
    {#if archiveOpen}<ChangeReviewArchive {assetId} {revision} />{/if}
  </details>
</aside>

<style>
  .decision { display: grid; gap: var(--space-4); align-content: start; min-width: 0; }
  .decision > section { padding: var(--space-4) var(--space-5); display: grid; gap: var(--space-2); }
  h2 { margin: 0; font-size: var(--font-body); }
  .archive { padding: var(--space-3) var(--space-5); }
  .archive summary { cursor: pointer; font-weight: 650; color: var(--color-action); }
</style>
