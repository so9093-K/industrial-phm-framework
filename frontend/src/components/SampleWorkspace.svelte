<script lang="ts">
  import {onMount, tick, untrack} from "svelte";
  import {explainWrite, sampleCommand, type Sample} from "../connections";
  import {OutcomeUnknown} from "../writes";

  /** A synthetic motor and local OPC UA sample in its own workspace; this workspace never
   * changes. An unknown start or stop is checked again, never sent twice. */
  type Props = {writable: boolean};
  let {writable}: Props = $props();
  let sample: Sample | null = $state(null);
  let busy = $state(false);
  let message = $state("");
  let uncertain = $state(false);
  let confirmingStop = $state(false);
  let confirmBox: HTMLElement | null = $state(null);
  let asked = false;
  const openUrl = $derived.by((): string | null => {
    const current: Sample | null = sample;
    return current?.url ? current.url + "?" + new URLSearchParams({return_to: location.origin + location.pathname + "?page=system"}) : null;
  });

  async function command(action: "status" | "start" | "stop") {
    if (!writable || busy) return;
    busy = true; confirmingStop = false; uncertain = false;
    message = action === "status" ? "예시 상태를 확인하고 있습니다." : action === "start" ? "예시를 시작하고 있습니다." : "예시를 종료하고 있습니다.";
    try {
      sample = await sampleCommand(action, new AbortController().signal);
      message = sample.state === "running" ? "예시가 별도 작업공간에서 실행 중입니다." : "예시가 실행 중이지 않습니다. 이 작업공간은 바뀌지 않았습니다.";
    } catch (cause: unknown) {
      uncertain = true;
      message = cause instanceof OutcomeUnknown ? "결과를 확인하지 못했습니다. 다시 시작·종료하지 말고 상태만 다시 확인하세요." : explainWrite(cause);
    } finally {
      busy = false;
    }
  }
  async function askStop() { confirmingStop = true; await tick(); confirmBox?.focus(); }
  // Write permission arrives after the page opens; check the sample once it does.
  $effect(() => {
    if (writable && !asked) { asked = true; untrack(() => void command("status")); }
  });
  let panel: HTMLElement | null = $state(null);
  // "예시로 둘러보기" on an empty first screen lands here.
  onMount(() => { if (location.hash === "#sample") panel?.scrollIntoView({block: "start"}); });
</script>

<section class="ui-panel" id="sample" aria-labelledby="sample-title" bind:this={panel}>
  <h2 id="sample-title">예시로 둘러보기</h2>
  <p class="context">가상 3상 모터와 로컬 OPC UA 예시를 이 작업공간과 분리된 작업공간에서 실행합니다. 실제 설비 데이터가 아닙니다.</p>
  {#if !writable}
    <p class="context">보기 전용이라 예시를 시작할 수 없습니다. 운영을 시작하면 할 수 있습니다.</p>
  {:else}
    <div class="actions">
      {#if sample?.state === "stopped"}
        <button type="button" class="ui-button ui-button-primary" disabled={busy} onclick={() => void command("start")}>예시 시작</button>
      {:else if sample?.state === "running"}
        {#if openUrl}<a class="ui-button ui-button-primary" href={openUrl} target="_blank" rel="noopener noreferrer">예시 화면 열기 (새 탭)</a>{/if}
        {#if !confirmingStop}<button type="button" class="ui-button" disabled={busy} onclick={() => void askStop()}>예시 종료</button>{/if}
      {/if}
      <button type="button" class="ui-button" disabled={busy} onclick={() => void command("status")}>상태 다시 확인</button>
    </div>
    {#if confirmingStop}
      <div class="confirm" role="group" aria-labelledby="sample-stop-question" tabindex="-1" bind:this={confirmBox}>
        <p id="sample-stop-question">예시를 종료할까요? 예시 작업공간은 지우지 않습니다.</p>
        <div class="actions">
          <button type="button" class="ui-button ui-button-primary" onclick={() => void command("stop")}>종료하기</button>
          <button type="button" class="ui-button" onclick={() => confirmingStop = false}>취소</button>
        </div>
      </div>
    {/if}
    {#if message}<p class="message" class:uncertain role="status">{message}</p>{/if}
  {/if}
</section>

<style>
  section { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  h2 { margin: 0; }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  .actions { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
  .confirm { padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); display: grid; gap: var(--space-2); }
  .uncertain { background: var(--color-uncertain-surface); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
</style>
