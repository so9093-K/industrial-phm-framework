import { renderPhmExplanation } from "./phm-explanation.js";
import { drawSignal, signalChoices } from "./monitor-signal.js";
// PHM monitoring: anomaly detection and RUL are separate screens over stored model results.
// All server strings enter the DOM as text. Values come only from persisted step results;
// nothing here recomputes a score, an interval or an estimate.
const byId = (id) => document.getElementById(id);
const node = (tag, text = "", className = "") => {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const svgNode = (tag, attributes = {}) => {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  return element;
};
const number = (value, digits = 3) => typeof value === "number" && Number.isFinite(value)
  ? value.toLocaleString("ko-KR", {maximumFractionDigits: digits}) : "값 없음";
const time = (value) => {
  if (!value) return "시각 없음";
  const parsed = Date.parse(value);
  return Number.isFinite(parsed)
    ? new Date(parsed).toISOString().replace("T", " ").replace(/\.\d+/, "").replace("Z", " UTC")
    : String(value);
};
const POLL_MS = 3000;
const TASK_LABEL = {"anomaly-score": "이상 점수", "rul-estimate": "RUL 추정"};
const STEP_KIND_LABEL = {"acquisition-snapshot": "획득 파형", "observation-window": "관측 윈도우"};
// A rejected input is not a fault; it means this package was not trained or validated for it.
const INPUT_GUIDE = "이 입력은 선택한 모델로 분석할 수 없습니다. "
  + "아래 모델 정보에서 필요한 입력 조건을 확인하고, 맞는 모델을 연결해야 합니다.";
// Only skips where the package does not fit the input get that guidance. A sequence warm-up,
// an unreadable file or a too-short window is not a reason to train another model.
const INPUT_MISMATCH = /^(package expects |channels differ |sampling rate .+ differs |sample count .+ differs |unsupported feature set |fixed sampling rate or sample count |RUL applicability unavailable)/;
const inputGuide = (reason) => INPUT_MISMATCH.test(reason || "") ? " · " + INPUT_GUIDE : "";
const FEATURE_LABEL = {
  rms: "RMS", mean: "평균", standard_deviation: "표준편차", absolute_peak: "절대 피크",
  peak_to_peak: "피크-피크", crest_factor: "파고율", skewness: "왜도", excess_kurtosis: "첨도(초과)",
};

let bindings = [];
const series = new Map();
const selected = {anomaly: "", rul: ""};
const zoom = {anomaly: null};
let chosenFeatures = [];
let focusPosition = null;
let rulFocusPosition = null;
let pollTimer = null;
let readError = "";
let refreshedAt = null;
let cycleVersion = 0;
let requestedResult = null;
const requestedParams = new URLSearchParams(location.search);
if (requestedParams.has("phm_binding") || requestedParams.has("phm_position")) {
  const view = location.hash.slice(1), position = Number(requestedParams.get("phm_position"));
  if (["anomaly", "rul"].includes(view)) requestedResult = {
    view, bindingId: requestedParams.get("phm_binding"), position,
    valid: Boolean(requestedParams.get("phm_binding")) && Number.isSafeInteger(position) && position > 0,
  };
}

function activeView() {
  const view = document.body.dataset.view;
  return view === "anomaly" || view === "rul" ? view : null;
}

async function getJson(url) {
  const response = await fetch(url, {headers: {Accept: "application/json"}});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "phm_read_failed");
  return data;
}

async function refreshBindings() {
  const data = await getJson("/api/v1/phm/bindings");
  bindings = data.bindings || [];
}

async function refreshSeries(bindingId) {
  const known = series.get(bindingId);
  const entry = known ? {...known, steps: new Map(known.steps)} : {steps: new Map(), changeSeq: 0};
  // Drain bounded pages. If input keeps arriving, the next poll resumes this cursor.
  for (let page = 0; page < 5; page++) {
    const data = await getJson("/api/v1/phm/series?binding_id=" + encodeURIComponent(bindingId) + "&since=" + entry.changeSeq);
    if (!data.binding || data.binding.binding_id !== bindingId) throw new Error("wrong_binding");
    for (const step of data.steps) entry.steps.set(step.position, step);
    Object.assign(entry, {
      changeSeq: data.change_seq, binding: data.binding, package: data.package,
      intervals: data.intervals, latestAnalyzed: data.latest_analyzed, latestDelivered: data.latest_delivered,
      latestProcessed: data.latest_processed,
    });
    if (!data.has_more) break;
  }
  series.set(bindingId, entry);
  return entry;
}

function bindingsFor(task) {
  return bindings.filter((item) => item.package && item.package.output && item.package.output.task === task);
}

function fillSelect(select, items, current) {
  const previous = current || select.value;
  select.replaceChildren();
  if (!items.length) {
    select.append(node("option", "연결된 모델 없음"));
    select.disabled = true;
    return "";
  }
  for (const item of items) {
    const recipe = item.package.recipe_id || "";
    const family = /autoencoder/.test(recipe) ? "재구성 오차 · LSTM" : /pca/.test(recipe) ? "재구성 오차 · PCA" : /iforest/.test(recipe) ? "이상 점수 · IF" : /lstm/.test(recipe) ? "RUL · LSTM" : /ridge/.test(recipe) ? "RUL · Ridge" : TASK_LABEL[item.package.output.task];
    const option = node("option", item.asset_id.replace(/^aihub-air-compressor-/, "공기압축기 ") + " · " + family);
    option.value = item.binding_id;
    select.append(option);
  }
  select.disabled = false;
  const keep = items.some((item) => item.binding_id === previous) ? previous : items[0].binding_id;
  select.value = keep;
  return keep;
}

function orderedSteps(entry) {
  return [...entry.steps.values()].sort((a, b) => a.position - b.position);
}

function axisFor(entry) {
  const steps = orderedSteps(entry);
  const timed = steps.length && steps.every((step) => step.event_start);
  const period = entry.package && entry.package.output && entry.package.output.step_period_seconds;
  return timed
    ? {cadence: period ? period * 1000 : null, x: (step) => Date.parse(step.event_start), label: "관측 시각 · UTC", format: (v) => time(new Date(v).toISOString()).slice(0, 16)}
    : {x: (step) => step.position, label: "획득 순번" + (period ? " · 기록 주기 " + period + "초" : ""), format: (v) => "#" + Math.round(v)};
}

// A window's position is an internal ordering key; people identify it by its event time.
function stepLabel(entry, position) {
  const step = entry.binding.step_kind === "observation-window"
    ? orderedSteps(entry).find((item) => item.position === position) : null;
  return step && step.event_start ? "윈도우 " + time(step.event_start) : "#" + position;
}

function freshness(entry) {
  const delivered = entry.latestDelivered, analyzed = entry.latestAnalyzed, processed = entry.latestProcessed;
  if (!analyzed && !delivered) return "아직 공급된 step이 없습니다.";
  const parts = [];
  if (entry.binding.step_kind === "observation-window") {
    if (delivered) parts.push("최신 수신 " + time(delivered.event_at) + " · 저장 " + time(delivered.delivered_at));
    if (analyzed) parts.push("최신 분석 " + time(analyzed.event_start) + " · 처리 " + time(analyzed.processed_at));
    if (delivered && processed) {
      const lag = Math.max(0, delivered.position - processed.position) / 1000000;
      parts.push(lag ? "최근 윈도우와 분석 시각 차이 " + number(lag / 60, 1) + "분" : "입력 처리 지연 없음");
    }
  } else {
    if (delivered) parts.push("최신 수신 #" + delivered.position + " · " + time(delivered.delivered_at));
    if (analyzed) parts.push("최신 분석 #" + analyzed.position + " · " + time(analyzed.processed_at));
    if (delivered && (processed || analyzed)) {
      const lag = delivered.position - (processed || analyzed).position;
      parts.push(lag > 0 ? "분석 대기 " + lag + "개" : "분석 지연 없음");
    }
  }
  if (processed && processed.state === "skipped") parts.push("최근 입력 조건 불충족 · 분석하지 않음");
  if (refreshedAt) parts.push("화면 갱신 " + refreshedAt.toLocaleTimeString("ko-KR"));
  return parts.join(" · ");
}

function setReplayTag(id, entry) {
  const replay = orderedSteps(entry).some((step) => step.replay) || (entry.latestDelivered && entry.latestDelivered.replay);
  byId(id).classList.toggle("hidden", !replay);
}

function card(title, value, detail) {
  const element = node("article", "", "condition-card");
  element.append(node("span", title), node("strong", value), node("small", detail));
  return element;
}

// Charts ---------------------------------------------------------------------

function linePlot({steps, value, axis, height, domain, threshold, intervals, highlight, label, onPick, unitText, width = 800, zeroBase = false}) {
  width = Math.max(260, width);
  const PLOT = {left: 56, right: width - 16, top: 14};
  const svg = svgNode("svg", {viewBox: `0 0 ${width} ${height + 34}`, class: "phm-svg", role: "img", "aria-label": label});
  const points = steps.filter((step) => typeof value(step) === "number");
  const [x0, x1] = domain;
  const visible = points.filter((step) => axis.x(step) >= x0 && axis.x(step) <= x1);
  const values = visible.map(value).concat(typeof threshold === "number" ? [threshold] : []);
  if (!values.length) return svg;
  let lo = Math.min(...values), hi = Math.max(...values);
  const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
  lo -= pad; hi += pad;
  if (zeroBase && lo >= -pad && values.every((v) => v >= 0)) lo = 0;
  const bottom = PLOT.top + height;
  const x = (v) => PLOT.left + (v - x0) / ((x1 - x0) || 1) * (PLOT.right - PLOT.left);
  const y = (v) => bottom - (v - lo) / ((hi - lo) || 1) * height;
  for (const interval of intervals || []) {
    const start = Math.max(x0, interval.from), end = Math.min(x1, interval.to);
    if (end < start) continue;
    svg.append(svgNode("rect", {x: x(start) - 2, y: PLOT.top, width: Math.max(4, x(end) - x(start) + 4), height,
      class: "phm-interval" + (interval.open ? " open" : "")}));
  }
  if (highlight) {
    const start = Math.max(x0, highlight[0]), end = Math.min(x1, highlight[1]);
    if (end >= start) svg.append(svgNode("rect", {x: x(start) - 3, y: PLOT.top, width: Math.max(6, x(end) - x(start) + 6), height, class: "phm-focus"}));
  }
  svg.append(svgNode("path", {d: `M${PLOT.left} ${PLOT.top}V${bottom}H${PLOT.right}`, class: "axis"}));
  let path = "", previous = null;
  for (const step of visible) {
    const contiguous = previous && (axis.cadence ? axis.x(step) - axis.x(previous) === axis.cadence : step.position - previous.position === 1);
    path += (contiguous ? "L" : "M") + x(axis.x(step)).toFixed(1) + " " + y(value(step)).toFixed(1) + " ";
    previous = step;
  }
  svg.append(svgNode("path", {d: path, class: "condition-curve"}));
  for (const step of visible) {
    const dot = svgNode("circle", {cx: x(axis.x(step)), cy: y(value(step)), r: highlight && axis.x(step) === highlight[0] ? 4 : 2, class: "phm-chart-dot"});
    const title = svgNode("title");title.textContent = axis.format(axis.x(step)) + " · " + number(value(step));dot.append(title);svg.append(dot);
  }
  if (typeof threshold === "number") svg.append(svgNode("path", {d: `M${PLOT.left} ${y(threshold).toFixed(1)}H${PLOT.right}`, class: "reference-line"}));
  const text = (content, attributes) => {const t = svgNode("text", attributes);t.textContent = content;svg.append(t);};
  for (const value of [lo, (lo + hi) / 2, hi]) {
    svg.insertBefore(svgNode("path", {d: `M${PLOT.left} ${y(value)}H${PLOT.right}`, class: "phm-chart-grid"}), svg.firstChild);
    text(number(value) + (unitText || ""), {x: 4, y: y(value) + 4});
  }
  text(axis.format(x0), {x: PLOT.left, y: bottom + 22});
  text(axis.format(x1), {x: PLOT.right, y: bottom + 22, "text-anchor": "end"});
  if (onPick) {
    svg.classList.add("pickable");
    svg.addEventListener("click", (event) => {
      const box = svg.getBoundingClientRect();
      const target = x0 + ((event.clientX - box.left) / box.width * width - PLOT.left) / (PLOT.right - PLOT.left) * (x1 - x0);
      if (!visible.length) return;
      const closest = visible.reduce((best, step) => Math.abs(axis.x(step) - target) < Math.abs(axis.x(best) - target) ? step : best, visible[0]);
      onPick(closest);
    });
  }
  return svg;
}


const PHASE_GROUPS = [
  {names: ["current.phase_r.mean_a", "current.phase_s.mean_a", "current.phase_t.mean_a"], title: "3상 평균 전류", unit: "A"},
  {names: ["voltage.phase_r.mean_v", "voltage.phase_s.mean_v", "voltage.phase_t.mean_v"], title: "3상 평균 전압", unit: "V"},
];

// Overlay only the same physical quantity and unit. This is presentation, not normalization.
function phasePlot(steps, group, axis, domain, onPick, width = 800) {
  width = Math.max(260, width);
  const PLOT = {left: 56, right: width - 16, top: 14};
  const height = 104, bottom = PLOT.top + height, [x0, x1] = domain;
  const svg = svgNode("svg", {viewBox: `0 0 ${width} ${height + 34}`, class: "phm-svg", role: "img",
    "aria-label": group.title + " R상·S상·T상 추세"});
  const visible = steps.filter((step) => axis.x(step) >= x0 && axis.x(step) <= x1);
  const values = visible.flatMap((step) => group.names.map((name) => step.features?.[name]))
    .filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!values.length) return svg;
  const min = Math.min(...values), max = Math.max(...values);
  const padding = (max - min) * 0.08 || Math.abs(max) * 0.05 || 1;
  const lo = min - padding, hi = max + padding;
  const x = (value) => PLOT.left + (value - x0) / ((x1 - x0) || 1) * (PLOT.right - PLOT.left);
  const y = (value) => bottom - (value - lo) / (hi - lo) * height;
  svg.append(svgNode("path", {d: `M${PLOT.left} ${PLOT.top}V${bottom}H${PLOT.right}`, class: "axis"}));
  for (const [index, name] of group.names.entries()) {
    let d = "", previous = null;
    for (const step of visible) {
      const value = step.features?.[name];
      if (typeof value !== "number" || !Number.isFinite(value)) {previous = null;continue;}
      const contiguous = previous && (axis.cadence
        ? axis.x(step) - axis.x(previous) === axis.cadence : step.position - previous.position === 1);
      d += (contiguous ? "L" : "M") + x(axis.x(step)).toFixed(1) + " " + y(value).toFixed(1) + " ";
      previous = step;
    }
    svg.append(svgNode("path", {d, class: "phm-phase-curve phm-phase-" + index}));
  }
  const label = (text, attrs) => {const t = svgNode("text", attrs);t.textContent = text;svg.append(t);};
  label(number(max) + " " + group.unit, {x: 4, y: PLOT.top + 10});
  label(number(min) + " " + group.unit, {x: 4, y: bottom});
  label(axis.format(x0), {x: PLOT.left, y: bottom + 22});
  label(axis.format(x1), {x: PLOT.right, y: bottom + 22, "text-anchor": "end"});
  if (onPick) {
    svg.classList.add("pickable");
    svg.addEventListener("click", (event) => {
      const box = svg.getBoundingClientRect();
      const target = x0 + ((event.clientX - box.left) / box.width * width - PLOT.left)
        / (PLOT.right - PLOT.left) * (x1 - x0);
      if (visible.length) onPick(visible.reduce((best, step) =>
        Math.abs(axis.x(step) - target) < Math.abs(axis.x(best) - target) ? step : best, visible[0]));
    });
  }
  return svg;
}

const channelLabel = (channel) => channel.replace("_vibration_signals", "").replace("Horizontal", "수평 진동").replace("Vertical", "수직 진동");

function featureLabel(name) {
  const electrical = {
    "current.phase_r.mean_a": "R상 평균 전류 · A", "current.phase_s.mean_a": "S상 평균 전류 · A",
    "current.phase_t.mean_a": "T상 평균 전류 · A", "voltage.phase_r.mean_v": "R상 평균 전압 · V",
    "voltage.phase_s.mean_v": "S상 평균 전압 · V", "voltage.phase_t.mean_v": "T상 평균 전압 · V",
    "current.unbalance.mean_percent": "전류 불평형 평균 · %",
    "voltage.unbalance.mean_percent": "전압 불평형 평균 · %",
    "current.three_phase_mean.std_a": "3상 평균 전류의 변동 · A",
    "frequency.mean_hz": "평균 주파수 · Hz",
  };
  if (electrical[name]) return electrical[name];
  const parts = name.split(".");
  const statistic = parts.at(-1), channel = parts.slice(1, -1).join(".");
  return channelLabel(channel) + " · " + (FEATURE_LABEL[statistic] || statistic);
}

// Anomaly screen ---------------------------------------------------------------

function renderAnomaly() {
  const choices = bindingsFor("anomaly-score");
  selected.anomaly = fillSelect(byId("anomaly-binding"), choices, selected.anomaly);
  const state = byId("anomaly-state");
  byId("anomaly-latest").hidden = focusPosition === null;
  state.hidden = false;
  for (const id of ["anomaly-cards", "anomaly-feature-chart", "anomaly-score-chart", "anomaly-intervals", "anomaly-model"]) byId(id).replaceChildren();
  if (readError) {
    byId("anomaly-asset-title").textContent = "데이터 조회 실패";
    byId("anomaly-observation").textContent = "최신 결과를 확인할 수 없습니다. 이전 결과를 현재 상태로 표시하지 않습니다.";
    renderPhmExplanation("anomaly", "", null);
    for (const id of ["anomaly-features", "anomaly-detail"]) byId(id).replaceChildren();
    byId("anomaly-freshness").textContent = "";
    byId("anomaly-replay").classList.add("hidden");
    state.className = "state error";state.textContent = "PHM 분석 결과를 읽지 못했습니다. 운영 관리 화면에서 분석 프로세스 상태를 확인하세요.";return;
  }
  if (!selected.anomaly) {
    byId("anomaly-detail").replaceChildren();
    byId("anomaly-asset-title").textContent = "연결된 설비 없음";
    byId("anomaly-observation").textContent = "모델이 연결되면 관측 결과를 표시합니다.";
    renderPhmExplanation("anomaly", "", null);
    state.className = "state";
    state.textContent = "이상 탐지 모델이 연결된 설비가 없습니다. `operations phm bind`로 검증된 모델 패키지를 설비 스트림에 연결하세요.";
    byId("anomaly-freshness").textContent = "";
    return;
  }
  const entry = series.get(selected.anomaly);
  if (!entry) return;
  const binding = choices.find((item) => item.binding_id === selected.anomaly);
  byId("anomaly-asset-title").textContent = entry.binding.asset_id?.replace(/^aihub-air-compressor-/, "공기압축기 ") || "설비 정보 없음";
  byId("anomaly-freshness").textContent = "최신 분석 " + (entry.latestAnalyzed ? stepLabel(entry, entry.latestAnalyzed.position) : "없음")
    + " · 최신 입력 " + (entry.latestDelivered ? stepLabel(entry, entry.latestDelivered.position) : "없음")
    + (entry.latestProcessed?.state === "skipped" ? " · 입력 조건 불충족" : "") + " · 3초 자동 조회";
  setReplayTag("anomaly-replay", entry);
  const steps = orderedSteps(entry);
  const analyzed = steps.filter((step) => step.state === "analyzed");
  const skipped = steps.length - analyzed.length;
  if (focusPosition !== null && entry.steps.get(focusPosition)?.state !== "analyzed") {
    state.className = "state error";state.textContent = "선택한 기록 " + stepLabel(entry, focusPosition) + "은 분석되지 않았습니다: " + (entry.steps.get(focusPosition)?.reason || "분석 결과 없음");
    byId("anomaly-observation").textContent = "선택한 입력의 점수를 표시할 수 없습니다.";
    renderPhmExplanation("anomaly", "", null);renderModelCard(byId("anomaly-model"), entry.package);return;
  }
  if (binding && binding.health === "unavailable") {
    state.className = "state error";state.textContent = "모델을 실행할 수 없습니다: " + (binding.health_reason || "이유 미기록");
  } else if (!analyzed.length) {
    state.className = "state";state.textContent = steps.length
      ? "입력을 분석할 수 없습니다: " + (steps.at(-1).reason || "모델 입력 조건 불충족") + inputGuide(steps.at(-1).reason)
      : "분석된 step이 아직 없습니다. 데이터가 공급되면 자동으로 갱신됩니다.";
  } else {
    state.className = "state";
    state.textContent = analyzed.length + "개 step 분석" + (skipped ? " · " + skipped + "개 분석 불가(이유 기록)" : "") + " · 점수는 고장 확률이나 진단이 아닙니다.";
  }
  if (analyzed.length && steps.at(-1).state === "skipped") state.textContent += " · 최근 입력은 분석되지 않았습니다: " + steps.at(-1).reason;
  if (entry.package && entry.package.validation && entry.package.validation.acceptance === "not-yet-evaluated") {
    state.textContent += " · 개발 모델: 합격 기준 검증 미완료";
  }
  if (!analyzed.length) {
    byId("anomaly-detail").replaceChildren();
    byId("anomaly-observation").textContent = skipped ? "이 모델로 분석되지 않은 입력이 있습니다. 입력 상태와 모델 규격을 확인하세요." : "분석 가능한 입력을 기다리고 있습니다.";
    renderPhmExplanation("anomaly", "", null);renderModelCard(byId("anomaly-model"), entry.package);return;
  }
  const latest = analyzed.at(-1);
  const last = analyzed.find((s) => s.position === focusPosition) || latest;
  const prior = analyzed.filter((s) => s.position < last.position).at(-1);
  const reconstruction = /autoencoder|pca/.test(entry.package?.recipe_id || "");
  const scoreName = reconstruction ? "재구성 오차" : "이상 점수";
  const latestSkipped = steps.at(-1)?.state === "skipped";
  const rms = Object.keys(last.features || {}).find((k) => /Horizontal.+\.rms$/.test(k));
  const change = rms && prior?.features?.[rms] > 0 ? (last.features[rms] / prior.features[rms] - 1) * 100 : null;
  byId("anomaly-observation").textContent = latestSkipped
    ? "최근 입력은 분석되지 않았습니다. 선택한 이전 기록 " + stepLabel(entry, last.position) + "의 결과입니다."
    : "선택 기록 " + stepLabel(entry, last.position)
      + (change === null ? "" : " · 수평 진동 크기 " + number(Math.abs(change), 1) + "% " + (change >= 0 ? "증가" : "감소"))
      + " · " + scoreName + (last.output.exceeds_threshold ? " 참고 기준 초과" : " 참고 기준 이내");
  state.hidden = !latestSkipped && binding?.health !== "unavailable";
  const threshold = last.output.threshold;
  const cards = byId("anomaly-cards");
  cards.append(
    card(latestSkipped ? last.position === latest.position ? "마지막 분석 점수" : "선택한 이전 점수" : "선택한 " + scoreName, number(last.output.score),
      "참고 기준 " + number(threshold) + (last.output.exceeds_threshold ? " · 초과" : " · 이하")),
    card("앞선 분석 대비", prior ? (last.output.score > prior.output.score ? "+" : "") + number(last.output.score - prior.output.score) : "첫 분석",
      prior ? number(prior.output.score) + " → " + number(last.output.score) + " · " + stepLabel(entry, prior.position) + " → " + stepLabel(entry, last.position) : "비교 기록 없음"),
  );
  const axis = axisFor(entry);
  const full = [axis.x(analyzed[0]), axis.x(analyzed.at(-1))];
  let firstIndex = analyzed.indexOf(last), lastIndex = firstIndex;
  const adjacent = (a, b) => axis.cadence ? axis.x(b) - axis.x(a) === axis.cadence : b.position - a.position === 1;
  while (firstIndex > 0 && lastIndex - firstIndex < 63 && adjacent(analyzed[firstIndex - 1], analyzed[firstIndex])) firstIndex--;
  while (lastIndex < analyzed.length - 1 && lastIndex - firstIndex < 63 && adjacent(analyzed[lastIndex], analyzed[lastIndex + 1])) lastIndex++;
  const recent = [axis.x(analyzed[firstIndex]), axis.x(analyzed[lastIndex])];
  const range = byId("anomaly-range");
  if (zoom.anomaly) {
    if (!range.querySelector('option[value="interval"]')) {const option = node("option", "기준 초과 구간");option.value = "interval";range.append(option);}
    range.value = "interval";
  } else range.querySelector('option[value="interval"]')?.remove();
  const domain = zoom.anomaly || (byId("anomaly-range").value === "all" ? full : recent);
  const intervals = entry.intervals.map((item) => ({
    from: axis.x(entry.steps.get(item.start_position) || {position: item.start_position, event_start: item.start_event_at}),
    to: axis.x(entry.steps.get(item.end_position) || {position: item.end_position, event_start: item.end_event_at}),
    open: item.open,
  }));
  const highlight = [axis.x(last), axis.x(last)];
  renderFeatureControls(analyzed);
  const featureRoot = byId("anomaly-feature-chart");
  const combined = new Set();
  for (const phaseGroup of PHASE_GROUPS) {
    if (!phaseGroup.names.every((name) => chosenFeatures.includes(name))) continue;
    const group = node("div", "", "phm-feature");
    group.append(node("p", phaseGroup.title + " · " + phaseGroup.unit, "phm-feature-title"));
    group.append(phasePlot(analyzed, phaseGroup, axis, domain, (step) => focusStep(step.position), featureRoot.clientWidth));
    const legend = node("p", "", "phm-phase-legend");
    for (const [index, phase] of ["R상", "S상", "T상"].entries()) {
      const sample = node("span", "", "phm-phase-key phm-phase-key-" + index);
      sample.setAttribute("aria-hidden", "true");
      const item = node("span", "", "phm-phase-label");
      item.append(sample, document.createTextNode(phase));
      legend.append(item);
    }
    group.append(legend);
    featureRoot.append(group);
    for (const name of phaseGroup.names) combined.add(name);
  }
  for (const name of chosenFeatures.filter((value) => !combined.has(value))) {
    const group = node("div", "", "phm-feature");
    group.append(node("p", featureLabel(name), "phm-feature-title"));
    group.append(linePlot({steps: analyzed, value: (step) => step.features ? step.features[name] : null, axis, height: 110, domain,
      highlight, width: featureRoot.clientWidth, zeroBase: /\.rms$/.test(name), label: featureLabel(name) + " 추세", onPick: (step) => focusStep(step.position)}));
    featureRoot.append(group);
  }
  featureRoot.append(node("p", axis.label + (entry.binding.step_kind === "observation-window" ? "" : " · 단위 미확인"), "muted"));
  const scoreRoot = byId("anomaly-score-chart");
  byId("anomaly-score-title").textContent = scoreName + " 추세";
  scoreRoot.append(linePlot({steps: analyzed, value: (step) => step.output.score, axis, height: 110, domain, threshold,
    intervals, highlight, width: scoreRoot.clientWidth, zeroBase: true, label: scoreName + "와 참고 기준", onPick: (step) => focusStep(step.position)}));
  scoreRoot.append(node("p", "점선: 참고 기준 " + number(threshold) + " · 점을 선택하면 해당 기록을 표시", "muted"));
  const zoomControls = node("div", "", "phm-zoom");
  if (zoom.anomaly) {
    const reset = node("button", "전체 기간 보기");reset.type = "button";
    reset.addEventListener("click", () => {zoom.anomaly = null;byId("anomaly-range").value = "all";renderAnomaly();});
    zoomControls.append(reset);
  }
  scoreRoot.append(zoomControls);
  renderIntervals(entry, axis);
  byId("anomaly-periods").querySelector("summary").textContent = "기준 초과 구간 " + entry.intervals.length + "개";
  renderModelCard(byId("anomaly-model"), entry.package);
  const explained = focusPosition ?? last.position;
  renderPhmExplanation("anomaly", selected.anomaly, explained,
                       () => {focusPosition = focusPosition ?? last.position;}, stepLabel(entry, explained));
}

function renderFeatureControls(steps) {
  const root = byId("anomaly-features");
  const names = Object.keys((steps.find((step) => step.features) || {}).features || {});
  if (!chosenFeatures.length || !chosenFeatures.every((name) => names.includes(name))) {
    chosenFeatures = names.filter((name) => /\.rms$/.test(name)).slice(0, 1);
    if (!chosenFeatures.length && PHASE_GROUPS[0].names.every((n) => names.includes(n))) chosenFeatures = [...PHASE_GROUPS[0].names];
    if (!chosenFeatures.length) chosenFeatures = names.slice(0, 3);
  }
  root.replaceChildren(node("legend", "입력 특징 (최대 6개)"));
  const select = byId("anomaly-signal");select.replaceChildren();
  const choices = PHASE_GROUPS.filter((g) => g.names.every((n) => names.includes(n))).map((g) => ({name: g.title + " · " + g.unit, names: g.names}));
  for (const name of names.filter((n) => !PHASE_GROUPS.some((g) => g.names.includes(n))).sort((a, b) => Number(/\.rms$/.test(b)) - Number(/\.rms$/.test(a)))) choices.push({name: featureLabel(name), names: [name]});
  for (const choice of choices) {const option = node("option", choice.name);option.value = JSON.stringify(choice.names);select.append(option);}
  if (!choices.some((c) => JSON.stringify(c.names) === JSON.stringify(chosenFeatures))) {const option = node("option", "직접 선택한 특징");option.value = JSON.stringify(chosenFeatures);select.append(option);}
  select.value = JSON.stringify(chosenFeatures);
  for (const name of names) {
    const label = node("label", "", "choice");
    const box = document.createElement("input");box.type = "checkbox";box.checked = chosenFeatures.includes(name);
    box.addEventListener("change", () => {
      if (box.checked && chosenFeatures.length >= 6) {box.checked = false;return;}
      chosenFeatures = box.checked ? [...chosenFeatures, name] : chosenFeatures.filter((item) => item !== name);
      renderAnomaly();
    });
    label.append(box, document.createTextNode(featureLabel(name)));
    root.append(label);
  }
}

function renderIntervals(entry, axis) {
  const root = byId("anomaly-intervals");
  root.append(node("h3", "검토 구간"));
  if (!entry.intervals.length) {root.append(node("p", "임계값을 연속으로 넘은 구간이 없습니다.", "muted"));return;}
  for (const item of [...entry.intervals].reverse()) {
    const row = node("article", "", "condition-event");
    const range = item.start_event_at ? time(item.start_event_at) + " → " + time(item.end_event_at || item.start_event_at) : "#" + item.start_position + " → #" + item.end_position;
    const button = node("button", range + (item.open ? " · 진행 중" : " · 종료"));button.type = "button";
    button.addEventListener("click", () => {
      const from = axis.x(entry.steps.get(item.start_position)), to = axis.x(entry.steps.get(item.end_position));
      const span = Math.max(to - from, 1);
      const steps = orderedSteps(entry).filter((s) => s.state === "analyzed");
      zoom.anomaly = [Math.max(axis.x(steps[0]), from - span), Math.min(axis.x(steps.at(-1)), to + span)];
      focusStep(item.end_position);
    });
    row.append(button, node("p", item.step_count + "개 step 초과 · 최고 점수 " + number(item.peak_score)));
    root.append(row);
  }
}

async function focusStep(position, pin = true) {
  if (pin) {updateMonitorTarget("anomaly", position);focusPosition = position;renderAnomaly();}
  const bindingId = selected.anomaly;
  const entry = series.get(selected.anomaly);
  const step = entry && entry.steps.get(position);
  const root = byId("anomaly-detail");
  const key = JSON.stringify([bindingId, position, step?.change_seq]);
  if (!pin && root.dataset.inputKey === key && root.childElementCount) return;
  root.replaceChildren();root.dataset.inputKey = key;
  if (!step) return;
  const heading = node("div", "", "phm-input-heading");
  heading.append(node("h3", (step.event_start ? time(step.event_start) : "획득 #" + step.position) + " · 원본 신호"));
  const picker = node("select");picker.setAttribute("aria-label", "선택한 기록");picker.id = "anomaly-position";
  const pickable = orderedSteps(entry).filter((s) => s.state === "analyzed").slice(-64);
  if (!pickable.some((s) => s.position === position)) pickable.unshift(step);
  for (const candidate of pickable) {const option = node("option", stepLabel(entry, candidate.position));option.value = String(candidate.position);picker.append(option);}
  picker.value = String(position);picker.addEventListener("change", () => focusStep(Number(picker.value)));
  heading.append(picker);root.append(heading);
  if (step.state !== "analyzed") {root.append(node("p", "분석 불가: " + step.reason));return;}
  const metadata = node("details", "", "phm-input-details");metadata.append(node("summary", "입력 특징·오차 분해"));
  metadata.append(node("p", "이상 점수 " + number(step.output.score) + " · 참고 기준 " + number(step.output.threshold) + (step.output.exceeds_threshold ? " (초과)" : " (이하)")));
  if (step.output.sequence_positions) {
    const positions = step.output.sequence_positions;
    root.append(node("p", "모델 입력 #" + positions[0] + "–#" + positions.at(-1) + " · 아래 파형은 선택 기록 #" + position, "muted"));
  }
  const facts = node("div", "", "phm-facts");
  for (const [name, value] of Object.entries(step.features || {})) facts.append(node("span", featureLabel(name) + " " + number(value)));
  metadata.append(facts);
  metadata.append(node("p", "분석 ID " + step.analysis_run_id + " · 입력 SHA-256 " + String(step.input_reference.sha256 || step.input_reference.window_id || "").slice(0, 16) + "…", "mono"));
  if (!step.output.feature_contributions) metadata.append(node("p", "이 모델은 변수별 기여도를 제공하지 않습니다.", "muted"));
  if (step.output.feature_contributions) {
    const contributions = node("div", "", "phm-facts");
    contributions.append(node("h4", "특징별 잔차 기여"));
    for (const [name, value] of Object.entries(step.output.feature_contributions).sort((a, b) => b[1] - a[1])) {
      contributions.append(node("span", featureLabel(name) + " · " + number(value)));
    }
    metadata.append(contributions, node("p", "잔차 기여는 모델 점수의 분해이며 물리적 고장 원인 판정은 아닙니다.", "muted"));
  }
  root.append(metadata);
  if (entry.binding.step_kind === "observation-window") {
    const holder = node("div", "원본 관측을 불러오는 중입니다.", "phm-raw");root.insertBefore(holder, metadata);
    try {
      const preview = await getJson("/api/v1/phm/window?binding_id=" + encodeURIComponent(bindingId) + "&position=" + position);
      if (selected.anomaly !== bindingId || root.dataset.inputKey !== key || readError) return;
      holder.replaceChildren(rawSignals(preview));
    } catch {holder.replaceChildren(node("p", "원본 관측을 확인할 수 없습니다.", "muted"));delete root.dataset.inputKey;}
  }
  if (entry.binding.step_kind === "acquisition-snapshot") {
    const holder = node("div", "", "phm-waveform");holder.append(node("p", "원본 파형을 불러오는 중입니다.", "muted"));root.insertBefore(holder, metadata);
    try {
      const preview = await getJson("/api/v1/phm/snapshot?binding_id=" + encodeURIComponent(bindingId) + "&position=" + position + "&bins=400");
      if (selected.anomaly !== bindingId || root.dataset.inputKey !== key || readError) return;
      holder.replaceChildren(waveform(preview));
    } catch {
      holder.replaceChildren(node("p", "원본 파형을 확인할 수 없습니다.", "muted"));
      delete root.dataset.inputKey;
    }
  }
}

function rawSignals(preview) {
  const box = node("div");
  if (!preview.available) {box.append(node("p", "원본 신호 조회 불가: " + preview.reason));return box;}
  const select = node("select");select.setAttribute("aria-label", "원본 측정 신호");
  const choices = signalChoices(preview);
  for (const choice of choices) {const option = node("option", choice.name);option.value = choice.id;select.append(option);}
  const plot = node("div", "", "phm-original-plot"), caption = node("p", "", "muted");box.append(select, plot, caption);
  const render = () => {
    const choice = choices.find((c) => c.id === select.value);
    drawSignal(plot, preview, select.value);
    const unavailable = (choice?.channels || []).flatMap((c) => c.points).filter((p) => p.quality !== "good").length;
    caption.textContent = (choice?.channels.length === 3 ? "R상 ━ · S상 ┄ · T상 ⋯ · " : "") + "관측 " + (choice?.channels[0]?.points.length || 0) + "개/채널 · 사용 불가 " + unavailable + "개 · 누락은 연결하지 않음";
  };
  plot.redraw = render;select.addEventListener("change", render);requestAnimationFrame(render);
  return box;
}

function waveform(preview) {
  const box = node("div");
  if (!preview.available) {box.append(node("p", "원본 파형 확인 불가: " + preview.reason, "muted"));return box;}
  const plots = node("div", "", "phm-original-waveforms");box.append(plots);
  for (const [index, channel] of preview.channels.entries()) {
    const group = node("div");group.append(node("p", channelLabel(channel.channel) + " · 단위 미확인", "phm-feature-title"));
    const plot = node("div", "", "phm-original-plot");group.append(plot);plots.append(group);
    const render = () => {drawSignal(plot, preview, String(index), 130);plot.querySelector("svg")?.classList.add("phm-wave");};
    plot.redraw = render;requestAnimationFrame(render);
  }
  return box;
}

// RUL screen ---------------------------------------------------------------------

function renderRul() {
  const choices = bindingsFor("rul-estimate");
  selected.rul = fillSelect(byId("rul-binding"), choices, selected.rul);
  const state = byId("rul-state");
  for (const id of ["rul-cards", "rul-chart", "rul-recent", "rul-model", "rul-selected"]) byId(id).replaceChildren();
  if (readError) {
    byId("rul-asset-title").textContent = "데이터 조회 실패";
    byId("rul-observation").textContent = "현재 결과를 조회할 수 없습니다. 이전 추정값을 최신 상태로 표시하지 않습니다.";
    byId("rul-validation-note").textContent = "";
    renderPhmExplanation("rul", "", null);
    byId("rul-freshness").textContent = "";
    byId("rul-replay").classList.add("hidden");
    state.className = "state error";state.textContent = "PHM 분석 결과를 읽지 못했습니다.";return;
  }
  if (!selected.rul) {
    byId("rul-asset-title").textContent = "연결된 설비 없음";
    byId("rul-observation").textContent = "분석 모델이 연결되면 수명 추정 결과를 표시합니다.";
    byId("rul-validation-note").textContent = "";
    renderPhmExplanation("rul", "", null);
    state.className = "state";
    state.textContent = "RUL 모델이 연결된 설비가 없습니다. RUL은 수명 종료 사건이 기록된 데이터로 검증된 모델에서만 제공하며, 근거가 없는 설비에는 표시하지 않습니다.";
    byId("rul-freshness").textContent = "";
    return;
  }
  const entry = series.get(selected.rul);
  if (!entry) return;
  byId("rul-asset-title").textContent = entry.binding.asset_id || "설비 정보 없음";
  byId("rul-validation-note").textContent = "";
  byId("rul-freshness").textContent = freshness(entry);
  setReplayTag("rul-replay", entry);
  const analyzed = orderedSteps(entry).filter((step) => step.state === "analyzed");
  const output = (entry.package && entry.package.output) || {};
  if (rulFocusPosition !== null && entry.steps.get(rulFocusPosition)?.state !== "analyzed") {
    state.className = "state error";state.textContent = "선택한 기록 " + stepLabel(entry, rulFocusPosition) + "은 분석되지 않았습니다.";
    byId("rul-observation").textContent = "선택한 입력의 RUL을 표시할 수 없습니다.";
    renderPhmExplanation("rul", "", null);renderModelCard(byId("rul-model"), entry.package);return;
  }
  if (!analyzed.length) {
    byId("rul-observation").textContent = "분석 가능한 입력을 기다리고 있습니다.";
    renderPhmExplanation("rul", "", null);state.className = "state";state.textContent = orderedSteps(entry).length ? "입력 조건 확인: " + orderedSteps(entry).at(-1).reason + inputGuide(orderedSteps(entry).at(-1).reason) : "아직 추정이 없습니다.";renderModelCard(byId("rul-model"), entry.package);return;
  }
  const last = analyzed.find((s) => s.position === rulFocusPosition) || analyzed.at(-1);
  updateMonitorTarget("rul", last.position);
  const latestRulSkipped = orderedSteps(entry).at(-1)?.state === "skipped";
  byId("rul-observation").textContent = latestRulSkipped
    ? "최근 입력은 분석되지 않았습니다. 아래 추정은 마지막으로 분석된 이전 입력의 결과입니다."
    : "기록된 마지막 획득 시점까지의 추정입니다. 실제 고장 시점 예측이 아닙니다.";
  const unit = unitText(last.output.unit);
  const period = output.step_period_seconds;
  state.className = "state";
  state.textContent = "종료점 의미: " + endpointText(last.output.endpoint_semantics) + " · 신뢰구간은 검증되지 않아 표시하지 않습니다.";
  const validation = (entry.package && entry.package.validation) || {};
  const sameAsset = (validation.per_asset || []).find((item) => item.asset_id === entry.binding.asset_id);
  byId("rul-cards").append(
    card(latestRulSkipped ? "마지막 분석 RUL 추정" : rulFocusPosition === null ? "마지막 RUL 추정" : "선택한 RUL 추정", number(last.output.estimate, 1) + " " + unit,
      (period ? "기록 주기 " + period + "초 기준 약 " + number(last.output.estimate * period / 3600, 1) + "시간 · " : "") + "획득 #" + last.position),
    card("이전 추정 대비", last.output.change_from_previous === null ? "첫 추정" : signed(last.output.change_from_previous) + " " + unit, "직전 추정값과 비교"),
  );
  const mae = validation.mean_asset_mean_absolute_error;
  byId("rul-validation-note").textContent = typeof mae === "number"
    ? (validation.metrics_origin === "recorded-research-model" ? "참고 연구 오차" : "검증 오차") + " (MAE) " + number(mae, 1) + " " + unit
      + (sameAsset ? " · 이 설비 검증 MAE " + number(sameAsset.mean_absolute_error, 1) : " · 이 설비에서 직접 검증된 수치가 아닙니다.")
      + " · 이 수치는 개별 추정의 신뢰구간이 아닙니다."
    : "이 추정의 검증 오차를 표시할 근거가 없습니다.";
  if (last.output.sequence_positions) {
    state.textContent += " · 과거 " + last.output.sequence_positions.length + "개 획득으로 계산";
  }
  if (validation.metrics_origin === "recorded-research-model") {
    state.textContent += " · MAE는 기존 연구 수치이며 이 가중치의 별도 성능 검증이 아닙니다.";
  }
  if (orderedSteps(entry).at(-1).state === "skipped") state.textContent += " · 최근 입력은 분석되지 않았습니다: " + orderedSteps(entry).at(-1).reason;
  const axis = axisFor(entry);
  const domain = [axis.x(analyzed[0]), axis.x(analyzed.at(-1))];
  byId("rul-chart").append(linePlot({steps: analyzed, value: (step) => step.output.estimate, axis, height: 190, domain,
    threshold: 0, label: "시점별 RUL 추정 궤적", unitText: "", width: byId("rul-chart").clientWidth,
    onPick: (step) => {rulFocusPosition = step.position;updateMonitorTarget("rul", step.position);renderRul();}}));
  byId("rul-chart").append(node("p", axis.label + " · 각 점은 그 시점까지의 입력만으로 계산한 추정입니다. 점선은 0(기록 종료점)이며 신뢰구간이 아닙니다.", "muted"));
  const recent = byId("rul-recent");
  recent.append(node("h3", "최근 추정 갱신"));
  const table = node("table", "", "phm-table");
  const head = node("tr");for (const label of ["step", "추정", "변화", "적용 범위"]) head.append(node("th", label));
  table.append(head);
  for (const step of analyzed.slice(-10).reverse()) {
    const row = node("tr");
    row.append(node("td", step.event_start ? time(step.event_start) : "#" + step.position), node("td", number(step.output.estimate, 1) + " " + unit),
      node("td", step.output.change_from_previous === null ? "—" : signed(step.output.change_from_previous)), node("td", applicabilityText(step.output.applicability)));
    table.append(row);
  }
  recent.append(table);
  renderModelCard(byId("rul-model"), entry.package);
  if (rulFocusPosition !== null) {
    const focused = entry.steps.get(rulFocusPosition);
    byId("rul-selected").textContent = focused
      ? "모니터에서 선택한 분석 " + stepLabel(entry, focused.position) + " · RUL " + number(focused.output.estimate, 1) + " " + unit
        + " · 처리 " + time(focused.processed_at) + " · 이 시점의 검토와 연결됩니다."
      : "선택한 시점이 이번 조회 범위에 없습니다.";
  }
  const explained = rulFocusPosition ?? last.position;
  renderPhmExplanation("rul", selected.rul, explained,
                       () => {rulFocusPosition = rulFocusPosition ?? last.position;}, stepLabel(entry, explained));
}

const signed = (value) => typeof value === "number" ? (value > 0 ? "+" : "") + number(value, 1) : "값 없음";
const unitText = (unit) => unit === "acquisition-interval" ? "획득 간격" : (unit || "단위 없음");
const endpointText = (value) => value === "last-recorded-acquisition" ? "데이터셋의 마지막 기록 획득(물리 고장 시각 아님)" : (value || "미기록");
const applicabilityText = (value, pkg = null) => {
  if (pkg && pkg.applicability && pkg.applicability.asset_id) {
    return ({inside: "연결 설비와 일치", outside: "다른 설비", unknown: "설비 범위 미확인"})[value] || "설비 범위 미확인";
  }
  return ({inside: "모델 등록 조건 일치", outside: "모델 등록 조건 불일치",
    unknown: "비교 정보 부족"})[value] || "비교 정보 부족";
};

function inputSpec(input) {
  return [
    STEP_KIND_LABEL[input.step_kind] || input.step_kind,
    "채널 " + (input.channels || []).join(", "),
    input.sampling_rate_hz ? number(input.sampling_rate_hz) + " Hz" : "",
    input.samples_per_step ? number(input.samples_per_step) + " 샘플/step" : "",
    input.feature_set_id ? "특징 " + input.feature_set_id : "",
  ].filter(Boolean).join(" · ");
}

function renderModelCard(root, pkg) {
  root.replaceChildren();
  if (!pkg) {root.append(node("p", "모델 패키지 정보를 읽지 못했습니다.", "muted"));return;}
  const summary = node("summary", "모델 정보 · 입력 조건과 검증 기록");
  root.append(summary);
  const facts = node("div", "", "facts");
  const add = (label, value) => {const item = node("div", "", "fact");item.append(node("span", label), node("strong", value));facts.append(item);};
  const scope = pkg.training_scope || {}, validation = pkg.validation || {};
  add("모델", (pkg.recipe_id || "") + " · " + (TASK_LABEL[pkg.output.task] || pkg.output.task));
  add("패키지", pkg.package_id);
  if (pkg.input) add("입력 규격", inputSpec(pkg.input));
  add("학습 데이터", [scope.dataset_id, scope.fold_id, scope.partition].filter(Boolean).join(" · ") + (scope.asset_ids ? " · " + scope.asset_ids.length + "개 설비" : ""));
  if (pkg.input && pkg.input.sequence_length > 1) add("시퀀스 입력", "과거 " + pkg.input.sequence_length + "개 획득 · 현재 시점이 오른쪽 끝");
  if (validation.performance_note) add("성능 수치 범위", validation.performance_note);
  if (scope.member) add("참조 기록", scope.member);
  if (scope.period) add("학습 기간", scope.period);
  if (scope.timezone_assumption) add("시각 가정", scope.timezone_assumption + " · 원본 시간대 미확인");
  if (pkg.output.threshold_rule) add("임계값 규칙", pkg.output.threshold_rule + " = " + number(pkg.output.threshold));
  add("검증 근거", (validation.evidence_class || "기록 없음") + (validation.artifact ? " · " + validation.artifact : ""));
  for (const item of validation.per_asset || []) {
    const metrics = Object.entries(item).filter(([key]) => key !== "asset_id").map(([key, value]) => key + " " + number(value)).join(" · ");
    add("검증 · " + item.asset_id, metrics);
  }
  if (validation.uncertainty) add("불확실성", validation.uncertainty);
  if (validation.score_semantics) add("점수 의미", validation.score_semantics);
  add("적용 운전 조건", Object.entries(pkg.applicability || {}).map(([key, values]) => key + ": " + values.join(", ")).join(" · ") || "기록 없음");
  root.append(facts);
}

// Polling --------------------------------------------------------------------------

async function cycle() {
  const view = activeView();
  if (!view) return;
  const version = ++cycleVersion;
  try {
    await refreshBindings();
    const choices = bindingsFor(view === "anomaly" ? "anomaly-score" : "rul-estimate");
    const target = requestedResult?.view === view ? requestedResult : null;
    if (target && (!target.valid || !choices.some((item) => item.binding_id === target.bindingId))) throw new Error("selected_result_unavailable");
    const current = target ? choices.find((item) => item.binding_id === target.bindingId)
      : choices.find((item) => item.binding_id === selected[view]) || choices[0];
    if (current) await refreshSeries(current.binding_id);
    if (target) {
      const result = await getJson("/api/v1/phm/result?binding_id=" + encodeURIComponent(target.bindingId) + "&position=" + target.position);
      if (result.binding_id !== target.bindingId || result.step?.position !== target.position) throw new Error("wrong_result");
      if (version !== cycleVersion) return;
      selected[view] = target.bindingId;
      series.get(target.bindingId).steps.set(target.position, result.step);
      if (view === "anomaly") focusPosition = target.position;else rulFocusPosition = target.position;
      requestedResult = null;
    }
    if (version !== cycleVersion) return;
    readError = "";
  } catch {
    if (version !== cycleVersion) return;
    readError = "read_failed";
  }
  refreshedAt = new Date();
  if (activeView() === "anomaly") {
    renderAnomaly();
    const entry = series.get(selected.anomaly);
    const shown = focusPosition ?? (entry && orderedSteps(entry).filter((s) => s.state === "analyzed").at(-1)?.position);
    if (!readError && shown != null) {
      updateMonitorTarget("anomaly", shown);
      await focusStep(shown, false);
    }
  }
  if (activeView() === "rul") renderRul();
}

function schedule() {
  clearTimeout(pollTimer);
  if (!activeView() || document.hidden) return;
  pollTimer = setTimeout(async () => {await cycle();schedule();}, POLL_MS);
}

export async function refreshPhm() {
  await cycle();schedule();
}

function updateMonitorTarget(view, position) {
  const url = new URL(location.href);
  const entry = series.get(selected[view]);if (entry?.binding.asset_id) url.searchParams.set("monitor_asset", entry.binding.asset_id);
  url.searchParams.set("phm_binding", selected[view]);url.searchParams.set("phm_position", position);
  url.searchParams.set("phm_view", view);
  history.replaceState(history.state, "", url);
}
function clearMonitorTarget() {
  requestedResult = null;
  const url = new URL(location.href);url.searchParams.delete("phm_binding");url.searchParams.delete("phm_position");url.searchParams.delete("phm_view");
  history.replaceState(history.state, "", url);
}
export function initializePhm() {
  byId("anomaly-binding").addEventListener("change", (event) => {
    clearMonitorTarget();selected.anomaly = event.target.value;zoom.anomaly = null;focusPosition = null;chosenFeatures = [];byId("anomaly-detail").replaceChildren();cycle();
  });
  byId("anomaly-range").addEventListener("change", () => {zoom.anomaly = null;renderAnomaly();});
  byId("anomaly-latest").addEventListener("click", () => {focusPosition = null;zoom.anomaly = null;clearMonitorTarget();cycle();});
  byId("anomaly-signal").addEventListener("change", (event) => {chosenFeatures = JSON.parse(event.target.value);renderAnomaly();});
  window.addEventListener("resize", () => {
    if (activeView() === "anomaly" && !readError) renderAnomaly();
    if (activeView() === "rul" && !readError) renderRul();
    for (const plot of document.querySelectorAll(".phm-original-plot")) if (plot.isConnected) plot.redraw?.();
  });
  byId("rul-binding").addEventListener("change", (event) => {clearMonitorTarget();selected.rul = event.target.value;rulFocusPosition = null;cycle();});
  const start = () => {if (activeView()) {byId("refresh").disabled = false;cycle().then(schedule);} else clearTimeout(pollTimer);};
  window.addEventListener("hashchange", () => {
    const params = new URLSearchParams(location.search);
    if (activeView() && params.has("phm_binding") && params.has("phm_view") && activeView() !== params.get("phm_view")) clearMonitorTarget();
    start();
  });
  document.addEventListener("visibilitychange", start);
  start();
}
