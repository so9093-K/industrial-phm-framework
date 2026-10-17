<script lang="ts">
  import {tick} from "svelte";
  import {
    analyzeFile, analyzePhase, diagnoseOpcua, explainWrite, nextStep, otherActions, receiveFile,
    requestCollection, setLifecycle, startHistory, waitForHistory, ACTION_LABEL, HistoryFailed,
    type Action, type SavedAnalysis,
  } from "../connections";
  import {receiptText, JOB, LIFECYCLE, type Source, type Sources} from "../operations-status";
  import {assetTabUrl, routeUrl} from "../routes";
  import {OutcomeUnknown, WriteRejected} from "../writes";
  import StatusNotice from "./StatusNotice.svelte";

  /** Registered connections, what each last received and the one next step that moves it
   * forward. Every action is its own server write with its own result. */
  type Props = {
    sources: Sources | null; loadState: "loading" | "ready" | "failed"; writable: boolean;
    analyzed: Set<string>; onReload: () => Promise<void>; onAnalyzed: (sourceId: string) => void;
  };
  let {sources, loadState, writable, analyzed, onReload, onAnalyzed}: Props = $props();
  let busy: Record<string, boolean> = $state({});
  let messages: Record<string, {text: string; kind: "information" | "uncertain" | "failure"; analysis?: SavedAnalysis}> = $state({});
  let confirming: Record<string, Action | null> = $state({});
  let confirmBox: HTMLElement | null = $state(null);
  const clock = (at: string | null) => at ? new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"}) : "기록 없음";
  const CONFIRM: Partial<Record<Action, string>> = {
    pause: "일시정지하면 이 연결의 데이터를 읽지 않습니다. 저장된 기록은 그대로입니다.",
    stop: "수집 중지는 원하는 상태만 기록합니다. 이미 받은 데이터는 그대로입니다.",
  };
  const investigations = (assetId: string) => routeUrl({page: "investigations", assetId, tab: "summary", method: null, data: null});

  function say(sourceId: string, text: string, kind: "information" | "uncertain" | "failure" = "information", analysis?: SavedAnalysis) {
    messages = {...messages, [sourceId]: {text, kind, analysis}};
  }
  /** Refusals that mean something specific for an analysis. */
  function analysisRefusal(action: Action, cause: unknown): string {
    if (cause instanceof WriteRejected && cause.status === 409) return action === "phase"
      ? "분석할 수 없습니다. 사용 중인 파일 연결, 저장된 측정 이력, 등록한 전압·전류와 R/S/T 근거를 확인하세요."
      : "분석할 수 없습니다. 사용 중인 파일 연결, 파일 읽기 확인과 1MiB 이하 원본인지 확인하세요.";
    if (cause instanceof WriteRejected && cause.status === 400) return action === "phase"
      ? "3상 분석에 쓸 표본이 없습니다. 같은 시각의 R/S/T 측정값이 모두 있는지 확인하세요."
      : "분석할 수 없습니다. 시간대가 있는 시각, 서로 다른 값이 있는 표본 두 개 이상, 유한한 수치를 확인하세요.";
    return explainWrite(cause);
  }
  async function ask(source: Source, action: Action) {
    if (CONFIRM[action]) { confirming = {...confirming, [source.sourceId]: action}; await tick(); confirmBox?.focus(); return; }
    await run(source, action);
  }
  async function run(source: Source, action: Action) {
    const id = source.sourceId;
    if (!writable || busy[id]) return;
    confirming = {...confirming, [id]: null};
    busy = {...busy, [id]: true};
    const signal = new AbortController().signal;
    let reloaded = false;
    say(id, ACTION_LABEL[action] + " 요청을 보내고 있습니다.");
    try {
      if (action === "activate" || action === "pause") {
        await setLifecycle(id, action === "activate" ? "active" : "paused", signal);
        say(id, action === "activate" ? "사용 중으로 바꿨습니다. 연결이나 수신을 확인한 것은 아닙니다." : "일시정지했습니다.");
      } else if (action === "collect" || action === "stop") {
        await requestCollection(id, action === "collect" ? "running" : "stopped", signal);
        say(id, (action === "collect" ? "수집 시작" : "수집 중지") + "을 요청했습니다. 실제 수신은 위 상태로 확인하세요.");
      } else if (action === "receive" || action === "diagnose") {
        const result = await (action === "receive" ? receiveFile : diagnoseOpcua)(id, signal);
        if (result.accepted) say(id, (action === "receive" ? "파일을 읽었습니다" : "한 번 읽어 연결을 확인했습니다") + " · " + clock(result.receivedAt));
        else say(id, "읽지 못했습니다 (" + (result.failure ?? "원인 미확인") + "). 이전에 받은 기록과 혼동하지 마세요.", "failure");
      } else if (action === "store") {
        const startedAt = await startHistory(id, signal);
        const stored = await waitForHistory(id, startedAt, signal, (seconds, known) =>
          say(id, "측정 이력을 저장하고 있습니다 · " + seconds + "초" + (known ? "" : " · 상태 조회 실패, 계속 확인합니다"), known ? "information" : "uncertain"));
        say(id, "측정 이력을 저장했습니다 · 측정값 " + stored.eventCount.toLocaleString("ko-KR") + "개");
      } else {
        const saved = await (action === "phase" ? analyzePhase : analyzeFile)(id, signal);
        await onReload(); reloaded = true;
        onAnalyzed(id);
        say(id, (action === "phase" ? "3상 불평형 분석" : "신호 통계 분석") + "을 저장했습니다.", "information", saved);
      }
    } catch (cause: unknown) {
      const text = cause instanceof HistoryFailed ? cause.message
        : action === "analyze" || action === "phase" ? analysisRefusal(action, cause) : explainWrite(cause);
      say(id, text, cause instanceof OutcomeUnknown ? "uncertain" : "failure");
    } finally {
      busy = {...busy, [id]: false};
    }
    if (!reloaded) await onReload();
  }
</script>

<section class="ui-panel" aria-labelledby="connections-title">
  <h2 id="connections-title">등록한 연결</h2>
  <p class="context">등록한 데이터 출처와 마지막으로 받은 시각입니다. 등록됐다고 데이터를 받은 것은 아닙니다.</p>
  {#if !writable}
    <p class="context">보기 전용이라 연결 상태를 바꾸거나 분석을 실행할 수 없습니다. 운영을 시작하면 할 수 있습니다.</p>
  {/if}
  {#if loadState === "loading" && !sources}
    <StatusNotice message="데이터 연결을 확인하고 있습니다." />
  {:else if loadState === "failed" || !sources}
    <StatusNotice kind="failure" title="데이터 연결 목록을 불러오지 못했습니다" message="연결이 없다는 뜻은 아닙니다." />
  {:else}
    {#if sources.readErrors.length || sources.liveErrors.length}
      <StatusNotice kind="uncertain" message={"일부 연결 정보를 읽지 못했습니다 (" + [...sources.readErrors, ...sources.liveErrors].join(", ") + "). 보이는 상태가 전부가 아닐 수 있습니다."} />
    {/if}
    {#if sources.truncated}
      <StatusNotice kind="uncertain" message="연결이 많아 일부만 보여 줍니다." />
    {/if}
    {#if !sources.items.length}
      <p class="context">아직 등록한 데이터 연결이 없습니다. 위에서 CSV 파일로 시작하세요.</p>
    {:else}
      <ul class="sources">
        {#each sources.items as source (source.sourceId)}
          {@const step = nextStep(source, analyzed.has(source.sourceId))}
          {@const others = otherActions(source, step.action)}
          {@const message = messages[source.sourceId]}
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
            {#if source.job}
              <p class="context">{JOB[source.job.state] ?? source.job.state}{source.job.eventCount !== null ? " · 측정값 " + source.job.eventCount.toLocaleString("ko-KR") + "개" : ""}</p>
            {/if}
            <div class="next">
              <p><strong>다음 단계</strong> · {step.text}</p>
              {#if step.action && writable}
                <button type="button" class="ui-button ui-button-primary" disabled={busy[source.sourceId]}
                  onclick={() => void ask(source, step.action!)}>{ACTION_LABEL[step.action]}</button>
              {/if}
            </div>
            {#if others.length && writable}
              <details>
                <summary>다른 작업 ({others.length})</summary>
                <div class="actions">
                  {#each others as action (action)}
                    <button type="button" class="ui-button" disabled={busy[source.sourceId]}
                      onclick={() => void ask(source, action)}>{ACTION_LABEL[action]}</button>
                  {/each}
                </div>
              </details>
            {/if}
            {#if confirming[source.sourceId]}
              {@const action = confirming[source.sourceId]!}
              <div class="confirm" role="group" aria-labelledby={"confirm-" + source.sourceId} tabindex="-1" bind:this={confirmBox}>
                <p id={"confirm-" + source.sourceId}>{ACTION_LABEL[action]}할까요? {CONFIRM[action]}</p>
                <div class="actions">
                  <button type="button" class="ui-button ui-button-primary" onclick={() => void run(source, action)}>{ACTION_LABEL[action]}</button>
                  <button type="button" class="ui-button" onclick={() => confirming = {...confirming, [source.sourceId]: null}}>취소</button>
                </div>
              </div>
            {/if}
            {#if message}
              <p class="message" class:uncertain={message.kind === "uncertain"} class:failure={message.kind === "failure"}
                role={message.kind === "failure" ? "alert" : "status"}>{message.text}
                {#if message.analysis}<a href={investigations(message.analysis.assetId)}>분석 기록에서 보기 →</a>{/if}</p>
            {/if}
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
                {#if source.phaseBindings}<div><dt>등록한 3상 역할</dt><dd>{source.phaseBindings}개</dd></div>{/if}
              </dl>
            </details>
          </article></li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  section { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  h2 { margin: 0; }
  h3 { margin: 0; font-size: var(--font-section); overflow-wrap: anywhere; }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2) var(--space-4); align-items: center; }
  .sources { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
  .sources > li { min-width: 0; }
  article { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-4);
    display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
  .badge { font-weight: 700; border: 1px solid var(--color-ink); border-radius: 999px; padding: 2px var(--space-3); font-size: var(--font-small); }
  .next { display: grid; gap: var(--space-2); justify-items: start; padding: var(--space-3); border-radius: var(--radius-control);
    background: var(--color-surface-selected); }
  .actions { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-2); }
  .confirm { padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  .message a { margin-inline-start: var(--space-2); }
  .uncertain { background: var(--color-uncertain-surface); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  .failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  dl { display: grid; gap: var(--space-2); margin: var(--space-2) 0; }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  dd { margin: 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
</style>
