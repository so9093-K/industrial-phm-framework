<script lang="ts">
  import {onMount, untrack} from "svelte";
  import type {Snapshot} from "../monitor";
  import {readRuntimeStatus, COMPONENT, CONDITION, type RuntimeStatus} from "../operations-status";
  import StatusNotice from "./StatusNotice.svelte";

  /** Whether the local services run and whether the stores were readable. Process state is
   * not sensor receipt or equipment condition. */
  type Props = {snapshot: Snapshot | null; storeState: "loading" | "ready" | "empty" | "failed"; storeError: string};
  let {snapshot, storeState, storeError}: Props = $props();
  let runtime: RuntimeStatus | null = $state(null);
  let runtimeState: "loading" | "ready" | "failed" = $state("loading");
  let request: AbortController | null = null;
  const clock = (at: string | null) => at ? new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"}) : "기록 없음";

  async function load() {
    request?.abort();
    const pending = new AbortController(); request = pending;
    runtimeState = "loading";
    try {
      const value = await readRuntimeStatus(pending.signal);
      if (!pending.signal.aborted) { runtime = value; runtimeState = "ready"; }
    } catch {
      if (!pending.signal.aborted) { runtime = null; runtimeState = "failed"; }
    }
  }
  // The page's own refresh reloads the stores; the services follow it.
  let previous = untrack(() => storeState);
  $effect(() => {
    const current = storeState;
    if (current === "loading" && previous !== "loading") untrack(() => void load());
    previous = current;
  });
  onMount(() => { void load(); return () => request?.abort(); });
</script>

<section class="ui-panel" aria-labelledby="runtime-title">
  <h2 id="runtime-title">실행 상태</h2>
  <p class="context">이 컴퓨터에서 도는 감독 프로세스·데이터 수집기·분석 실행기·Web 화면의 상태입니다. 센서 수신이나 설비 상태가 아닙니다.</p>
  {#if runtimeState === "loading"}
    <StatusNotice message="실행 상태를 확인하고 있습니다." />
  {:else if runtimeState === "failed" || !runtime}
    <StatusNotice kind="failure" title="실행 상태를 확인하지 못했습니다"
      message="서비스가 멈췄다는 뜻은 아닙니다. 터미널의 operations status·logs로 확인하세요." />
  {:else}
    <p class="summary" class:attention={!runtime.ready}>{runtime.ready ? "로컬 서비스가 실행 중입니다."
      : "로컬 서비스가 모두 준비됐는지 확인되지 않습니다. 아래 상태를 보고 필요하면 터미널 로그를 확인하세요."}</p>
    <ul class="components">
      <li><strong>감독 프로세스</strong><span>{CONDITION[runtime.supervisor.condition]}</span>
        <span class="context">마지막 응답 {clock(runtime.supervisor.heartbeatAt)}</span></li>
      {#each runtime.components as part (part.kind)}
        <!-- A running part without its own heartbeat (the Web screen) needs no "기록 없음" line. -->
        <li><strong>{COMPONENT[part.kind]}</strong><span>{CONDITION[part.condition]}</span>
          {#if part.heartbeatAt || part.condition !== "running"}<span class="context">마지막 응답 {clock(part.heartbeatAt)}</span>{/if}</li>
      {/each}
    </ul>
    <details>
      <summary>기술 상세</summary>
      <dl>
        <div><dt>조회 시각</dt><dd>{clock(runtime.assessedAt)}</dd></div>
        <div><dt>감독 프로세스 PID</dt><dd>{runtime.supervisor.pid ?? "없음"}</dd></div>
        {#each runtime.components as part (part.kind)}
          <div><dt>{COMPONENT[part.kind]} PID · 런타임 상태</dt><dd>{part.pid ?? "없음"} · {part.runtimeState ?? "기록 없음"}</dd></div>
        {/each}
      </dl>
    </details>
  {/if}
</section>

<section class="ui-panel" aria-labelledby="stores-title">
  <h2 id="stores-title">저장소 조회</h2>
  {#if storeState === "loading"}
    <StatusNotice message="저장소를 읽고 있습니다." />
  {:else if !snapshot}
    <StatusNotice kind="failure" title="저장소를 읽지 못했습니다" message={storeError + " 기록이 없다는 뜻은 아닙니다."} />
  {:else if snapshot.errorScopes.length}
    <StatusNotice kind="uncertain" message={"일부 저장소를 읽지 못했습니다: " + snapshot.errorScopes.join(", ") + ". 보이지 않는 관측·분석·검토 기록이 있을 수 있습니다."} />
  {:else if snapshot.systemReadUncertain}
    <StatusNotice kind="uncertain" message="저장소를 모두 읽었는지 확인하지 못했습니다." />
  {:else}
    <p>저장소를 모두 읽었습니다.</p>
  {/if}
  {#if snapshot}
  <dl class="counts">
    <div><dt>조회 시각</dt><dd>{clock(snapshot.assessedAt)}</dd></div>
    <div><dt>설비</dt><dd>{snapshot.assets.length}{snapshot.truncated ? " (일부)" : ""}</dd></div>
    <div><dt>분석 결과</dt><dd>{snapshot.analyses.available ? snapshot.analyses.records.length + (snapshot.analyses.truncated ? " (일부)" : "") : "확인 안 됨"}</dd></div>
    <div><dt>분석 결과 검토</dt><dd>{snapshot.reviewInbox.available ? snapshot.reviewInbox.reviews.length + (snapshot.reviewInbox.partial ? " (일부)" : "") : "확인 안 됨"}</dd></div>
  </dl>
  {/if}
</section>

<style>
  section { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  h2 { margin: 0; }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  .summary { font-weight: 650; }
  .summary.attention { color: var(--color-failure-ink); }
  .components { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
  .components { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
  .components li { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3);
    display: grid; gap: var(--space-1); min-width: 0; }
  .components li .context { font-size: var(--font-small); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  dl { display: grid; gap: var(--space-2); margin: var(--space-2) 0; }
  .counts { grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  dd { margin: 0; overflow-wrap: anywhere; }
  details dd { font-family: ui-monospace, monospace; }
</style>
