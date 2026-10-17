<script lang="ts">
  import {onMount, untrack} from "svelte";
  import type {Snapshot} from "../monitor";
  import {
    readRuntimeStatus, readSources, receiptText, COMPONENT, CONDITION, JOB, LIFECYCLE,
    type RuntimeStatus, type Sources,
  } from "../operations-status";
  import {assetTabUrl} from "../routes";
  import StatusNotice from "./StatusNotice.svelte";

  /** Whether the local services run, which data connections exist and what they last
   * received, and whether the stores were readable. Changes stay on the previous screen. */
  type Props = {snapshot: Snapshot | null; storeState: "loading" | "ready" | "empty" | "failed"; storeError: string};
  let {snapshot, storeState, storeError}: Props = $props();
  let runtime: RuntimeStatus | null = $state(null);
  let runtimeState: "loading" | "ready" | "failed" = $state("loading");
  let sources: Sources | null = $state(null);
  let sourceState: "loading" | "ready" | "failed" = $state("loading");
  let request: AbortController | null = null;
  const clock = (at: string | null) => at ? new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"}) : "기록 없음";

  async function load() {
    request?.abort();
    const pending = new AbortController(); request = pending;
    runtimeState = "loading"; sourceState = "loading";
    await Promise.all([
      readRuntimeStatus(pending.signal).then((value) => {
        if (!pending.signal.aborted) { runtime = value; runtimeState = "ready"; }
      }).catch(() => { if (!pending.signal.aborted) { runtime = null; runtimeState = "failed"; } }),
      readSources(pending.signal).then((value) => {
        if (!pending.signal.aborted) { sources = value; sourceState = "ready"; }
      }).catch(() => { if (!pending.signal.aborted) { sources = null; sourceState = "failed"; } }),
    ]);
  }
  // The page's own refresh reloads the stores; the services and connections follow it.
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
        <li><strong>{COMPONENT[part.kind]}</strong><span>{CONDITION[part.condition]}</span>
          <span class="context">마지막 응답 {clock(part.heartbeatAt)}</span></li>
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

<section class="ui-panel" aria-labelledby="sources-title">
  <h2 id="sources-title">데이터 연결</h2>
  <p class="context">등록한 데이터 출처와 마지막으로 받은 시각입니다. 등록됐다고 데이터를 받은 것은 아닙니다.
    연결 등록·수집 시작과 중지·분석 실행은 아직 <a href="/web/#connect">이전 화면의 데이터 연결</a>에서 합니다.</p>
  {#if sourceState === "loading"}
    <StatusNotice message="데이터 연결을 확인하고 있습니다." />
  {:else if sourceState === "failed" || !sources}
    <StatusNotice kind="failure" title="데이터 연결 목록을 불러오지 못했습니다" message="연결이 없다는 뜻은 아닙니다." />
  {:else}
    {#if sources.readErrors.length || sources.liveErrors.length}
      <StatusNotice kind="uncertain" message={"일부 연결 정보를 읽지 못했습니다 (" + [...sources.readErrors, ...sources.liveErrors].join(", ") + "). 보이는 상태가 전부가 아닐 수 있습니다."} />
    {/if}
    {#if sources.truncated}
      <StatusNotice kind="uncertain" message="연결이 많아 일부만 보여 줍니다." />
    {/if}
    {#if !sources.items.length}
      <p class="context">아직 등록한 데이터 연결이 없습니다. <a href="/web/#connect">데이터 연결하기 →</a></p>
    {:else}
      <ul class="sources">
        {#each sources.items as source (source.sourceId)}
          <li><article aria-labelledby={"source-" + source.sourceId}>
            <div class="head">
              <h3 id={"source-" + source.sourceId}>{source.name}</h3>
              <span class="badge">{receiptText(source)}</span>
            </div>
            <p class="context">{source.type === "opcua" ? "OPC UA" : "CSV 파일"} · 설비 {source.assetId}
              {source.pointId ? " · 측정 위치 " + source.pointId : ""} · {source.lifecycle ? LIFECYCLE[source.lifecycle] ?? source.lifecycle : "관리 상태 미확인"}</p>
            <p>마지막 수신 {clock(source.live ? source.live.receivedAt : source.lastAcceptedAt)}
              {#if source.lastObservedAt} · 원래 측정 시각 {clock(source.lastObservedAt)}{/if}</p>
            {#if source.type === "file" && source.lastObservedAt}
              <p class="context">파일을 읽은 시각과 원래 측정한 시각은 다를 수 있습니다. 과거 측정 기록이 지금 설비 상태를 뜻하지는 않습니다.</p>
            {/if}
            {#if source.live?.desired}
              <p class="context">수집 요청 {source.live.desired === "running" ? "시작" : "중지"} · 요청이 기록됐을 뿐 실제 수집 여부는 위 상태로 판단합니다.</p>
            {/if}
            {#if source.job}<p class="context">{JOB[source.job.state] ?? source.job.state}</p>{/if}
            <p class="links"><a href={assetTabUrl(source.assetId, "signals")}>측정 신호 보기 →</a></p>
            <details>
              <summary>기술 상세</summary>
              <dl>
                <div><dt>데이터 연결 ID</dt><dd>{source.sourceId}</dd></div>
                {#if source.live}
                  <div><dt>OPC UA 세션 마지막 기록</dt><dd>{source.live.session ?? "기록 없음"}</dd></div>
                  <div><dt>이력 저장 마지막 반영</dt><dd>{clock(source.live.historyCommittedAt)}</dd></div>
                {/if}
                {#if source.job}<div><dt>이력 저장 작업</dt><dd>{source.job.state} · 시작 {clock(source.job.startedAt)} · 종료 {clock(source.job.finishedAt)}</dd></div>{/if}
              </dl>
            </details>
          </article></li>
        {/each}
      </ul>
    {/if}
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
  h3 { margin: 0; font-size: var(--font-section); overflow-wrap: anywhere; }
  p { margin: 0; overflow-wrap: anywhere; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2) var(--space-4); align-items: center; }
  .context { color: var(--color-ink-muted); }
  .summary { font-weight: 650; }
  .summary.attention { color: var(--color-failure-ink); }
  .components, .sources { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
  .components { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
  .components li { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3);
    display: grid; gap: var(--space-1); min-width: 0; }
  .components li .context { font-size: var(--font-small); }
  .sources > li { min-width: 0; }
  .sources article { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-4);
    display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
  .badge { font-weight: 700; border: 1px solid var(--color-ink); border-radius: 999px; padding: 2px var(--space-3); font-size: var(--font-small); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  dl { display: grid; gap: var(--space-2); margin: var(--space-2) 0; }
  .counts { grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  dd { margin: 0; overflow-wrap: anywhere; }
  details dd { font-family: ui-monospace, monospace; }
</style>
