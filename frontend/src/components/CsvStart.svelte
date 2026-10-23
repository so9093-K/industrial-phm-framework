<script lang="ts">
  import {tick} from "svelte";
  import {
    declaredRoles, emptyRoles, explainWrite, phaseRoleProblem, preflightUpload, receiveFile, registerUpload,
    setLifecycle, startHistory, waitForHistory, HistoryFailed, type CsvSetup, type Preflight,
  } from "../connections";
  import {
    channelChoices, inspectCsv, intervals, offsetChoices, parseCsv, unitExample, previewPoints, previewProblems, readTimes, summarize,
    suggestedSourceId, suggestSignalNames, MAX_CHANNELS, MAX_CSV_BYTES, type CsvTable,
  } from "../csv-preview";
  import {num} from "../format";
  import {measure, yTicks} from "../chart-axis";
  import {readSources} from "../operations-status";
  import {assetTabUrl, routeUrl} from "../routes";
  import {OutcomeUnknown} from "../writes";
  import AnalysisOptions from "./AnalysisOptions.svelte";
  import PhaseRoles from "./PhaseRoles.svelte";

  /** One CSV file to stored measurements: see the file's own values, let the server check it
   * without saving, then register, put in use, read once and store history as visible steps.
   * A retry resumes from the server's state and never registers or stores twice. */
  type Props = {writable: boolean; onSaved: () => Promise<void>};
  let {writable, onSaved}: Props = $props();
  type StepId = "register" | "activate" | "receive" | "store";
  type StepState = "pending" | "running" | "done" | "failed" | "unknown";
  const STEPS: {id: StepId; title: string; text: string}[] = [
    {id: "register", title: "연결 등록", text: "파일을 작업공간에 복사하고 설정을 기록합니다."},
    {id: "activate", title: "사용 시작", text: "이 연결을 사용 상태로 바꿉니다."},
    {id: "receive", title: "파일 읽기 확인", text: "저장된 파일을 다시 읽어 확인합니다."},
    {id: "store", title: "측정 이력 저장", text: "측정값을 원래 측정 시각 그대로 저장합니다. 큰 파일은 몇 분 걸립니다."},
  ];
  const STATE_TEXT: Record<StepState, string> = {pending: "대기", running: "진행 중", done: "완료", failed: "실패", unknown: "결과 확인 필요"};

  const TICKET_KEY = "phm-csv-pending-v1";
  let fileDigest = "";
  let fileChoice = 0;
  let file: File | null = $state(null);
  let table: CsvTable | null = $state(null);
  let fileMessage = $state("아직 파일을 고르지 않았습니다. 저장하기 전까지 파일은 이 브라우저에서만 읽습니다.");
  let fileProblem = $state(false);
  let timeIndex = $state(-1);
  // Timestamps written without an offset are read at this one; most field exports are local time.
  let offset = $state("+09:00");
  let timeZoneConfirmed = $state(false);
  const offsets = offsetChoices();
  let channels: string[] = $state([]);
  let chartChannel = $state("");
  // How each saved column reads on screens; empty keeps the column name.
  let labels: Record<string, {label: string; unit: string}> = $state({});
  const shown = (name: string) => labels[name]?.label.trim() || name;
  let assetId = $state("");
  let pointId = $state("");
  let sourceId = $state("");
  let sourceName = $state("");
  // Optional 3-phase roles let the load/unbalance analysis read this file.
  let roles = $state(emptyRoles());
  // Every input change makes an earlier server check stale.
  let revision = $state(0);
  let checkedRevision = $state(-1);
  let checking = $state(false);
  let report: Preflight | null = $state(null);
  let checkMessage = $state("");
  let progress: {setup: CsvSetup; done: Partial<Record<StepId, boolean>>} | null = $state(null);
  let steps: Record<StepId, {state: StepState; detail: string}> = $state(fresh());
  let saving = $state(false);
  let saveMessage = $state("");
  let saveFailed = $state(false);
  let stored: {eventCount: number} | null = $state(null);
  let fileInput: HTMLInputElement | null = $state(null);
  let doneHeading: HTMLElement | null = $state(null);

  const clock = (at: string | null) => at ? new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"}) : "기록 없음";
  const choices = $derived(table ? channelChoices(table, timeIndex) : []);
  const problems = $derived(table ? previewProblems(table, timeIndex, channels, offset) : []);
  const timing = $derived(table && timeIndex >= 0 ? readTimes(table, timeIndex, offset) : null);
  const timeZoneReady = $derived(!timing?.naive || timeZoneConfirmed);
  const gaps = $derived(timing ? intervals(timing) : null);
  const points = $derived(table && timing && chartChannel ? previewPoints(table, timing, chartChannel) : []);
  const checked = $derived.by((): boolean => {
    const current: Preflight | null = report;
    return current !== null && checkedRevision === revision && current.status === "ready";
  });
  const locked = $derived(progress !== null || saving);
  const declared = $derived(declaredRoles(roles));
  const roleProblem = $derived(phaseRoleProblem(declared, channels));

  function fresh(): Record<StepId, {state: StepState; detail: string}> {
    return {register: {state: "pending", detail: ""}, activate: {state: "pending", detail: ""},
      receive: {state: "pending", detail: ""}, store: {state: "pending", detail: ""}};
  }
  function setStep(id: StepId, state: StepState, detail = "") { steps = {...steps, [id]: {state, detail}}; }
  function changed() { revision++; report = null; checkMessage = ""; }
  function duration(seconds: number): string {
    return seconds >= 3600 ? num(seconds / 3600) + "시간" : seconds >= 60 ? num(seconds / 60) + "분" : num(seconds) + "초";
  }

  async function choose() {
    const token = ++fileChoice;
    const chosen = fileInput?.files?.[0] ?? null;
    fileDigest = "";
    timeZoneConfirmed = false;
    file = null; table = null; progress = null; steps = fresh(); stored = null; saveMessage = ""; roles = emptyRoles();
    fileProblem = false; changed();
    if (!chosen) { fileMessage = "아직 파일을 고르지 않았습니다."; return; }
    if (!/\.csv$/i.test(chosen.name) || !chosen.size) { fileProblem = true; fileMessage = "비어 있지 않은 .csv 파일을 고르세요."; return; }
    if (chosen.size > MAX_CSV_BYTES) {
      fileProblem = true;
      fileMessage = "이 파일은 " + (chosen.size / 1048576).toFixed(1) + "MiB입니다. 화면에서 바로 저장할 수 있는 CSV는 20MiB까지입니다. "
        + "기간을 나눈 파일로 시작하거나, 운영을 멈춘 상태에서 industrial-phm maintenance history backfill로 저장하세요.";
      return;
    }
    let text: string;
    let bytes: ArrayBuffer;
    try {
      bytes = await chosen.arrayBuffer();
      if (token !== fileChoice) return;
      text = new TextDecoder("utf-8", {fatal: true}).decode(bytes).replace(/^﻿/, "");
    } catch {
      fileProblem = true; fileMessage = "UTF-8로 읽을 수 없는 파일입니다. UTF-8로 다시 저장한 뒤 고르세요."; return;
    }
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    if (token !== fileChoice) return;
    fileDigest = [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
    const inspected = inspectCsv(parseCsv(text));
    file = chosen; table = inspected;
    timeIndex = inspected.times[0]?.index ?? -1;
    channels = channelChoices(inspected, timeIndex).filter((c) => c.usable).slice(0, MAX_CHANNELS).map((c) => c.name);
    chartChannel = channels[0] ?? "";
    const suggested = suggestSignalNames(channelChoices(inspected, timeIndex).map((c) => c.name));
    labels = Object.fromEntries(inspected.header.map((name) => [name, {label: suggested.get(name) ?? "", unit: ""}]));
    sourceId = suggestedSourceId(chosen.name, Math.random().toString(16).slice(2, 6));
    sourceName = chosen.name.slice(0, 128);
    let restored = false;
    try {
      const ticket = JSON.parse(localStorage.getItem(TICKET_KEY) ?? "null");
      const prior = ticket?.setup;
      if (ticket?.digest === fileDigest && prior
        && ["source_id", "name", "asset_id", "measurement_point_id", "timestamp_column"].every(key => typeof prior[key] === "string" && prior[key].length <= 128)
        && Array.isArray(prior.channel_columns) && prior.channel_columns.length <= MAX_CHANNELS
        && prior.channel_columns.every((name: unknown) => typeof name === "string" && inspected.header.includes(name))) {
        sourceId = prior.source_id; sourceName = prior.name; assetId = prior.asset_id; pointId = prior.measurement_point_id;
        timeIndex = inspected.header.indexOf(prior.timestamp_column); channels = [...prior.channel_columns];
        chartChannel = channels[0] ?? ""; restored = true;
        if (offsets.some((choice) => choice.value === prior.timestamp_utc_offset)) offset = prior.timestamp_utc_offset;
        if (Array.isArray(prior.channel_labels)) for (const item of prior.channel_labels) {
          if (typeof item?.channel_id === "string" && item.channel_id in labels && typeof item.label === "string")
            labels[item.channel_id] = {label: item.label, unit: typeof item.unit === "string" ? item.unit : ""};
        }
      }
    } catch { /* Blocked browser storage does not prevent a new upload. */ }
    fileMessage = (restored ? "이전 작업 입력 복원 · 같은 파일인지 SHA-256으로 확인했습니다. 서버에서 다시 점검하세요. · " : "") + chosen.name + " · " + (chosen.size / 1024).toFixed(1) + "KiB · 데이터 " + inspected.sampleCount + "행 · 열 " + inspected.header.length + "개";
  }
  function chooseTime(value: string) {
    timeZoneConfirmed = false;
    timeIndex = value === "" ? -1 : Number(value);
    channels = channels.filter((name) => table?.columns.find((c) => c.name === name)?.index !== timeIndex);
    if (!channels.includes(chartChannel)) chartChannel = channels[0] ?? "";
    changed();
  }
  function toggle(name: string, on: boolean) {
    channels = on ? [...channels, name].slice(0, MAX_CHANNELS) : channels.filter((item) => item !== name);
    if (!channels.includes(chartChannel)) chartChannel = channels[0] ?? "";
    changed();
  }
  function setup(): CsvSetup {
    return {source_id: sourceId.trim(), name: sourceName.trim(), asset_id: assetId.trim(),
      measurement_point_id: pointId.trim(), channel_columns: channels,
      timestamp_column: table && timeIndex >= 0 ? table.header[timeIndex] : "",
      ...(declared.length ? {phase_channels: declared} : {}),
      ...(named().length ? {channel_labels: named()} : {}),
      ...(timing?.naive ? {timestamp_utc_offset: offset} : {})};
  }
  function named(): {channel_id: string; label: string; unit: string | null}[] {
    return channels.flatMap((name) => {
      const label = labels[name]?.label.trim() ?? "", unit = labels[name]?.unit.trim() ?? "";
      return label || unit ? [{channel_id: name, label: label || name, unit: unit || null}] : [];
    });
  }
  function rename(name: string, field: "label" | "unit", value: string) {
    labels[name] = {...(labels[name] ?? {label: "", unit: ""}), [field]: value};
    changed();
  }

  async function check() {
    if (!file || !table || !writable || checking) return;
    const values = setup();
    if (!values.asset_id || !values.source_id || !values.name) { checkMessage = "설비 이름을 입력하세요. 연결 ID와 이름도 비어 있으면 안 됩니다."; return; }
    if (problems.length) { checkMessage = "미리보기에서 찾은 문제를 먼저 고치세요."; return; }
    if (roleProblem) { checkMessage = roleProblem; return; }
    if (!timeZoneReady) { checkMessage = "시간대가 없는 파일입니다. 선택한 시간대를 확인하세요."; return; }
    const token = revision;
    checking = true; checkMessage = "서버의 데이터 검증기로 파일을 점검합니다. 아무것도 저장하지 않습니다.";
    try {
      const result = await preflightUpload(values, file, new AbortController().signal);
      if (token !== revision) return;
      report = result; checkedRevision = token;
      checkMessage = result.status === "ready"
        ? "점검 통과 · 측정값 " + result.sampleCount + "행 · " + result.channels.join(", ") + " · 원래 측정 " + clock(result.first) + " ~ " + clock(result.last)
          + (result.warnings.length ? " 측정 간격 주의: " + result.warnings.join(", ") + " · 원래 간격대로 저장합니다." : "")
          + (result.match === "matching" ? " 같은 파일과 설정이 이미 등록돼 있습니다. 저장하면 남은 단계부터 이어서 진행합니다." : "")
        : (result.status === "blocked" ? "점검 실패 · 파일이나 설정을 고친 뒤 다시 점검하세요." : "추가 확인이 필요합니다 · 아직 저장할 수 없습니다.")
          + (result.issue ? " " + (result.issue.row ? result.issue.row + "행" + (result.issue.column ? " / " + result.issue.column + " 열" : "") + ": " : "") + result.issue.guidance : "");
    } catch (cause: unknown) {
      if (token !== revision) return;
      checkMessage = explainWrite(cause);
    } finally {
      checking = false;
    }
  }

  /** Resume from durable server state, so a retry never repeats a finished or unknown registration. */
  async function resync(values: CsvSetup, current: File, signal: AbortSignal) {
    const registered = (await readSources(signal)).items.find((item) => item.sourceId === values.source_id);
    if (registered) {
      const verified = await preflightUpload(values, current, signal);
      if (verified.status !== "ready" || verified.match !== "matching")
        throw new Error("같은 ID로 다른 파일이나 설정이 등록돼 있습니다. 연결 ID를 바꾸세요.");
    }
    const done = {register: Boolean(registered), activate: registered?.lifecycle === "active", receive: false};
    for (const id of ["register", "activate"] as const) if (done[id]) setStep(id, "done");
    return done;
  }

  async function save() {
    if (!file || !checked || !timeZoneReady || saving || !writable) return;
    const current = file;
    const signal = new AbortController().signal;
    const retry = progress !== null || report?.match === "matching";
    progress ??= {setup: setup(), done: {}};
    try { localStorage.setItem(TICKET_KEY, JSON.stringify({digest: fileDigest, setup: progress.setup})); } catch { /* The server still owns every completed step. */ }
    saving = true; saveFailed = false;
    let step: StepId = "register";
    try {
      if (retry) { saveMessage = "서버의 현재 연결 상태를 확인하고 이어서 진행합니다."; progress.done = await resync(progress.setup, current, signal); }
      const values = progress.setup;
      if (!progress.done.register) {
        setStep(step, "running"); await registerUpload(values, current, signal);
        progress.done.register = true; setStep(step, "done", "연결 " + values.name);
      }
      step = "activate";
      if (!progress.done.activate) {
        setStep(step, "running"); await setLifecycle(values.source_id, "active", signal);
        progress.done.activate = true; setStep(step, "done");
      }
      step = "receive";
      if (!progress.done.receive) {
        setStep(step, "running");
        const result = await receiveFile(values.source_id, signal);
        if (!result.accepted) throw new Error("파일을 다시 읽어 확인하지 못했습니다 (" + (result.failure ?? "원인 미확인") + ").");
        progress.done.receive = true; setStep(step, "done", clock(result.receivedAt));
      }
      step = "store";
      setStep(step, "running", "시작 요청 중");
      const startedAt = await startHistory(values.source_id, signal);
      const result = await waitForHistory(values.source_id, startedAt, signal, (seconds, known) => setStep("store",
        known ? "running" : "unknown", seconds + "초 · " + (known ? "다른 화면으로 가도 저장은 계속됩니다" : "상태 조회 실패 · 결과 미확정")));
      progress.done.store = true; setStep(step, "done", "측정값 " + result.eventCount.toLocaleString("ko-KR") + "개");
      stored = result;
      try { localStorage.removeItem(TICKET_KEY); } catch { /* Storage may be disabled. */ }
      saveMessage = "저장했습니다 · 설비 " + values.asset_id + "에 측정값 " + result.eventCount.toLocaleString("ko-KR") + "개를 원래 측정 시각으로 저장했습니다.";
      await tick(); doneHeading?.focus();
    } catch (cause: unknown) {
      const unknown = cause instanceof OutcomeUnknown || (cause instanceof HistoryFailed && cause.message.includes("중단"));
      setStep(step, unknown ? "unknown" : "failed");
      saveFailed = true;
      saveMessage = (cause instanceof HistoryFailed || (cause instanceof Error && !("code" in cause) && step === "receive")
        ? cause.message : explainWrite(cause)) + (progress?.done.register ? " 입력은 유지되며, 다시 시도하면 끝난 단계는 건너뜁니다." : " 입력은 그대로입니다.");
      if (progress && !progress.done.register && !(cause instanceof OutcomeUnknown)) progress = null;
    } finally {
      saving = false;
      await onSaved();
    }
  }


  async function restart() {
    if (fileInput) fileInput.value = "";
    assetId = ""; pointId = ""; await choose(); fileInput?.focus();
  }
</script>

<section class="ui-panel csv-start" aria-labelledby="csv-start-title">
  <h2 id="csv-start-title">CSV 파일로 시작</h2>
  <p class="context">파일의 실제 값을 먼저 보고, 서버가 점검한 뒤 저장하면 설비 화면의 신호 탭에서 같은 값을 봅니다.</p>
  <ol class="flow" aria-label="진행 순서">
    <li>파일 고르기</li><li>측정값·설비 확인</li><li>서버 점검 (저장 안 함)</li><li>등록하고 이력 저장</li>
  </ol>

  <div class="field">
    <span id="csv-file-label">CSV 파일 (UTF-8 · 20MiB 이하)</span>
    <span class="file-pick">
      <label class="ui-button" aria-disabled={locked}>파일 선택
        <input type="file" class="visually-hidden" aria-labelledby="csv-file-label" accept=".csv,text/csv"
          bind:this={fileInput} disabled={locked} onchange={() => void choose()} /></label>
    </span>
  </div>
  <p class="context" class:problem={fileProblem} role="status">{fileMessage}</p>

  {#if table}
    <section aria-labelledby="csv-preview-title">
      <h3 id="csv-preview-title">파일 미리보기</h3>
      <p class="tag">{stored ? "이 브라우저에서 읽은 값 · 아래와 같이 저장했습니다" : report?.status === "ready" ? "이 브라우저에서 읽은 값 · 서버가 확인함 · 아직 저장 전" : "이 브라우저에서 읽은 값 · 아직 서버 점검·저장 전"}</p>
      <div class="columns">
        <label class="field">시각 열
          <select value={String(timeIndex)} disabled={locked} onchange={(event) => chooseTime(event.currentTarget.value)}>
            {#if !table.times.length}<option value="-1">시각 열 후보 없음</option>{/if}
            {#each table.times as column (column.index)}<option value={String(column.index)}>{column.name}</option>{/each}
          </select>
        </label>
        {#if timing?.naive}
          <label class="field">시각의 시간대 (파일에 시간대가 없음)
            <select value={offset} disabled={locked} onchange={(event) => { offset = event.currentTarget.value; timeZoneConfirmed = false; changed(); }}>
              {#each offsets as choice (choice.value)}<option value={choice.value}>{choice.label}</option>{/each}
            </select>
          </label>
          <label class="choice">
            <input type="checkbox" checked={timeZoneConfirmed} disabled={locked}
              onchange={(event) => timeZoneConfirmed = event.currentTarget.checked} />
            이 CSV의 측정 시각이 선택한 시간대 기준임을 확인했습니다. 저장되는 측정 시각에 영향을 줍니다.
          </label>
        {/if}
        <fieldset>
          <legend>저장할 측정값 (숫자 열 · 최대 {MAX_CHANNELS}개)</legend>
          {#each choices as choice (choice.name)}
            <label class="choice">
              <input type="checkbox" checked={channels.includes(choice.name)} disabled={locked || !choice.usable
                || (!channels.includes(choice.name) && channels.length >= MAX_CHANNELS)}
                onchange={(event) => toggle(choice.name, event.currentTarget.checked)} />
              {choice.name}{choice.note ? " · " + choice.note : ""}
            </label>
          {/each}
        </fieldset>
      </div>
      {#if problems.length}
        <ul class="problems" aria-label="저장 전에 고칠 것">
          {#each problems as problem, i (i)}<li>{problem}</li>{/each}
        </ul>
      {:else}
        <p class="ok">이 브라우저에서 찾은 구조 문제는 없습니다. 서버 점검으로 최종 확인합니다.</p>
      {/if}
      {#if channels.length}
        <fieldset class="names">
          <legend>화면에 보일 이름·단위 (선택)</legend>
          <p class="context">비워 두면 열 이름이 그대로 보입니다.</p>
          {#each channels as name (name)}
            <div class="name-row">
              <span class="column">{name}</span>
              <input maxlength="60" placeholder="이름" aria-label={name + " 이름"} disabled={locked}
                value={labels[name]?.label ?? ""} oninput={(event) => rename(name, "label", event.currentTarget.value)} />
              <input maxlength="16" placeholder={unitExample(name) ? "단위 예: " + unitExample(name) : "단위"} aria-label={name + " 단위"} disabled={locked}
                value={labels[name]?.unit ?? ""} oninput={(event) => rename(name, "unit", event.currentTarget.value)} />
            </div>
          {/each}
        </fieldset>
        <div class="scroll"><table>
          <caption>측정값 요약</caption>
          <thead><tr><th scope="col">측정값</th><th scope="col">값</th><th scope="col">빈 값</th><th scope="col">최소</th>
            <th scope="col">중앙값</th><th scope="col">최대</th><th scope="col">평균</th></tr></thead>
          <tbody>
            {#each channels as name (name)}
              {@const summary = summarize(table, name)}
              <tr><th scope="row">{shown(name)}</th><td>{summary.count.toLocaleString("ko-KR")}</td><td>{summary.missing}</td>
                <td>{num(summary.min, "—")}</td><td>{num(summary.median, "—")}</td><td>{num(summary.max, "—")}</td><td>{num(summary.mean, "—")}</td></tr>
            {/each}
          </tbody>
        </table></div>
      {/if}
      {#if gaps}
        <p class="context">측정 간격 · 보통 {duration(gaps.usualSeconds)} · 간격이 크게 다른 곳 {gaps.uneven}곳 · 가장 긴 공백 {duration(gaps.longestSeconds)}
          {gaps.longestAfter !== null ? " (" + clock(new Date(gaps.longestAfter).toISOString()) + " 이후)" : ""}</p>
      {/if}
      {#if channels.length && points.length}
        <label class="field">미리 볼 측정값
          <select bind:value={chartChannel}>{#each channels as name (name)}<option value={name}>{shown(name)}</option>{/each}</select>
        </label>
        {@const low = Math.min(...points.map((p) => p.min))}
        {@const high = Math.max(...points.map((p) => p.max))}
        {@const y = (v: number) => 110 - (high === low ? 0.5 : (v - low) / (high - low)) * 92}
        {@const start = timing!.points[0].at}
        {@const end = timing!.points.at(-1)!.at}
        {@const x = (at: number) => 66 + ((at - start) / Math.max(1, end - start)) * 562}
        {@const unit = labels[chartChannel]?.unit.trim() || null}
        <svg viewBox="0 0 650 130" role="img" aria-label={shown(chartChannel) + "의 시간 구간별 평균과 최소·최대 (파일의 실제 값)"}>
          {#each high === low ? [] : yTicks(low, high, 18, 110, 3) as tick (tick.value)}
            <line x1="62" x2="632" y1={tick.y} y2={tick.y} class="grid" />
            <text x="56" y={tick.y + 3.5} text-anchor="end" class="tick">{measure(tick.value, unit)}</text>
          {/each}
          <path d="M62 12 V114 H632" class="axis" />
          {#each points as point (point.at)}
            <line x1={x(point.at)} x2={x(point.at)} y1={y(point.min)} y2={y(point.max)} class="range" />
            <circle cx={x(point.at)} cy={y(point.mean)} r="3" class="dot"><title>{clock(new Date(point.at).toISOString())} · 평균 {num(point.mean)} · 최소 {num(point.min)} · 최대 {num(point.max)}</title></circle>
          {/each}
        </svg>
        <p class="context">측정 기간 (KST) · {clock(new Date(start).toISOString())} ~ {clock(new Date(end).toISOString())}</p>
        <p class="context">{timing?.points.length.toLocaleString("ko-KR")}행 · 구간 평균(점)과 최소·최대(선) · 최소 {measure(low, unit)} · 최대 {measure(high, unit)}</p>
      {/if}
    </section>

    <section aria-labelledby="csv-asset-title">
      <h3 id="csv-asset-title">설비 정보</h3>
      <div class="grid">
        <label class="field">설비 이름·번호<input maxlength="128" placeholder="예: 1호 펌프" autocomplete="off" disabled={locked}
          value={assetId} oninput={(event) => { assetId = event.currentTarget.value; changed(); }} /></label>
        <label class="field">측정 위치 (선택)<input maxlength="128" placeholder="예: panel-main" autocomplete="off" disabled={locked}
          value={pointId} oninput={(event) => { pointId = event.currentTarget.value; changed(); }} /></label>
      </div>
      <details>
        <summary>연결 ID·이름 (자동으로 만듦 · 필요하면 수정)</summary>
        <div class="grid">
          <label class="field">연결 ID<input maxlength="128" autocomplete="off" disabled={locked}
            value={sourceId} oninput={(event) => { sourceId = event.currentTarget.value; changed(); }} /></label>
          <label class="field">연결 이름<input maxlength="128" autocomplete="off" disabled={locked}
            value={sourceName} oninput={(event) => { sourceName = event.currentTarget.value; changed(); }} /></label>
        </div>
      </details>
      <details open={declared.length > 0}>
        <summary>3상 전압·전류 역할 지정 (선택 · 부하·불평형 분석에 필요)</summary>
        <PhaseRoles {channels} bind:roles disabled={locked} onchange={changed} />
        {#if roleProblem}<p class="message failure" role="status">{roleProblem}</p>{/if}
      </details>
      {#if !writable}
        <p class="context">보기 전용이라 서버 점검과 저장을 할 수 없습니다. 미리보기는 볼 수 있습니다.</p>
      {:else}
        <button type="button" class="ui-button" disabled={checking || locked || !assetId.trim() || problems.length > 0 || !timeZoneReady}
          onclick={() => void check()}>서버에서 점검 (저장 안 함)</button>
      {/if}
      {#if checkMessage}
        <p class="message" class:failure={report !== null && report.status !== "ready"} role="status">{checkMessage}{#if report?.status === "ready" && !checking}{stored ? " · 저장했습니다." : " · 아직 저장하지 않았습니다."}{/if}</p>
      {/if}
    </section>

    <section aria-labelledby="csv-save-title">
      <h3 id="csv-save-title">등록하고 이력 저장</h3>
      <p class="context">중간에 실패해도 입력은 남고, 다시 시도하면 끝난 단계는 건너뜁니다.</p>
      <ol class="steps">
        {#each STEPS as item (item.id)}
          <li data-state={steps[item.id].state}><strong>{item.title}</strong><span>{item.text}</span>
            {#if progress || steps[item.id].state !== "pending"}<em>{STATE_TEXT[steps[item.id].state]}{steps[item.id].detail ? " · " + steps[item.id].detail : ""}</em>{/if}</li>
        {/each}
      </ol>
      {#if !stored}
        <button type="button" class="ui-button ui-button-primary" disabled={!writable || !checked || !timeZoneReady || saving}
          onclick={() => void save()}>{saveFailed && progress ? "실패한 단계부터 다시 시도" : "등록하고 이력 저장"}</button>
      {/if}
      {#if saveMessage}
        <p class="message" class:failure={saveFailed} role={saveFailed ? "alert" : "status"}>{saveMessage}</p>
      {/if}
    </section>

    {#if stored && progress}
      <section aria-labelledby="csv-done-title">
        <h3 id="csv-done-title" tabindex="-1" bind:this={doneHeading}>다음 할 일</h3>
        <p class="links">
          <a class="ui-button ui-button-primary" href={assetTabUrl(progress.setup.asset_id, "signals")}>설비 화면에서 신호 보기 →</a>
          <a href={routeUrl({page: "assets", assetId: progress.setup.asset_id, tab: "summary", method: null, data: null})}>설비 요약 보기 →</a>
          {#if progress.setup.phase_channels?.length}
            <a href={assetTabUrl(progress.setup.asset_id, "change", "electrical")}>부하·불평형 보기 →</a>
          {/if}
        </p>
        <AnalysisOptions assetId={progress.setup.asset_id} level={4} />
        <button type="button" class="ui-button" onclick={() => void restart()}>다른 파일로 시작</button>
      </section>
    {/if}
  {/if}
</section>

<style>
  .csv-start { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  .csv-start > section { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; border-top: 1px solid var(--color-border); padding-top: var(--space-4); }
  h2, h3 { margin: 0; }
  h3 { font-size: var(--font-section); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  .problem { color: var(--color-failure-ink); }
  .flow { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-5); margin: 0; padding-inline-start: var(--space-5); color: var(--color-ink-muted); font-size: var(--font-small); }
  .field { display: grid; gap: var(--space-1); font-weight: 650; min-width: 0; }
  input:not([type="checkbox"]), select { font: inherit; font-weight: 400; min-height: 40px; padding: var(--space-2) var(--space-3); min-width: 0;
    border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); }
  input[type="file"] { max-width: 100%; }
  .columns { display: grid; gap: var(--space-3); }
  .names { display: grid; gap: var(--space-2); }
  .names .context { margin: 0; }
  .name-row { display: grid; grid-template-columns: minmax(90px, 1fr) minmax(120px, 2fr) minmax(90px, 1fr); gap: var(--space-2); align-items: center; }
  .name-row .column { overflow-wrap: anywhere; color: var(--color-ink-muted); font-size: var(--font-small); }
  @media (max-width: 560px) { .name-row { grid-template-columns: 1fr 1fr; } .name-row .column { grid-column: 1 / -1; } }
  fieldset { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3); margin: 0; min-width: 0; }
  legend { font-weight: 650; padding-inline: var(--space-1); }
  .choice { display: flex; gap: var(--space-2); align-items: flex-start; padding-block: var(--space-1); overflow-wrap: anywhere; }
  .tag { font-size: var(--font-small); color: var(--color-ink-muted); }
  .problems { margin: 0; padding-inline-start: var(--space-5); color: var(--color-failure-ink); }
  .ok { color: var(--color-ink-muted); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-3); }
  .scroll { max-width: 100%; overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; }
  caption { text-align: left; color: var(--color-ink-muted); font-size: var(--font-small); }
  th, td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--color-border); }
  thead th { white-space: nowrap; }
  svg { width: 100%; height: auto; max-height: 180px; }
  .grid { stroke: var(--color-border); stroke-width: 1; opacity: 0.7; }
  .tick { font-size: 10px; fill: var(--color-ink-muted); }
  .axis { fill: none; stroke: var(--color-border); }
  .range { stroke: var(--color-ink-muted); stroke-width: 1; }
  .dot { fill: var(--color-action); }
  .steps { margin: 0; padding-inline-start: var(--space-5); display: grid; gap: var(--space-2); }
  .steps li { display: grid; gap: 2px; }
  .steps span, .steps em { color: var(--color-ink-muted); font-size: var(--font-small); }
  .steps li[data-state="done"] em { color: var(--color-ink); font-style: normal; font-weight: 650; }
  .steps li[data-state="failed"] em { color: var(--color-failure-ink); font-style: normal; font-weight: 650; }
  .message.failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  .links { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  .ui-button { justify-self: start; align-self: flex-start; }
</style>
