// Operating-condition questions first; exact identifiers live in analysis details.
import {formatTime, kstInputToInstant} from "./time.js";
const byId = (id) => document.getElementById(id);
const node = (tag, text = "", className = "") => {
  const element = document.createElement(tag);
  element.textContent = text;element.className = className;return element;
};
const number = (value, unit = "") => typeof value === "number" && Number.isFinite(value)
  ? value.toLocaleString("ko-KR", {maximumFractionDigits: 2}) + unit : "분석값 없음";
const time = (value) => formatTime(value);
const states = {
  "no-history": "저장된 측정값이 없습니다. 데이터를 연결하고 이력을 불러오세요.",
  "select-source": "서로 다른 데이터 소스가 있습니다. 분석할 소스·측정 지점을 선택하세요.",
  "unsupported-signals": "전압·전류의 R/S/T와 단위가 확인되지 않아 전기 상태를 분석할 수 없습니다. 신호 화면에서 측정 의미를 확인하세요.",
  "ambiguous-phase-roles": "한 측정 지점에 같은 상 역할의 신호가 여러 개 있습니다. 매핑을 확인하세요.",
  "changed-measurement-meaning": "기준과 분석 구간 사이에 측정 의미가 변경됐습니다. 같은 의미의 구간을 선택하세요.",
  "no-usable-target": "결측·충돌·품질 문제로 분석 가능한 관측이 없습니다. 원본 신호와 수집 상태를 확인하세요.",
  "no-target-observations": "선택한 기간에 관측이 없습니다. 분석 종료 시각을 확인하세요.",
  "too-many-sources": "데이터 소스가 조회 범위를 초과합니다. 분석 대상을 좁혀 주세요.",
  "unknown-event-time": "관측 시각을 확인할 수 없습니다.",
};
const metrics = {
  current_mean_a: ["3상 평균 전류", "A"],
  voltage_unbalance_percent: ["전압 불평형", "%"],
  current_unbalance_percent: ["전류 불평형", "%"],
  pattern_score: ["기준 패턴과의 차이", "score"],
};
let assetId = "";
let sequence = 0;
let result = null;
let contexts = [];
const contextKey = (item) => JSON.stringify([item.source_id, item.point_id || null]);

function clearResults() {
  result = null;byId("condition-reference").textContent = "";
  for (const id of ["condition-cards", "condition-insights", "condition-chart", "condition-events", "condition-detail", "condition-method"])
    byId(id).replaceChildren();
}
function comparisonCard(title, target, reference, unit) {
  const card = node("article", "", "condition-card");
  card.append(node("span", title), node("strong", number(target, unit)));
  card.append(node("small", "기준 구간 " + number(reference, unit)));
  return card;
}
function showDetail(point) {
  const root = byId("condition-detail");root.replaceChildren();
  root.append(node("h3", time(point.at) + " · 측정값 확인"));
  for (const [key, [label, unit]] of Object.entries(metrics))
    root.append(node("p", label + ": " + number(point[key], unit === "score" ? "" : " " + unit)));
  for (const [key, unit] of [["voltage_phase_v", "V"], ["current_phase_a", "A"]]) {
    if (Array.isArray(point[key])) root.append(node("p", "R / S / T: " + point[key].map((v) => number(v, " " + unit)).join(" / ")));
  }
  root.append(node("p", "이 시각의 운전 스케줄·부하 변경 여부와 상별 측정값을 확인하세요. 전압이 기준 범위에서 크게 벗어나면 원본 값·계측 단위·센서 상태를 먼저 점검하세요.", "next-check"));
  root.tabIndex = -1;root.focus({preventScroll: true});root.scrollIntoView({block: "nearest"});
}
function drawChart() {
  const root = byId("condition-chart");root.replaceChildren();
  if (!result) return;
  const metric = byId("condition-metric").value;
  const points = result.timeline;
  const values = points.map((point) => point[metric]).filter((value) => typeof value === "number");
  if (!values.length) {root.append(node("p", "이 신호의 평가 가능한 값이 없습니다. 저전류 구간의 불평형은 계산하지 않습니다."));return;}
  const svgNode = (tag) => document.createElementNS("http://www.w3.org/2000/svg", tag);
  const svg = svgNode("svg");svg.setAttribute("viewBox", "0 0 800 210");svg.setAttribute("class", "condition-svg");
  svg.setAttribute("role", "img");svg.setAttribute("aria-label", metrics[metric][0] + "의 관측 시각별 추세. 결측과 시간 공백은 연결하지 않습니다.");
  const threshold = metric === "pattern_score" ? result.pattern.threshold : null;
  const hi = Math.max(...values, ...(typeof threshold === "number" ? [threshold] : []));
  const lo = Math.min(...values);
  const pad = Math.max((hi - lo) * .1, .01);
  const min = Math.max(0, lo - pad), max = hi + pad;
  const start = Date.parse(result.target_start), end = Date.parse(result.target_end);
  const x = (at) => 58 + (Date.parse(at) - start) / (end - start) * 718;
  const y = (value) => 174 - (value - min) / (max - min || 1) * 145;
  const grid = svgNode("path");grid.setAttribute("d", "M58 16V174H776");grid.setAttribute("class", "axis");svg.append(grid);
  let path = "", previous = null;
  const intervals = points.slice(1).map((point, index) => Date.parse(point.at) - Date.parse(points[index].at)).sort((a, b) => a - b);
  const gapLimit = (intervals[Math.floor(intervals.length / 2)] || 60000) * 1.5;
  for (const point of points) {
    const value = point[metric];
    if (typeof value !== "number") {previous = null;continue;}
    const contiguous = previous && Date.parse(point.at) - Date.parse(previous.at) <= gapLimit;
    path += (contiguous ? "L" : "M") + x(point.at).toFixed(2) + " " + y(value).toFixed(2) + " ";
    previous = point;
  }
  const curve = svgNode("path");curve.setAttribute("d", path);curve.setAttribute("class", "condition-curve");svg.append(curve);
  if (typeof threshold === "number") {
    const line = svgNode("path");line.setAttribute("d", `M58 ${y(threshold)}H776`);line.setAttribute("class", "reference-line");svg.append(line);
  }
  for (const [value, labelY] of [[hi, 25], [lo, 172]]) {
    const label = svgNode("text");label.setAttribute("x", "4");label.setAttribute("y", String(labelY));label.textContent = number(value);svg.append(label);
  }
  const from = svgNode("text");from.setAttribute("x", "58");from.setAttribute("y", "202");from.textContent = formatTime(result.target_start, {seconds: false});
  const until = svgNode("text");until.setAttribute("x", "776");until.setAttribute("y", "202");until.setAttribute("text-anchor", "end");until.textContent = formatTime(result.target_end, {seconds: false});
  svg.append(from, until);
  svg.addEventListener("click", (event) => {
    const box = svg.getBoundingClientRect();
    const targetAt = start + (((event.clientX - box.left) / box.width * 800 - 58) / 718) * (end - start);
    const closest = points.reduce((best, point) => Math.abs(Date.parse(point.at) - targetAt) < Math.abs(Date.parse(best.at) - targetAt) ? point : best);
    showDetail(closest);
  });
  root.append(svg, node("p", "원본 측정 시각(KST) · 그래프를 선택하면 그 시각의 값을 확인합니다."
    + (metric === "pattern_score" ? " 점선은 기준 구간 점수의 99% 분위수입니다." : ""), "muted"));
}
function render(data) {
  result = data;
  const baseline = data.reference, observed = data.target, pattern = data.pattern;
  byId("condition-state").className = "state";
  byId("condition-state").textContent = time(data.target_start) + " → " + time(data.target_end) + " · 저장된 관측 분석";
  byId("condition-reference").textContent = "비교 기준: " + time(data.reference_start) + " → " + time(data.reference_end);
  const cards = byId("condition-cards");
  cards.append(comparisonCard("관측 평균 전류", observed.current_mean_a, baseline.current_mean_a, " A"),
    comparisonCard("전류 통전 시간 · 관측 추정", observed.current_above_floor_hours, baseline.current_above_floor_hours, " h"),
    comparisonCard("전압 불평형 · 최고", observed.voltage_unbalance_max_percent, baseline.voltage_unbalance_max_percent, "%"),
    comparisonCard("전류 불평형 · p95", observed.current_unbalance_p95_percent, baseline.current_unbalance_p95_percent, "%"));
  const insights = byId("condition-insights");
  insights.append(node("h3", "기준 구간과 달라진 점"));
  if (typeof observed.current_above_floor_hours === "number" && typeof baseline.current_above_floor_hours === "number") {
    const sameDuration = Date.parse(data.target_end) - Date.parse(data.target_start)
      === Date.parse(data.reference_end) - Date.parse(data.reference_start);
    const difference = observed.current_above_floor_hours - baseline.current_above_floor_hours;
    if (sameDuration) insights.append(node("p", "전류 " + observed.current_floor_a + "A 이상이 관측된 시간이 기준보다 "
      + number(Math.abs(difference), " h") + (difference >= 0 ? " 늘었습니다." : " 줄었습니다.")
      + " 운전 시간이나 부하 스케줄이 달라졌는지 확인하세요."));
    if (!sameDuration) insights.append(node("p", "전류 통전 관측 비율: 기준 "
      + number(typeof baseline.current_above_floor_fraction === "number" ? baseline.current_above_floor_fraction * 100 : null, "%") + " → 분석 구간 "
      + number(typeof observed.current_above_floor_fraction === "number" ? observed.current_above_floor_fraction * 100 : null, "%") + ". 기간 길이가 달라 관측 비율로 비교합니다."));
    insights.append(node("p", "가장 큰 3상 평균 전류는 " + number(observed.current_peak_a, " A") + " · " + time(observed.current_peak_at) + "입니다."));
  }
  if (pattern.state === "scored") {
    insights.append(node("p", "기준 패턴의 99% 점수 범위를 넘은 관측 " + pattern.above_reference_count + "개 / "
      + pattern.scored_samples + "개 (" + number(pattern.above_reference_percent, "%") + ")."));
    if (!pattern.above_reference_count) insights.append(node("p", "이번 구간에서는 기준 점수 범위를 넘는 패턴이 관측되지 않았습니다."));
  } else insights.append(node("p", "패턴 비교에 필요한 기준 데이터가 부족하거나 거의 일정합니다. 기준 기간을 변경하세요."));
  insights.append(node("p", "운전 조건 변화와 함께 보세요.", "muted"));
  const events = byId("condition-events");events.append(node("h3", "먼저 확인할 시각"));
  const notable = pattern.notable?.filter((point) => point.above_reference) || [];
  for (const item of notable) {
    const card = node("article", "", "condition-event");
    const button = node("button", time(item.at) + " · 구간 확인");button.type = "button";
    button.addEventListener("click", () => {byId("condition-metric").value = item.unit === "V" ? "voltage_unbalance_percent" : "current_mean_a";drawChart();showDetail(data.timeline.find((point) => point.at === item.at));});
    card.append(button, node("p", item.channel_id + " " + number(item.value, " " + item.unit)
      + " · 기준 5–95% 범위 " + number(item.reference_p05) + "–" + number(item.reference_p95, " " + item.unit)));
    events.append(card);
  }
  if (!notable.length) {
    events.append(node("p", pattern.state === "scored"
      ? "점수 기준을 넘은 시각은 없습니다. 가장 큰 관측값을 확인할 수 있습니다."
      : "기준 패턴 점수가 없어 이탈 여부를 평가하지 않았습니다. 가장 큰 관측값을 확인할 수 있습니다.", "muted"));
    for (const [label, at] of [["최대 전류 시각", observed.current_peak_at], ["최대 전압 불평형 시각", observed.voltage_unbalance_max_at]]) {
      if (!at) continue;
      const button = node("button", label + " · " + time(at));button.type = "button";
      button.addEventListener("click", () => showDetail(data.timeline.find((point) => point.at === at)));
      events.append(button);
    }
  }
  const methods = byId("condition-method");
  for (const [label, value] of Object.entries({
    "데이터 소스": data.source_id, "측정 지점": data.point_id || "미지정", "마지막 관측": time(data.last_observed_at),
    "관측 수": observed.sample_count, "기준 관측 수": baseline.sample_count,
    "전류 관측 시간": number(observed.current_observed_hours, " h"),
    "저전류로 불평형 미평가": observed.current_low_signal_count,
    "시각 근거": data.time_evidence?.join(" · ") || "입력 관측 시각 사용; 장비 시계의 정확성을 검증하지 않음",
    "센서 품질": data.source_quality === "unknown" ? "원본 기록에 품질 판정 없음" : "관측별 원본 상태 사용",
    "모델": pattern.model || "기준 부족으로 미실행", "학습 표본": pattern.fit_samples || "—",
    "비교 기준": "선택한 앞선 구간만 학습·점수 기준 계산; 정상 구간 확인을 뜻하지 않음",
    "불평형 계산": "상 값 평균에 대한 최대 편차 / 평균 × 100; 전압 50V 미만·전류 1A 미만 제외",
    "제외 사유": JSON.stringify(data.excluded), "저장 시점": data.snapshot_id,
  })) methods.append(node("p", label + ": " + value));
  if (typeof observed.current_mean_a !== "number") byId("condition-metric").value = "voltage_unbalance_percent";
  drawChart();
}
export async function loadCondition(selectedAsset, {reset = false} = {}) {
  const token = ++sequence;
  if (selectedAsset !== assetId || reset) {
    byId("condition-source").value = "";byId("condition-end").value = "";
    byId("condition-reference-start").value = "";byId("condition-reference-end").value = "";
  }
  assetId = selectedAsset;clearResults();
  const state = byId("condition-state"), button = byId("condition-run");
  button.disabled = true;state.className = "state";
  if (!assetId) {state.textContent = "설비를 선택하면 부하·불평형·기준 패턴 변화를 분석합니다.";return;}
  state.textContent = "선택한 설비의 관측값을 분석하고 있습니다.";
  const requestedAsset = assetId;
  const params = new URLSearchParams({asset_id: requestedAsset, period: byId("condition-period").value});
  const context = contexts.find((item) => contextKey(item) === byId("condition-source").value);
  if (byId("condition-source").value && context) {params.set("source_id", context.source_id);params.set("point_id", context.point_id || "");}
  const end = byId("condition-end").value;
  const start = byId("condition-reference-start").value, until = byId("condition-reference-end").value;
  if (Boolean(start) !== Boolean(until)) {state.textContent = "기준 기간의 시작과 종료를 모두 입력하세요.";button.disabled = false;return;}
  try {
    // The inputs are KST wall-clock times; send the same instant with its explicit offset.
    if (end) params.set("end_at", kstInputToInstant(end));
    if (start) {params.set("reference_start", kstInputToInstant(start));params.set("reference_end", kstInputToInstant(until));}
  } catch {state.className = "state error";state.textContent = "분석·기준 시각 형식을 확인하세요. 시각은 KST입니다.";button.disabled = false;return;}
  try {
    const response = await fetch("/api/v1/condition?" + params, {cache: "no-store"});
    const data = await response.json();
    if (token !== sequence) return;
    if (!response.ok || data.schema_version !== 1) throw new Error(response.status === 400 ? "invalid-period" : "read-failed");
    if (data.asset_id !== requestedAsset || data.meaning !== "measured-operating-change-and-reference-pattern-not-fault-diagnosis"
        || (data.state === "analyzed" && context && (data.source_id !== context.source_id
          || (data.point_id || null) !== (context.point_id || null)))) throw new Error("context-mismatch");
    const previous = byId("condition-source").value;
    contexts = data.sources || [];
    byId("condition-source").replaceChildren(node("option", "데이터 소스 선택"));
    byId("condition-source").firstChild.value = "";
    contexts.forEach((item) => {const option = node("option", item.source_id + " / " + (item.point_id || "미지정"));option.value = contextKey(item);byId("condition-source").append(option);});
    // Preserve source/point identity even when newly discovered sources change list order.
    byId("condition-source").value = previous;
    byId("condition-source-field").hidden = contexts.length <= 1;
    if (data.state !== "analyzed") {state.className = "state error";state.textContent = states[data.state] || "분석 가능한 관측이 없습니다.";return;}
    render(data);
  } catch (error) {
    if (token !== sequence) return;
    clearResults();state.className = "state error";
    state.textContent = error.message === "context-mismatch" ? "선택한 설비·데이터 소스와 분석 응답이 일치하지 않습니다. 다시 불러오세요."
      : error.message === "invalid-period" ? "분석 기간과 그보다 앞선 기준 기간을 확인하세요. 시각은 KST입니다."
      : "분석 데이터를 읽지 못했습니다. 이전 결과는 표시하지 않습니다. 고주파 데이터는 분석 기간을 줄이고 다시 시도하세요.";
  } finally {if (token === sequence) button.disabled = false;}
}
export function initializeCondition() {
  for (const id of ["condition-run", "condition-period", "condition-source"]) {
    byId(id).addEventListener(id === "condition-run" ? "click" : "change", () => loadCondition(assetId));
  }
  byId("condition-metric").addEventListener("change", drawChart);
}
