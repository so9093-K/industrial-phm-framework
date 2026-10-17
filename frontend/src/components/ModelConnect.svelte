<script lang="ts">
  import {onMount} from "svelte";
  import {explainWrite} from "../connections";
  import {WriteRejected} from "../writes";
  import {connectModel, modelTitle, noModelReason, readModelChoices, type ModelCandidate, type ModelChoices} from "../model-connect";

  /** Anomaly detection packages whose declared input fits this asset's own streams. Connecting
   * records only that the runner should analyze; scores appear once it has. */
  type Props = {assetId: string; writable: boolean; hasModel: boolean; onConnected: (bindingId: string) => void};
  let {assetId, writable, hasModel, onConnected}: Props = $props();
  let choices: ModelChoices | null = $state(null);
  let failed = $state(false);
  let busy = $state(false);
  let message = $state("");
  let messageFailed = $state(false);
  const key = (item: ModelCandidate) => item.packageId + "\n" + item.stream.sourceId + "\n" + (item.stream.pointId ?? "");

  function streamText(item: ModelCandidate): string {
    const parts = [item.stream.name];
    if (item.stream.channels) parts.push(item.stream.channels + "채널");
    if (item.stream.rateHz) parts.push((item.stream.rateHz / 1000).toLocaleString("ko-KR", {maximumFractionDigits: 1}) + " kHz");
    return parts.join(" · ");
  }
  async function load() {
    try {
      choices = await readModelChoices(assetId, new AbortController().signal);
      failed = false;
    } catch {
      failed = true;
    }
  }
  async function connect(item: ModelCandidate) {
    if (!writable || busy) return;
    busy = true; messageFailed = false; message = "모델을 연결하고 있습니다.";
    try {
      const bindingId = await connectModel(assetId, item, new AbortController().signal);
      message = "연결했습니다. 분석 실행기가 입력을 분석하면 점수가 나타납니다.";
      onConnected(bindingId);
    } catch (cause: unknown) {
      messageFailed = true;
      message = cause instanceof WriteRejected && cause.code === "source_control_conflict"
        ? "연결할 수 없습니다. 모델 입력 규격과 이 설비의 데이터가 맞는지 확인하세요." : explainWrite(cause);
      await load();
    } finally {
      busy = false;
    }
  }
  onMount(() => { void load(); });
</script>

{#snippet list(current: ModelChoices)}
  <ul class="models">
    {#each current.ready as item (key(item))}
      <li>
        <div class="text">
          <strong>{modelTitle(item.recipeId, item.stream.kind)}</strong>
          <span>{streamText(item)}</span>
          <span>{item.stream.stored ? "저장된 입력부터 분석합니다." : "관측 입력이 만들어지면 분석합니다."}</span>
          <span class="mono">모델 {item.recipeId}</span>
        </div>
        {#if writable}
          <button type="button" class="ui-button ui-button-primary" disabled={busy}
            aria-label={modelTitle(item.recipeId, item.stream.kind) + " 모델 연결"} onclick={() => void connect(item)}>연결</button>
        {/if}
      </li>
    {/each}
  </ul>
{/snippet}

{#if failed}
  <p class="context">연결할 수 있는 모델을 불러오지 못했습니다.</p>
{:else if choices}
  {#if hasModel}
    {#if choices.ready.length}
      <details>
        <summary>다른 모델 연결 ({choices.ready.length})</summary>
        {@render list(choices)}
      </details>
    {/if}
  {:else}
    <section class="connect" aria-labelledby="model-connect-title">
      <h3 id="model-connect-title">연결할 수 있는 이상 탐지 모델</h3>
      {#if choices.ready.length}
        <p class="context">연결하면 이 설비의 입력을 분석해 점수를 여기에 보여 줍니다.{writable ? "" : " 보기 전용이라 연결할 수 없습니다."}</p>
        {@render list(choices)}
      {:else}
        <p class="context">{noModelReason(choices)}</p>
        {#if choices.blocked.length}
          <details>
            <summary>입력 형식이 맞지 않는 모델 {choices.blocked.length}개</summary>
            <ul class="blocked">
              {#each choices.blocked as item (item.packageId)}<li>{modelTitle(item.recipeId, null)} · {item.recipeId} — {item.reason}</li>{/each}
            </ul>
          </details>
        {/if}
      {/if}
    </section>
  {/if}
  {#if message}<p class="message" class:failure={messageFailed} role={messageFailed ? "alert" : "status"}>{message}</p>{/if}
{/if}

<style>
  .connect { display: grid; gap: var(--space-3); margin-top: var(--space-4); }
  h3 { margin: 0; font-size: var(--font-section); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  .models { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  .models li { display: flex; flex-wrap: wrap; gap: var(--space-3); justify-content: space-between; align-items: center;
    border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3); }
  .text { display: grid; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
  .text span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .mono { font-family: ui-monospace, monospace; }
  .blocked { margin: 0; padding-inline-start: var(--space-5); color: var(--color-ink-muted); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  .message { margin-top: var(--space-3); }
  .message.failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
</style>
