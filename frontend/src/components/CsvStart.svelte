<script lang="ts">
  import {dateTime as clock} from "../date-format";
  import {tick} from "svelte";
  import {
    declaredRoles, emptyRoles, explainWrite, PHASE_ROLES, phaseRoleProblem, preflightUpload, receiveFile, registerUpload,
    setLifecycle, startHistory, waitForHistory, HistoryFailed, type CsvSetup, type Preflight,
  } from "../connections";
  import {
    channelChoices, inspectCsv, intervals, offsetChoices, parseCsv, unitExample, previewPoints, previewProblems, readTimes, summarize,
    suggestedSourceId, suggestSignalNames, MAX_CHANNELS, MAX_CSV_BYTES, type CsvTable,
  } from "../csv-preview";
  import {num} from "../format";
  import {measure, yTicks} from "../chart-axis";
  import {readSources} from "../operations-status";
  import {assetTabUrl} from "../routes";
  import {OutcomeUnknown} from "../writes";
  import PhaseRoles from "./PhaseRoles.svelte";

  /** One CSV file to stored measurements: see the file's own values, let the server check it
   * without saving, then register, put in use, read once and store history as recoverable steps behind one confirmation.
   * A retry resumes from the server's state and never registers or stores twice. */
  type Props = {writable: boolean; onSaved: () => Promise<void>; onFileSelected?:(selected:boolean)=>void};
  let {writable, onSaved,onFileSelected}: Props = $props();
  $effect(()=>{onFileSelected?.(table!==null);});
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
  let operatingCurrent=$state("");
  let labels: Record<string, {label: string; unit: string}> = $state({});
  const currentProblem=$derived(operatingCurrent&&labels[operatingCurrent]?.unit.trim()!=="A"?"운전 수준에 사용할 전류의 단위를 A로 확인하세요.":null);
  const shown = (name: string) => labels[name]?.label.trim() || name;
  // Columns whose quantity has an example unit and whose unit field is still empty.
  const unfilledExamples = $derived(channels.filter((name) => unitExample(name) && !labels[name]?.unit.trim()));
  function fillExampleUnits() {
    for (const name of unfilledExamples) rename(name, "unit", unitExample(name) ?? "");
  }
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


  const choices = $derived(table ? channelChoices(table, timeIndex) : []);
  const numericColumns = $derived(choices.filter(choice=>choice.usable));
  const excludedColumns = $derived(numericColumns.filter(choice=>!channels.includes(choice.name)));
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
  // What the person still has to do before the server check, said next to the disabled button.
  const saveNeeds = $derived([
    ...(!timeZoneReady ? ["시간대 확인"] : []),
    ...(!assetId.trim() ? ["설비 이름·번호 입력"] : []),
  ]);
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
    operatingCurrent="";
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
        operatingCurrent=prior.operating_current??""; sourceId = prior.source_id; sourceName = prior.name; assetId = prior.asset_id; pointId = prior.measurement_point_id;
        timeIndex = inspected.header.indexOf(prior.timestamp_column); channels = [...prior.channel_columns];
        chartChannel = channels[0] ?? ""; restored = true;
        if (offsets.some((choice) => choice.value === prior.timestamp_utc_offset)) offset = prior.timestamp_utc_offset;
        if (Array.isArray(prior.channel_labels)) for (const item of prior.channel_labels) {
          if (typeof item?.channel_id === "string" && item.channel_id in labels && typeof item.label === "string")
            labels[item.channel_id] = {label: item.label, unit: typeof item.unit === "string" ? item.unit : ""};
        }
        if (Array.isArray(prior.phase_channels)) {
          roles = PHASE_ROLES.map((role) => {
            const saved = prior.phase_channels.find((item: unknown) => {
              if (!item || typeof item !== "object") return false;
              const value = item as Record<string, unknown>;
              return value.quantity === role.quantity && value.phase === role.phase
                && typeof value.channel_id === "string" && channels.includes(value.channel_id)
                && typeof value.unit_evidence === "string" && value.unit_evidence.length <= 128
                && typeof value.interpretation_evidence === "string" && value.interpretation_evidence.length <= 128;
            });
            return saved ? {channel: saved.channel_id, unit: saved.unit_evidence, meaning: saved.interpretation_evidence}
              : {channel: "", unit: "", meaning: ""};
          });
        }
      }
    } catch { /* Blocked browser storage does not prevent a new upload. */ }
    fileMessage = (restored ? "이전에 입력한 내용을 불러왔습니다. · " : "") + chosen.name + " · " + (chosen.size / 1024).toFixed(1) + "KiB · 데이터 " + inspected.sampleCount + "행 · 열 " + inspected.header.length + "개";
  }
  function chooseTime(value: string) {
    timeZoneConfirmed = false;
    timeIndex = value === "" ? -1 : Number(value);
    channels = channels.filter((name) => table?.columns.find((c) => c.name === name)?.index !== timeIndex);
    if(!channels.includes(operatingCurrent))operatingCurrent="";
    if (!channels.includes(chartChannel)) chartChannel = channels[0] ?? "";
    changed();
  }
  function toggle(name: string, on: boolean) {
    channels = on ? [...channels, name].slice(0, MAX_CHANNELS) : channels.filter((item) => item !== name);
    if(!channels.includes(operatingCurrent))operatingCurrent="";
    if (!channels.includes(chartChannel)) chartChannel = channels[0] ?? "";
    changed();
  }
  function setup(): CsvSetup {
    return {source_id: sourceId.trim(), name: sourceName.trim(), asset_id: assetId.trim(),
      measurement_point_id: pointId.trim(), channel_columns: channels,
      timestamp_column: table && timeIndex >= 0 ? table.header[timeIndex] : "",
      ...(operatingCurrent?{operating_current:operatingCurrent}:{}),
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
    if(currentProblem){checkMessage=currentProblem;return;}
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
          + (result.warnings.length ? " 측정 간격 주의: " + result.warnings.map(code=>code==="irregular-sampling"?"측정 간격이 일정하지 않음":"측정 시각·간격 확인 필요").join(", ") + " · 원래 간격대로 저장합니다." : "")
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

  async function confirmAndSave() {
    if(checking||saving)return;
    if(!checked)await check();
    if(checked)await save();
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

<section class="ui-panel csv-start" class:has-file={table!==null} aria-labelledby="csv-start-title">
  <div class="file-heading">
  <h2 id="csv-start-title" class:visually-hidden={table!==null}>CSV 데이터 등록</h2>
  {#if !table}<p class="context">측정 시각과 값을 확인하고 설비 이름을 입력하면 저장할 수 있습니다.</p>{/if}
  {#if !table}<ol class="flow" aria-label="진행 순서">
    {#each ["파일 선택", "미리보기·설비 확인", "저장하고 분석"] as label, index (label)}
      {@const at = stored ? 3 : saving || checking ? 2 : table ? 1 : 0}
      <li data-state={index < at ? "done" : index === at ? "current" : "todo"} aria-current={index === at ? "step" : undefined}>
        <span class="mark" aria-hidden="true">{index < at ? "✓" : index + 1}</span>{label}{#if index < at}<span class="visually-hidden"> 완료</span>{/if}</li>
    {/each}
  </ol>{/if}

  {#if table}<p class="context file-message" class:problem={fileProblem} role="status">{fileMessage}</p>{/if}
  <div class="field file-row">
    <span id="csv-file-label" class:visually-hidden={table!==null}>CSV 파일 (UTF-8 · 20MiB 이하)</span>
    <span class="file-pick">
      <label class="ui-button" aria-disabled={locked}>{table?"파일 변경":"파일 선택"}
        <input type="file" class="visually-hidden" aria-labelledby="csv-file-label" accept=".csv,text/csv"
          bind:this={fileInput} disabled={locked} onchange={() => void choose()} /></label>
    </span>
  </div>
  </div>{#if !table}<p class="context" class:problem={fileProblem} role="status">{fileMessage}</p>{/if}

  {#if table}
    {#if !stored}<section aria-labelledby="csv-preview-title">
      <div class="preview-heading"><h3 id="csv-preview-title">파일 미리보기</h3>
      <p class="tag">{report?.status === "ready"?"저장할 내용을 확인했습니다":"시간과 저장할 신호를 선택하세요"}</p><div class="save-action">
        <button type="button" class="ui-button ui-button-primary csv-save" disabled={!writable || !timeZoneReady || checking || saving || !assetId.trim() || problems.length>0 || !!roleProblem || !!currentProblem}
          aria-describedby={saveNeeds.length?"csv-save-needs":undefined} onclick={() => void confirmAndSave()}>{checking?"내용 확인 중":saving?"측정 기록 저장 중":saveFailed && progress ? "실패한 단계부터 다시 시도" : "확인하고 저장하기"}</button>
        {#if saveNeeds.length}<span id="csv-save-needs">{saveNeeds.join(" · ")}</span>{/if}</div></div>
      {#if saveMessage&&saveFailed}<p class="message failure" role="alert">{saveMessage}</p>{/if}
      {#if report&&report.status!=="ready"&&checkMessage}<p class="message failure" role="alert">{checkMessage}</p>{/if}
      <div class="preview-grid"><div class="preview-main">
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
              onchange={(event) => { timeZoneConfirmed = event.currentTarget.checked; changed(); }} />
            이 CSV의 측정 시각은 위 시간대 기준입니다.
          </label>
        {/if}

      </div>
      {#if problems.length}
        <ul class="problems" aria-label="저장 전에 고칠 것">
          {#each problems as problem, i (i)}<li>{problem}</li>{/each}
        </ul>

      {/if}
      {#if channels.length && points.length}
        <label class="field">미리보기 신호
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
            <line x1="62" x2="632" y1={tick.y} y2={tick.y} class="gridline" />
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
        {#if channels.length}{#if channels.some(name=>labels[name]?.unit.trim()==="A") || operatingCurrent}
        <label class="field">운전 수준을 나눌 전류 (선택)
          <select value={operatingCurrent} disabled={locked} onchange={event=>{operatingCurrent=event.currentTarget.value;changed();}}>
            <option value="">사용하지 않음</option>
            {#each channels.filter(name=>labels[name]?.unit.trim()==="A" || name===operatingCurrent) as name(name)}<option value={name}>{shown(name)} · A</option>{/each}
          </select>
        </label><p class="context">A 단위를 확인한 이 전류로 운전 수준을 나눠 비교합니다.</p>
        {#if currentProblem}<p role="alert">{currentProblem}</p>{/if}
        {:else}<p class="context">전류 열의 단위를 A로 확인하면 운전 수준별 비교에도 사용할 수 있습니다.</p>{/if}{/if}
      </div><div class="preview-units">
    <section aria-labelledby="csv-asset-title">
      <h3 id="csv-asset-title" class="visually-hidden">설비 정보</h3>
      <div class="grid">
        <label class="field">설비 이름·번호<input maxlength="128" placeholder="예: 1호 펌프" autocomplete="off" disabled={locked}
          value={assetId} oninput={(event) => { assetId = event.currentTarget.value; changed(); }} /></label>
      </div>
    </section>

      <section class="signal-editor" aria-label="저장할 측정값과 단위">
        <header><strong>저장할 신호 {channels.length} / {numericColumns.length}개</strong>
          {#if unfilledExamples.length&&!locked}<button type="button" class="unit-examples" onclick={fillExampleUnits}>단위 예시 채우기</button>{/if}</header>
        <p class="context">최대 {MAX_CHANNELS}개 · 신호를 고르고 계측 단위를 입력하세요. 모르면 비워 둘 수 있습니다.</p>
        <div class="signal-table"><table><thead><tr><th scope="col">저장</th><th scope="col">측정값 이름</th><th scope="col">단위</th></tr></thead>
          <tbody>{#each numericColumns as choice(choice.name)}<tr class:omitted={!channels.includes(choice.name)}>
            <td><input type="checkbox" aria-label={choice.name+" 저장"} checked={channels.includes(choice.name)} disabled={locked||(!channels.includes(choice.name)&&channels.length>=MAX_CHANNELS)} onchange={e=>toggle(choice.name,e.currentTarget.checked)}/></td>
            <td><input maxlength="60" aria-label={choice.name+" 이름"} title={"원본 열: "+choice.name} disabled={locked||!channels.includes(choice.name)} value={shown(choice.name)} oninput={e=>rename(choice.name,"label",e.currentTarget.value)}/></td>
            <td><input maxlength="16" aria-label={choice.name+" 단위"} placeholder={unitExample(choice.name)??"—"} disabled={locked||!channels.includes(choice.name)} value={labels[choice.name]?.unit??""} oninput={e=>rename(choice.name,"unit",e.currentTarget.value)}/></td>
          </tr>{/each}</tbody></table></div>
        {#if excludedColumns.length}<p class="omitted-count">선택하지 않은 {excludedColumns.length}개 신호는 저장하지 않습니다.</p>{/if}
      </section>


    {#if progress||saveFailed}<section aria-labelledby="csv-save-title">
      <h3 id="csv-save-title" class="visually-hidden">확인하고 저장하기</h3>
      {#if saveFailed}<p class="context">입력은 남아 있습니다. 다시 시도하면 완료한 단계부터 이어집니다.</p>{/if}

      <details open={saveFailed}><summary>저장 처리 내역</summary><ol class="steps">
        {#each STEPS as item (item.id)}
          <li data-state={steps[item.id].state}><strong>{item.title}</strong><span>{item.text}</span>
            {#if progress || steps[item.id].state !== "pending"}<em>{STATE_TEXT[steps[item.id].state]}{steps[item.id].detail ? " · " + steps[item.id].detail : ""}</em>{/if}</li>
        {/each}
      </ol></details>
    </section>{/if}
      </div></div>
      <div class="advanced-setup"><details>
        <summary>측정 위치·연결 상세 설정 (선택)</summary>
        <label class="field">측정 위치 (선택)<input maxlength="128" placeholder="예: panel-main" autocomplete="off" disabled={locked}
          value={pointId} oninput={(event) => { pointId = event.currentTarget.value; changed(); }} /></label>
        <p class="context">연결 ID와 이름은 자동으로 만듭니다. 필요한 경우 수정하세요.</p>
        <div class="grid">
          <label class="field">연결 ID<input maxlength="128" autocomplete="off" disabled={locked}
            value={sourceId} oninput={(event) => { sourceId = event.currentTarget.value; changed(); }} /></label>
          <label class="field">연결 이름<input maxlength="128" autocomplete="off" disabled={locked}
            value={sourceName} oninput={(event) => { sourceName = event.currentTarget.value; changed(); }} /></label>
        </div>
      </details>
      <details open={declared.length > 0}>
        <summary>3상 전압·전류 역할 지정 (선택 · 3상 전력·불평형 분석에 필요)</summary>
        <PhaseRoles {channels} bind:roles disabled={locked} onchange={changed} />
        {#if roleProblem}<p class="message failure" role="status">{roleProblem}</p>{/if}
      </details>
      {#if !writable}<p class="context">보기 전용에서는 미리보기만 볼 수 있습니다.</p>{/if}
      </div>
      <details><summary>측정값 통계</summary>{#if channels.length}<div class="scroll"><table>
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
        </table></div>{/if}      {#if gaps}
        <p class="context">측정 간격 · 보통 {duration(gaps.usualSeconds)} · 간격이 크게 다른 곳 {gaps.uneven}곳 · 가장 긴 공백 {duration(gaps.longestSeconds)}
          {gaps.longestAfter !== null ? " (" + clock(new Date(gaps.longestAfter).toISOString()) + " 이후)" : ""}</p>
      {/if}
</details>
    </section>


    {/if}
    {#if stored && progress}
      <section aria-labelledby="csv-done-title">
        <h3 id="csv-done-title" tabindex="-1" bind:this={doneHeading}>등록 완료</h3>
        <p><strong>{progress.setup.asset_id}</strong>의 측정 기록을 저장했습니다. 모니터링에서 실제 추이를 바로 볼 수 있습니다.</p>
        <p class="links">
          <a class="ui-button ui-button-primary" href="/web/">모니터링에서 보기 →</a>
          <a href={assetTabUrl(progress.setup.asset_id, "signals")}>원본 신호 보기 →</a>
          {#if progress.setup.phase_channels?.length}
            <a href={assetTabUrl(progress.setup.asset_id, "change", "electrical")}>3상 전력·불평형 보기 →</a>
          {/if}
        </p>
        <button type="button" class="ui-button" onclick={() => void restart()}>다른 파일 등록</button>
      </section>
    {/if}
  {/if}
</section>

<style>
  .file-heading{display:grid;gap:var(--space-3)}
  .file-message{font-size:var(--font-small);margin:0;flex:1}
  .has-file .file-heading{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:var(--space-2)}
  .save-action{margin-left:auto;display:grid;justify-items:end;gap:3px}.save-action span{font-size:12px;color:var(--color-ink-muted)}
  .preview-heading{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--space-3)}
  .csv-start { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  .csv-start > section { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; border-top: 1px solid var(--color-border); padding-top: var(--space-4); }
  h2, h3 { margin: 0; }
  h3 { font-size: var(--font-section); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  .problem { color: var(--color-failure-ink); }
  .flow { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-5); margin: 0; padding: 0; list-style: none; color: var(--color-ink-muted); font-size: var(--font-small); }
  .flow li { display: flex; align-items: center; gap: var(--space-2); }
  .flow .mark { display: inline-grid; place-items: center; width: 1.5rem; height: 1.5rem; border-radius: 999px; border: 1px solid var(--color-control-border); font-weight: 700; font-size: var(--font-label); }
  .flow li[data-state="current"] { color: var(--color-ink); font-weight: 700; }
  .flow li[data-state="current"] .mark { background: var(--color-action); border-color: var(--color-action); color: var(--color-action-ink); }
  .flow li[data-state="done"] .mark { border-color: var(--color-action); color: var(--color-action); }
  .field { display: grid; gap: var(--space-1); font-weight: 650; min-width: 0; }
  input:not([type="checkbox"]), select { font: inherit; font-weight: 400; min-height: 40px; padding: var(--space-2) var(--space-3); min-width: 0;
    border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); }
  input[type="file"] { max-width: 100%; }
  .columns { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 360px)); align-items: end; }
  .columns .choice { grid-column: 1 / -1; }
  /* 넓은 화면에서는 미리보기 그래프 옆에서 이름과 단위를 확인한다. */
  .signal-editor{display:grid;gap:8px}.signal-editor header{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:var(--font-small)}.signal-editor .context,.omitted-count{font-size:12px}.omitted-count{color:var(--color-ink-muted)}
  .signal-table{max-height:250px;overflow:auto;border:1px solid var(--color-border);border-radius:6px}.signal-table thead{position:sticky;top:0;background:var(--color-surface-selected);z-index:1}.signal-table th,.signal-table td{padding:4px 6px;font-size:12px}.signal-table th:first-child{width:40px}.signal-table th:last-child{width:80px}.signal-table td input:not([type="checkbox"]){width:100%;height:30px;min-height:30px;box-sizing:border-box;line-height:1.2;padding:3px 6px;border-color:transparent;border-radius:4px;font-size:var(--font-label)}.signal-table td input:focus{border-color:var(--color-action)}.signal-table .omitted{color:var(--color-ink-muted)}.signal-table .omitted input{opacity:.6}.unit-examples{font:inherit;font-size:12px;padding:4px 6px;background:none;border:0;color:var(--color-action);cursor:pointer}
  .preview-grid { display: grid; gap: var(--space-4) var(--space-8); grid-template-columns: minmax(0, 1fr); align-items: start; }
  .preview-units > section {display:grid;gap:var(--space-2);min-width:0;}
  .preview-units h3{font-size:var(--font-body)}
  .file-row{display:flex;align-items:center;gap:var(--space-4)}
  .advanced-setup{font-size:var(--font-small);display:flex;flex-wrap:wrap;align-items:start;gap:var(--space-2) var(--space-5)}
  .advanced-setup>details[open]{flex-basis:100%}
  .preview-main, .preview-units { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  @media (min-width: 1100px) { .preview-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } }
  .preview-main > .field, .grid > .field { max-width: 360px; }
  .choice { display: flex; gap: var(--space-2); align-items: flex-start; padding-block: var(--space-1); overflow-wrap: anywhere; }
  .tag { font-size: var(--font-small); color: var(--color-ink-muted); }
  .problems { margin: 0; padding-inline-start: var(--space-5); color: var(--color-failure-ink); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-3); }
  .scroll { max-width: 100%; overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; }
  caption { text-align: left; color: var(--color-ink-muted); font-size: var(--font-small); }
  th, td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--color-border); }
  thead th { white-space: nowrap; }
  svg { width: 100%; max-width: 760px; height: auto; max-height: 180px; }
  .gridline { stroke: var(--color-border); stroke-width: 1; opacity: 0.7; }
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
