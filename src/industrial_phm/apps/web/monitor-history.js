import {drawStoredTrend} from "./monitor-signal.js";
import {formatTime} from "./time.js";
// Model-independent observation: the selected asset's stored Asset History, with or without PHM.
// Every history read reloads the server snapshot, so reads stay explicit and bounded: the channel
// list once per asset, and the trend only when the selection changes, new receipt or commit
// evidence appears for the asset, or at most every 30 seconds. A failed read never keeps old values.
const STALE_MS = 30000;
const RETRY_MS = 6000;
const MAX_GROUPS = 3;
const byId = (id) => document.getElementById(id);
const node = (tag, text = "", className = "") => {const e = document.createElement(tag);e.textContent = text;e.className = className;return e;};
const number = (n) => typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("ko-KR", {maximumFractionDigits: 3}) : "—";
const quality = {good: "원본 품질 정상 표시", "non-good": "원본 품질 문제", unknown: "원본 품질 정보 없음"};
const channelCache = new Map();
let selected = {assetId: "", channel: "", range: "1h"};
let loaded = {selectionKey: "", dataKey: "", at: 0, data: null, error: false};
let pending = "", version = 0, paintedKey = "";

function readChannels(assetId, dataKey, onChange) {
  // Channels rarely change: a known list is re-read at most every 30 s, while a missing or
  // failed list is re-read as soon as new stored data is signalled (or after a short retry).
  const cached = channelCache.get(assetId), age = cached ? Date.now() - cached.at : 0;
  const expired = cached && cached.state !== "loading" && (cached.state === "ready" ? age > STALE_MS
    : cached.dataKey !== dataKey || age > (cached.state === "error" ? RETRY_MS : STALE_MS));
  if (cached && !expired) return cached;
  const entry = {state: "loading", channels: cached?.channels || [], dataKey, at: Date.now()};
  channelCache.set(assetId, entry);
  fetch("/api/v1/history/channels?asset_id=" + encodeURIComponent(assetId), {cache: "no-store", signal: AbortSignal.timeout(5000)})
    .then(async (response) => {
      const data = await response.json().catch(() => null);
      if (response.ok && data?.schema_version === 1 && data.asset_id === assetId && Array.isArray(data.channels?.items)) {
        entry.state = data.channels.items.length ? "ready" : "empty";
        entry.channels = data.channels.items;entry.truncated = Boolean(data.channels.truncated);
      } else {entry.state = response.status === 503 ? "unavailable" : "error";entry.channels = [];}
    })
    .catch(() => {entry.state = "error";entry.channels = [];})
    .finally(() => {entry.at = Date.now();if (channelCache.get(assetId) === entry) onChange();});
  return entry;
}

// The asset is model-bound when this is null; a stream option is offered only for real channels.
export function storedChannelState(assetId, dataKey, onChange) {
  return readChannels(assetId, dataKey, onChange);
}

export function invalidateStored(assetId = null) {
  if (assetId === null) channelCache.clear();else channelCache.delete(assetId);
  loaded = {...loaded, at: 0};paintedKey = "";
}

// The PHM input view owns the shared chart while it is shown; repaint the stored view on return.
export function leaveStored() {byId("monitor-history-range-field").hidden = true;paintedKey = "";}
export function selectStoredChannel(channel) {selected.channel = channel;paintedKey = "";}
export function selectStoredRange(range) {selected.range = range;paintedKey = "";}

function setControls(entry) {
  const select = byId("monitor-signal-channel");
  const values = entry.channels;
  if ([...select.options].map((o) => o.value).join("\u0000") !== values.join("\u0000")) {
    select.replaceChildren(...values.map((channel) => {const option = node("option", channel);option.value = channel;return option;}));
  }
  if (!values.includes(selected.channel)) selected.channel = values[0] || "";
  select.value = selected.channel;select.disabled = !values.length;
  byId("monitor-history-range-field").hidden = !values.length;
  byId("monitor-history-range").value = selected.range;
}

function clearStoredDisplay(message) {
  byId("monitor-signal-chart").replaceChildren();byId("monitor-signal-reading").replaceChildren();
  byId("monitor-signal-reading").hidden = true;byId("monitor-signal-legend").textContent = "";
  byId("monitor-signal-state").textContent = message;paintedKey = "";
}

// `asset` is the /api/v1/monitor row; `historyError` is the snapshot's asset-history read scope.
export function showStored({assetId, asset, dataKey, historyError, onChange}) {
  if (selected.assetId !== assetId) {selected = {assetId, channel: "", range: selected.range};paintedKey = "";}
  byId("monitor-signal-mode").textContent = "저장 측정 이력";
  byId("monitor-range-field").hidden = true;byId("monitor-last-good").hidden = true;
  byId("monitor-signal-context").textContent = receiptText(asset);
  const entry = readChannels(assetId, dataKey, onChange);
  setControls(entry);
  if (entry.state === "loading" && !entry.channels.length) {clearStoredDisplay("저장된 측정 신호 목록을 확인하고 있습니다.");return;}
  if (entry.state === "empty") {clearStoredDisplay("이 설비에 저장된 측정 신호가 없습니다. 데이터 연결에서 수신과 이력 저장을 확인하세요.");return;}
  if (entry.state === "unavailable" || entry.state === "error") {
    clearStoredDisplay(historyError || entry.state === "error"
      ? "저장 이력을 읽지 못했습니다. 이전 값을 표시하지 않고 자동으로 다시 조회합니다."
      : "저장된 측정 이력이 확인되지 않습니다. 이력 저장 전이거나 일시적으로 읽지 못했습니다.");
    return;
  }
  const selectionKey = JSON.stringify([assetId, selected.channel, selected.range]);
  const now = Date.now();
  const due = loaded.selectionKey !== selectionKey
    || (loaded.error ? now - loaded.at >= RETRY_MS : loaded.dataKey !== dataKey || now - loaded.at >= STALE_MS);
  if (loaded.selectionKey === selectionKey && loaded.data) paint(loaded.data);
  else if (loaded.selectionKey === selectionKey && loaded.error) clearStoredDisplay("저장된 측정값을 읽지 못했습니다. 이전 값을 표시하지 않고 자동으로 다시 조회합니다.");
  else clearStoredDisplay("저장된 측정값을 읽고 있습니다.");
  const request = selectionKey + "\u0000" + dataKey;
  if (due && pending !== request) void load(assetId, selected.channel, selected.range, selectionKey, dataKey, request, onChange);
}

function receiptText(asset) {
  if (!asset) return "저장된 측정 이력 · 이 설비의 수신 상태는 확인되지 않았습니다.";
  if (asset.data_flow_status === "stored-history") return "저장된 과거 기록 · 등록된 수신 소스가 없어 최근 수신 근거가 없습니다.";
  return "저장된 측정 이력 · " + (asset.last_data_at ? "마지막 수신 " + formatTime(asset.last_data_at) : "수신 근거 없음")
    + " · 수신과 이력 저장은 서로 다른 시점일 수 있습니다.";
}

async function load(assetId, channel, range, selectionKey, dataKey, request, onChange) {
  const token = ++version;pending = request;
  try {
    const params = new URLSearchParams({asset_id: assetId, channel_id: channel, range, anchor: "latest", buckets: "120"});
    const response = await fetch("/api/v1/history/trend?" + params, {cache: "no-store", signal: AbortSignal.timeout(8000)});
    const data = await response.json();
    if (token !== version) return;
    if (!response.ok || data.schema_version !== 1 || data.asset_id !== assetId || !Array.isArray(data.buckets)
        || !Array.isArray(data.latest_stored) || !(data.channel_ids || []).includes(channel)) throw new Error("read_failed");
    loaded = {selectionKey, dataKey, at: Date.now(), data, error: false};
  } catch {
    if (token !== version) return;
    loaded = {selectionKey, dataKey, at: Date.now(), data: null, error: true};
  } finally {
    if (token === version) {pending = "";paintedKey = "";onChange();}
  }
}

export function repaintStored() {paintedKey = "";if (loaded.data && loaded.selectionKey === JSON.stringify([selected.assetId, selected.channel, selected.range])) paint(loaded.data);}

function paint(data) {
  const key = JSON.stringify([loaded.selectionKey, loaded.at]);
  if (paintedKey === key) return;
  paintedKey = key;
  const channel = selected.channel;
  const groups = new Map();
  for (const bucket of data.buckets.filter((b) => b.channel_id === channel)) {
    const id = JSON.stringify([bucket.source_id, bucket.measurement_point_id, bucket.interpretation_id]);
    if (!groups.has(id)) groups.set(id, []);
    groups.get(id).push(bucket);
  }
  const unitFor = (sourceId, pointId) => [...groups.values()].map((g) => g[0])
    .find((b) => b.source_id === sourceId && b.measurement_point_id === pointId)?.semantics?.unit || "";
  const reading = byId("monitor-signal-reading");reading.replaceChildren();
  const latest = data.latest_stored.filter((point) => point.channel_id === channel).slice(0, MAX_GROUPS);
  for (const point of latest) {
    const cell = node("div");
    const unit = unitFor(point.source_id, point.measurement_point_id);
    cell.append(node("small", "마지막 저장 측정값 · " + point.source_id + (point.measurement_point_id ? " / " + point.measurement_point_id : "")
      + (unit ? "" : " · 단위 미확인")),
      node("strong", point.usable_for_display ? number(point.value) + (unit ? " " + unit : "") : "표시 불가 (결측·품질·충돌)"),
      node("small", "원본 측정 " + formatTime(point.event_at)),
      node("small", (quality[point.source_quality] || "원본 품질 " + point.source_quality) + (point.conflicting_duplicate ? " · 중복 값 충돌" : "")));
    reading.append(cell);
  }
  reading.hidden = !latest.length;
  const chart = byId("monitor-signal-chart");chart.replaceChildren();
  const shown = [...groups.values()].slice(0, MAX_GROUPS);
  for (const buckets of shown) {
    const first = buckets[0], unit = first.semantics?.unit || "";
    if (groups.size > 1) chart.append(node("p", "출처 " + first.source_id + (first.measurement_point_id ? " / " + first.measurement_point_id : "")
      + " · " + (unit || "단위 미확인"), "monitor-stored-source"));
    const plot = node("div");chart.append(plot);
    drawStoredTrend(plot, buckets, data.start_at, data.end_at, data.bucket_seconds, unit);
  }
  const counts = data.buckets.filter((b) => b.channel_id === channel).reduce((sum, b) => {
    for (const k of ["usable_count", "null_count", "non_good_count", "conflict_count"]) sum[k] += Number(b[k]) || 0;
    return sum;
  }, {usable_count: 0, null_count: 0, non_good_count: 0, conflict_count: 0});
  byId("monitor-signal-state").textContent = shown.length
    ? "원본 측정 시각 기준 " + formatTime(data.start_at, {seconds: false}) + " ~ " + formatTime(data.end_at, {seconds: false})
      + " · " + data.bucket_seconds + "초 구간 평균과 최소·최대"
    : "선택한 구간에 저장된 측정값이 없습니다. 표시 구간을 넓혀 보세요.";
  byId("monitor-signal-legend").textContent = shown.length
    ? "사용 가능 " + counts.usable_count + " · 결측 " + counts.null_count + " · 품질 문제 " + counts.non_good_count + " · 중복 충돌 "
      + counts.conflict_count + " · 평소 측정 간격보다 긴 공백은 연결하지 않으며, 측정값은 설비 정상·고장 판정이 아닙니다."
      + (groups.size > MAX_GROUPS ? " · 출처 " + groups.size + "개 중 " + MAX_GROUPS + "개 표시" : "")
    : "";
}
