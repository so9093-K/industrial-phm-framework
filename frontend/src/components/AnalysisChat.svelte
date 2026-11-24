<script lang="ts">
  import {untrack} from "svelte";
  import {resolveFocus} from "../analysis-chat";
  import {carriedConversation, newChangeConversation} from "../change-investigation";
  import type {EvidenceFocus} from "../change-evidence";
  import type {AnalysisReadout} from "../analysis-readout.svelte";
  import {playbackScope} from "../record-playback";
  import ChangeInvestigation from "./ChangeInvestigation.svelte";

  /** 분석 화면 옆의 AI 조사. 조사 화면에서 넘어온 특이사항에 대해 같은 대화를 이어 묻고, AI는 이 화면이
   * 보여 주는 수치(view)도 함께 읽는다. 대화 번호는 주소(chat)에 남겨, 다른 분석 탭으로 옮겨도 이어진다. */
  let {assetId, view, viewTitle, readout, onClose}: {assetId: string; view: string | null; viewTitle: string; readout: AnalysisReadout | null; onClose: () => void} = $props();
  const search = untrack(() => location.search);
  const scope = playbackScope(search);
  const conversation = carriedConversation(search) ?? newChangeConversation();
  if (!carriedConversation(search)) {
    const url = new URL(location.href);
    url.searchParams.set("chat", conversation);
    history.replaceState(history.state, "", url.pathname + url.search + url.hash);
  }
  let focus: EvidenceFocus | null = $state(null), status = $state<"loading" | "ready" | "missing">("loading");
  $effect(() => {
    const request = new AbortController();
    void resolveFocus(assetId, search, scope, request.signal)
      .then(found => { if (!request.signal.aborted) { focus = found; status = found ? "ready" : "missing"; } })
      .catch(() => { if (!request.signal.aborted) status = "missing"; });
    return () => request.abort();
  });
</script>

{#if focus}
  <ChangeInvestigation {assetId} {focus} {scope} carried={conversation} {view} {viewTitle} {readout} {onClose}/>
{:else}
  <p class="note">{status === "loading" ? "대화를 불러오는 중" : "이 분석의 특이사항을 찾지 못했습니다. 변화 조사에서 다시 열어 주세요."}</p>
{/if}

<style>
  .note { margin: 0; padding: var(--space-3); font-size: var(--font-small); color: var(--color-ink-muted);
    border: 1px solid var(--color-border); border-radius: 10px; background: var(--color-surface); }
</style>
