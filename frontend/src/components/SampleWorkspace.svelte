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
    return current?.url ? current.url + "?" + new URLSearchParams({return_to: location.origin + location.pathname + "?page=system",
      ...(current.scenario==="bearing"||current.scenario==="xjtu"?{page:"assets",monitor_asset:current.assetId??"demo-bearing-change"}:{})}) : null;
  });

  async function command(action: "status" | "start" | "stop", scenario: "bearing" | "live" | "xjtu" = "bearing") {
    if (!writable || busy) return;
    busy = true; confirmingStop = false; uncertain = false;
    message = action === "status" ? "예시 상태를 확인하고 있습니다." : action === "start"
      ? scenario==="xjtu"?"준비된 XJTU-SY 실기록과 두 모델의 분석을 열고 있습니다.":scenario==="bearing"?"별도 작업공간에서 합성 참조로 두 모델을 학습하고 진동 기록을 분석합니다. 처음에는 잠시 걸립니다.":"실시간 수신 예시를 시작하고 있습니다."
      : "예시를 종료하고 있습니다.";
    try {
      sample = await sampleCommand(action, new AbortController().signal, action==="stop"?sample?.scenario??scenario:scenario);
      message = sample.state === "running" ? "예시가 별도 작업공간에서 실행 중입니다." : "예시가 실행 중이지 않습니다.";
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
  <p class="context">준비된 데이터로 무엇이 달라졌는지 조사해 보세요. 실제 데이터 분석과 수신 점검을 선택할 수 있습니다. 체험 기록과 검토는 별도 작업공간에 저장됩니다.</p>
  {#if !writable}
    <p class="context">보기 전용이라 예시를 시작할 수 없습니다. 운영을 시작하면 할 수 있습니다.</p>
  {:else}
    <div class="scenarios">
      <article class="real-data"><h3>XJTU-SY 실제 베어링 데이터 분석</h3>
        <p>보유한 베어링 실기록을 Isolation Forest·LSTM 오토인코더로 비교합니다. 학습에 사용하지 않은 베어링을 조사합니다.</p>
        <p class="context">기록 출처 → 두 모델의 차이 → 원본 신호·두 기간·주파수 비교 → 검토 기록</p>
        {#if sample?.xjtuAvailable}
          <p class="context">준비된 실기록과 분석 결과를 사용합니다. 종료·재실행 후에도 검토 기록이 유지됩니다.</p>
        {:else}
          <p class="context">이 실행 환경에 실제 데이터 작업공간이 연결되지 않았습니다. 아래 준비 방법을 확인하세요.</p>
          <a href="#xjtu-setup">실제 데이터 준비 방법</a>
        {/if}
        <button type="button" class="ui-button ui-button-primary" disabled={busy || uncertain || sample?.state!=="stopped" || !sample?.xjtuAvailable}
          onclick={() => void command("start", "xjtu")}>실제 데이터로 분석 시작</button>
      </article>
      <article><h3>데이터 없이 기능 둘러보기</h3>
        <p>96회·2채널의 합성 진동 기록과 Isolation Forest·LSTM 오토인코더를 준비합니다. 별도 합성 참조로 학습한 실제 모델 계산을 확인합니다.</p>
        <p class="context">모델 점수 비교 → 원본·특징값 → 두 기간 분포·관계·주파수 → 검토 기록</p>
        <p class="context">종료 후 다시 열어도 이 예시의 분석·검토 기록은 유지됩니다.</p>
        <button type="button" class="ui-button" disabled={busy || uncertain || sample?.state!=="stopped"}
          onclick={() => void command("start", "bearing")}>베어링 분석 체험 시작</button>
      </article>
      <article><h3>실시간 수신 확인</h3><p class="context">합성 3상 모터의 OPC UA 수신·저장·신호 흐름을 읽기 전용으로 확인합니다.</p>
        <button type="button" class="ui-button" disabled={busy || uncertain || sample?.state!=="stopped"}
          onclick={() => void command("start", "live")}>실시간 수신 예시 시작</button>
      </article>
    </div>
    <div class="actions">
      {#if sample?.state === "running"}
        <span>{sample.scenario==="xjtu"?"XJTU-SY 실제 데이터 분석":sample.scenario==="bearing"?"합성 베어링 분석 체험":"실시간 수신 예시"} 실행 중</span>
        {#if openUrl}<a class="ui-button ui-button-primary" href={openUrl} target="_blank" rel="noopener noreferrer">예시 화면 열기 (새 탭)</a>{/if}
        {#if !confirmingStop}<button type="button" class="ui-button" disabled={busy || uncertain} onclick={() => void askStop()}>예시 종료</button>{/if}
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
  <details id="xjtu-setup" open={!sample?.xjtuAvailable}><summary>실제 XJTU-SY 데이터 준비 방법</summary>
    <p class="context">XJTU-SY 원본을 <code>data/interim/xjtu-sy</code>에 둔 뒤 저장소 루트에서 차례로 실행하면 위 버튼이 켜집니다. 처음 준비할 때는 두 모델을 학습하느라 몇 분 걸립니다.</p>
    <ol class="context">
      <li><code>uv run industrial-phm demo xjtu --until 100 --workspace artifacts/demo-xjtu-ui --prepare-only</code></li>
      <li><code>docker compose --env-file /dev/null -f compose.yaml -f compose.xjtu.yaml up -d --build</code></li>
    </ol>
  </details>
  {/if}
</section>

<style>
  section { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  h2 { margin: 0; }
  h3{margin:0;font-size:1rem}.scenarios{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:var(--space-3)}
  article{display:flex;flex-direction:column;gap:var(--space-3);padding:var(--space-3);border:1px solid var(--color-border);border-radius:var(--radius-panel)}
  .real-data{border-color:var(--color-accent,#00718b);background:var(--color-surface)}
  article button{align-self:flex-start;margin-top:auto}ol{margin:var(--space-2) 0 0;padding-left:var(--space-5);display:grid;gap:var(--space-2)}summary{cursor:pointer}code{overflow-wrap:anywhere;white-space:normal}
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  .actions { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
  .confirm { padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); display: grid; gap: var(--space-2); }
  .uncertain { background: var(--color-uncertain-surface); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
</style>
