<script lang="ts">
  import type {BriefingProjection} from "../outlook-briefings";
  import OutlookBriefings from "./OutlookBriefings.svelte";
  let {projection, onEvidenceChanged}: {
    projection: BriefingProjection; onEvidenceChanged: () => void;
  } = $props();
  let open = $state(false);
</script>

<details class="optional-ai" bind:open>
  <summary>AI 해설·추가 질문</summary>
  {#if open}<OutlookBriefings {projection} {onEvidenceChanged} />{/if}
</details>
