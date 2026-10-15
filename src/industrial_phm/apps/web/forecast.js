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

export function initializeForecast() {
  onAssetChange(() => {loadedFor = "";remember({forecast_series: "", forecast_horizon: "", forecast_threshold: "", forecast_unit: "", forecast_count: "", forecast_assumed_period: "", forecast_prior: "", forecast_range: "", forecast_training: "", forecast_seasonality: "", forecast_backtest: ""});if (document.body.dataset.view === "forecast") void load();});
  window.addEventListener("hashchange", () => {
    if (document.body.dataset.view !== "forecast") return;
    const wanted = params().get("forecast_series");
    if (loadedFor !== currentAsset() || (wanted && wanted !== (shown ? shown.kind + "|" + shown.series : byId("forecast-series")?.value))) void load();
  });
  window.addEventListener("resize", () => {if (shown && document.body.dataset.view === "forecast") render(shown);});
  if (document.body.dataset.view === "forecast") void load();
}

async function load() {
  const asset = currentAsset(), ticket = ++request;
  loadedFor = asset;
  clear(byId("forecast-controls"));clear(byId("forecast-result"));shown = null;previous = null;
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
  series.addEventListener("change", () => {
    remember({forecast_series: series.value});
    const kind = series.value.split("|")[0];
    unitSelect.value = kind === "acquisition" && !options.acquisition?.period_seconds ? "count" : (params().get("forecast_unit") || "time");
    drawHorizons();refreshUnit();void run();
  });
  const applyThreshold = () => {remember({forecast_threshold: thresholdInput.value.trim()});void run();};
  apply.addEventListener("click", applyThreshold);
  thresholdInput.addEventListener("keydown", (event) => {if (event.key === "Enter") {event.preventDefault();applyThreshold();}});

  const horizonField = create("div", "forecast-horizon-field");horizonField.append(create("span", "forecast-label", "예측 기간"), horizons);
  const countField = create("label", null, "미래 획득 수");const countInput = create("input");
  countInput.type = "number";countInput.min = "1";countInput.max = "2000";countInput.step = "1";
  countInput.id = "forecast-count";countInput.value = params().get("forecast_count") || "30";countField.append(countInput);
  const unitField = create("label", null, "예측 단위");const unitSelect = create("select");
  unitSelect.id = "forecast-unit";
  for (const [key, label] of [["time", "시간"], ["count", "획득 개수"]]) unitSelect.append(Object.assign(create("option", null, label), {value: key}));
  unitSelect.value = params().get("forecast_unit") === "count" || (series.value.startsWith("acquisition|") && !options.acquisition?.period_seconds) ? "count" : "time";
  unitField.append(unitSelect);
  const countApply = create("button", "secondary", "획득 수 적용");countApply.type = "button";
  const countChanged = () => {remember({forecast_count: countInput.value});void run();};
  countApply.addEventListener("click", countChanged);
  countInput.addEventListener("keydown", event => {if (event.key === "Enter") {event.preventDefault();countChanged();}});
  const assumption = create("label", null, "가정 획득 간격 · 초 (선택)");
  const assumedInput = create("input");assumedInput.type = "number";assumedInput.min = "1";assumedInput.max = "86400";assumedInput.step = "any";
  assumedInput.placeholder = "원본 간격";assumedInput.id = "forecast-assumed-period";
  assumedInput.value = params().get("forecast_assumed_period") || "";assumption.append(assumedInput);
  const assumptionApply = create("button", "secondary", "간격 적용");assumptionApply.type = "button";
  assumptionApply.addEventListener("click", () => {remember({forecast_assumed_period: assumedInput.value});void run();});
  const details = create("details", "forecast-details");details.id = "forecast-details";
  details.append(create("summary", null, "예측 설정 및 상세 분석"));
  const advanced = create("div", "forecast-advanced");
  const numeric = (id, label, initial, min, max, step) => {
    const field = create("label", null, label), input = create("input");input.id = id;
    input.type = "number";input.min = String(min);input.max = String(max);input.step = String(step);
    input.value = params().get(id.replaceAll("-", "_")) || initial;field.append(input);advanced.append(field);return input;
  };
  const prior = numeric("forecast-prior", "추세 민감도 (0.001–0.5)", "0.05", 0.001, 0.5, 0.001);
  const changeRange = numeric("forecast-range", "변화점 탐색 범위 (0.5–0.95)", "0.9", 0.5, 0.95, 0.01);
  const training = numeric("forecast-training", "최근 학습 획득·측정 수 (선택)", "", 20, 1000, 1);
  const seasonality = create("select");seasonality.id = "forecast-seasonality";
  for (const [key, label] of [["auto", "반복 패턴 자동"], ["off", "반복 패턴 사용 안 함"]]) seasonality.append(Object.assign(create("option", null, label), {value: key}));
  seasonality.value = params().get("forecast_seasonality") || "auto";
  const seasonField = create("label", null, "반복 패턴");seasonField.append(seasonality);advanced.append(seasonField);
  const settingsApply = create("button", "secondary", "설정 적용");settingsApply.type = "button";
  settingsApply.addEventListener("click", () => {
    remember({forecast_prior: prior.value, forecast_range: changeRange.value, forecast_training: training.value, forecast_seasonality: seasonality.value});
    void run();
  });
  advanced.append(settingsApply);details.append(advanced);
  const validation = create("button", "secondary", "여러 과거 시점 비교");validation.type = "button";
  validation.addEventListener("click", () => {remember({forecast_backtest: "multi"});details.open = true;void run();});
  details.append(validation);
  const detailMetrics = create("div", "forecast-detail-metrics");detailMetrics.id = "forecast-detail-metrics";details.append(detailMetrics);
  const refreshUnit = () => {
    const acquisition = series.value.startsWith("acquisition|"), count = acquisition && unitSelect.value === "count";
    unitField.hidden = !acquisition;horizonField.hidden = count;
    countField.hidden = !count;countApply.hidden = !count;
    assumption.hidden = !acquisition;assumptionApply.hidden = !acquisition;
  };
  unitSelect.addEventListener("change", () => {remember({forecast_unit: unitSelect.value});refreshUnit();void run();});
  root.append(seriesField, unitField, horizonField, countField, countApply, thresholdField, apply, details);
  advanced.prepend(assumption, assumptionApply);
  drawHorizons();refreshUnit();

}

async function run() {
  const asset = currentAsset(), ticket = ++request;
  const value = byId("forecast-series")?.value;
  if (!value) return;
  const [kind, ...rest] = value.split("|");
  const series = rest.join("|");
  const unit = kind === "acquisition" && byId("forecast-unit")?.value === "count" ? "count" : "time";
  const horizon = unit === "count" ? "count" : params().get("forecast_horizon") || "1h";
  const assumedPeriod = byId("forecast-assumed-period")?.value || "";
  if (horizon !== "count" && options[kind].horizons[horizon] &&
      !(kind === "acquisition" && assumedPeriod)) {
    clear(byId("forecast-result"));
    state(REASON[options[kind].horizons[horizon]] || "이 기간은 예측할 수 없습니다.");
    return;
  }
  const query = new URLSearchParams({asset_id: asset, kind, series, horizon});
  const threshold = params().get("forecast_threshold");
  if (threshold && Number.isFinite(Number(threshold))) query.set("threshold", threshold);
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
  if (params().get("forecast_backtest") === "multi") query.set("backtest", "multi");
  state("예측을 계산합니다.");
  try {
    const data = await getJson("/api/v1/forecast?" + query.toString());
    if (ticket !== request || asset !== currentAsset()) return;
    state("");
    previous = shown && shown.asset_id === data.asset_id && shown.kind === data.kind
      && shown.series === data.series && shown.axis === data.axis && shown.horizon === data.horizon
      && shown.period_seconds === data.period_seconds ? shown : null;
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
  const span = data.horizon === "count" ? data.horizon_count + "개 획득" : HORIZONS.find(([key]) => key === data.horizon)?.[1] || data.horizon;
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
  row("예측선의 방향", words[trend.slope_direction || trend.direction]
    + " · 예측 시작~종료 변화 " + value(trend.change) + unit);
  if (data.backtest) row("과거 자료 확인", "최근 " + num(data.backtest.points) + "개 관측값으로 예측 흐름을 확인했습니다. 세부 비교는 상세 보기에서 확인할 수 있습니다.");
  else row("과거 자료 확인", "가려서 확인할 만큼 기록이 길지 않습니다.");
  return list;
}

function chart(data) {
  // Drawn at the panel's own width so labels stay readable on a phone.
  const width = Math.max(320, Math.round(byId("forecast-result").clientWidth || 900));
  const height = width < 600 ? 220 : 260, left = 52, right = width - 12, top = 14, bottom = height - 40;
  const xs = [...data.history.map((p) => p[0]), ...data.forecast.map((p) => p[0])];
  const toNumber = (x) => data.axis === "acquisition" ? x : Date.parse(x);
  const x0 = toNumber(xs[0]), x1 = toNumber(xs.at(-1));
  const ys = [...data.history.map((p) => p[1]), ...data.forecast.flatMap((p) => [p[2], p[3]]), ...(showWholeScale && data.threshold ? [data.threshold.value] : [])];
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
  if (data.threshold) {
    const y = Y(data.threshold.value);
    if (y >= top && y <= bottom) svg.append(svgNode("line", {x1: left, x2: right, y1: y, y2: y, class: "forecast-threshold"}));
    else {
      const hint = svgNode("text", {x: right - 5, y: data.threshold.value > y1 ? top + 13 : bottom - 6,
        "text-anchor": "end", class: "explore-axis-label"});
      hint.textContent = "관리 기준 " + value(data.threshold.value) + (data.threshold.value > y1 ? " ↑" : " ↓");svg.append(hint);
    }
  }
  const text = (content, attributes) => {const node = svgNode("text", {class: "explore-axis-label", ...attributes});node.textContent = content;svg.append(node);};
  text(value(y1), {x: left - 6, y: top + 4, "text-anchor": "end"});text(value(y0), {x: left - 6, y: bottom, "text-anchor": "end"});
  text(axisText(data, xs[0]), {x: left, y: bottom + 18});
  text("마지막 측정", {x: now, y: bottom + 34, "text-anchor": "middle"});
  text(axisText(data, xs.at(-1)), {x: right, y: bottom + 18, "text-anchor": "end"});
  const legend = create("p", "forecast-legend");
  for (const [cls, label] of [["history", "측정값"], ["fitted", "모델이 읽은 흐름"], ...(previous ? [["compare", "이전 예측"]] : []), ["line", "예측"], ["band", Math.round(data.model.interval_width * 100) + "% 범위"], ...(data.threshold ? [["threshold", "관리 기준"]] : [])]) {
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
  const scale = create("button", "secondary", showWholeScale ? "측정 변화 중심 보기" : "관리 기준 포함 보기");
  scale.type = "button";scale.addEventListener("click", () => {showWholeScale = !showWholeScale;render(data);});
  const outlook = conditionOutlook(data);
  root.replaceChildren(summary(data), ...chart(data), scale, outlook, note);
  const metricRoot = byId("forecast-detail-metrics");
  if (metricRoot) {
    const check = data.backtest;
    const lines = create("dl", "forecast-summary");
    const row = (term, value) => {const entry = create("div");entry.append(create("dt", null, term), create("dd", null, value));lines.append(entry);};
    row("설정", "추세 민감도 " + data.model.changepoint_prior_scale + " · 변화점 탐색 범위 " + data.model.changepoint_range + " · 학습 " + data.model.points + "개");
    row("예측 시작값과 마지막 실측 차이", value(data.trend.level_gap));
    if (previous) row("이전 설정과 비교", "이전 종료 예상 " + value(previous.trend.end)
      + " → 현재 종료 예상 " + value(data.trend.end));
    if (check) {
      row("과거 검증", "가린 관측 " + check.points + "개 · 평균 절대 오차 " + value(check.mean_absolute_error));
      row("비교 기준", "마지막 관측값 유지 시 평균 절대 오차 " + value(check.naive_mean_absolute_error));
      row(Math.round(data.model.interval_width * 100) + "% 예측 범위 내 실제값 포함", Math.round(check.inside_interval * 100) + "%");
    } else row("과거 검증", "현재 구간에서는 과거 값을 충분히 가려 비교할 수 없습니다.");
    if (Array.isArray(data.rolling_backtests)) {
      row("여러 과거 시점", data.rolling_backtests.length + "개 기준 시점 확인");
      for (const [index, result] of data.rolling_backtests.entries()) {
        row("과거 시점 " + (index + 1), "관측 " + result.points + "개 · 평균 절대 오차 " + value(result.mean_absolute_error)
          + " · 마지막 값 유지 " + value(result.naive_mean_absolute_error)
          + " · 범위 안 " + Math.round(result.inside_interval * 100) + "%");
      }
    }
    metricRoot.replaceChildren(lines);
  }
}

function conditionOutlook(data) {
  const root = create("section", "forecast-outlook");
  root.append(create("h3", null, "설비 상태 전망"));
  root.append(create("p", "muted", "선택한 측정 신호의 변화와 예측을 함께 살펴봅니다. 고장 여부나 실제 잔여수명을 자동으로 판정하지 않습니다."));
  const list = create("dl", "forecast-summary");
  const add = (term, content) => {const row = create("div");row.append(create("dt", null, term), create("dd", null, content));list.append(row);};
  const history = data.history, current = history.at(-1)[1];
  const previous = history[Math.max(0, history.length - Math.max(2, Math.floor(history.length * 0.2)))][1];
  add("최근 관측 변화", value(previous) + " → " + value(current) + (data.unit ? " " + data.unit : ""));
  add("미래 상태", "선택 기간의 예측값 " + value(data.trend.end)
    + " · 예측선 변화 " + value(data.trend.change));
  if (data.threshold) {
    const difference = Math.abs(data.threshold.value - current);
    add("관리 기준까지 현재 거리", value(difference) + (data.unit ? " " + data.unit : ""));
    const threshold = data.threshold;
    const horizonUnit = data.axis === "acquisition" ? "획득 #" : "";
    const result = threshold.state === "expected"
      ? (data.axis === "acquisition" ? "예상 도달까지 약 " + num(Math.max(0, Math.round(threshold.expected_at - history.at(-1)[0]))) + "개 획득"
        : "예상 도달까지 " + duration(Math.max(0, (Date.parse(threshold.expected_at) - Date.parse(history.at(-1)[0])) / 1000)))
      : threshold.state === "already" ? "현재 측정값이 기준에 도달한 상태"
      : threshold.state === "possible" ? "예측 범위 안에서 기준에 닿을 가능성"
      : "선택한 예측 기간 안에서 예상 도달 없음";
    add("기준 도달·잔여 여유", result);
  } else add("기준 도달·잔여 여유", "관리 기준을 입력하면 기준과의 거리와 예상 도달 시점을 확인할 수 있습니다.");
  root.append(list);
  const links = create("p", "forecast-explore-links");
  const addLink = (label, hash) => {
    const url = new URL(location.href);
    url.hash = hash;
    if (hash === "signals") {
      url.searchParams.set("explore_kind", data.kind);
      url.searchParams.set("explore_series", data.series);
    }
    if (hash === "anomaly" && data.kind === "history") url.searchParams.set("forecast_anomaly_series", data.series);
    const link = create("a", null, label);link.href = url.pathname + url.search + url.hash;links.append(link);
  };
  addLink("같은 신호 탐색", "signals");
  if (data.kind === "history") addLink("이상 변화 구간 보기", "anomaly");
  root.append(links);
  return root;
}
