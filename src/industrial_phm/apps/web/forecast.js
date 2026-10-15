// Future values of one stored measurement for the selected asset: the stored flow continued
// ahead with an interval, the model's own reading of the history, an optional management level
// and a check against the signal's own recent past. The server computes; this screen draws.
import { currentAsset, onAssetChange } from "./asset-context.js";
import { formatTime } from "./time.js";
import { byId, clear, create, num } from "./web-utils.js";

const HORIZONS = [["1h", "1시간"], ["24h", "24시간"], ["7d", "7일"], ["30d", "30일"]];
const HORIZON_SECONDS = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000};
const REASON = {
  "few-points": "예측하려면 기록이 20개 이상 필요합니다.",
  "short-history": "선택한 기간의 2배 이상 기록이 있어야 예측합니다.",
  "engine-unavailable": "예측 엔진이 설치되지 않았습니다. make up으로 다시 시작하면 설치됩니다.",
  "unknown-interval": "획득 간격이 기록되지 않아 시간 기준으로 예측할 수 없습니다.",
};
const svgNode = (name, attributes = {}) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
};
let options = null, request = 0, loadedFor = "", shown = null;

async function getJson(url) {
  const response = await fetch(url, {cache: "no-store", credentials: "same-origin"});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(body.error || "read_failed"), {status: response.status, reason: body.reason});
  return body;
}
const state = (text, error = false) => {const node = byId("forecast-state");node.textContent = text;node.className = error ? "state error" : "state";node.hidden = !text;};
const params = () => new URL(location.href).searchParams;
function remember(values) {
  const url = new URL(location.href);
  for (const [key, value] of Object.entries(values)) {
    if (value === "" || value === null || value === undefined) url.searchParams.delete(key);else url.searchParams.set(key, value);
  }
  history.replaceState(history.state, "", url);
}
const duration = (seconds) => seconds >= 86400 ? num(seconds / 86400) + "일" : seconds >= 3600 ? num(seconds / 3600) + "시간"
  : seconds >= 60 ? num(Math.round(seconds / 60)) + "분" : num(Math.round(seconds)) + "초";

export function initializeForecast() {
  onAssetChange(() => {loadedFor = "";remember({forecast_series: "", forecast_horizon: "", forecast_threshold: ""});if (document.body.dataset.view === "forecast") void load();});
  window.addEventListener("hashchange", () => {if (document.body.dataset.view === "forecast" && loadedFor !== currentAsset()) void load();});
  window.addEventListener("resize", () => {if (shown && document.body.dataset.view === "forecast") render(shown);});
  if (document.body.dataset.view === "forecast") void load();
}

async function load() {
  const asset = currentAsset(), ticket = ++request;
  loadedFor = asset;
  clear(byId("forecast-controls"));clear(byId("forecast-result"));shown = null;
  if (!asset) {state("설비를 선택하세요.");return;}
  state("예측할 수 있는 측정값을 확인합니다.");
  let found;
  try {found = await getJson("/api/v1/forecast/options?asset_id=" + encodeURIComponent(asset));}
  catch {if (ticket === request) state("예측할 수 있는 측정값을 확인하지 못했습니다.", true);return;}
  if (ticket !== request || asset !== currentAsset()) return;
  options = found;
  if (!options.history && !options.acquisition) {
    state("이 설비에는 예측할 저장 측정이 없습니다. 측정 이력을 저장하거나, 진동 파형이면 이상 탐지 모델을 연결하면 예측할 수 있습니다.");
    return;
  }
  renderControls();
  await run();
}

function choices() {
  const list = [];
  if (options.history) for (const item of options.history.series) list.push({value: "history|" + item.key, label: item.label, kind: "history"});
  if (options.acquisition) for (const item of options.acquisition.series) list.push({value: "acquisition|" + item.key, label: item.label, kind: "acquisition"});
  return list;
}

function renderControls() {
  const root = byId("forecast-controls");clear(root);
  const series = create("select");series.id = "forecast-series";
  const groups = {history: "측정 이력", acquisition: "진동 획득 특징"};
  const items = choices();
  for (const kind of ["history", "acquisition"]) {
    const subset = items.filter((item) => item.kind === kind);
    if (!subset.length) continue;
    const group = document.createElement("optgroup");group.label = groups[kind];
    for (const item of subset) group.append(Object.assign(create("option", null, item.label), {value: item.value}));
    series.append(group);
  }
  const wanted = params().get("forecast_series");
  const preferred = items.find((item) => item.value === wanted) || items.find((item) => /Horizontal_vibration_signals\.rms$/.test(item.value)) || items[0];
  series.value = preferred.value;
  const seriesField = create("label", null, "측정값");seriesField.append(series);

  const horizons = create("div", "forecast-horizons");horizons.setAttribute("role", "group");horizons.setAttribute("aria-label", "예측 기간");
  const thresholdInput = create("input");thresholdInput.id = "forecast-threshold";thresholdInput.type = "number";thresholdInput.step = "any";
  thresholdInput.placeholder = "없음";thresholdInput.value = params().get("forecast_threshold") || "";
  const thresholdField = create("label", null, "관리 기준 (선택)");thresholdField.append(thresholdInput);
  const apply = create("button", "secondary", "기준 적용");apply.type = "button";

  const drawHorizons = () => {
    clear(horizons);
    const kind = series.value.split("|")[0];
    const reasons = options[kind].horizons;
    let current = params().get("forecast_horizon");
    if (!current || reasons[current]) current = HORIZONS.map(([key]) => key).find((key) => !reasons[key]) || "1h";
    remember({forecast_horizon: current});
    for (const [key, label] of HORIZONS) {
      const button = create("button", "forecast-horizon", label);button.type = "button";
      button.setAttribute("aria-pressed", String(key === current));
      if (reasons[key]) {button.disabled = true;button.title = REASON[reasons[key]] || "";}
      button.addEventListener("click", () => {remember({forecast_horizon: key});drawHorizons();void run();});
      horizons.append(button);
    }
  };
  series.addEventListener("change", () => {remember({forecast_series: series.value});drawHorizons();void run();});
  const applyThreshold = () => {remember({forecast_threshold: thresholdInput.value.trim()});void run();};
  apply.addEventListener("click", applyThreshold);
  thresholdInput.addEventListener("keydown", (event) => {if (event.key === "Enter") {event.preventDefault();applyThreshold();}});
  const horizonField = create("div", "forecast-horizon-field");horizonField.append(create("span", "forecast-label", "예측 기간"), horizons);
  root.append(seriesField, horizonField, thresholdField, apply);
  drawHorizons();
}

async function run() {
  const asset = currentAsset(), ticket = ++request;
  const value = byId("forecast-series")?.value;
  if (!value) return;
  const [kind, ...rest] = value.split("|");
  const series = rest.join("|");
  const horizon = params().get("forecast_horizon") || "1h";
  if (options[kind].horizons[horizon]) {
    clear(byId("forecast-result"));
    state(REASON[options[kind].horizons[horizon]] || "이 기간은 예측할 수 없습니다.");
    return;
  }
  const query = new URLSearchParams({asset_id: asset, kind, series, horizon});
  const threshold = params().get("forecast_threshold");
  if (threshold && Number.isFinite(Number(threshold))) query.set("threshold", threshold);
  state("예측을 계산합니다.");
  try {
    const data = await getJson("/api/v1/forecast?" + query.toString());
    if (ticket !== request || asset !== currentAsset()) return;
    state("");
    render(data);
  } catch (error) {
    if (ticket !== request) return;
    clear(byId("forecast-result"));
    state(error.status === 422 ? REASON[error.reason] || "이 측정값은 예측할 수 없습니다." : "예측을 계산하지 못했습니다.", true);
  }
}

const axisText = (data, x) => data.axis === "acquisition" ? "#" + Math.round(x) : formatTime(x, {seconds: false});
const value = (number) => num(number);

function summary(data) {
  const list = create("dl", "forecast-summary");
  const row = (label, text) => {const item = create("div");item.append(create("dt", null, label), create("dd", null, text));list.append(item);};
  const words = {up: "증가", down: "감소", flat: "유지"};
  const trend = data.trend, unit = data.unit ? " " + data.unit : "";
  const span = HORIZONS.find(([key]) => key === data.horizon)?.[1] || data.horizon;
  row("예상 추세", words[trend.direction] + " · 마지막 측정 " + value(data.history.at(-1)[1]) + " → " + span + " 뒤 " + value(trend.end) + unit
    + " (" + Math.round(data.model.interval_width * 100) + "% 범위 " + value(trend.end_lower) + "–" + value(trend.end_upper) + ")");
  if (data.threshold) {
    const t = data.threshold, when = (x) => axisText(data, x);
    row("관리 기준 " + value(t.value) + unit,
      t.state === "already" ? "마지막 측정값이 이미 기준을 " + (t.direction === "up" ? "넘었습니다." : "밑돌았습니다.")
      : t.state === "expected" ? "예상 도달 " + when(t.expected_at) + (t.earliest_at && t.earliest_at !== t.expected_at ? " · 빠르면 " + when(t.earliest_at) : "")
      : t.state === "possible" ? (t.earliest_at === data.forecast[0][0]
        ? "예측선은 도달하지 않지만 예측 범위가 처음부터 기준에 닿습니다."
        : "예측선은 도달하지 않지만 예측 범위가 " + when(t.earliest_at) + "부터 기준에 닿습니다.")
      : "예측 기간 안에 도달하지 않습니다.");
  }
  const check = data.backtest;
  if (check) {
    const better = check.mean_absolute_error <= check.naive_mean_absolute_error;
    row("과거 자료로 확인", "최근 " + (data.axis === "acquisition" ? num(Math.round(check.hidden_seconds / data.period_seconds)) + "개 획득" : duration(check.hidden_seconds))
      + "을 가리고 예측한 평균 오차 " + value(check.mean_absolute_error) + " · 마지막 값 유지 " + value(check.naive_mean_absolute_error)
      + " · 범위 안 " + Math.round(check.inside_interval * 100) + "%"
      + (better ? "" : " · 이 구간은 마지막 값을 유지한 쪽이 더 가까웠습니다"));
  } else {
    row("과거 자료로 확인", "가려서 확인할 만큼 기록이 길지 않습니다.");
  }
  return list;
}

function chart(data) {
  // Drawn at the panel's own width so labels stay readable on a phone.
  const width = Math.max(320, Math.round(byId("forecast-result").clientWidth || 900));
  const height = width < 600 ? 220 : 260, left = 52, right = width - 12, top = 14, bottom = height - 40;
  const xs = [...data.history.map((p) => p[0]), ...data.forecast.map((p) => p[0])];
  const toNumber = (x) => data.axis === "acquisition" ? x : Date.parse(x);
  const x0 = toNumber(xs[0]), x1 = toNumber(xs.at(-1));
  const ys = [...data.history.map((p) => p[1]), ...data.forecast.flatMap((p) => [p[2], p[3]]), ...(data.threshold ? [data.threshold.value] : [])];
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (y1 <= y0) {y0 -= 1;y1 += 1;}
  const pad = (y1 - y0) * 0.05;y0 -= pad;y1 += pad;
  const X = (x) => left + (toNumber(x) - x0) / (x1 - x0 || 1) * (right - left);
  const Y = (y) => bottom - (y - y0) / (y1 - y0) * (bottom - top);
  const svg = svgNode("svg", {viewBox: `0 0 ${width} ${height}`, class: "forecast-chart", role: "img",
    "aria-label": data.label + "의 측정값과 " + (HORIZONS.find(([key]) => key === data.horizon)?.[1] || "") + " 예측"});
  const path = (points, cls) => svg.append(svgNode("path", {d: points.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" "), class: cls}));
  svg.append(svgNode("path", {d: `M${left} ${top} V${bottom} H${right}`, class: "axis"}));
  const band = [...data.forecast.map((p) => [p[0], p[3]]), ...data.forecast.slice().reverse().map((p) => [p[0], p[2]])];
  svg.append(svgNode("path", {d: band.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" ") + "Z", class: "forecast-band"}));
  path(data.history, "forecast-history");
  path(data.fitted, "forecast-fitted");
  path(data.forecast.map((p) => [p[0], p[1]]), "forecast-line");
  const now = X(data.history.at(-1)[0]);
  svg.append(svgNode("line", {x1: now, x2: now, y1: top, y2: bottom, class: "forecast-now"}));
  if (data.threshold) {
    const y = Y(data.threshold.value);
    svg.append(svgNode("line", {x1: left, x2: right, y1: y, y2: y, class: "forecast-threshold"}));
  }
  const text = (content, attributes) => {const node = svgNode("text", {class: "explore-axis-label", ...attributes});node.textContent = content;svg.append(node);};
  text(value(y1), {x: left - 6, y: top + 4, "text-anchor": "end"});text(value(y0), {x: left - 6, y: bottom, "text-anchor": "end"});
  text(axisText(data, xs[0]), {x: left, y: bottom + 18});
  text("마지막 측정", {x: now, y: bottom + 34, "text-anchor": "middle"});
  text(axisText(data, xs.at(-1)), {x: right, y: bottom + 18, "text-anchor": "end"});
  const legend = create("p", "forecast-legend");
  for (const [cls, label] of [["history", "측정값"], ["fitted", "모델이 읽은 흐름"], ["line", "예측"], ["band", Math.round(data.model.interval_width * 100) + "% 범위"], ...(data.threshold ? [["threshold", "관리 기준"]] : [])]) {
    const item = create("span", "forecast-key forecast-key-" + cls, label);legend.append(item);
  }
  return [svg, legend];
}

function render(data) {
  shown = data;
  const root = byId("forecast-result");
  const note = create("p", "muted", "Prophet · 학습 " + num(data.model.points) + "점"
    + (data.axis === "acquisition" ? " · 획득 간격 " + duration(data.period_seconds) + " 기준"
      : " (원본 " + num(data.raw_count) + "개" + (data.bucket_seconds && data.raw_count > data.model.points * 1.5 ? ", " + duration(data.bucket_seconds) + " 구간 평균" : "") + ")")
    + (data.model.seasonality.length ? " · 반복 패턴 " + data.model.seasonality.map((name) => name === "daily" ? "하루" : "일주일").join("·") : "")
    + (data.other_identities ? " · 같은 이름의 다른 출처·해석 " + data.other_identities + "개는 제외" : ""));
  root.replaceChildren(summary(data), ...chart(data), note);
}
