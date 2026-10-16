import { byId, create, clear, fmt, num, rows, empty, getJSON, presentError } from "./web-utils.js";
import { createSourceManagement } from "./source-management.js";
import { createAnalysisRecords } from "./analysis-records.js";
import { loadRuntimeStatus, systemViews, renderMonitorAttention } from "./system-status.js";
import { initializeSyntheticDemo } from "./synthetic-demo.js";
import { initializeCondition, loadCondition } from "./condition.js";
import { initializeNavigation, navigate } from "./navigation.js";
import { initializePhm, refreshPhm } from "./phm.js";
import { initializeMonitor, refreshMonitor } from "./monitor.js";
import { currentAsset, initializeAssetContext, onAssetChange, registerAssets } from "./asset-context.js";
import { initializeCsvStart, exploreExample } from "./csv-start.js";
import { formatTime } from "./time.js";
import { initializeSignalExplore } from "./signal-explore.js";
import { initializeCapabilities } from "./capabilities.js";
import { initializeForecast, refreshForecast } from "./forecast.js";
import { initializeOutlookCaptures } from "./outlook-captures.js";
import { initializeAnomalyExplore } from "./anomaly-explore.js";
// Packaged Operations Web UI. All server strings enter the DOM as text, never HTML.
// Source mutations are explicit and protected; monitoring reads never trigger analysis.
let phmModelCount = 0;
let monitor = null;
let monitorReadState = "loading";
let sourceSnapshot = null;
let sourceReadState = "loading";
let latestStored = [];
const sourceHistory = new Map();
let selectedAsset = "";
let selectedChannels = [];
let generation = 0;
let trendSequence = 0;
const records = createAnalysisRecords({getMonitor: () => monitor, refresh, setNotice});
const evidenceViews = records.render;
const sources = createSourceManagement({
  getMonitor: () => monitor, sourceHistory, refresh, openSavedAnalysis: records.openSavedAnalysis,
  onSourceRead: (state, data = sourceSnapshot) => {sourceReadState = state;sourceSnapshot = data;renderWorkspace();},
});
const {loadSources, renderOnboardingGuide, analyzeFile} = sources;
function setNotice(message, error = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.className = message ? "notice" + (error ? " error" : "") : "notice hidden";
}
function trendState(message, error = false) {
  const node = byId("trend-state");
  node.textContent = message;
  node.className = message ? "state" + (error ? " error" : "") : "state hidden";
}
function renderWorkspace() {
  const title = byId("workspace-state");
  const detail = byId("workspace-detail");
  const start = byId("workspace-start");
  start.classList.add("hidden");
  document.body.dataset.workspaceState = "known";
  if (monitorReadState === "loading" || sourceReadState === "loading") {
    title.textContent = "작업공간 확인 중";
    detail.textContent = "관측·등록·저장소 조회 상태를 확인합니다.";
    return;
  }
  const errors = monitorReadState === "error" || sourceReadState === "error"
    || monitor?.system_error_scopes?.length || sourceSnapshot?.read_error_scopes?.length
    || sourceSnapshot?.live_evidence_error_scopes?.length;
  if (errors) {
    title.textContent = "조회 미확인 · 빈 작업공간으로 판단할 수 없습니다";
    detail.textContent = "일부 근거를 읽지 못했습니다. 오류 안내와 시스템 근거를 확인하고 다시 불러오세요.";
    return;
  }
  const sources = rows(sourceSnapshot, "sources");
  const assets = rows(monitor, "assets");
  const analyses = (monitor?.phase_unbalance_analyses?.total || 0) + (monitor?.file_feature_analyses?.total || 0);
  const received = sources.some((source) => source.last_live_receive_fresh);
  const hasEvidence = phmModelCount || assets.length || sources.length || analyses || monitor?.review_requests?.total;
  if (!hasEvidence && !monitor?.assets?.truncated && !sourceSnapshot?.sources?.truncated) {
    document.body.dataset.workspaceState = "empty";
    title.textContent = "빈 작업공간";
    detail.textContent = "등록 소스와 관측·분석·검토 기록이 없습니다.";
    start.classList.remove("hidden");
  } else if (received) {
    title.textContent = "최근 수신 근거 있음";
    detail.textContent = "조회 시점 기준 30초 이내 OPC UA 수신 기록이 있습니다. 저장·분석 결과와 관측 시각은 각각 확인하세요.";
  } else if (latestStored.length) {
    title.textContent = "저장된 기록 데이터";
    detail.textContent = "저장된 과거 측정값을 표시합니다.";
  } else {
    title.textContent = "등록된 데이터";
    detail.textContent = "소스 " + (sourceSnapshot?.sources?.total ?? "미확인") + "개 · 설비 "
      + (monitor?.assets?.total ?? "미확인") + "개 · 분석 " + analyses + "건";
  }
}
function checkedChannels() {
  return [...byId("channel-options").querySelectorAll('input[type="checkbox"]:checked')].map((n) => n.value);
}
function changeChannelSelection() {
  const ids = checkedChannels();
  byId("channel-options").querySelectorAll('input[type="checkbox"]:not(:checked)').forEach((node) => {
    node.disabled = ids.length >= 6;
  });
  selectedChannels = ids;
  byId("show-trend").disabled = !selectedAsset || !selectedChannels.length;
}
async function loadChannels(id, token) {
  const box = byId("channel-options");
  clear(box);
  const legend = create("legend", null, "비교할 신호 (최대 6개)");
  box.append(legend, create("p", "muted", "저장된 신호를 조회 중입니다."));
  try {
    const url = "/api/v1/history/channels?asset_id=" + encodeURIComponent(id);
    const response = await getJSON(url);
    if (token !== generation) return;
    clear(box); box.append(legend);
    const ids = rows(response, "channels");
    if (!ids.length) {box.append(create("p", "empty", "저장된 신호가 없습니다. 연결과 수신 기록을 확인하세요.")); return;}
    const choices = create("div", "choices");
    ids.forEach((channel, index) => {
      const label = create("label", "choice");
      const input = create("input"); input.type = "checkbox"; input.value = channel;
      input.checked = selectedChannels.length ? selectedChannels.includes(channel) : index === 0; input.addEventListener("change", changeChannelSelection);
      label.append(input, document.createTextNode(channel));
      choices.append(label);
    });
    box.append(choices);
    if (response.channels.truncated) box.append(create("p", "muted", "신호가 100개를 초과합니다. 목록에 표시되지 않는 항목이 있습니다."));
    changeChannelSelection();
    if (selectedChannels.length) await loadTrend(token);
  } catch (error) {
    if (token !== generation) return;
    clear(box);box.append(legend);
    box.append(create("p", "empty", presentError(error)));
    trendState("신호 목록을 확인할 수 없습니다.", true);
  }
}
const svgNode = (name) => document.createElementNS("http://www.w3.org/2000/svg", name);
function drawSeries(entries, group) {
  const root = create("div", "trend-group");
  root.append(create("div", "trend-title", group.channel_id + " · " + group.source_id));
  root.append(create("div", "trend-meta", "측정 지점: " + fmt(group.measurement_point_id) + " · 단위: " + fmt(group.semantics && group.semantics.unit) + " · " + fmt(group.semantics && group.semantics.observed_property)));
  if (group.semantics?.unit_evidence || group.semantics?.interpretation_evidence) {
    const details = create("details", "measurement-provenance");
    details.append(create("summary", null, "측정 의미·출처 근거"));
    details.append(create("p", "hint", "단위 근거: " + fmt(group.semantics.unit_evidence)));
    details.append(create("p", "hint", "해석·출처 근거: " + fmt(group.semantics.interpretation_evidence)));
    root.append(details);
  }
  const svg = svgNode("svg");
  svg.setAttribute("class", "trend-svg"); svg.setAttribute("viewBox", "0 0 640 130");
  svg.setAttribute("role", "img");svg.setAttribute("aria-label", "연속선을 그리지 않은 관측 버킷 평균 점 그래프. 비어 있는 시간대는 공백입니다.");
  const axis = svgNode("path");axis.setAttribute("d","M28 12 V110 H628");axis.setAttribute("class","axis");svg.append(axis);
  const vals = entries.map((e) => e.mean).filter((n) => typeof n === "number" && Number.isFinite(n));
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 0;
  const pad = hi === lo ? 1 : (hi - lo) * .16;
  const min = lo - pad, max = hi + pad;
  const start = Date.parse(group.start_at), end = Date.parse(group.end_at);
  entries.forEach((bucket) => {
    const t = Date.parse(bucket.bucket_start);
    const v = bucket.mean;
    if (!Number.isFinite(t) || !Number.isFinite(start) || end <= start) return;
    const x = 28 + (t - start) / (end - start) * 600;
    if (typeof v === "number" && Number.isFinite(v) && bucket.usable_count > 0) {
      const y = 106 - (v - min) / (max - min) * 87;
      const circle = svgNode("circle");
      circle.setAttribute("cx", String(x));circle.setAttribute("cy", String(y));circle.setAttribute("r", "4");circle.setAttribute("class", "trend-dot");
      const label = svgNode("title");label.textContent = formatTime(bucket.bucket_start) + " · 평균 " + num(v) + " · 유효 " + bucket.usable_count;
      circle.append(label);svg.append(circle);
    } else {
      const circle = svgNode("circle");
      circle.setAttribute("cx",String(x));circle.setAttribute("cy","105");circle.setAttribute("r","3.5");circle.setAttribute("class","trend-dot missing");
      svg.append(circle);
    }
  });
  root.append(svg);
  root.append(create("p", "legend", "버킷 " + entries.length + "개 · 원본 결측/품질/충돌 건수 확인"));
  const quality = entries.reduce((acc, item) => {
    ["usable_count","null_count","non_good_count","conflict_count"].forEach((key) => acc[key] = (acc[key] || 0) + (Number(item[key]) || 0));
    return acc;
  },{});
  root.append(create("p", "trend-meta", "사용 가능 " + quality.usable_count + " · 결측 " + quality.null_count + " · 비정상 원본 품질 " + quality.non_good_count + " · 충돌 " + quality.conflict_count));
  return root;
}
function showTrend(data) {
  const box = byId("trend-results");const latest = byId("last-values");
  clear(box);clear(latest);
  const buckets = Array.isArray(data.buckets) ? data.buckets : [];
  if (!buckets.length) empty(box,"선택한 기간에 저장된 측정값이 없습니다. 최근 저장값은 별도 확인하세요.");
  const grouped = new Map();
  buckets.forEach((item) => {
    const key = [item.channel_id,item.source_id,item.measurement_point_id,item.interpretation_id].map(String).join("\u0000");
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(item);
  });
  grouped.forEach((items) => box.append(drawSeries(items, {...items[0], start_at:data.start_at, end_at:data.end_at})));
  const points = Array.isArray(data.latest_stored) ? data.latest_stored : [];
  latestStored = points;
  
  points.forEach((point) => sourceHistory.set(point.source_id, data.snapshot_id));
  renderWorkspace();renderOnboardingGuide();
  if (points.length) latest.append(create("h3", null, "마지막 저장된 측정값"));
  points.forEach((p) => {
    const item = create("div","latest-item");
    item.append(create("small",null,p.channel_id + " / " + p.source_id));
    item.append(create("strong",null, p.usable_for_display ? num(p.value) : "표시 신뢰 불가"));
    item.append(create("small",null,"원본 측정 " + formatTime(p.event_at)));
    item.append(create("small",null,"원본 품질 " + fmt(p.source_quality) + " · " + (p.conflicting_duplicate ? "충돌 있음" : "충돌 없음")));
    const provenance = create("details", "point-provenance");
    provenance.append(create("summary", null, "원본 근거 ID"), create("small", null, "evidence: " + fmt(p.raw_evidence_id)));
    item.append(provenance);
    latest.append(item);
  });
  trendState((data.time_anchor === "latest" ? "마지막 저장 기록 기준 · " : "현재 조회 시각 기준 · ") + "이력 snapshot " + fmt(data.snapshot_id) + " · " + formatTime(data.start_at) + " ~ " + formatTime(data.end_at) + " · " + grouped.size + "개 신호/출처 조합");
  if (grouped.size) {
    // The same window and signals continue in the period comparison below, as two halves.
    const start = Date.parse(data.start_at), end = Date.parse(data.end_at), middle = new Date((start + end) / 2).toISOString();
    const compare = create("button", "secondary", "이 기간을 두 구간으로 나눠 비교");compare.type = "button";
    compare.addEventListener("click", () => document.dispatchEvent(new CustomEvent("explore-request", {detail: {
      kind: "history", series: selectedChannels.join(","), a: data.start_at + "~" + middle, b: middle + "~" + data.end_at}})));
    box.append(compare);
  }
}
async function loadTrend(token = generation) {
  if (!selectedAsset || !selectedChannels.length) return;
  const request = ++trendSequence;
  trendState("실제 측정 이력을 읽는 중입니다.");
  clear(byId("trend-results"));clear(byId("last-values"));
  const params = new URLSearchParams({asset_id:selectedAsset,range:byId("range-select").value,anchor:byId("time-anchor").value,buckets:"60"});
  selectedChannels.forEach((channel) => params.append("channel_id",channel));
  try {
    const data = await getJSON("/api/v1/history/trend?" + params.toString());
    if (token !== generation || request !== trendSequence) return;
    showTrend(data);
  } catch (error) {
    if (token !== generation || request !== trendSequence) return;
    latestStored = [];sourceHistory.clear();renderWorkspace();renderOnboardingGuide();
    trendState(presentError(error),true);
  }
}
let signalsLoadedFor = "";
async function loadSignals(token = generation) {
  signalsLoadedFor = selectedAsset;
  clear(byId("trend-results"));clear(byId("last-values"));
  byId("show-trend").disabled = true;
  if (!selectedAsset) {trendState("설비를 선택하세요.");return;}
  // An asset known only from model inputs (e.g. vibration acquisitions) has no stored history.
  if (monitor && !rows(monitor, "assets").some((asset) => asset.asset_id === selectedAsset)) {
    const box = byId("channel-options");
    box.replaceChildren(create("legend", null, "비교할 신호 (최대 6개)"), create("p", "empty", "이 설비에는 저장된 측정 이력이 없습니다."));
    trendState("획득별 특징은 아래 구간 비교에서, 원본 파형은 개요와 이상 탐지 탭에서 볼 수 있습니다.");
    return;
  }
  trendState("설비의 저장된 신호 목록을 확인합니다.");
  await loadChannels(selectedAsset, token);
}
async function selectAsset() {
  generation += 1;
  selectedAsset = currentAsset();
  selectedChannels = [];
  latestStored = [];sourceHistory.clear();signalsLoadedFor = "";
  renderWorkspace();
  evidenceViews();
  if (document.body.dataset.view === "signals") await loadSignals();
  if (byId("condition-disclosure").open) void loadCondition(selectedAsset, {reset: true});
}
async function refresh() {
  const token = ++generation;
  trendSequence += 1;
  monitorReadState = "loading";
  latestStored = [];
  sourceHistory.clear();
  renderWorkspace();
  byId("show-trend").disabled = true;
  clear(byId("trend-results"));
  clear(byId("last-values"));
  trendState("현재 설비의 측정 이력을 다시 확인합니다.");
  byId("refresh").disabled = document.body.dataset.view !== "anomaly";
  setNotice("저장된 관측 현황을 불러오는 중입니다.");
  try {
    const data = await getJSON("/api/v1/monitor");
    if (token !== generation) return;
    monitor = data;
    monitorReadState = "ready";
    renderMonitorAttention(data);
    systemViews(data);
    byId("asset-count").textContent = fmt(data.assets && data.assets.total);
    byId("analysis-count").textContent = fmt((data.phase_unbalance_analyses?.total ?? 0) + (data.file_feature_analyses?.total ?? 0));
    byId("review-count").textContent = fmt(data.review_requests && data.review_requests.total);
    byId("assessed-at").textContent = formatTime(data.assessed_at);
    const assets = rows(data,"assets");
    registerAssets("monitor", assets.map((asset) => asset.asset_id));
    if (selectedAsset !== currentAsset()) {selectedAsset = currentAsset();selectedChannels = [];}
    evidenceViews();
    signalsLoadedFor = "";
    if (document.body.dataset.view === "signals") await loadSignals(token);
    if (data.system_error_scopes && data.system_error_scopes.length) {
      setNotice("일부 저장소를 읽지 못했습니다 (" + data.system_error_scopes.join(", ") + "). 표시되지 않은 근거가 있을 수 있습니다.", true);
    } else if (data.assets && data.assets.truncated) {
      setNotice("설비 목록이 100건으로 제한되었습니다. 추가 설비 조회는 후속 페이지 API가 필요합니다.");
    } else {
      setNotice("");
    }
  } catch (error) {
    if (token !== generation) return;
    monitorReadState = "error";
    latestStored = [];sourceHistory.clear();
    monitor = null;setNotice(presentError(error),true);
    byId("monitor-attention").classList.remove("hidden");
    byId("monitor-attention").textContent = "운영 상태 조회 실패 · 이전 확인 항목을 현재 상태로 표시하지 않습니다.";
    byId("system-status").className = "state error";
    byId("system-status").textContent = "시스템 조회 실패 · 정상 상태로 판단할 수 없습니다.";
    clear(byId("system-facts"));
    for (const id of ["evidence-results","review-results"]) empty(byId(id),"기록을 읽지 못했습니다. 다시 불러오세요.");
    for (const id of ["asset-count","analysis-count","review-count","assessed-at"]) byId(id).textContent = "—";
    selectedChannels = [];
    clear(byId("trend-results"));clear(byId("last-values"));trendState(presentError(error),true);
    byId("show-trend").disabled = true;
  } finally {
    if (token === generation) {renderWorkspace();renderOnboardingGuide();if (byId("condition-disclosure").open) void loadCondition(selectedAsset);}
    byId("refresh").disabled = false;
  }
}
byId("refresh").addEventListener("click",() => {
  if (document.body.dataset.view === "anomaly") {void refreshPhm();return;}
  if (document.body.dataset.view === "monitor") {void refreshMonitor({force: true});return;}
  if (document.body.dataset.view === "forecast") void refreshForecast();
  void refresh();void loadSources();void loadRuntimeStatus();
});
byId("runtime-refresh").addEventListener("click",loadRuntimeStatus);
onAssetChange(() => void selectAsset());
window.addEventListener("hashchange", () => {
  if (document.body.dataset.view === "signals" && signalsLoadedFor !== selectedAsset) void loadSignals();
  if (document.body.dataset.view === "system") {void refresh();void loadRuntimeStatus();}
});
byId("show-trend").addEventListener("click",() => loadTrend());
byId("range-select").addEventListener("change",() => loadTrend());
byId("time-anchor").addEventListener("change",() => loadTrend());
initializeAssetContext();
initializeNavigation();
initializeCondition();
initializePhm();
byId("start-example").addEventListener("click", () => void exploreExample());
byId("start-file").addEventListener("click", () => navigate("#connect", byId("csv-start-file")));
byId("start-opcua").addEventListener("click", () => {byId("opcua-registration").open = true;navigate("#connect", byId("opcua-form").querySelector('input[name="source_id"]'));});
initializeCsvStart();
initializeSignalExplore();
initializeCapabilities();
initializeOutlookCaptures();
initializeForecast();
initializeAnomalyExplore();
records.initialize();loadRuntimeStatus();
// Automatic Monitor updates retain selection/forms and never call condition fitting or history trends.
async function readMonitorFacts() {
  const result = await Promise.allSettled([
    getJSON("/api/v1/monitor", {signal: AbortSignal.timeout(5000)}), getJSON("/api/v1/sources", {signal: AbortSignal.timeout(5000)}),
  ]);
  const errors = [];
  if (result[0].status === "fulfilled") {
    monitor = result[0].value;monitorReadState = "ready";
    renderMonitorAttention(monitor);
    byId("asset-count").textContent = fmt(monitor.assets?.total);
    byId("analysis-count").textContent = fmt((monitor.phase_unbalance_analyses?.total ?? 0) + (monitor.file_feature_analyses?.total ?? 0));
    byId("review-count").textContent = fmt(monitor.review_requests?.total);
    byId("assessed-at").textContent = formatTime(monitor.assessed_at);
    if (monitor.system_error_scopes?.length) errors.push("monitor-store");
  } else {
    monitor = null;monitorReadState = "error";errors.push("monitor");
    byId("monitor-attention").classList.remove("hidden");
    byId("monitor-attention").textContent = "운영 수신 상태 조회 실패 · 자동으로 재조회합니다.";
    for (const id of ["asset-count", "analysis-count", "review-count", "assessed-at"]) byId(id).textContent = "—";
  }
  if (result[1].status === "fulfilled") {
    sourceSnapshot = result[1].value;sourceReadState = "ready";
    if (sourceSnapshot.read_error_scopes?.length || sourceSnapshot.live_evidence_error_scopes?.length) errors.push("sources-store");
  } else {sourceSnapshot = null;sourceReadState = "error";errors.push("sources");}
  registerAssets("monitor", rows(monitor, "assets").map((asset) => asset.asset_id));
  renderWorkspace();
  if (document.body.dataset.view === "monitor") {
    byId("refresh").disabled = false;
    if (byId("notice").textContent === "저장된 관측 현황을 불러오는 중입니다.") setNotice("");
  }
  return {monitor, sources: sourceSnapshot, errors};
}
document.addEventListener("phm-monitor-count", (event) => {phmModelCount = event.detail;renderWorkspace();});
// The guided CSV flow performs its own explicit writes; reread sources and evidence afterwards.
document.addEventListener("workspace-changed", () => {void loadSources();void refresh();});
document.addEventListener("file-analysis-request", (event) => void analyzeFile(event.detail.sourceId, event.detail.button, event.detail.output));
loadSources();initializeSyntheticDemo();
// One Web: when operations is not running behind this page, say so once for every screen.
getJSON("/api/v1/session").then((session) => {
  if (session.mode !== "view-only") return;
  const notice = create("p", "notice view-only-context", "운영이 실행 중이 아닌 화면입니다 · 저장된 데이터는 모두 볼 수 있고, 측정 저장·모델 연결·AI 질문은 make up으로 운영을 시작한 화면에서 할 수 있습니다.");
  document.querySelector(".topbar").after(notice);
}).catch(() => {});
initializeMonitor(readMonitorFacts);

byId("condition-disclosure").addEventListener("toggle", () => {if (byId("condition-disclosure").open) void loadCondition(selectedAsset);});
