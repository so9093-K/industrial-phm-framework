<script lang="ts">
  import {onMount} from "svelte";
  import {explainWrite} from "../connections";
  import {kstInstant} from "../electrical-condition";
  import {readSignalNames, signalName, type SignalNames} from "../history";
  import {OutcomeUnknown, WriteForbidden, WriteRejected} from "../writes";
  import {
    buildHistoryModel, MAX_SIGNALS, readHistoryStreams, referencePeriod, streamLabel, WINDOW_CHOICES,
    type HistoryStream, type ReferenceChoice,
  } from "../history-model";
  import StatusNotice from "./StatusNotice.svelte";

  /** Build an Isolation Forest from a period of this asset's own stored record and bind it
   * (ADR-0032). Shown only for assets with stored history; nothing happens without the press. */
  type Props = {assetId: string; writable: boolean; hasModel: boolean; onBuilt: (bindingId: string, notice: string) => void};
  let {assetId, writable, hasModel, onBuilt}: Props = $props();
  let load: "loading" | "failed" | "ready" = $state("loading");
  let streams: HistoryStream[] = $state([]);
  let names: SignalNames | null = $state(null);
  let chosen: string[] = $state([]);
  let streamIndex = $state(0);
  const stream = $derived(streams[streamIndex] ?? null);
  let choice: ReferenceChoice = $state("first-30");
  let from = $state(""), to = $state("");
  let windowSeconds = $state(600);
  let busy = $state(false);
  let message = $state("");
  let failed = $state(false);
  const clock = (iso: string) => new Date(iso).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});

  let request: AbortController | null = null;
  function readStreams() {
    request?.abort();
    const current = request = new AbortController();
    load = "loading";
    void readHistoryStreams(assetId, current.signal).then((value) => {
      if (current.signal.aborted) return;
      streams = value; load = "ready"; pick(0);
    }).catch(() => { if (!current.signal.aborted) load = "failed"; });
  }
  onMount(() => {
    readStreams();
    // Signal names only label the choices; without them the stored IDs are shown.
    void readSignalNames(assetId).then((value) => { if (request && !request.signal.aborted) names = value; }).catch(() => {});
    return () => request?.abort();
  });
  /** A stream offers only its own signals and period. */
  function pick(index: number) {
    streamIndex = index; chosen = (streams[index]?.channels ?? []).slice(0, 4);
  }

  function toggle(channel: string, on: boolean) {
    chosen = on ? [...chosen, channel].slice(0, MAX_SIGNALS) : chosen.filter((item) => item !== channel);
  }
  async function build() {
    if (!stream || !writable || busy || !chosen.length) return;
    busy = true; failed = false; message = "기준 기간의 기록을 읽고 모델을 학습하고 있습니다.";
    try {
      const period = referencePeriod(choice, stream,
        choice === "custom" ? {from: from && kstInstant(from), to: to && kstInstant(to)} : null);
      const result = await buildHistoryModel({assetId, stream, channels: chosen,
        from: period.from, to: period.to, windowSeconds}, new AbortController().signal);
      if (!result.built) { failed = true; message = result.reason; return; }
      message = result.reused
        ? "같은 신호·기준 기간·구간 길이로 만든 모델이 이미 있어 그 모델을 연결했습니다 · 기준 구간 "
          + result.referenceWindows + "개로 학습한 모델입니다."
        : "모델을 만들어 연결했습니다 · 기준 구간 " + result.referenceWindows + "개로 학습"
          + (result.skippedWindows ? " (값이 부족한 구간 " + result.skippedWindows + "개 제외)" : "")
          + ". 분석 실행기가 기록을 구간마다 채점하면 점수가 나타납니다.";
      onBuilt(result.bindingId, message);
    } catch (cause: unknown) {
      failed = true;
      message = cause instanceof WriteRejected || cause instanceof WriteForbidden || cause instanceof OutcomeUnknown
        ? explainWrite(cause) : cause instanceof Error ? cause.message : "모델을 만들지 못했습니다.";
    } finally {
      busy = false;
    }
  }
</script>

{#if load === "failed"}
  <StatusNotice kind="failure" title="모델 만들기에 쓸 기록 정보를 읽지 못했습니다"
    message="저장된 기록의 신호와 기간을 불러오지 못해 모델 만들기를 보여 줄 수 없습니다. 기록이 없다는 뜻은 아닙니다."
    actionLabel="다시 불러오기" onAction={readStreams} />
{:else if stream}
  <details class="build" open={!hasModel}>
    <summary>{hasModel ? "이 설비 데이터로 다른 모델 만들기" : "이 설비 데이터로 모델 만들기"}</summary>
    <p class="context">고른 기준 기간을 평소 모습으로 삼아 Isolation Forest 모델을 학습하고 이 설비에 연결합니다.
      이후 기록을 구간마다 채점해 그 모델의 기준을 넘는지 보여 줍니다.</p>
    <fieldset>
      <legend>신호 (최대 {MAX_SIGNALS}개)</legend>
      {#each stream.channels as channel (channel)}
        <label class="check"><input type="checkbox" checked={chosen.includes(channel)} disabled={busy}
          onchange={(event) => toggle(channel, event.currentTarget.checked)} /> {signalName(names, channel)}</label>
      {/each}
    </fieldset>
    {#if streams.length > 1}
      <label class="field">데이터 출처<select value={streamIndex} disabled={busy}
        onchange={(event) => pick(Number(event.currentTarget.value))}>
        {#each streams as item, index (index)}<option value={index}>{streamLabel(item)}</option>{/each}</select></label>
    {/if}
    <fieldset>
      <legend>기준 기간 · 기록 {clock(stream.startAt)} ~ {clock(stream.endAt)}</legend>
      <label class="check"><input type="radio" bind:group={choice} value="first-30" disabled={busy} /> 기록 처음 30%</label>
      <label class="check"><input type="radio" bind:group={choice} value="first-50" disabled={busy} /> 기록 처음 50%</label>
      <label class="check"><input type="radio" bind:group={choice} value="custom" disabled={busy} /> 직접 지정 (KST)</label>
      {#if choice === "custom"}
        <div class="period">
          <label class="field">시작<input type="datetime-local" bind:value={from} disabled={busy} /></label>
          <label class="field">끝<input type="datetime-local" bind:value={to} disabled={busy} /></label>
        </div>
      {/if}
    </fieldset>
    <label class="field">구간 길이<select bind:value={windowSeconds} disabled={busy}>
      {#each WINDOW_CHOICES as item (item.seconds)}<option value={item.seconds}>{item.label}</option>{/each}</select></label>
    <p class="context">기준 기간은 비교 기준일 뿐 정상으로 확인된 기간이 아니며, 만든 모델은 현장 검증을 거친 모델이 아닙니다.</p>
    {#if writable}
      <button type="button" class="ui-button ui-button-primary" disabled={busy || !chosen.length} onclick={() => void build()}>
        {busy ? "만드는 중" : "이 기간으로 모델 만들기"}</button>
    {:else}
      <p class="context">보기 전용이라 모델을 만들 수 없습니다.</p>
    {/if}
    {#if message}<p class="message" class:failed role={failed ? "alert" : "status"}>{message}</p>{/if}
  </details>
{/if}

<style>
  .build { display: grid; gap: var(--space-3); margin-top: var(--space-4); padding: var(--space-3) var(--space-4);
    border: 1px solid var(--color-border); border-radius: var(--radius-panel); min-width: 0; }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); }
  fieldset { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); border: 0; padding: 0; margin: 0; min-width: 0; }
  legend { font-weight: 650; margin-bottom: var(--space-2); overflow-wrap: anywhere; }
  .check { display: inline-flex; gap: var(--space-1); align-items: center; }
  .field { display: grid; gap: var(--space-1); }
  .period { display: flex; flex-wrap: wrap; gap: var(--space-3); flex-basis: 100%; }
  .context { margin: 0; color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .message { margin: 0; overflow-wrap: anywhere; }
  .failed { color: var(--color-failure-ink); }
  button { justify-self: start; }
</style>
