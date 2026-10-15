// Analysis shortcuts for the selected asset, as the server decided them from the stores. Each row is
// a name, the fact it rests on and a way in; what this data cannot support is listed once, quietly,
// with its reason. The Web only words the decision and opens the view with the asset kept.
import { currentAsset, onAssetChange, setAsset } from "./asset-context.js";
import { navigate } from "./navigation.js";
import { openPhmAssistant } from "./phm-explanation.js";
import { requestExploreGoal } from "./signal-explore.js";
import { formatTime } from "./time.js";
import { byId, create, getJSON, num } from "./web-utils.js";

const NAME = {measurements: "측정 신호", "period-compare": "구간 비교", relation: "신호 관계", spectrum: "주파수 성분",
  forecast: "상태 전망", anomaly: "이상 탐지", "ai-question": "AI 질문"};
const HORIZON = {"1h": "1시간", "24h": "24시간", "7d": "7일", "30d": "30일"};

// The fact each row rests on, in a few words.
function fact(item, data) {
  const facts = item.facts || {}, history = data.history, acquisition = data.acquisition;
  switch (item.reason) {
    case "history":
      if (item.id === "measurements") return "신호 " + num(history.channel_count) + "개 · "
        + formatTime(history.start_at, {seconds: false}) + " ~ " + formatTime(history.end_at, {seconds: false, zone: false});
      if (item.id === "relation") return facts.channels > 2 ? "신호 " + num(facts.channels) + "개 중 2개 선택" : "신호 2개";
      return "두 시간 구간의 분포·데이터 상태";
    case "acquisition":
      if (item.id === "measurements") return "획득 " + num(facts.count) + "개 · 원본 파형";
      if (item.id === "relation") return "같은 획득의 두 특징";
      if (item.id === "spectrum") return "원본 파형 · " + num(acquisition.sampling_rate_hz / 1000) + " kHz";
      return "획득 #" + acquisition.first + "–#" + acquisition.last;
    case "explore": return "모델 없이 기준 구간에서 벗어난 값 찾기" + (facts.packages ? " · 맞는 모델 " + num(facts.packages) + "개 연결 가능" : "");
    case "stored-flow": return "변화·기준까지 여유 · 최대 " + (HORIZON[facts.horizon] || facts.horizon) + " 앞까지 예측";
    case "stored-flow-count": return "변화·기준까지 여유 · 획득 순서 기준";
    case "short-history": return "기록이 짧음 (예측 기간의 2배 이상 필요)";
    case "connected": return "결과 " + num(facts.results) + "건" + (facts.recorded_replay ? " · 기록 재생" : "");
    case "model-results": return "결과 시점을 골라 질문";
    case "compatible-model": return "입력이 맞는 모델 " + num(facts.packages) + "개";
    case "waveforms-need-model": return "모델 연결 후 획득별 특징 계산";
    case "waiting-results": return "첫 결과 대기";
    case "few-acquisitions": return "분석된 획득 " + num(facts.count) + "개";
    case "no-waveform": return "원본 진동 파형 없음";
    case "no-model-input": return "CSV 측정 이력은 모델 입력이 아님";
    case "no-model-package": return "설치된 모델 없음";
    case "input-mismatch": return "모델 입력 조건 불일치" + (facts.details?.length ? " (" + facts.details.join(", ") + ")" : "");
    case "single-signal": return "신호 1개";
    case "single-moment": return "측정 시각 1개";
    case "read-only": return "운영을 시작한 화면에서 사용 (make up)";
    case "needs-results": return "모델 결과 없음";
    default: return "";
  }
}

async function whenEnabled(button, ms = 8000) {
  const end = Date.now() + ms;
  while (button.disabled && Date.now() < end) await new Promise((resolve) => setTimeout(resolve, 150));
  return !button.disabled;
}

// Open the view of one analysis with the asset kept.
async function open(asset, item) {
  const {view, goal} = item.target;
  setAsset(asset);
  if (view === "connect") {navigate("#connect", byId("csv-start-file"));return;}
  if (view === "signals") {
    navigate("#signals", byId(goal === "trend" ? "show-trend" : "explore-title"));
    requestExploreGoal(goal);
    return;
  }
  if (view === "monitor") {navigate("#monitor", byId("monitor-signal-title"));return;}
  if (view === "forecast") {navigate("#forecast", byId("forecast-title"));return;}
  navigate("#" + view, byId(item.reason === "explore" ? "anomaly-explore" : view + "-title"));
  if (item.id === "ai-question" && await whenEnabled(byId(view + "-ask"))) openPhmAssistant(view);
}

function action(body, item, text, label) {
  const button = create("button", "capability-open", text);
  button.type = "button";button.setAttribute("aria-label", label);
  button.addEventListener("click", () => void open(body.asset_id, item));
  return button;
}

export function renderCapabilities(root, body, {here = null} = {}) {
  const title = create("h3", null, "분석 바로가기");
  // A shortcut to the view already on screen is left out.
  const items = body.capabilities.filter((item) => !here || item.status !== "ready" || item.target?.view !== here);
  // Nothing stored yet (the server gives these reasons only then): one line instead of seven refusals.
  const empty = items.find((item) => ["no-data", "not-received"].includes(item.reason));
  if (empty) {
    const line = create("p", "capability-empty",
      empty.reason === "not-received" ? "등록한 소스에서 아직 저장된 측정이 없습니다. " : "저장된 측정이 없습니다. ");
    const link = create("button", "capability-open", "데이터 연결");link.type = "button";
    link.addEventListener("click", () => navigate("#connect", byId("csv-start-file")));
    line.append(link);
    root.replaceChildren(title, line);
    return;
  }
  const list = create("ul", "capability-list");
  const unavailable = [];
  for (const item of items) {
    if (item.status === "unavailable") {unavailable.push(item);continue;}
    const row = create("li", "capability");row.dataset.status = item.status;row.dataset.capability = item.id;
    row.append(create("span", "capability-name", NAME[item.id] || item.id), create("span", "capability-fact", fact(item, body.data)));
    if (item.status === "ready") row.append(action(body, item, "열기", NAME[item.id] + " 열기"));
    else if (item.status === "needs-connection") row.append(action(body, item, "모델 연결", NAME[item.id] + " 모델 연결"));
    else row.append(create("span", "capability-state", "대기"));
    list.append(row);
  }
  const parts = [title, list];
  if (unavailable.length) {
    const rest = create("p", "capability-unavailable");
    rest.append(create("span", "capability-unavailable-label", "사용 불가"));
    for (const item of unavailable) {
      const entry = create("span", "capability-unavailable-item", NAME[item.id] + " — " + fact(item, body.data));
      entry.dataset.capability = item.id;rest.append(entry);
    }
    parts.push(rest);
  }
  root.replaceChildren(...parts);
}

export async function loadCapabilities(root, asset, options = {}) {
  root.replaceChildren(create("p", "muted", "분석 항목을 확인합니다."));
  try {
    const body = await getJSON("/api/v1/explore/capabilities?asset_id=" + encodeURIComponent(asset));
    if (root.dataset.asset && root.dataset.asset !== asset) return null;
    renderCapabilities(root, body, options);
    return body;
  } catch {
    root.replaceChildren(create("p", "muted", "분석 항목을 확인하지 못했습니다. 각 탭에서 직접 열 수 있습니다."));
    return null;
  }
}

// The overview keeps one list for the selected asset; a slower answer for another asset is dropped.
export function initializeCapabilities() {
  const root = byId("asset-capabilities");
  let loaded = "";
  const refresh = () => {
    const asset = currentAsset();
    if (!asset || document.body.dataset.view !== "monitor" || loaded === asset) return;
    loaded = asset;root.dataset.asset = asset;root.hidden = false;
    void loadCapabilities(root, asset, {here: "monitor"});
  };
  onAssetChange(() => {loaded = "";refresh();});
  // Coming back to the overview rereads it: a model may have been connected meanwhile.
  window.addEventListener("hashchange", () => {if (document.body.dataset.view === "monitor") loaded = "";refresh();});
  document.addEventListener("workspace-changed", () => {loaded = "";refresh();});
  refresh();
}
