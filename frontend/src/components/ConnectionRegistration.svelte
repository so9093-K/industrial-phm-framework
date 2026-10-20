<script lang="ts">
  import {
    browseOpcua, channelIdFrom, declaredRoles, emptyRoles, explainWrite, phaseRoleProblem, preflightCsv, registerCsv,
    registerOpcua, type FileRegistration, type OpcuaBrowse, type Preflight,
  } from "../connections";
  import {MAX_CHANNELS, MAX_CSV_BYTES} from "../csv-preview";
  import PhaseRoles from "./PhaseRoles.svelte";

  /** Other ways to register a connection: a CSV already in the workspace or with declared
   * 3-phase roles, and a local OPC UA server. Registration alone receives nothing. */
  type Props = {writable: boolean; onRegistered: () => Promise<void>};
  let {writable, onRegistered}: Props = $props();

  // CSV with a workspace path or 3-phase roles.
  let csv = $state({sourceId: "", name: "", assetId: "", pointId: "", filePath: "", channels: "", time: ""});
  let csvFile: File | null = $state(null);
  let roles = $state(emptyRoles());
  let csvRevision = $state(0);
  let csvChecked = $state(-1);
  let csvReport: Preflight | null = $state(null);
  let csvMessage = $state("");
  let csvFailed = $state(false);
  let csvBusy = $state(false);
  const channelList = $derived(csv.channels.split(",").map((item) => item.trim()).filter(Boolean));
  const declared = $derived(declaredRoles(roles));
  const csvProblem = $derived.by((): string | null => {
    if (!csv.sourceId.trim() || !csv.name.trim() || !csv.assetId.trim()) return "연결 ID, 이름, 설비를 입력하세요.";
    if (!csvFile && !csv.filePath.trim()) return "파일을 고르거나 작업공간 안 CSV 경로를 입력하세요.";
    if (!channelList.length || channelList.length > MAX_CHANNELS || new Set(channelList).size !== channelList.length)
      return "겹치지 않는 측정값 열 1~" + MAX_CHANNELS + "개를 쉼표로 입력하세요.";
    if (!csv.time.trim()) return "시각 열을 입력하세요.";
    return phaseRoleProblem(declared, channelList);
  });
  const csvReady = $derived.by((): boolean => {
    const report: Preflight | null = csvReport;
    return report !== null && report.status === "ready" && csvChecked === csvRevision;
  });

  function csvValues(): FileRegistration {
    return {source_id: csv.sourceId.trim(), name: csv.name.trim(), asset_id: csv.assetId.trim(),
      measurement_point_id: csv.pointId.trim(), channel_columns: channelList, timestamp_column: csv.time.trim(),
      phase_channels: declared};
  }
  function csvChanged() { csvRevision++; csvReport = null; csvMessage = ""; csvFailed = false; }
  async function chooseCsv(input: HTMLInputElement) {
    const chosen = input.files?.[0] ?? null;
    csvChanged(); csvFile = null;
    if (!chosen) return;
    if (!/\.csv$/i.test(chosen.name) || !chosen.size || chosen.size > MAX_CSV_BYTES) {
      csvFailed = true; csvMessage = "20MiB 이하의 비어 있지 않은 .csv 파일을 고르세요."; return;
    }
    csvFile = chosen;
    try {
      const header = (await chosen.slice(0, 8192).text()).replace(/^﻿/, "").split(/\r?\n/, 1)[0];
      const columns = header.split(",").map((column) => column.trim().replace(/^"(.*)"$/, "$1"));
      const time = columns.find((column) => /^(timestamp|time|event_time|observed_at)$/i.test(column));
      if (time && !csv.time) csv.time = time;
      const rest = columns.filter((column) => column && column !== time);
      if (rest.length && rest.length <= MAX_CHANNELS && !csv.channels) csv.channels = rest.join(",");
      csvMessage = chosen.name + " · 첫 줄의 열: " + columns.join(", ") + " · 실제 검사는 서버 점검에서 합니다.";
    } catch {
      csvMessage = "첫 줄을 읽지 못했습니다. 측정값·시각 열을 직접 입력하세요.";
    }
  }
  async function checkCsv() {
    if (csvProblem || csvBusy) { csvFailed = true; csvMessage = csvProblem ?? ""; return; }
    const token = csvRevision;
    csvBusy = true; csvFailed = false; csvMessage = "서버에서 CSV와 역할을 점검합니다. 아무것도 저장하지 않습니다.";
    try {
      const report = await preflightCsv(csvValues(), csvFile, csv.filePath.trim(), new AbortController().signal);
      if (token !== csvRevision) return;
      csvReport = report; csvChecked = token; csvFailed = report.status !== "ready";
      csvMessage = report.status === "ready"
        ? "점검 통과 · 측정값 " + report.sampleCount + "행 · " + report.channels.join(", ")
          + (declared.length ? " · 3상 역할 " + declared.length + "개 (단위·배선 근거는 현장에서 확인한 내용이어야 합니다)" : "")
          + (report.warnings.length ? " · 측정 간격 주의: " + report.warnings.join(", ") : "") + " · 아직 저장하지 않았습니다."
        : "점검 실패 · " + (report.issue ? (report.issue.row ? report.issue.row + "행" + (report.issue.column ? " / " + report.issue.column : "") + ": " : "") + report.issue.guidance : "파일이나 설정을 확인하세요.");
    } catch (cause: unknown) {
      if (token !== csvRevision) return;
      csvFailed = true; csvMessage = explainWrite(cause);
    } finally {
      csvBusy = false;
    }
  }
  async function registerCsvSource() {
    if (!csvReady || csvBusy) return;
    csvBusy = true; csvFailed = false; csvMessage = "연결을 등록하고 있습니다. 수집이나 저장은 시작하지 않습니다.";
    try {
      await registerCsv(csvValues(), csvFile, csv.filePath.trim(), new AbortController().signal);
      csvMessage = "연결 " + csv.sourceId.trim() + "을 등록했습니다. 아래 등록한 연결에서 사용을 시작하세요.";
      csvReport = null; csvRevision++;
      await onRegistered();
    } catch (cause: unknown) {
      csvFailed = true; csvMessage = explainWrite(cause);
    } finally {
      csvBusy = false;
    }
  }

  // Local OPC UA.
  let opc = $state({sourceId: "", name: "", assetId: "", pointId: "", endpoint: "opc.tcp://127.0.0.1:4840/", start: "i=85"});
  let browse: OpcuaBrowse | null = $state(null);
  let mappings: {channel_id: string; node_id: string}[] = $state([]);
  let opcMessage = $state("");
  let opcFailed = $state(false);
  let browseMessage = $state("");
  let browseFailed = $state(false);
  let opcBusy = $state(false);
  const opcProblem = $derived.by((): string | null => {
    if (!opc.sourceId.trim() || !opc.name.trim() || !opc.assetId.trim()) return "연결 ID, 이름, 설비를 입력하세요.";
    if (!/^opc\.tcp:\/\/127\.0\.0\.1:\d+\/?/.test(opc.endpoint.trim())) return "이 컴퓨터(127.0.0.1)의 OPC UA 서버 주소를 입력하세요.";
    if (!mappings.length || mappings.length > MAX_CHANNELS) return "가져올 변수를 1~" + MAX_CHANNELS + "개 고르세요.";
    if (mappings.some((item) => !/^[A-Za-z0-9_-]{1,64}$/.test(item.channel_id))) return "채널 ID는 영문·숫자·_·- 로 적으세요.";
    if (new Set(mappings.map((item) => item.channel_id)).size !== mappings.length) return "채널 ID가 겹칩니다.";
    return null;
  });

  async function findVariables(start = opc.start.trim() || "i=85") {
    if (opcBusy) return;
    opc.start = start; opcBusy = true; browseFailed = false; browseMessage = "OPC UA 서버의 변수를 찾고 있습니다. 아무것도 받거나 등록하지 않습니다.";
    try {
      browse = await browseOpcua(opc.endpoint.trim(), start, new AbortController().signal);
      browseMessage = "변수 " + browse.variables.length + "개 · 객체 " + browse.objects.length + "개"
        + (browse.truncated ? " · 일부만 보입니다. 객체 안쪽을 찾아 범위를 좁히세요." : "");
    } catch (cause: unknown) {
      browse = null; browseFailed = true;
      browseMessage = explainWrite(cause) + " 서버가 이 컴퓨터에서 실행 중인지, 주소와 시작 NodeId가 맞는지 확인하세요.";
    } finally {
      opcBusy = false;
    }
  }
  function add(nodeId: string, name: string) {
    if (mappings.some((item) => item.node_id === nodeId) || mappings.length >= MAX_CHANNELS) return;
    mappings = [...mappings, {channel_id: channelIdFrom(name, mappings.map((item) => item.channel_id)), node_id: nodeId}];
  }
  async function registerOpcuaSource() {
    if (opcProblem || opcBusy) { opcFailed = true; opcMessage = opcProblem ?? ""; return; }
    opcBusy = true; opcFailed = false; opcMessage = "연결을 등록하고 있습니다. 수집은 시작하지 않습니다.";
    try {
      await registerOpcua({source_id: opc.sourceId.trim(), name: opc.name.trim(), asset_id: opc.assetId.trim(),
        measurement_point_id: opc.pointId.trim(), endpoint_url: opc.endpoint.trim(), node_mappings: mappings},
        new AbortController().signal);
      opcMessage = "OPC UA 연결 " + opc.sourceId.trim() + "을 등록했습니다. 아래 등록한 연결에서 사용을 시작하고 1회 읽기로 확인하세요.";
      mappings = []; browse = null;
      await onRegistered();
    } catch (cause: unknown) {
      opcFailed = true; opcMessage = explainWrite(cause);
    } finally {
      opcBusy = false;
    }
  }
</script>

<section class="ui-panel" aria-labelledby="register-title">
  <h2 id="register-title">다른 방법으로 연결</h2>
  {#if !writable}<p class="context">보기 전용이라 연결을 등록할 수 없습니다. 운영을 시작하면 할 수 있습니다.</p>{/if}

  <details>
    <summary>작업공간 안 CSV · 3상 역할 지정</summary>
    <p class="context">작업공간 안의 CSV 경로를 쓰거나, 3상 불평형 분석을 위해 전압·전류의 R/S/T 역할과 근거를 함께 등록합니다. 등록만 하며 읽기·저장·분석은 따로 합니다.</p>
    <div class="grid">
      <label class="field">연결 ID<input maxlength="128" autocomplete="off" bind:value={csv.sourceId} oninput={csvChanged} /></label>
      <label class="field">연결 이름<input maxlength="128" autocomplete="off" bind:value={csv.name} oninput={csvChanged} /></label>
      <label class="field">설비<input maxlength="128" autocomplete="off" bind:value={csv.assetId} oninput={csvChanged} /></label>
      <label class="field">측정 위치 (선택)<input maxlength="128" autocomplete="off" bind:value={csv.pointId} oninput={csvChanged} /></label>
      <div class="field wide">
        <span id="workspace-csv-file-label">내 컴퓨터의 CSV (선택 · 20MiB 이하)</span>
        <span class="file-pick">
          <label class="ui-button">파일 선택
            <input type="file" class="visually-hidden" aria-labelledby="workspace-csv-file-label" accept=".csv,text/csv"
              onchange={(event) => void chooseCsv(event.currentTarget)} /></label>
          <span class="file-name">{csvFile?.name ?? "선택한 파일 없음"}</span>
        </span>
      </div>
      <label class="field wide">작업공간 안 CSV 경로 (파일을 고르지 않을 때)
        <input maxlength="128" autocomplete="off" placeholder="inputs/phase-voltage.csv" disabled={csvFile !== null}
          bind:value={csv.filePath} oninput={csvChanged} /></label>
      <label class="field">측정값 열 (쉼표로 구분)<input maxlength="700" autocomplete="off" placeholder="voltage_a,voltage_b,voltage_c"
        bind:value={csv.channels} oninput={csvChanged} /></label>
      <label class="field">시각 열<input maxlength="128" autocomplete="off" placeholder="timestamp" bind:value={csv.time} oninput={csvChanged} /></label>
    </div>
    <PhaseRoles channels={channelList} bind:roles onchange={csvChanged} />
    <div class="actions">
      <button type="button" class="ui-button" disabled={!writable || csvBusy} onclick={() => void checkCsv()}>점검 (저장 안 함)</button>
      <button type="button" class="ui-button ui-button-primary" disabled={!writable || csvBusy || !csvReady} onclick={() => void registerCsvSource()}>연결 등록</button>
    </div>
    {#if csvMessage}<p class="message" class:failure={csvFailed} role={csvFailed ? "alert" : "status"}>{csvMessage}</p>{/if}
  </details>

  <details>
    <summary>OPC UA로 연결</summary>
    <p class="context">이 컴퓨터(127.0.0.1)에서 실행 중인 익명 OPC UA 서버만 연결합니다. 변수를 찾아 고른 뒤 등록하고, 등록한 연결에서 1회 읽기로 확인합니다.</p>
    <div class="grid">
      <label class="field">연결 ID<input maxlength="128" autocomplete="off" bind:value={opc.sourceId} /></label>
      <label class="field">연결 이름<input maxlength="128" autocomplete="off" bind:value={opc.name} /></label>
      <label class="field">설비<input maxlength="128" autocomplete="off" bind:value={opc.assetId} /></label>
      <label class="field">측정 위치 (선택)<input maxlength="128" autocomplete="off" bind:value={opc.pointId} /></label>
      <label class="field wide">OPC UA 서버 주소<input maxlength="128" autocomplete="off" bind:value={opc.endpoint} /></label>
      <label class="field">찾기 시작 NodeId<input maxlength="128" autocomplete="off" bind:value={opc.start} /></label>
    </div>
    <div class="actions">
      <button type="button" class="ui-button" disabled={!writable || opcBusy} onclick={() => void findVariables()}>변수 찾기</button>
    </div>
    {#if browseMessage}<p class="message" class:failure={browseFailed} role={browseFailed ? "alert" : "status"}>{browseMessage}</p>{/if}
    {#if browse}
      {#if browse.objects.length}
        <p class="label">객체</p>
        <ul class="nodes">
          {#each browse.objects as node (node.nodeId)}
            <li><span>{node.name} <code>{node.nodeId}</code></span>
              <button type="button" class="ui-button" disabled={opcBusy} onclick={() => void findVariables(node.nodeId)}>안쪽 찾기</button></li>
          {/each}
        </ul>
      {/if}
      <p class="label">변수</p>
      {#if browse.variables.length}
        <ul class="nodes">
          {#each browse.variables as node (node.nodeId)}
            <li><span>{node.name} <code>{node.nodeId}</code></span>
              <button type="button" class="ui-button" disabled={mappings.some((item) => item.node_id === node.nodeId) || mappings.length >= MAX_CHANNELS}
                onclick={() => add(node.nodeId, node.name)}>가져올 변수로 추가</button></li>
          {/each}
        </ul>
      {:else}
        <p class="context">이 위치에 변수가 없습니다. 객체 안쪽을 찾아보세요.</p>
      {/if}
    {/if}
    {#if mappings.length}
      <fieldset>
        <legend>가져올 변수 ({mappings.length}/{MAX_CHANNELS})</legend>
        {#each mappings as mapping, index (mapping.node_id)}
          <div class="mapping">
            <label class="field">채널 ID<input maxlength="64" bind:value={mappings[index].channel_id} /></label>
            <code>{mapping.node_id}</code>
            <button type="button" class="ui-button" onclick={() => mappings = mappings.filter((item) => item.node_id !== mapping.node_id)}>빼기</button>
          </div>
        {/each}
      </fieldset>
    {/if}
    <div class="actions">
      <button type="button" class="ui-button ui-button-primary" disabled={!writable || opcBusy || opcProblem !== null}
        onclick={() => void registerOpcuaSource()}>OPC UA 연결 등록</button>
    </div>
    {#if opcMessage}<p class="message" class:failure={opcFailed} role={opcFailed ? "alert" : "status"}>{opcMessage}</p>{/if}
  </details>
</section>

<style>
  section { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  h2 { margin: 0; }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  details { border-top: 1px solid var(--color-border); padding-top: var(--space-2); display: grid; gap: var(--space-3); }
  details[open] > :not(summary) { margin-top: var(--space-3); }
  summary { cursor: pointer; font-weight: 700; color: var(--color-action); padding-block: var(--space-2); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-3); }
  .wide { grid-column: 1 / -1; }
  .field { display: grid; gap: var(--space-1); font-weight: 650; min-width: 0; }
  input:not([type="file"]) { font: inherit; font-weight: 400; min-height: 40px; padding: var(--space-2) var(--space-3); min-width: 0;
    border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); }
  input[type="file"] { max-width: 100%; min-width: 0; font: inherit; font-weight: 400; }
  fieldset { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3); margin: 0; min-width: 0; display: grid; gap: var(--space-3); }
  legend { font-weight: 650; padding-inline: var(--space-1); }
  .mapping { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-3); align-items: end; }
  .mapping .field { flex: 1 1 200px; }
  .actions { display: flex; flex-wrap: wrap; gap: var(--space-3); }
  .label { font-weight: 650; }
  .nodes { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  .nodes li { display: flex; flex-wrap: wrap; gap: var(--space-2); justify-content: space-between; align-items: center; overflow-wrap: anywhere; }
  code { overflow-wrap: anywhere; font-size: var(--font-small); }
  .message.failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
</style>
