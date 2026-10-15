// Departures from a chosen baseline in stored measurements, for assets with or without a model.
// The server scores each signal against the baseline part of its own record; this view draws the
// combined score, lists the furthest departures and opens a period comparison for each.
import { currentAsset, onAssetChange } from "./asset-context.js";
import { navigate } from "./navigation.js";
import { formatTime } from "./time.js";
import { byId, clear, create, num } from "./web-utils.js";

const MAX_SERIES = 6;
const BASELINES = [["first-30", "기록 처음 30%"], ["first-50", "기록 처음 50%"], ["all", "기록 전체"]];
const svgNode = (name, attributes = {}) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
};
let request = 0, loadedFor = "", shown = null;

async function getJson(url) {
  const response = await fetch(url, {cache: "no-store", credentials: "same-origin"});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(body.error || "read_failed"), {status: response.status});
  return body;
}
const time = (iso) => formatTime(iso, {seconds: false});

export function initializeAnomalyExplore() {
  onAssetChange(() => {loadedFor = "";if (document.body.dataset.view === "anomaly") void load();});
  window.addEventListener("hashchange", () => {if (document.body.dataset.view === "anomaly" && loadedFor !== currentAsset()) void load();});
  window.addEventListener("resize", () => {if (shown && document.body.dataset.view === "anomaly") draw(shown);});
  if (document.body.dataset.view === "anomaly") void load();
}

// Only assets with stored history get the section; a connected model keeps it folded.
async function load() {
  const root = byId("anomaly-explore"), asset = currentAsset(), ticket = ++request;
  loadedFor = asset;shown = null;clear(root);root.hidden = true;
  if (!asset) return;
  let capabilities;
  try {capabilities = await getJson("/api/v1/explore/capabilities?asset_id=" + encodeURIComponent(asset));} catch {return;}
  if (ticket !== request || asset !== currentAsset() || !capabilities.data.history) return;
  const anomaly = capabilities.capabilities.find((item) => item.id === "anomaly");
  const modelled = anomaly && ["connected", "waiting-results"].includes(anomaly.reason);
  const box = create(modelled ? "details" : "div", "anomaly-explore-box");
  const title = "평소 범위를 벗어난 구간 (모델 없이)";
  if (modelled) box.append(create("summary", null, title));else box.append(create("h3", null, title));
  box.append(create("p", "muted", "고른 신호를 기록의 기준 구간과 비교해 크게 벗어난 시점을 찾습니다. 기준 구간은 비교의 출발점일 뿐 정상 상태라는 뜻은 아니며, 고장 판정이 아닙니다."));
  const controls = create("div", "anomaly-explore-controls"), output = create("div", "anomaly-explore-output");
  box.append(controls, output);root.append(box);root.hidden = false;
  await run(controls, output, null);
}

async function run(controls, output, choice) {
  const asset = currentAsset(), ticket = ++request;
  const query = new URLSearchParams({asset_id: asset, baseline: choice?.baseline || "first-30"});
  for (const key of choice?.series || []) query.append("series", key);
  output.replaceChildren(create("p", "muted", "기준 구간과 비교합니다."));
  let data;
  try {data = await getJson("/api/v1/explore/anomaly?" + query.toString());}
  catch {if (ticket === request) output.replaceChildren(create("p", "muted", "저장된 측정을 비교하지 못했습니다."));return;}
  if (ticket !== request || asset !== currentAsset()) return;
  renderControls(controls, output, data);
  shown = {output, data};
  draw(shown);
}

function renderControls(controls, output, data) {
  clear(controls);
  const fieldset = create("fieldset", "channel-fieldset");fieldset.append(create("legend", null, "신호 (최대 " + MAX_SERIES + "개)"));
  const choices = create("div", "choices");
  for (const key of data.available) {
    const label = create("label", "choice"), input = create("input");input.type = "checkbox";input.value = key;
    input.checked = data.series.includes(key);label.append(input, document.createTextNode(key));choices.append(label);
  }
  const limit = () => {
    const checked = [...choices.querySelectorAll("input:checked")];
    for (const input of choices.querySelectorAll("input")) input.disabled = !input.checked && checked.length >= MAX_SERIES;
  };
  choices.addEventListener("change", limit);limit();
  // A long signal list folds behind its selection so the result stays in view.
  if (data.available.length > 8) {
    const fold = create("details", "anomaly-explore-fold");
    const summary = create("summary", null, "신호 선택 · " + data.series.join(", "));
    fold.append(summary, choices);fieldset.append(fold);
  } else fieldset.append(choices);
  const baseline = create("select");baseline.setAttribute("aria-label", "기준 구간");
  for (const [value, label] of BASELINES) baseline.append(Object.assign(create("option", null, label), {value}));
  baseline.value = data.baseline.name;
  const field = create("label", null, "기준 구간");field.append(baseline);
  const apply = create("button", "secondary", "다시 비교");apply.type = "button";
  apply.addEventListener("click", () => {
    const series = [...choices.querySelectorAll("input:checked")].map((input) => input.value);
    if (series.length) void run(controls, output, {series, baseline: baseline.value});
  });
  controls.append(fieldset, field, apply);
}

function draw({output, data}) {
  const intervals = data.intervals, unit = (key) => data.units[key] ? " " + data.units[key] : "";
  const parts = [];
  const top = intervals[0];
  parts.push(create("p", "anomaly-explore-summary", data.interval_count
    ? "기준에서 크게 벗어난 구간 " + num(data.interval_count) + "개 · 가장 크게 벗어난 곳: " + top.channel + " " + time(top.start)
      + " · 기준 중앙값 " + num(top.median) + unit(top.channel) + " → " + num(top.value) + unit(top.channel)
    : "기준 구간에서 크게 벗어난 값이 없습니다."));
  parts.push(chart(data));
  if (intervals.length) {
    const list = create("ol", "anomaly-explore-list");
    for (const item of intervals.slice(0, 10)) {
      const row = create("li");
      const where = time(item.start) + (item.end !== item.start ? " ~ " + formatTime(item.end, {seconds: false, zone: false}).slice(11) : "");
      row.append(create("span", "anomaly-explore-when", where),
        create("span", null, item.channel + " " + (item.direction === "up" ? "위로" : "아래로") + " · " + num(item.median) + " → " + num(item.value) + unit(item.channel)
          + " · 벗어남 " + num(Math.round(item.distance * 10) / 10) + (item.channels.length > 1 ? " · 함께: " + item.channels.filter((key) => key !== item.channel).join(", ") : "")));
      const compare = create("button", "capability-open", "구간 비교");compare.type = "button";
      compare.setAttribute("aria-label", where + " 구간 비교");
      compare.addEventListener("click", () => openComparison(data, item));
      row.append(compare);list.append(row);
    }
    parts.push(list);
    if (data.interval_count > 10) parts.push(create("p", "muted", "가장 크게 벗어난 10개만 보여줍니다 · 나머지 " + num(data.interval_count - 10) + "개는 그래프에 표시"));
  }
  const skipped = data.channels.filter((item) => item.state !== "scored");
  parts.push(create("p", "muted", "벗어남은 기준 구간 중앙값과의 차이를 기준 구간의 흔한 변동 폭(MAD)으로 나눈 값이며 " + data.threshold + " 이상을 표시합니다 · 기준 구간 "
    + time(data.baseline.from) + " ~ " + formatTime(data.baseline.to, {seconds: false, zone: false}).slice(11)
    + (data.bucket_seconds > 1 ? " · 값은 약 " + num(Math.round(data.bucket_seconds)) + "초 구간 평균" : "")
    + (skipped.length ? " · 비교하지 못한 신호: " + skipped.map((item) => item.key + (item.state === "constant" ? "(값이 일정)" : "(기준 구간 기록 부족)")).join(", ") : "")));
  output.replaceChildren(...parts);
}

function chart(data) {
  const width = Math.max(320, Math.round(byId("anomaly-explore").clientWidth || 900));
  const height = 170, left = 40, right = width - 10, top = 10, bottom = height - 28;
  const points = data.score.map(([at, value]) => [Date.parse(at), value]);
  const svg = svgNode("svg", {viewBox: `0 0 ${width} ${height}`, class: "anomaly-explore-chart", role: "img", "aria-label": "기준에서 벗어난 정도의 시간 흐름"});
  if (!points.length) return svg;
  const x0 = points[0][0], x1 = points.at(-1)[0] || x0 + 1;
  // A few huge departures must not flatten the rest: the scale stops near the 98th percentile and
  // taller marks sit on the top edge.
  const sorted = points.map((p) => p[1]).sort((a, b) => a - b);
  const ymax = Math.max(data.threshold * 3, sorted[Math.floor(0.98 * (sorted.length - 1))] * 1.1);
  const X = (x) => left + (x - x0) / (x1 - x0 || 1) * (right - left), Y = (y) => bottom - Math.min(y, ymax) / ymax * (bottom - top);
  const baseEnd = Date.parse(data.baseline.to);
  svg.append(svgNode("rect", {x: left, y: top, width: Math.max(0, X(Math.min(baseEnd, x1)) - left), height: bottom - top, class: "anomaly-explore-baseline"}));
  svg.append(svgNode("path", {d: `M${left} ${top} V${bottom} H${right}`, class: "axis"}));
  svg.append(svgNode("path", {d: points.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" "), class: "anomaly-explore-line"}));
  svg.append(svgNode("line", {x1: left, x2: right, y1: Y(data.threshold), y2: Y(data.threshold), class: "anomaly-explore-threshold"}));
  for (const [x, y] of points) if (y >= data.threshold) svg.append(svgNode("circle", {cx: X(x).toFixed(1), cy: Y(y).toFixed(1), r: 2.6, class: "anomaly-explore-mark"}));
  const text = (content, attributes) => {const node = svgNode("text", {class: "explore-axis-label", ...attributes});node.textContent = content;svg.append(node);};
  text(String(data.threshold), {x: left - 4, y: Y(data.threshold) + 4, "text-anchor": "end"});
  text(time(data.score[0][0]), {x: left, y: bottom + 18});
  text(time(data.score.at(-1)[0]), {x: right, y: bottom + 18, "text-anchor": "end"});
  return svg;
}

// Compare the baseline with the departure, widened so the period holds a few values.
function openComparison(data, item) {
  const start = Date.parse(item.start), end = Date.parse(item.end);
  const pad = Math.max(0, (10 * data.bucket_seconds * 1000 - (end - start)) / 2);
  const b = [new Date(start - pad).toISOString(), new Date(end + pad).toISOString()];
  navigate("#signals", byId("explore-title"));
  document.dispatchEvent(new CustomEvent("explore-request", {detail: {
    kind: "history", series: [...new Set([item.channel, ...data.series])].slice(0, MAX_SERIES).join(","),
    a: data.baseline.from + "~" + data.baseline.to, b: b[0] + "~" + b[1],
  }}));
}
