<script lang="ts">
  import {onMount} from "svelte";
  import {bandName, bandRange, percent} from "../record-findings";
  import {readModelOperation, unlearnedText, type ModelOperation} from "../model-operation";
  /** Excesses of a time-window model per operating level, beside its reference period's mix. */
  let {bindingId}: {bindingId: string} = $props();
  let operation: ModelOperation | null = $state(null);
  onMount(() => {
    const request = new AbortController();
    void readModelOperation(bindingId, request.signal).then(value => { operation = value; }).catch(() => { operation = null; });
    return () => request.abort();
  });
  const told = $derived(operation ? unlearnedText(operation) : null);
</script>

{#if operation && operation.windows.length}
  {@const shown = operation}
  <section class="operation" aria-labelledby={"model-operation-" + bindingId}>
    <h3 id={"model-operation-" + bindingId}>운전 상태별 기준 초과 <small>{shown.label} 기준</small></h3>
    {#if told}<p class="told">{told}</p>{/if}
    <div class="table"><table>
      <thead><tr><th scope="col">상태</th><th scope="col">전류</th><th scope="col">모델 기준 기간</th><th scope="col">분석한 창</th><th scope="col">기준 초과</th></tr></thead>
      <tbody>{#each shown.windows as row (row.band)}
        <tr><th scope="row">{bandName(shown.names, row.band)}</th><td>{bandRange(shown.names, row.band)}</td>
          <td>{shown.reference?.shares ? percent(shown.reference.shares[row.band]) : "기록 없음"}</td>
          <td>{row.count.toLocaleString("ko-KR")}</td><td>{row.exceeded.toLocaleString("ko-KR")} ({percent(row.exceeded / row.count)})</td></tr>
      {/each}</tbody>
    </table></div>
    <p class="note">창마다 가장 오래 머문 운전 상태로 나눴습니다.{#if shown.unplaced} 전류 측정이 없어 나누지 못한 창 {shown.unplaced.toLocaleString("ko-KR")}개는 표에 없습니다.{/if}</p>
  </section>
{/if}

<style>
  .operation { display: grid; gap: var(--space-2); margin: var(--space-3) 0; padding: var(--space-3) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  h3 { margin: 0; font-size: var(--font-body); }
  h3 small { font-weight: 400; color: var(--color-ink-muted); font-size: var(--font-small); }
  .told { margin: 0; overflow-wrap: anywhere; }
  .table { overflow-x: auto; }
  table { border-collapse: collapse; font-size: var(--font-small); font-variant-numeric: tabular-nums; }
  th, td { padding: var(--space-1) var(--space-2) var(--space-1) 0; text-align: right; white-space: nowrap; }
  th:first-child, td:nth-child(2) { text-align: left; }
  thead th { color: var(--color-ink-muted); font-weight: 400; }
  .note { margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); }
</style>
