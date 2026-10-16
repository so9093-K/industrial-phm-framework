// The condition outlook of one stored measurement for the selected asset: its change and the
// remaining margin to the conditions the user sets (outlook.js), then the stored flow continued
// ahead with an interval, the model's own reading of the history, the conditions and a check
// against the signal's own recent past. The server computes; this screen draws.
import { currentAsset, onAssetChange } from "./asset-context.js";
import { clearOutlook, refreshOutlook, renderOutlook } from "./outlook.js";
import { formatTime } from "./time.js";
import { byId, clear, create, num } from "./web-utils.js";

const HORIZONS = [["1h", "1시간"], ["24h", "24시간"], ["7d", "7일"], ["30d", "30일"]];
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
let options = null, request = 0, loadedFor = "", shown = null, previous = null, showWholeScale = false;

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

// Reload options as well as forecast/outlook: new stored measurements can change eligibility.
export function refreshForecast() {
  if (document.body.dataset.view === "forecast") void load();
}

export function initializeForecast() {
  onAssetChange(() => {loadedFor = "";clearOutlook();remember({forecast_series: "", forecast_horizon: "", forecast_threshold: "", forecast_end: "", forecast_direction: "", forecast_context_from: "", forecast_context_to: "", forecast_context_kind: "", forecast_unit: "", forecast_count: "", forecast_assumed_period: "", forecast_prior: "", forecast_range: "", forecast_training: "", forecast_seasonality: "", forecast_backtest: ""});if (document.body.dataset.view === "forecast") void load();});
  window.addEventListener("hashchange", () => {
    if (document.body.dataset.view !== "forecast") return;
    const wanted = params().get("forecast_series");
    if (loadedFor !== currentAsset() || (wanted && wanted !== (shown ? shown.kind + "|" + shown.series : byId("forecast-series")?.value))) void load();
    else if (shown) render(shown);
  });
  window.addEventListener("resize", () => {if (shown && document.body.dataset.view === "forecast") render(shown);});
  if (document.body.dataset.view === "forecast") void load();
}

async function load() {
  const asset = currentAsset(), ticket = ++request;
  loadedFor = asset;
  clear(byId("forecast-controls"));clear(byId("forecast-chart-controls"));clear(byId("forecast-result"));shown = null;previous = null;
  clear(byId("forecast-settings-root"));byId("forecast-settings").hidden = true;
  clearOutlook();byId("forecast-chart-section").hidden = true;
  if (!asset) {state("설비를 선택하세요.");return;}
  state("전망할 수 있는 측정값을 확인합니다.");
  let found;
  try {found = await getJson("/api/v1/forecast/options?asset_id=" + encodeURIComponent(asset));}
  catch {if (ticket === request) state("전망할 수 있는 측정값을 확인하지 못했습니다.", true);return;}
  if (ticket !== request || asset !== currentAsset()) return;
  options = found;
  if (!options.history && !options.acquisition) {
    state("이 설비에는 전망할 저장 측정이 없습니다. 측정 이력을 저장하거나, 진동 파형이면 이상 탐지 모델을 연결하면 계산합니다.");
    return;
  }
  if (await renderControls()) await run();
}

function choices() {
  const list = [];
  if (options.history) for (const item of options.history.series) list.push({value: "history|" + item.key, label: item.label, kind: "history"});
  if (options.acquisition) for (const item of options.acquisition.series) {
    if (item.valid_points < 20) continue;
    list.push({value: "acquisition|" + item.key, label: item.label, kind: "acquisition"});
  }
  return list;
}

async function renderControls() {
  const root = byId("forecast-controls");clear(root);
  const series = create("select");series.id = "forecast-series";
  const groups = {history: "측정 이력", acquisition: "진동 획득 특징"};
  const items = choices();
  if (!items.length) {
    state("분석 이력은 있지만 유효한 측정값이 20개 이상인 신호가 없습니다.");
    return false;
  }
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
  const endInput = create("input");endInput.id = "forecast-end";endInput.type = "number";endInput.step = "any";
  endInput.placeholder = "없음";endInput.value = params().get("forecast_end") || "";
  const endField = create("label", null, "종료 기준 (선택)");endField.append(endInput);
  const apply = create("button", "secondary", "기준 적용");apply.type = "button";

  const drawHorizons = async () => {
    const ticket = ++request;
    const [kind, ...parts] = series.value.split("|");
    const query = new URLSearchParams({asset_id: currentAsset(), kind, series: parts.join("|")});
    const training = byId("forecast-training")?.value;
    const assumed = kind === "acquisition" && byId("forecast-assumed-period")?.value;
    if (training) query.set("training_points", training);
    if (assumed) query.set("assumed_period_seconds", assumed);
    let reasons;
    try {
      const result = await getJson("/api/v1/forecast/options?" + query.toString());
      if (ticket !== request) return false;
      reasons = result.selection.horizons;
    } catch {
      if (ticket === request) state("선택 신호와 예측 설정을 확인하지 못했습니다. 설정값의 범위를 확인하세요.", true);
      return false;
    }
    clear(horizons);
    let current = params().get("forecast_horizon");
    if (!current || reasons[current])
      current = HORIZONS.map(([key]) => key).find((key) => !reasons[key]) || "1h";
    remember({forecast_horizon: current});
    for (const [key, label] of HORIZONS) {
      const button = create("button", "forecast-horizon", label);button.type = "button";
      button.setAttribute("aria-pressed", String(key === current));
      if (reasons[key]) {button.disabled = true;button.title = REASON[reasons[key]] || "";}
      button.addEventListener("click", () => {remember({forecast_horizon: key});void update();});
      horizons.append(button);
    }
    return true;
  };
  const update = async () => {if (await drawHorizons()) await run();};
  series.addEventListener("change", () => {
    remember({forecast_series: series.value, forecast_backtest: "",
      forecast_context_kind: "", forecast_context_from: "", forecast_context_to: ""});
    const kind = series.value.split("|")[0];
    if (kind === "acquisition" && !params().get("forecast_count"))
      countInput.value = recommendedCount(series.value);
    unitSelect.value = kind === "acquisition" && !Object.values(options.acquisition?.horizons || {}).some(reason => !reason)
      ? "count" : (params().get("forecast_unit") || "time");
    refreshUnit();void update();
  });
  const directionField = create("label", null, "기준 방향");
  const directionSelect = create("select");directionSelect.id = "forecast-direction";
  for (const [key, label] of [["upper", "상한 (이상)"], ["lower", "하한 (이하)"]])
    directionSelect.append(Object.assign(create("option", null, label), {value: key}));
  directionSelect.value = params().get("forecast_direction") === "lower" ? "lower" : "upper";
  directionField.append(directionSelect);
  const applyThreshold = () => {
    remember({forecast_threshold: thresholdInput.value.trim(), forecast_end: endInput.value.trim(), forecast_direction: directionSelect.value});
    void run();
  };
  directionSelect.addEventListener("change", applyThreshold);
  apply.addEventListener("click", applyThreshold);
  for (const input of [thresholdInput, endInput]) input.addEventListener("keydown", (event) => {if (event.key === "Enter") {event.preventDefault();applyThreshold();}});

  const horizonField = create("div", "forecast-horizon-field");horizonField.append(horizons);
  const countField = create("label", "forecast-inline", "획득 수");const countInput = create("input");
  countInput.type = "number";countInput.min = "1";countInput.max = "2000";countInput.step = "1";
  countInput.id = "forecast-count";
  const acquisition = options.acquisition;
  const recommendedCount = (selection) => {
    const selected = acquisition?.series.find(item => "acquisition|" + item.key === selection);
    const span = selected?.valid_span_steps ?? (acquisition ? acquisition.last - acquisition.first : 60);
    return String(Math.max(1, Math.min(30, Math.floor(span / 2))));
  };
  countInput.value = params().get("forecast_count") || recommendedCount(series.value);
  countField.append(countInput);
  const unitField = create("label", "forecast-inline", "단위");const unitSelect = create("select");
  unitSelect.id = "forecast-unit";
  for (const [key, label] of [["time", "시간"], ["count", "획득 개수"]]) unitSelect.append(Object.assign(create("option", null, label), {value: key}));
  unitSelect.value = params().get("forecast_unit") === "count"
    || (series.value.startsWith("acquisition|") && !Object.values(options.acquisition?.horizons || {}).some(reason => !reason))
    ? "count" : "time";
  unitField.append(unitSelect);
  const countApply = create("button", "secondary compact", "적용");countApply.type = "button";
  countApply.setAttribute("aria-label", "획득 수 적용");
  const countChanged = () => {remember({forecast_count: countInput.value, forecast_backtest: ""});void run();};
  countApply.addEventListener("click", countChanged);
  countInput.addEventListener("keydown", event => {if (event.key === "Enter") {event.preventDefault();countChanged();}});
  const assumption = create("label", null, "가정 획득 간격 · 초 (선택)");
  const assumedInput = create("input");assumedInput.type = "number";assumedInput.min = "1";assumedInput.max = "86400";assumedInput.step = "any";
  assumedInput.placeholder = "원본 간격";assumedInput.id = "forecast-assumed-period";
  assumedInput.value = params().get("forecast_assumed_period") || "";assumption.append(assumedInput);
  const assumptionApply = create("button", "secondary", "간격 적용");assumptionApply.type = "button";
  assumptionApply.addEventListener("click", () => {
    remember({forecast_assumed_period: assumedInput.value, forecast_backtest: ""});
    void update();
  });
  // Settings and checks of the forecast live with the evidence, folded under the outlook.
  const details = create("div", "forecast-details");details.id = "forecast-details";
  details.append(create("h4", null, "예측 설정"));
  const advanced = create("div", "forecast-advanced");
  const numeric = (id, label, initial, min, max, step) => {
    const field = create("label", null, label), input = create("input");input.id = id;
    input.type = "number";input.min = String(min);input.max = String(max);input.step = String(step);
    input.value = params().get(id.replaceAll("-", "_")) || initial;field.append(input);advanced.append(field);return input;
  };
  const prior = numeric("forecast-prior", "추세 민감도 (0.001-0.5)", "0.05", 0.001, 0.5, 0.001);
  const changeRange = numeric("forecast-range", "변화점 탐색 범위 (0.5–0.95)", "0.9", 0.5, 0.95, 0.01);
  const training = numeric("forecast-training", "최근 학습 획득·측정 수 (선택)", "", 20, 1000, 1);
  const seasonality = create("select");seasonality.id = "forecast-seasonality";
  for (const [key, label] of [["auto", "반복 패턴 자동"], ["off", "반복 패턴 사용 안 함"]]) seasonality.append(Object.assign(create("option", null, label), {value: key}));
  seasonality.value = params().get("forecast_seasonality") || "auto";
  const seasonField = create("label", null, "반복 패턴");seasonField.append(seasonality);advanced.append(seasonField);
  const settingsApply = create("button", "secondary", "설정 적용");settingsApply.type = "button";
  settingsApply.addEventListener("click", () => {
    remember({forecast_prior: prior.value, forecast_range: changeRange.value, forecast_training: training.value, forecast_seasonality: seasonality.value, forecast_backtest: ""});
    void update();
  });
  advanced.append(settingsApply);details.append(advanced);
  const validation = create("button", "secondary", "여러 과거 시점 비교");validation.type = "button";
  validation.addEventListener("click", () => {remember({forecast_backtest: "multi"});byId("forecast-settings").open = true;void run();});
  details.append(validation);
  const detailMetrics = create("div", "forecast-detail-metrics");detailMetrics.id = "forecast-detail-metrics";details.append(detailMetrics);
  const refreshUnit = () => {
    const acquisition = series.value.startsWith("acquisition|"), count = acquisition && unitSelect.value === "count";
    unitField.hidden = !acquisition;horizonField.hidden = count;
    countField.hidden = !count;countApply.hidden = !count;
    assumption.hidden = !acquisition;assumptionApply.hidden = !acquisition;
  };
  unitSelect.addEventListener("change", () => {remember({forecast_unit: unitSelect.value, forecast_backtest: ""});refreshUnit();void run();});
  root.append(seriesField, thresholdField, endField, directionField, apply);
  byId("forecast-settings-root").append(details);byId("forecast-settings").hidden = false;
  // The horizon only shapes the chart; the margin is searched over half the record's length.
  byId("forecast-chart-controls").append(unitField, horizonField, countField, countApply);
  advanced.prepend(assumption, assumptionApply);
  refreshUnit();
  return drawHorizons();

}

// The two independently calculated API responses must describe the same last observation.
function sameObservation(forecast, outlook) {
  if (forecast.asset_id !== outlook.asset_id || forecast.kind !== outlook.kind ||
      forecast.series !== outlook.series || forecast.axis !== outlook.axis ||
      forecast.source_id !== outlook.source_id ||
      (forecast.measurement_point_id || null) !== (outlook.measurement_point_id || null)) return false;
  const last = forecast.history?.at(-1)?.[0], observed = outlook.record?.last;
  if (forecast.axis === "acquisition") return Number.isFinite(last) && last === observed;
  return typeof last === "string" && typeof observed === "string" &&
    Number.isFinite(Date.parse(last)) && Date.parse(last) === Date.parse(observed);
}

async function run() {
  const asset = currentAsset(), ticket = ++request;
  const value = byId("forecast-series")?.value;
  if (!value) return;
  const [kind, ...rest] = value.split("|");
  const series = rest.join("|");
  const unit = kind === "acquisition" && byId("forecast-unit")?.value === "count" ? "count" : "time";
  const horizon = unit === "count" ? "count" : params().get("forecast_horizon") || "1h";
  const query = new URLSearchParams({asset_id: asset, kind, series, horizon});
  const threshold = params().get("forecast_threshold");
  if (threshold && Number.isFinite(Number(threshold))) query.set("threshold", threshold);
  query.set("threshold_direction", byId("forecast-direction")?.value || "upper");
  const setNumber = (id, field, min, max, integer = false) => {
    const text = byId(id)?.value?.trim();
    if (!text) return true;
    const value = Number(text);
    if (!Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value))) return false;
    query.set(field, text);return true;
  };
  if (!(setNumber("forecast-prior", "changepoint_prior_scale", 0.001, 0.5)
    && setNumber("forecast-range", "changepoint_range", 0.5, 0.95)
    && setNumber("forecast-training", "training_points", 20, 1000, true)
    && (horizon !== "count" || setNumber("forecast-count", "horizon_count", 1, 2000, true))
    && (kind !== "acquisition" || setNumber("forecast-assumed-period", "assumed_period_seconds", 1, 86400)))) {
    state("예측 설정값의 범위를 확인하세요.", true);return;
  }
  if (horizon === "count" && !query.has("horizon_count")) {state("예측할 획득 수를 입력하세요.", true);return;}
  if (kind === "acquisition" && byId("forecast-unit")) remember({forecast_unit: unit});
  query.set("seasonality", byId("forecast-seasonality")?.value || "auto");
  const outlookQuery = new URLSearchParams({asset_id: asset, kind, series, direction: query.get("threshold_direction")});
  if (query.has("threshold")) outlookQuery.set("management_limit", query.get("threshold"));
  const end = params().get("forecast_end");
  if (end && Number.isFinite(Number(end))) outlookQuery.set("end_limit", end);
  for (const field of ["changepoint_prior_scale", "changepoint_range", "training_points", "seasonality", "assumed_period_seconds"])
    if (query.has(field)) outlookQuery.set(field, query.get(field));
  if (params().get("forecast_backtest") === "multi") query.set("backtest", "multi");
  // Hide old results while both requests run. Neither is shown as a fresh pair alone.
  clear(byId("forecast-result"));byId("forecast-chart-section").hidden = true;
  clearOutlook();
  const context = contextText(kind);
  state("예측과 상태 전망을 계산합니다.");
  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      const [data, outlook] = await Promise.all([
        getJson("/api/v1/forecast?" + query.toString()),
        refreshOutlook(outlookQuery, context, {deferRender: true, force: true}),
      ]);
      if (ticket !== request || asset !== currentAsset()) return;
      if (!outlook) {
        state("상태 전망을 계산하지 못했습니다. 새로고침해 주세요.", true);
        return;
      }
      if (sameObservation(data, outlook)) {
        state("");
        previous = shown && shown.asset_id === data.asset_id && shown.kind === data.kind
          && shown.series === data.series && shown.axis === data.axis && shown.horizon === data.horizon
          && shown.period_seconds === data.period_seconds && shown.horizon_count === data.horizon_count ? shown : null;
        render(data);
        renderOutlook(outlook, context);
        return;
      }
      state("새 측정을 확인하며 예측과 전망을 다시 맞춥니다.");
    }
    clearOutlook();
    state("예측과 상태 전망의 마지막 측정 시점이 다릅니다. 다시 새로고침해 주세요.", true);
  } catch (error) {
    if (ticket !== request) return;
    clearOutlook();
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
  const span = data.horizon === "count" ? data.horizon_count + "개 획득" : HORIZONS.find(([key]) => key === data.horizon)?.[1] || data.horizon;
  row("예측 종료값", "마지막 측정 " + value(data.history.at(-1)[1]) + " · " + span + " 뒤 " + value(trend.end) + unit
    + " (" + Math.round(data.model.interval_width * 100) + "% 범위 " + value(trend.end_lower) + "–" + value(trend.end_upper) + ")");
  row("예측선 변화", words[trend.change > 0 ? "up" : trend.change < 0 ? "down" : "flat"]
    + " · 예측 시작~종료 " + value(trend.change) + unit);
  row("추세 성분", words[trend.slope_direction || trend.direction]
    + " · 변화 " + value(trend.trend_component_change ?? trend.change) + unit);
  return list;
}

function chart(data) {
  // Drawn at the panel's own width so labels stay readable on a phone.
  const width = Math.max(320, Math.round(byId("forecast-result").clientWidth || 900));
  const height = width < 600 ? 220 : 260, left = 52, right = width - 12, top = 14, bottom = height - 40;
  const xs = [...data.history.map((p) => p[0]), ...data.forecast.map((p) => p[0])];
  const toNumber = (x) => data.axis === "acquisition" ? x : Date.parse(x);
  const x0 = toNumber(xs[0]), x1 = toNumber(xs.at(-1));
  const ys = [...data.history.map(p => p[1]), ...data.forecast.flatMap(p => [p[2], p[3]]),
    ...(previous ? previous.forecast.map(p => p[1]) : []),
    ...(showWholeScale ? limits(data).map(([, limit]) => limit) : [])];
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
  if (previous) path(previous.forecast.map(p => [p[0], p[1]]), "forecast-compare");
  path(data.forecast.map((p) => [p[0], p[1]]), "forecast-line");
  const now = X(data.history.at(-1)[0]);
  svg.append(svgNode("line", {x1: now, x2: now, y1: top, y2: bottom, class: "forecast-now"}));
  for (const [name, limit] of limits(data)) {
    const y = Y(limit);
    if (y >= top && y <= bottom) svg.append(svgNode("line", {x1: left, x2: right, y1: y, y2: y, class: name === "end" ? "forecast-end" : "forecast-threshold"}));
    else {
      const hint = svgNode("text", {x: right - 5, y: limit > y1 ? top + 13 : bottom - 6 - (name === "end" ? 14 : 0),
        "text-anchor": "end", class: "explore-axis-label"});
      hint.textContent = (name === "end" ? "종료 기준 " : "관리 기준 ") + value(limit) + (limit > y1 ? " ↑" : " ↓");svg.append(hint);
    }
  }
  const text = (content, attributes) => {const node = svgNode("text", {class: "explore-axis-label", ...attributes});node.textContent = content;svg.append(node);};
  text(value(y1), {x: left - 6, y: top + 4, "text-anchor": "end"});text(value(y0), {x: left - 6, y: bottom, "text-anchor": "end"});
  text(axisText(data, xs[0]), {x: left, y: bottom + 18});
  text("마지막 측정", {x: now, y: bottom + 34, "text-anchor": "middle"});
  text(axisText(data, xs.at(-1)), {x: right, y: bottom + 18, "text-anchor": "end"});
  const legend = create("p", "forecast-legend");
  for (const [cls, label] of [["history", "측정값"], ["fitted", "모델이 읽은 흐름"], ...(previous ? [["compare", "이전 예측"]] : []), ["line", "예측"], ["band", Math.round(data.model.interval_width * 100) + "% 범위"], ...limits(data).map(([name]) => name === "end" ? ["end", "종료 기준"] : ["threshold", "관리 기준"])]) {
    const item = create("span", "forecast-key forecast-key-" + cls, label);legend.append(item);
  }
  return [svg, legend];
}

function render(data) {
  shown = data;
  const root = byId("forecast-result");
  const note = create("p", "muted", "Prophet · 학습 " + num(data.model.points) + "점"
    + (data.axis === "acquisition" ? (data.time_basis === "ordinal" ? " · 획득 순서 기준 (기록된 시간 간격 없음)"
      : " · " + (data.time_basis === "assumed" ? "가정 획득 간격 " : "기록 획득 간격 ") + duration(data.period_seconds) + " 기준")
      : " (원본 " + num(data.raw_count) + "개" + (data.bucket_seconds && data.raw_count > data.model.points * 1.5 ? ", " + duration(data.bucket_seconds) + " 구간 평균" : "") + ")")
    + (data.model.seasonality.length ? " · 반복 패턴 " + data.model.seasonality.map((name) => name === "daily" ? "하루" : "일주일").join("·") : "")
    + (data.other_identities ? " · 같은 이름의 다른 출처·해석 " + data.other_identities + "개는 제외" : ""));
  const scale = create("button", "link-button", showWholeScale ? "측정 변화 중심" : "기준까지 보기");
  scale.type = "button";scale.addEventListener("click", () => {showWholeScale = !showWholeScale;render(data);});
  byId("forecast-chart-section").hidden = false;
  const [svg, legend] = chart(data);
  if (limits(data).length) legend.append(scale);
  root.replaceChildren(svg, legend);
  const metricRoot = byId("forecast-detail-metrics");
  if (metricRoot) {
    const check = data.backtest;
    const lines = summary(data);
    const row = (term, value) => {const entry = create("div");entry.append(create("dt", null, term), create("dd", null, value));lines.append(entry);};
    row("설정", "추세 민감도 " + data.model.changepoint_prior_scale + " · 변화점 탐색 범위 " + data.model.changepoint_range + " · 학습 " + data.model.points + "개");
    row("예측 시작값과 마지막 실측 차이", value(data.trend.level_gap));
    if (previous) row("이전 설정과 비교", "이전 종료 예상 " + value(previous.trend.end)
      + " → 현재 종료 예상 " + value(data.trend.end));
    if (check) {
      row("과거 자료로 확인", "최근 " + check.points + "개를 가리고 예측 · 평균 절대 오차 " + value(check.mean_absolute_error));
      row("마지막 값 유지", "같은 구간 평균 절대 오차 " + value(check.naive_mean_absolute_error));
      row(Math.round(data.model.interval_width * 100) + "% 예측 범위 내 실제값 포함", Math.round(check.inside_interval * 100) + "%");
    } else row("과거 자료로 확인", "가려서 확인할 만큼 기록이 길지 않습니다.");
    if (Array.isArray(data.rolling_backtests)) {
      row("여러 과거 시점", data.rolling_backtests.length + "개 기준 시점 확인");
      for (const [index, result] of data.rolling_backtests.entries()) {
        row("과거 시점 " + (index + 1), "관측 " + result.points + "개 · 평균 절대 오차 " + value(result.mean_absolute_error)
          + " · 마지막 값 유지 " + value(result.naive_mean_absolute_error)
          + " · 범위 안 " + Math.round(result.inside_interval * 100) + "%");
      }
    }
    metricRoot.replaceChildren(lines, note);
  }
}

// The conditions drawn on the chart: the management level the forecast was asked about, and the
// end condition entered with it.
function limits(data) {
  const list = data.threshold ? [["management", data.threshold.value]] : [];
  const end = Number(params().get("forecast_end"));
  if (params().get("forecast_end") && Number.isFinite(end)) list.push(["end", end]);
  return list;
}

// A range chosen on another screen before coming here, named once in the outlook's evidence.
function contextText(kind) {
  const from = params().get("forecast_context_from"), to = params().get("forecast_context_to");
  const contextKind = params().get("forecast_context_kind");
  const fits = kind === "acquisition" ? /^\d+$/.test(from) && /^\d+$/.test(to)
    : Number.isFinite(Date.parse(from)) && Number.isFinite(Date.parse(to));
  if (!from || !to || !contextKind || !fits) return "";
  const shownRange = kind === "acquisition" ? "#" + from + "–#" + to
    : formatTime(from, {seconds: false}) + " ~ " + formatTime(to, {seconds: false, zone: false});
  return (contextKind === "anomaly" ? "이상 탐지에서 고른 구간 " : "구간 비교의 구간 B ") + shownRange + " (예측 학습 범위와 별개)";
}
