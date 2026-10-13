import {navigate} from "./navigation.js";
import {drawStoredTrend} from "./monitor-signal.js";
import {openMonitorAsset} from "./monitor.js";
import {formatTime} from "./time.js";
// First data from one CSV file: see the file's own signals, check it on the server, then run the
// existing register → activate → receipt → history writes as one visible sequence. Each write
// keeps its own contract and result; the browser preview is never presented as validation or storage.
const MAX_BYTES = 20 * 1024 * 1024;
const HISTORY_WAIT_MS = 15 * 60 * 1000;
const MAX_CHANNELS = 12;
const PREVIEW_BUCKETS = 120;
const byId = (id) => document.getElementById(id);
const node = (tag, text = "", className = "") => {const e = document.createElement(tag);e.textContent = text;if (className) e.className = className;return e;};
const ISO = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$/;
const NUMBER = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;
const TIME_NAME = /time|timestamp|date|시각|시간|일시/i;
const STEPS = ["register", "activate", "receive", "store"];
const stepState = {pending: "대기", running: "진행 중", done: "완료", failed: "실패", unknown: "결과 확인 필요"};
let file = null, table = null, revision = 0, checkedRevision = -1, progress = null, running = false, checkedRows = 0;
let checkedMatch = "absent", syntheticPreview = false;
let fileDigest = "";
const TICKET_KEY = "phm-csv-pending-v1";
function readTicket() {try {return JSON.parse(localStorage.getItem(TICKET_KEY) || "null");} catch {return null;}}
function remember() {
  if (!progress || !fileDigest) return;
  try {localStorage.setItem(TICKET_KEY, JSON.stringify({digest: fileDigest, setup: progress.setup}));} catch {}
}

// RFC 4180 subset matching the server's csv module defaults: comma, double quotes, CRLF or LF.
function parseCsv(text) {
  const rows = [];let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c !== '"') field += c;
      else if (text[i + 1] === '"') {field += '"';i++;} else quoted = false;
    } else if (c === '"' && field === "") quoted = true;
    else if (c === ",") {row.push(field);field = "";}
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);rows.push(row);row = [];field = "";
    } else field += c;
  }
  if (field !== "" || row.length) {row.push(field);rows.push(row);}
  return rows;
}

// Browser-side reading for orientation only. The server validator remains the authority.
function inspect(rows) {
  const header = rows[0] || [];
  const columns = header.map((name, index) => ({name, index, numeric: 0, missing: 0, invalid: 0, iso: 0, zoned: 0, firstMissing: null, firstInvalid: null, firstNonIso: null}));
  const issues = [];
  let blank = null, width = null;
  const data = rows.slice(1);
  data.forEach((row, offset) => {
    const line = offset + 2;
    if (row.length === 1 && row[0] === "") {blank ??= line;return;}
    if (row.length !== header.length) {width ??= line;return;}
    for (const column of columns) {
      const value = row[column.index].trim();
      if (!value) {column.missing++;column.firstMissing ??= line;continue;}
      const iso = ISO.exec(value);
      if (iso) {column.iso++;if (iso[1]) column.zoned++;} else column.firstNonIso ??= line;
      if (NUMBER.test(value) && Number.isFinite(Number(value))) column.numeric++;
      else {column.invalid++;column.firstInvalid ??= line;}
    }
  });
  if (!header.length || header.some((name) => !name.trim())) issues.push(["error", "헤더에 빈 컬럼 이름이 있습니다. 첫 줄의 컬럼 이름을 확인하세요."]);
  if (new Set(header).size !== header.length) issues.push(["error", "헤더에 같은 컬럼 이름이 두 번 이상 있습니다."]);
  if (blank) issues.push(["error", blank + "행이 빈 줄입니다. 빈 줄을 지우세요."]);
  if (width) issues.push(["error", width + "행의 값 개수가 헤더와 다릅니다. 쉼표·따옴표를 확인하세요."]);
  const valid = data.filter((row) => row.length === header.length && !(row.length === 1 && row[0] === "")).length;
  // A time column may still contain a bad row; keep it as a candidate and report that row.
  const times = columns.filter((c) => c.iso && c.iso >= valid / 2)
    .sort((a, b) => Number(TIME_NAME.test(b.name)) - Number(TIME_NAME.test(a.name)) || a.index - b.index);
  return {header, rows: data, columns, issues, times, sampleCount: valid};
}

function timeIssues(columnIndex) {
  const parsed = [];let previous = null, firstBackwards = null, firstInvalidDate = null, naive = false;
  table.rows.forEach((row, offset) => {
    if (row.length !== table.header.length) return;
    const text = row[columnIndex].trim(), match = ISO.exec(text);
    if (!match) return;
    if (!match[1]) naive = true;
    // Without an offset the wall time is placed on UTC only to order and space the preview.
    const at = Date.parse(match[1] ? text.replace(" ", "T") : text.replace(" ", "T") + "Z");
    const day = Date.parse(text.slice(0, 10) + "T00:00:00Z");
    if (!Number.isFinite(at) || !Number.isFinite(day) || new Date(day).toISOString().slice(0, 10) !== text.slice(0, 10) || Number(text.slice(11, 13)) > 23) {
      firstInvalidDate ??= offset + 2;return;
    }
    if (previous !== null && !(at > previous)) firstBackwards ??= offset + 2;
    previous = at;parsed.push({at, row});
  });
  return {parsed, naive, firstBackwards, firstInvalidDate};
}

function resetSave() {
  progress = null;
  for (const step of STEPS) setStep(step, "pending");
  byId("csv-start-save-result").textContent = "";byId("csv-start-save-result").className = "";
  byId("csv-start-done").hidden = true;
}

function invalidateCheck(message = "") {
  revision++;
  byId("csv-start-save").disabled = true;
  const result = byId("csv-start-check-result");
  result.className = message ? "state" : "state hidden";result.textContent = message;
}

function setCurrent(step) {
  for (const item of byId("csv-start-steps").children) {
    if (item.dataset.step === step) item.setAttribute("aria-current", "step");else item.removeAttribute("aria-current");
  }
}

async function chooseFile(example = null) {
  const chosen = example || byId("csv-start-file").files[0];
  file = null;table = null;resetSave();invalidateCheck();
  syntheticPreview = Boolean(example);
  byId("csv-start-preview").hidden = true;byId("csv-start-details").hidden = true;
  const state = byId("csv-start-file-state");state.className = "hint";
  if (!chosen) {state.textContent = "아직 파일을 선택하지 않았습니다.";setCurrent("file");return;}
  if (!/\.csv$/i.test(chosen.name) || !chosen.size) {
    state.className = "hint error";state.textContent = "비어 있지 않은 .csv 파일을 선택하세요.";return;
  }
  if (chosen.size > MAX_BYTES) {
    state.className = "hint error";
    state.textContent = "이 파일은 " + (chosen.size / 1048576).toFixed(1) + "MiB입니다. Web에서 바로 저장할 수 있는 CSV는 20MiB까지입니다. "
      + "기간을 나눈 20MiB 이하 파일로 시작하거나, 운영 중지 상태에서 'industrial-phm maintenance history backfill' 절차로 적재하세요.";
    return;
  }
  let text;
  try {
    const bytes = new Uint8Array(await chosen.arrayBuffer());
    fileDigest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((v) => v.toString(16).padStart(2, "0")).join("");
    text = new TextDecoder("utf-8", {fatal: true}).decode(bytes).replace(/^﻿/, "");
  } catch {
    state.className = "hint error";state.textContent = "UTF-8로 읽을 수 없는 파일입니다. CSV를 UTF-8로 다시 저장한 뒤 선택하세요.";return;
  }
  file = chosen;table = inspect(parseCsv(text));
  byId("csv-start-channels").replaceChildren();byId("csv-start-time").replaceChildren();
  state.textContent = (example ? "합성 예시 파일 · 실제 설비 아님 · 모니터링 전용 · " : "") + chosen.name + " · " + (chosen.size / 1024).toFixed(1) + "KiB · 데이터 " + table.sampleCount + "행 · 컬럼 " + table.header.length + "개";
  renderColumns();
  const stem = chosen.name.replace(/\.csv$/i, "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "file";
  byId("csv-start-source-id").value = "csv-" + stem + "-" + Math.random().toString(16).slice(2, 6);
  byId("csv-start-source-name").value = chosen.name.slice(0, 128);
  const ticket = readTicket();
  if (!syntheticPreview && ticket?.digest === fileDigest && ticket.setup) {
    for (const [id, key] of [["csv-start-source-id", "source_id"], ["csv-start-source-name", "name"], ["csv-start-asset", "asset_id"], ["csv-start-point", "measurement_point_id"]]) {
      byId(id).value = typeof ticket.setup[key] === "string" ? ticket.setup[key] : "";
    }
    const column = table.columns.find((c) => c.name === ticket.setup.timestamp_column);
    if (column) {byId("csv-start-time").value = String(column.index);renderColumns();}
    for (const box of byId("csv-start-channels").querySelectorAll("input")) box.checked = (ticket.setup.channel_columns || []).includes(box.value);
    drawPreview();state.textContent += " · 이전 작업 입력 복원 · 서버 점검으로 동일성을 다시 확인하세요.";
  }
  byId("csv-start-preview").hidden = false;byId("csv-start-details").hidden = false;
  setCurrent("asset");
}

function renderColumns() {
  const timeSelect = byId("csv-start-time"), previous = timeSelect.value;
  timeSelect.replaceChildren(...table.times.map((c) => {const o = node("option", c.name);o.value = String(c.index);return o;}));
  if (!table.times.length) timeSelect.append(Object.assign(node("option", "시간 컬럼 후보 없음"), {value: ""}));
  if ([...timeSelect.options].some((o) => o.value === previous)) timeSelect.value = previous;
  const timeIndex = timeSelect.value === "" ? -1 : Number(timeSelect.value);
  const box = byId("csv-start-channels");
  const checked = new Set([...box.querySelectorAll("input:checked")].map((i) => i.value));
  const choices = node("div", "", "choices");
  const candidates = table.columns.filter((c) => c.index !== timeIndex);
  let defaults = 0;
  for (const column of candidates) {
    const label = node("label", "", "choice");
    const input = Object.assign(document.createElement("input"), {type: "checkbox", value: column.name});
    const usable = column.numeric > 0 && !column.invalid;
    input.checked = checked.size ? checked.has(column.name) && usable : usable && defaults++ < MAX_CHANNELS;
    input.disabled = !usable;
    const note = !usable ? (column.invalid ? " · 숫자 아닌 값 " + column.invalid + "개 (" + column.firstInvalid + "행부터)" : " · 값 없음")
      : column.missing ? " · 빈 값 " + column.missing + "개 (" + column.firstMissing + "행부터)" : "";
    label.append(input, document.createTextNode(column.name + note));
    input.addEventListener("change", () => {limitChannels();invalidateCheck("저장할 컬럼이 바뀌었습니다. 서버 점검을 다시 실행하세요.");drawPreview();});
    choices.append(label);
  }
  box.replaceChildren(node("legend", "저장할 측정 컬럼 (숫자 · 최대 " + MAX_CHANNELS + "개)"), choices);
  limitChannels();drawPreview();
}

function selectedChannels() {return [...byId("csv-start-channels").querySelectorAll("input:checked")].map((i) => i.value);}

function limitChannels() {
  const full = selectedChannels().length >= MAX_CHANNELS;
  for (const input of byId("csv-start-channels").querySelectorAll("input")) {
    const column = table.columns.find((c) => c.name === input.value);
    input.disabled = !(column.numeric > 0 && !column.invalid) || (full && !input.checked);
  }
}

function drawPreview() {
  const issues = byId("csv-start-issues");issues.replaceChildren();
  const list = [...table.issues];
  const timeIndex = byId("csv-start-time").value === "" ? -1 : Number(byId("csv-start-time").value);
  const channels = selectedChannels();
  let timing = null;
  if (timeIndex < 0) list.push(["error", "ISO 8601 시간 컬럼을 찾지 못했습니다. Web 이력 저장에는 예: 2026-10-11T09:00:00+09:00 형식의 시간 컬럼이 필요합니다."]);
  else {
    timing = timeIssues(timeIndex);
    if (timing.naive) list.push(["error", "시각에 시간대(+09:00, Z 등)가 없습니다. 이력은 원래 측정 순간으로 저장하므로 시간대가 필요합니다. 예: 2026-10-11T09:00:00+09:00"]);
    const column = table.columns.find((c) => c.index === timeIndex);
    if (column.missing) list.push(["error", column.firstMissing + "행의 시각이 비어 있습니다 (빈 시각 " + column.missing + "개)."]);
    if (column.firstNonIso) list.push(["error", column.firstNonIso + "행의 시각을 ISO 8601로 읽을 수 없습니다. 예: 2026-10-11T09:00:00+09:00"]);
    if (timing.firstBackwards) list.push(["error", timing.firstBackwards + "행의 시각이 앞 행보다 늦지 않습니다. 시간 순서대로 정렬하고 중복 시각을 확인하세요."]);
    if (timing.firstInvalidDate) list.push(["error", timing.firstInvalidDate + "행의 날짜·시각이 유효하지 않습니다. 달력 날짜와 시·분·초를 확인하세요."]);
  }
  for (const name of channels) {
    const column = table.columns.find((c) => c.name === name);
    if (column.missing) list.push(["error", name + " 컬럼의 " + column.firstMissing + "행이 비어 있습니다 (빈 값 " + column.missing + "개). 빈 측정값은 저장할 수 없습니다."]);
  }
  if (!channels.length) list.push(["error", "저장할 숫자 측정 컬럼을 하나 이상 선택하세요."]);
  if (!list.length) list.push(["ok", "브라우저에서 확인한 구조 문제는 없습니다. 서버 점검으로 최종 확인합니다."]);
  for (const [kind, text] of list) issues.append(node("li", text, kind === "error" ? "error" : ""));
  const select = byId("csv-start-preview-channel"), previous = select.value;
  select.replaceChildren(...channels.map((name) => Object.assign(node("option", name), {value: name})));
  select.value = channels.includes(previous) ? previous : channels[0] || "";
  drawChart();
}

function drawChart() {
  const select = byId("csv-start-preview-channel");
  const timeIndex = byId("csv-start-time").value === "" ? -1 : Number(byId("csv-start-time").value);
  const timing = timeIndex < 0 ? null : timeIssues(timeIndex);
  const chart = byId("csv-start-chart"), note = byId("csv-start-chart-note");
  chart.replaceChildren();note.textContent = "";
  const column = table.columns.find((c) => c.name === select.value);
  if (!timing || !column || timing.parsed.length < 1) {note.textContent = "시간 컬럼과 측정 컬럼을 고르면 실제 값을 그립니다.";return;}
  const points = timing.parsed;
  // Large files have hundreds of thousands of rows: never spread them into Math.min/max arguments.
  let start = Infinity, end = -Infinity;
  for (const {at} of points) {if (at < start) start = at;if (at > end) end = at;}
  end = Math.max(end, start + 1000);
  const step = Math.max(1, Math.ceil((end - start) / PREVIEW_BUCKETS));
  const buckets = new Map();
  for (const {at, row} of points) {
    const index = Math.max(0, Math.min(PREVIEW_BUCKETS - 1, Math.floor((at - start) / step)));
    const bucket = buckets.get(index) || {bucket_start: new Date(start + index * step).toISOString(), usable_count: 0, sum: 0, minimum: null, maximum: null};
    const text = row[column.index].trim(), value = Number(text);
    if (text && NUMBER.test(text) && Number.isFinite(value)) {
      bucket.usable_count++;bucket.sum += value;
      bucket.minimum = bucket.minimum === null ? value : Math.min(bucket.minimum, value);
      bucket.maximum = bucket.maximum === null ? value : Math.max(bucket.maximum, value);
    }
    buckets.set(index, bucket);
  }
  const rows = [...buckets.values()].map((b) => ({...b, mean: b.usable_count ? b.sum / b.usable_count : null}));
  drawStoredTrend(chart, rows, new Date(start).toISOString(), new Date(start + step * PREVIEW_BUCKETS).toISOString(), step / 1000, "", {timeLabels: !timing.naive});
  const first = points[0].row[timeIndex].trim(), last = points.at(-1).row[timeIndex].trim();
  note.textContent = "파일의 실제 값 " + points.length + "행 · 구간 평균과 최소·최대 · 원본 표기 " + first + " ~ " + last
    + (timing.naive ? " · 시간대가 없어 KST로 바꾸지 않았습니다" : " · " + formatTime(points[0].at) + " ~ " + formatTime(points.at(-1).at));
}

function setup() {
  const timeIndex = byId("csv-start-time").value;
  return {
    source_id: byId("csv-start-source-id").value.trim(), name: byId("csv-start-source-name").value.trim(),
    asset_id: byId("csv-start-asset").value.trim(), measurement_point_id: byId("csv-start-point").value.trim(),
    channel_columns: selectedChannels(), timestamp_column: timeIndex === "" ? "" : table.header[Number(timeIndex)],
  };
}

async function base64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer()), parts = [];
  for (let offset = 0; offset < bytes.length; offset += 8192) parts.push(String.fromCharCode(...bytes.subarray(offset, offset + 8192)));
  return btoa(parts.join(""));
}

async function post(path, payload) {
  const session = await (await fetch("/api/v1/session", {cache: "no-store", credentials: "same-origin"})).json();
  if (session.write_scope !== "supervisor-owned-source-control") throw Object.assign(new Error("read-only"), {code: "read-only"});
  let response;
  try {
    response = await fetch(path, {method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token}, body: JSON.stringify(payload)});
  } catch {throw Object.assign(new Error("outcome-unknown"), {code: "command_outcome_unknown"});}
  const body = await response.json().catch(() => null);
  if (!response.ok) throw Object.assign(new Error("http-" + response.status), {code: body?.error?.code || "http-" + response.status});
  if (body?.schema_version !== 1) throw Object.assign(new Error("schema"), {code: "command_outcome_unknown"});
  return body;
}

function explain(error) {
  return ({
    "read-only": "감독형 Web에서만 파일을 저장할 수 있습니다. 이 화면은 읽기 전용입니다.",
    workspace_writer_busy: "다른 작업이 작업공간을 쓰는 중입니다. 잠시 후 다시 시도하세요.",
    source_id_exists: "이미 등록된 소스 ID입니다. '소스 ID·이름'에서 다른 ID를 사용하세요.",
    invalid_source_action: "서버가 입력을 거부했습니다. 설비 ID·컬럼·파일 형식을 확인하세요.",
    source_control_conflict: "현재 소스 상태에서 이 단계를 실행할 수 없습니다. 소스 목록에서 상태를 확인하세요.",
    command_outcome_unknown: "요청 결과를 확인하지 못했습니다. 다시 시도하면 서버 상태를 먼저 확인한 뒤 이어서 진행합니다.",
    history_interrupted: "서비스 재시작으로 이력 저장이 중단됐습니다. 다시 시도하면 이어서 저장합니다.",
    source_state_unavailable: "이력 저장소에 쓰지 못했습니다. 운영 관리에서 서비스 상태를 확인한 뒤 다시 시도하세요.",
  })[error.code] || "요청에 실패했습니다. 로컬 서버 상태를 확인하고 다시 시도하세요.";
}

async function check() {
  const output = byId("csv-start-check-result"), button = byId("csv-start-check");
  const values = setup();
  if (!file || !table) return;
  if (syntheticPreview) {output.className = "state";output.textContent = "합성 예시는 미리보기 전용입니다. 격리 예시 환경에서 둘러보세요. 현재 작업공간에는 저장하지 않습니다.";return;}
  if (!values.asset_id || !values.source_id || !values.name) {output.className = "state error";output.textContent = "설비 ID를 입력하세요. 소스 ID·이름도 비어 있으면 안 됩니다.";return;}
  if (!values.timestamp_column || !values.channel_columns.length) {output.className = "state error";output.textContent = "시간 컬럼과 저장할 측정 컬럼을 확인하세요.";return;}
  const token = ++revision;button.disabled = true;
  output.className = "state";output.textContent = "서버의 실제 데이터 검증기로 파일을 점검합니다. 아무것도 저장하지 않습니다.";
  setCurrent("check");
  try {
    const report = await post("/api/v1/sources/file/upload/preflight", {setup: values, csv_base64: await base64(file)});
    if (token !== revision) return;
    if (report.meaning !== "csv-preflight-only-not-registered-or-ingested") throw Object.assign(new Error("schema"), {code: "schema-mismatch"});
    const lines = [];
    if (report.status === "ready") {
      checkedRevision = token;checkedMatch = report.registration_match;checkedRows = report.sample_count * report.channel_columns.length;
      lines.push("서버 점검 통과 · 측정값 " + report.sample_count + "행 · " + report.channel_columns.join(", "),
        "원본 측정 " + formatTime(report.first_timestamp) + " ~ " + formatTime(report.last_timestamp) + " · 아직 저장하지 않았습니다.");
      if (report.quality_warnings?.length) lines.push("측정 간격 주의: " + report.quality_warnings.join(", ") + " · 원래 간격대로 저장합니다.");
      if (checkedMatch === "matching") lines.push("기존 파일·설정과 동일합니다. 저장 상태를 확인해 이어서 진행할 수 있습니다.");
    } else {
      lines.push(report.status === "blocked" ? "서버 점검 실패 · 파일 또는 설정을 고친 뒤 다시 점검하세요." : "추가 확인 필요 · 아직 저장할 수 없습니다.");
    }
    if (report.issue) lines.push((report.issue.row_number ? report.issue.row_number + "행" + (report.issue.column ? " / " + report.issue.column + " 컬럼" : "") + ": " : "") + report.issue.guidance);
    output.className = report.status === "ready" ? "state" : "state error";output.textContent = lines.join("\n");
    byId("csv-start-save").disabled = report.status !== "ready";
    if (report.status === "ready") setCurrent("save");
  } catch (error) {
    if (token !== revision) return;
    output.className = "state error";output.textContent = explain(error);
  } finally {button.disabled = false;}
}

function setStep(step, state, detail = "") {
  const item = byId("csv-start-save-steps").querySelector('[data-step="' + step + '"]');
  item.dataset.state = state;item.querySelector("em").textContent = stepState[state] + (detail ? " · " + detail : "");
}

function lockInputs(locked) {
  for (const id of ["csv-start-file", "csv-start-time", "csv-start-asset", "csv-start-point", "csv-start-source-id", "csv-start-source-name", "csv-start-check"]) byId(id).disabled = locked;
  for (const input of byId("csv-start-channels").querySelectorAll("input")) input.disabled = locked;
  if (!locked) limitChannels();
}

// Resume from durable server state, so a retry never repeats a completed or unknown registration.
async function resync() {
  const response = await fetch("/api/v1/sources", {cache: "no-store", credentials: "same-origin", signal: AbortSignal.timeout(5000)})
    .catch(() => {throw Object.assign(new Error("read"), {code: "command_outcome_unknown"});});
  const data = await response.json().catch(() => {throw Object.assign(new Error("read"), {code: "command_outcome_unknown"});});
  if (!response.ok || data.schema_version !== 1) throw Object.assign(new Error("read"), {code: "command_outcome_unknown"});
  const source = (data.sources?.items || []).find((item) => item.source_id === progress.setup.source_id);
  if (source) {
    const verified = await post("/api/v1/sources/file/upload/preflight", {setup: progress.setup, csv_base64: await base64(file)});
    if (verified.status !== "ready" || verified.registration_match !== "matching") throw Object.assign(new Error("other"), {code: "source_id_exists"});
  }
  progress.done.register = Boolean(source);
  progress.done.activate = source?.lifecycle_state === "active";
  // The receipt has no content digest: verify the current file again before reusing a batch.
  progress.done.receive = false;
}

async function save() {
  if (running || syntheticPreview || checkedRevision !== revision || !file) return;
  running = true;byId("csv-start-save").disabled = true;
  const output = byId("csv-start-save-result");output.className = "";
  const retry = Boolean(progress) || checkedMatch === "matching";
  progress ??= {setup: setup(), done: {}, stored: null};
  remember();
  lockInputs(true);
  let current = STEPS.find((step) => !progress.done[step]) || "store";
  try {
    if (retry) {output.textContent = "서버의 현재 소스 상태를 확인하고 이어서 진행합니다.";await resync();}
    for (const step of STEPS) if (progress.done[step]) setStep(step, "done");
    current = "register";
    if (!progress.done.register) {
      setStep(current, "running");
      const result = await post("/api/v1/sources/file/upload", {setup: progress.setup, csv_base64: await base64(file)});
      if (result.registration_state !== "registered" || result.source_id !== progress.setup.source_id) throw Object.assign(new Error("schema"), {code: "schema-mismatch"});
      progress.done.register = true;setStep(current, "done", "소스 " + result.source_id);
    }
    current = "activate";
    if (!progress.done.activate) {
      setStep(current, "running");
      const result = await post("/api/v1/sources/lifecycle", {source_id: progress.setup.source_id, target_state: "active"});
      if (result.lifecycle_state !== "active") throw Object.assign(new Error("state"), {code: "source_control_conflict"});
      progress.done.activate = true;setStep(current, "done");
    }
    current = "receive";
    if (!progress.done.receive) {
      setStep(current, "running");
      const result = await post("/api/v1/sources/file/receive", {source_id: progress.setup.source_id});
      if (result.cycle_state !== "succeeded" || result.accepted_new_receipt !== true) {
        throw Object.assign(new Error("receipt"), {code: "receipt", detail: result.failure_scope});
      }
      progress.done.receive = true;setStep(current, "done", "수신 " + formatTime(result.accepted_received_at));
    }
    current = "store";
    setStep(current, "running", "시작 요청 중");
    // The supervisor writes history in the background; re-running a stored batch reuses its
    // commit, so a retry here cannot duplicate history.
    const job = await post("/api/v1/sources/file/backfill/start", {source_id: progress.setup.source_id});
    if (job.source_id !== progress.setup.source_id || !["running", "succeeded"].includes(job.state)) {
      throw Object.assign(new Error("schema"), {code: "schema-mismatch"});
    }
    const stored = await waitForHistory(progress.setup.source_id, job.started_at, (seconds, known) => setStep(current, known ? "running" : "unknown",
      "경과 " + seconds + "초 · " + (known ? "서버에서 저장 중 · 다른 화면으로 이동해도 작업은 유지됩니다" : "최근 상태 조회 실패 · 저장 결과 미확정")));
    progress.done.store = true;progress.stored = stored;
    try {localStorage.removeItem(TICKET_KEY);} catch {}
    setStep(current, "done", "측정값 " + stored.event_count.toLocaleString("ko-KR") + "개");
    finish();
  } catch (error) {
    setStep(current, ["command_outcome_unknown", "history_interrupted"].includes(error.code) ? "unknown" : "failed");
    output.className = "error";
    output.textContent = (error.code === "receipt" ? "파일을 다시 읽어 수신 근거를 남기지 못했습니다 (" + (error.detail || "원인 미확인") + "). " : explain(error) + " ")
      + (progress.done.register ? "입력은 유지되며, 다시 시도하면 완료된 단계는 건너뜁니다." : "입력은 그대로 유지됩니다.");
    if (!progress.done.register && error.code !== "command_outcome_unknown") {progress = null;lockInputs(false);}
    byId("csv-start-save").textContent = progress ? "실패한 단계부터 다시 시도" : "등록하고 이력 저장";
    byId("csv-start-save").disabled = false;
  } finally {
    running = false;
    document.dispatchEvent(new CustomEvent("workspace-changed"));
  }
}

// Poll the supervisor job status. A failed status read is not a failed write: keep waiting.
async function waitForHistory(sourceId, startedAt, onTick) {
  const started = Date.now();
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    let job = null;
    try {
      const response = await fetch("/api/v1/sources", {cache: "no-store", credentials: "same-origin", signal: AbortSignal.timeout(5000)});
      const data = await response.json();
      if (response.ok && data.schema_version === 1) job = (data.sources?.items || []).find((s) => s.source_id === sourceId)?.file_history_job || null;
    } catch {}
    onTick(Math.round((Date.now() - started) / 1000), Boolean(job));
    if (job && job.started_at !== startedAt) throw Object.assign(new Error("job-changed"), {code: "command_outcome_unknown"});
    if (job?.state === "succeeded" && Number.isSafeInteger(job.event_count) && Number.isSafeInteger(job.history_snapshot_id)) return job;
    if (job?.state === "failed") throw Object.assign(new Error("history"), {code: job.failure || "source_state_unavailable"});
    if (job?.state === "interrupted") throw Object.assign(new Error("history"), {code: "history_interrupted"});
    if (Date.now() - started > HISTORY_WAIT_MS) throw Object.assign(new Error("history"), {code: "command_outcome_unknown"});
  }
}

function finish() {
  const {setup: values, stored} = progress;
  const timeIndex = Number(byId("csv-start-time").value), timing = timeIssues(timeIndex);
  const span = timing.parsed.length ? timing.parsed.at(-1).at - timing.parsed[0].at : 0;
  const range = span >= 86400000 ? "7d" : span >= 3600000 ? "24h" : span >= 900000 ? "1h" : "15m";
  byId("csv-start-save-result").textContent = "저장 완료 · 설비 " + values.asset_id + "에 측정값 " + stored.event_count.toLocaleString("ko-KR") + "개를 원래 측정 시각으로 저장했습니다. PHM 분석은 실행하지 않았습니다.";
  byId("csv-start-done").hidden = false;byId("csv-start-save").hidden = true;
  setCurrent("monitor");
  const open = byId("csv-start-open-monitor");
  open.onclick = () => {
    openMonitorAsset(values.asset_id, {channel: byId("csv-start-preview-channel").value || values.channel_columns[0], range, sourceId: values.source_id});
    navigate("#monitor", byId("monitor-signal-title"));
  };
  open.focus();
}

// Bundled synthetic examples, like Gradio's examples: one click fills the same flow a user's file
// takes. They are labelled as synthetic and never presented as a real asset's measurements.
const EXAMPLES = {
  motor: {file: "example-motor.csv", asset: "example-motor-01", source: "example-motor", name: "합성 예시 · 모터 전류·진동"},
  invalid: {file: "example-invalid.csv", asset: "example-invalid-01", source: "example-invalid", name: "합성 예시 · 오류 파일"},
};

async function loadExample(key) {
  const example = EXAMPLES[key];
  if (progress) restart();
  const response = await fetch("/web/" + example.file, {cache: "no-store", credentials: "same-origin"});
  if (!response.ok) throw new Error("example-unavailable");
  byId("csv-start-file").value = "";
  await chooseFile(new File([await response.blob()], example.file, {type: "text/csv"}));
  byId("csv-start-asset").value = example.asset;
  byId("csv-start-source-id").value = example.source;byId("csv-start-source-name").value = example.name;
  invalidateCheck();
}

// Kibana-style sample data: run the same check → register → store sequence for the bundled
// example and open the Monitor. A repeated click resumes from the stored example, never duplicates it.
export async function exploreExample() {document.dispatchEvent(new CustomEvent("isolated-example-request"));}

function restart() {
  byId("csv-start-file").value = "";byId("csv-start-asset").value = "";byId("csv-start-point").value = "";
  byId("csv-start-save").hidden = false;byId("csv-start-save").textContent = "등록하고 이력 저장";
  lockInputs(false);void chooseFile();byId("csv-start-file").focus();
}

export function initializeCsvStart() {
  byId("csv-start-file").addEventListener("change", () => void chooseFile());
  byId("csv-start-time").addEventListener("change", () => {invalidateCheck("시간 컬럼이 바뀌었습니다. 서버 점검을 다시 실행하세요.");renderColumns();});
  byId("csv-start-preview-channel").addEventListener("change", drawChart);
  for (const id of ["csv-start-asset", "csv-start-point", "csv-start-source-id", "csv-start-source-name"]) {
    byId(id).addEventListener("input", () => {if (!progress) invalidateCheck("입력이 바뀌었습니다. 서버 점검을 다시 실행하세요.");});
  }
  byId("csv-start-asset").addEventListener("keydown", (event) => {if (event.key === "Enter") {event.preventDefault();void check();}});
  byId("csv-start-check").addEventListener("click", () => void check());
  byId("csv-start-save").addEventListener("click", () => void save());
  byId("csv-start-restart").addEventListener("click", restart);
  byId("csv-start-example-motor").addEventListener("click", () => void loadExample("motor").catch(() => {}));
  byId("csv-start-example-invalid").addEventListener("click", () => void loadExample("invalid").catch(() => {}));
  new ResizeObserver(() => {if (table && !byId("csv-start-preview").hidden) drawChart();}).observe(byId("csv-start-chart"));
}
