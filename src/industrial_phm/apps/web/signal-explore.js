// Period comparison for the selected asset: two periods of stored measurements (or two
// acquisition ranges) compared by exact statistics, data quality and distribution. Period A is
// what the user compares against, not a verified normal baseline.
import { currentAsset, onAssetChange } from "./asset-context.js";
import { formatTime, kstInputToInstant } from "./time.js";
import { byId, clear, create, num } from "./web-utils.js";

const MAX_SERIES = 6;
const KIND_LABEL = {history: "측정 이력", acquisition: "획득별 특징"};
const svgNode = (name, attributes = {}) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
};
let sources = null, kind = null, loadedKey = "", request = 0;

async function getJson(url) {
  const response = await fetch(url, {cache: "no-store", credentials: "same-origin"});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(body.error || "read_failed"), {status: response.status});
  return body;
}
const state = (text, error = false) => {const node = byId("explore-state");node.textContent = text;node.className = error ? "state error" : "state";};
const toInput = (iso) => formatTime(iso, {zone: false}).replace(" ", "T");
const params = () => new URL(location.href).searchParams;
const viewKey = () => [currentAsset(), ...["explore_kind", "explore_series", "explore_a", "explore_b"].map((k) => params().get(k) || "")].join("|");

export function initializeSignalExplore() {
  onAssetChange(() => {loadedKey = "";if (document.body.dataset.view === "signals") void load();});
  window.addEventListener("hashchange", () => {if (document.body.dataset.view === "signals" && loadedKey !== viewKey()) void load();});
  if (document.body.dataset.view === "signals") void load();
}

async function load() {
  const asset = currentAsset();
  loadedKey = viewKey();
  for (const id of ["explore-controls", "explore-quality", "explore-results"]) clear(byId(id));
  if (!asset) {state("설비를 선택하세요.");return;}
  state("비교할 수 있는 측정을 확인합니다.");
  try {sources = await getJson("/api/v1/explore/sources?asset_id=" + encodeURIComponent(asset));}
  catch {state("비교할 측정 목록을 읽지 못했습니다.", true);return;}
  if (asset !== currentAsset()) return;
  const kinds = ["history", "acquisition"].filter((name) => sources[name]);
  if (!kinds.length) {state("이 설비에는 비교할 저장 측정이 없습니다. 측정 이력을 저장하거나 모델을 연결하면 여기서 비교할 수 있습니다.");return;}
  kind = kinds.includes(params().get("explore_kind")) ? params().get("explore_kind") : kinds[0];
  renderControls(kinds);
  await compare();
}

function seriesChoices() {
  if (kind === "history") return sources.history.channels.map((name) => ({key: name, label: name}));
  return sources.acquisition.features;
}

function defaultSeries(choices) {
  const wanted = (params().get("explore_series") || "").split(",").filter((key) => choices.some((c) => c.key === key));
  if (wanted.length) return wanted.slice(0, MAX_SERIES);
  if (kind === "acquisition") {
    const rms = choices.filter((c) => /\.rms$/.test(c.key)).map((c) => c.key);
    return (rms.length ? rms : choices.map((c) => c.key)).slice(0, 3);
  }
  return choices.slice(0, 3).map((c) => c.key);
}

// Default periods: the first and second half of what is stored; a link can name others.
function defaultPeriods() {
  const parse = (value) => (value || "").split("~");
  const [aFrom, aTo] = parse(params().get("explore_a")), [bFrom, bTo] = parse(params().get("explore_b"));
  if (kind === "acquisition") {
    const {first, last} = sources.acquisition;
    const middle = Math.floor((first + last) / 2);
    return {a: [aFrom || first, aTo || middle], b: [bFrom || middle + 1, bTo || last]};
  }
  const start = Date.parse(sources.history.start_at), end = Date.parse(sources.history.end_at) + 1000;
  const middle = new Date((start + end) / 2).toISOString();
  return {
    a: [aFrom || sources.history.start_at, aTo || middle],
    b: [bFrom || middle, bTo || new Date(end).toISOString()],
  };
}

function renderControls(kinds) {
  const root = byId("explore-controls");clear(root);
  if (kinds.length > 1) {
    const field = create("label", null, "비교할 측정");
    const select = create("select");select.id = "explore-kind";
    for (const name of kinds) select.append(Object.assign(create("option", null, KIND_LABEL[name]), {value: name}));
    select.value = kind;
    select.addEventListener("change", () => {kind = select.value;renderControls(kinds);void compare();});
    field.append(select);root.append(field);
  }
  const choices = seriesChoices();
  const chosen = defaultSeries(choices);
  const fieldset = create("fieldset", "channel-fieldset");fieldset.id = "explore-series";
  fieldset.append(create("legend", null, "비교할 " + (kind === "history" ? "신호" : "특징") + " (최대 " + MAX_SERIES + "개)"));
  const list = create("div", "choices");
  for (const choice of choices) {
    const item = create("label", "choice");
    const box = Object.assign(create("input"), {type: "checkbox", value: choice.key, checked: chosen.includes(choice.key)});
    box.addEventListener("change", () => {
      const checked = [...fieldset.querySelectorAll("input:checked")];
      for (const other of fieldset.querySelectorAll("input")) other.disabled = !other.checked && checked.length >= MAX_SERIES;
    });
    item.append(box, document.createTextNode(choice.label));list.append(item);
  }
  // A long signal list stays folded; what is chosen is named on the fold.
  if (choices.length > 8) {
    const fold = create("details", "explore-series-fold");
    const summary = create("summary");
    const count = () => {summary.textContent = "고른 항목 " + fieldset.querySelectorAll("input:checked").length + "개 · 전체 " + choices.length + "개 중에서 고르기";};
    fold.append(summary, list);fieldset.append(fold);count();
    list.addEventListener("change", count);
  } else fieldset.append(list);
  root.append(fieldset);
  fieldset.querySelector("input")?.dispatchEvent(new Event("change"));
  const periods = defaultPeriods();
  const grid = create("div", "explore-periods");
  for (const name of ["a", "b"]) {
    const group = create("fieldset", "explore-period");
    group.append(create("legend", null, name === "a" ? "구간 A · 비교 기준으로 고른 구간" : "구간 B · 살펴볼 구간"));
    for (const [index, edge] of [[0, "부터"], [1, "까지"]]) {
      const label = create("label", null, (kind === "history" ? "KST " : "획득 #") + edge);
      const input = create("input");input.id = "explore-" + name + "-" + index;
      if (kind === "history") {input.type = "datetime-local";input.step = "1";input.value = toInput(periods[name][index]);}
      else {Object.assign(input, {type: "number", min: sources.acquisition.first, max: sources.acquisition.last, value: periods[name][index]});}
      label.append(input);group.append(label);
    }
    grid.append(group);
  }
  root.append(grid);
  const presets = create("div", "explore-presets");
  const preset = (text, split) => {
    const button = create("button", "secondary", text);button.type = "button";
    button.addEventListener("click", () => {setPeriods(split);void compare();});
    presets.append(button);
  };
  preset("앞 절반 · 뒤 절반", [0, 0.5, 0.5, 1]);
  preset("처음 1/4 · 마지막 1/4", [0, 0.25, 0.75, 1]);
  const run = create("button", null, "구간 비교");run.type = "button";run.id = "explore-run";
  run.addEventListener("click", () => void compare());
  presets.append(run);
  root.append(presets);
}

function setPeriods([a0, a1, b0, b1]) {
  if (kind === "acquisition") {
    const {first, last} = sources.acquisition, span = last - first;
    const at = (share) => Math.round(first + span * share);
    const values = [at(a0), Math.max(at(a0), at(a1) - (a1 === b0 ? 1 : 0)), at(b0), at(b1)];
    ["a-0", "a-1", "b-0", "b-1"].forEach((id, index) => {byId("explore-" + id).value = values[index];});
    return;
  }
  const start = Date.parse(sources.history.start_at), end = Date.parse(sources.history.end_at) + 1000;
  const at = (share) => toInput(new Date(start + (end - start) * share).toISOString());
  ["a-0", "a-1", "b-0", "b-1"].forEach((id, index) => {byId("explore-" + id).value = at([a0, a1, b0, b1][index]);});
}

async function compare() {
  const asset = currentAsset();
  const series = [...byId("explore-series").querySelectorAll("input:checked")].map((input) => input.value);
  if (!series.length) {state("비교할 항목을 하나 이상 고르세요.", true);return;}
  const values = {};
  try {
    for (const id of ["a-0", "a-1", "b-0", "b-1"]) {
      const raw = byId("explore-" + id).value;
      values[id] = kind === "history" ? kstInputToInstant(raw) : String(Math.trunc(Number(raw)));
      if (kind === "acquisition" && !/^\d+$/.test(values[id])) throw new Error("bad");
    }
  } catch {state("구간의 시작과 끝을 확인하세요.", true);return;}
  const query = new URLSearchParams({asset_id: asset, kind, a_from: values["a-0"], a_to: values["a-1"], b_from: values["b-0"], b_to: values["b-1"]});
  for (const key of series) query.append("series", key);
  const url = new URL(location.href);
  url.searchParams.set("explore_kind", kind);url.searchParams.set("explore_series", series.join(","));
  url.searchParams.set("explore_a", values["a-0"] + "~" + values["a-1"]);url.searchParams.set("explore_b", values["b-0"] + "~" + values["b-1"]);
  history.replaceState(history.state, "", url);loadedKey = viewKey();
  const ticket = ++request;
  state("두 구간의 저장 측정을 계산합니다.");
  try {
    const data = await getJson("/api/v1/explore/profile?" + query.toString());
    if (ticket !== request || asset !== currentAsset()) return;
    render(data);
  } catch (error) {
    if (ticket !== request) return;
    clear(byId("explore-quality"));clear(byId("explore-results"));
    state(error.status === 400 ? "구간을 확인하세요. 각 구간은 시작이 끝보다 앞서야 하고 31일을 넘을 수 없습니다." : "구간 비교를 계산하지 못했습니다.", true);
  }
}

const rangeText = (data, name) => kind === "history"
  ? formatTime(data.periods[name].from, {seconds: false}) + " ~ " + formatTime(data.periods[name].to, {seconds: false, zone: false})
  : "#" + data.periods[name].from + "–#" + data.periods[name].to;
const duration = (seconds) => seconds === null || seconds === undefined ? "—"
  : seconds >= 3600 ? num(seconds / 3600) + "시간" : seconds >= 60 ? num(seconds / 60) + "분" : num(seconds) + "초";
const percent = (value) => typeof value === "number" ? (value > 0 ? "+" : "") + value.toLocaleString("ko-KR", {maximumFractionDigits: 1}) + "%" : "—";

function render(data) {
  const quality = byId("explore-quality"), results = byId("explore-results");
  clear(quality);clear(results);
  if (!data.series.length) {state("선택한 구간에 저장된 측정이 없습니다.");return;}
  state(KIND_LABEL[data.kind] + " · 구간 A " + rangeText(data, "a") + " · 구간 B " + rangeText(data, "b"));
  for (const name of ["a", "b"]) quality.append(qualityCard(data, name));
  for (const item of data.series) results.append(seriesCard(item));
  const links = modelLinks(data);
  if (links) results.append(links);
  results.append(relationSection(data));
  if (data.kind === "acquisition") results.append(spectrumSection(data));
}

const periodQuery = (data) => ({a_from: String(data.periods.a.from), a_to: String(data.periods.a.to),
  b_from: String(data.periods.b.from), b_to: String(data.periods.b.to)});

// How two measured series moved together in each period, from paired observations only.
function relationSection(data) {
  const box = create("section", "explore-relation");
  box.append(create("h3", null, "두 항목의 관계"));
  const choices = data.series.map((item) => ({key: item.key, label: item.label}));
  if (choices.length < 2) {
    box.append(create("p", "muted", "관계를 보려면 위에서 항목을 두 개 이상 고르세요."));
    return box;
  }
  const controls = create("div", "explore-relation-controls");
  const pick = (name, index) => {
    const label = create("label", null, name);
    const select = create("select");
    for (const choice of choices) select.append(Object.assign(create("option", null, choice.label), {value: choice.key}));
    select.value = choices[index].key;label.append(select);controls.append(label);
    return select;
  };
  const x = pick("가로축", 0), y = pick("세로축", 1);
  const output = create("div");
  const draw = async () => {
    if (x.value === y.value) {output.replaceChildren(create("p", "muted", "서로 다른 두 항목을 고르세요."));return;}
    output.replaceChildren(create("p", "muted", "짝지은 관측을 계산합니다."));
    const query = new URLSearchParams({asset_id: currentAsset(), kind: data.kind, x: x.value, y: y.value, ...periodQuery(data)});
    try {
      const relation = await getJson("/api/v1/explore/relation?" + query.toString());
      output.replaceChildren(...relationView(relation, choices));
    } catch {output.replaceChildren(create("p", "muted", "관계를 계산하지 못했습니다."));}
  };
  x.addEventListener("change", draw);y.addEventListener("change", draw);
  box.append(controls, output);
  void draw();
  return box;
}

function relationView(relation, choices) {
  const name = (key) => choices.find((choice) => choice.key === key)?.label || key;
  const groups = relation.groups.filter((group) => group.pair_count > 0);
  if (!groups.length) return [create("p", "muted", "두 항목이 같은 시각에 함께 기록된 관측이 없습니다.")];
  const all = groups.flatMap((group) => group.points);
  const xs = all.map((point) => point[1]), ys = all.map((point) => point[2]);
  const bounds = (values) => {const low = Math.min(...values), high = Math.max(...values);return high > low ? [low, high] : [low - 1, high + 1];};
  const [x0, x1] = bounds(xs), [y0, y1] = bounds(ys);
  const svg = svgNode("svg", {viewBox: "0 0 420 260", class: "explore-scatter", role: "img",
    "aria-label": name(relation.x) + "와 " + name(relation.y) + "의 짝지은 관측 산점도"});
  svg.append(svgNode("path", {d: "M40 10 V224 H410", class: "axis"}));
  for (const group of groups) {
    for (const [, vx, vy] of group.points) {
      svg.append(svgNode("circle", {cx: 40 + (vx - x0) / (x1 - x0) * 370, cy: 224 - (vy - y0) / (y1 - y0) * 214, r: 2.6,
        class: "explore-dot-" + group.period}));
    }
  }
  const text = (content, attributes) => {const node = svgNode("text", attributes);node.textContent = content;svg.append(node);};
  text(num(x0), {x: 40, y: 240, class: "explore-axis-label"});text(num(x1), {x: 410, y: 240, "text-anchor": "end", class: "explore-axis-label"});
  text(num(y1), {x: 36, y: 16, "text-anchor": "end", class: "explore-axis-label"});text(num(y0), {x: 36, y: 224, "text-anchor": "end", class: "explore-axis-label"});
  text(name(relation.x), {x: 225, y: 256, "text-anchor": "middle", class: "explore-axis-label"});
  const table = create("table", "phm-table explore-table");
  const head = create("tr");for (const title of ["", "짝지은 관측", "Pearson", "Spearman"]) head.append(create("th", null, title));table.append(head);
  const r = (value) => typeof value === "number" ? value.toLocaleString("ko-KR", {maximumFractionDigits: 2}) : "—";
  for (const group of relation.groups) {
    const row = create("tr");
    row.append(create("th", null, "구간 " + group.period.toUpperCase() + (relation.groups.length > 2 ? " · " + group.source_id : "")),
      create("td", null, num(group.pair_count) + " / " + num(Math.max(group.x_usable_count, group.y_usable_count))),
      create("td", null, r(group.pearson)), create("td", null, r(group.spearman)));
    table.append(row);
  }
  const how = relation.pairing === "same-acquisition" ? "같은 획득의 두 특징을 짝지었습니다." : "같은 출처·측정 지점·시각의 관측만 짝지었습니다.";
  return [svg, create("p", "muted", "세로축 " + name(relation.y) + " · 회색 구간 A, 청록 구간 B"), table,
    create("p", "muted", how + " 상관은 함께 움직인 정도이며 원인을 뜻하지 않습니다.")];
}

// Where vibration energy sits and how it moved, from verified raw waveforms of both ranges.
function spectrumSection(data) {
  const box = create("section", "explore-spectrum");
  box.append(create("h3", null, "진동 주파수 성분"));
  const output = create("div");output.append(create("p", "muted", "원본 파형으로 주파수 성분을 계산합니다."));
  box.append(output);
  const query = new URLSearchParams({asset_id: currentAsset(), ...periodQuery(data)});
  getJson("/api/v1/explore/spectrum?" + query.toString()).then((spectrum) => {
    output.replaceChildren();
    const channel = create("select");channel.setAttribute("aria-label", "주파수 채널");
    spectrum.channels.forEach((item, index) => channel.append(Object.assign(create("option", null, item.label), {value: String(index)})));
    const view = create("div");
    const show = () => view.replaceChildren(...spectrumView(spectrum, spectrum.channels[Number(channel.value)]));
    channel.addEventListener("change", show);
    const field = create("label", null, "채널");field.append(channel);
    output.append(field, view);show();
    output.append(create("p", "muted", "Welch PSD · " + num(spectrum.segment) + "점 구간 · 샘플링 " + num(spectrum.sampling_rate_hz / 1000) + " kHz · 구간 A 획득 "
      + spectrum.acquisitions.a.map((n) => "#" + n).join(" ") + " / 구간 B 획득 " + spectrum.acquisitions.b.map((n) => "#" + n).join(" ") + " 평균"));
  }).catch(() => output.replaceChildren(create("p", "muted", "원본 파형을 읽지 못해 주파수 성분을 계산하지 못했습니다.")));
  return box;
}

function spectrumView(spectrum, channel) {
  const width = 900, height = 220, left = 46, right = 890, top = 10, bottom = 190;
  const svg = svgNode("svg", {viewBox: "0 0 " + width + " " + height, class: "explore-spectrum-chart", role: "img",
    "aria-label": channel.label + " 구간 A와 B의 주파수 성분"});
  const values = [...channel.a, ...channel.b].filter((value) => value > 0);
  const low = Math.log10(Math.min(...values)), high = Math.log10(Math.max(...values));
  const topHz = spectrum.frequencies.at(-1);
  const x = (hz) => left + hz / topHz * (right - left);
  const y = (value) => value > 0 ? bottom - (Math.log10(value) - low) / (high - low || 1) * (bottom - top) : bottom;
  svg.append(svgNode("path", {d: "M" + left + " " + top + " V" + bottom + " H" + right, class: "axis"}));
  for (const name of ["a", "b"]) {
    const path = channel[name].map((value, index) => (index ? "L" : "M") + x(spectrum.frequencies[index]).toFixed(1) + " " + y(value).toFixed(1)).join(" ");
    svg.append(svgNode("path", {d: path, class: "explore-psd-" + name}));
  }
  [0, 0.25, 0.5, 0.75, 1].forEach((share, index, all) => {
    const anchor = index === 0 ? "start" : index === all.length - 1 ? "end" : "middle";
    const label = svgNode("text", {x: x(topHz * share), y: 206, "text-anchor": anchor, class: "explore-axis-label"});
    label.textContent = (topHz * share / 1000).toLocaleString("ko-KR", {maximumFractionDigits: 1}) + " kHz";svg.append(label);
  });
  const list = create("ul", "explore-band-changes");
  for (const band of channel.band_changes) {
    const khz = (hz) => (hz / 1000).toLocaleString("ko-KR", {maximumFractionDigits: 1});
    list.append(create("li", null, khz(band.from_hz) + "–" + khz(band.to_hz) + " kHz · 구간 B가 A보다 "
      + (band.change_db > 0 ? "+" : "") + band.change_db.toLocaleString("ko-KR", {maximumFractionDigits: 1}) + " dB"));
  }
  return [svg, create("p", "muted", "로그 세로축 · 회색 구간 A, 청록 구간 B · 크게 달라진 대역"), list];
}

// What the data itself says before any value: how much was recorded, missing or unusable.
function qualityCard(data, name) {
  const card = create("div", "explore-quality-card");
  card.append(create("strong", null, "구간 " + name.toUpperCase() + " 데이터 상태"), create("small", null, rangeText(data, name)));
  const periods = data.series.map((item) => item.periods[name] || {});
  const sum = (key) => periods.reduce((total, item) => total + (item[key] || 0), 0);
  const lines = data.kind === "history"
    ? [["측정 기록", sum("observation_count")], ["사용 가능", sum("usable_count")], ["값 없음", sum("missing_count")],
      ["원본 품질 문제", sum("non_good_count")], ["같은 시각 충돌", sum("conflict_count")],
      ["가장 긴 공백", duration(Math.max(...periods.map((item) => item.largest_gap?.seconds || 0)) || null)],
      ["평소 간격의 3배를 넘는 공백", sum("long_gap_count")]]
    : [["전달된 획득", Math.max(...periods.map((item) => item.observation_count || 0))],
      ["특징이 있는 획득", Math.max(...periods.map((item) => item.usable_count || 0))],
      ["빠진 획득 번호", Math.max(...periods.map((item) => item.missing_count || 0))],
      ["분석되지 않은 획득", Math.max(...periods.map((item) => item.unanalyzed_count || 0))]];
  const list = create("dl");
  for (const [term, value] of lines) list.append(create("dt", null, term), create("dd", null, typeof value === "number" ? num(value) : value));
  card.append(list);
  return card;
}

function seriesCard(item) {
  const card = create("article", "explore-series");
  const a = item.periods.a || {}, b = item.periods.b || {};
  const title = create("h3", null, item.label + (item.unit ? " · " + item.unit : ""));
  const source = create("p", "muted", item.source_id + (item.measurement_point_id ? " · " + item.measurement_point_id : ""));
  card.append(title, source);
  const change = item.comparison || {};
  if (a.quantiles && b.quantiles) {
    const lead = create("p", "explore-lead");
    lead.append(create("span", null, "중앙값 " + num(a.quantiles[2]) + " → " + num(b.quantiles[2])),
      create("strong", null, " " + percent(change.median_change_percent)));
    if (typeof change.b_outside_a_band_percent === "number") {
      lead.append(create("span", null, " · B 값의 " + change.b_outside_a_band_percent.toLocaleString("ko-KR", {maximumFractionDigits: 0}) + "%가 A의 5–95% 범위 밖"));
    }
    card.append(lead);
    card.append(chart(item));
  } else {
    card.append(create("p", "empty", !a.quantiles && !b.quantiles ? "두 구간 모두 사용할 수 있는 값이 없습니다." : (a.quantiles ? "구간 B" : "구간 A") + "에 사용할 수 있는 값이 없습니다."));
  }
  const table = create("table", "phm-table explore-table");
  const head = create("tr");for (const text of ["", "구간 A", "구간 B"]) head.append(create("th", null, text));table.append(head);
  const row = (name, read) => {const tr = create("tr");tr.append(create("th", null, name), create("td", null, read(a)), create("td", null, read(b)));table.append(tr);};
  const q = (index) => (p) => p.quantiles ? num(p.quantiles[index]) : "—";
  row("중앙값", q(2));
  row("25–75%", (p) => p.quantiles ? num(p.quantiles[1]) + " ~ " + num(p.quantiles[3]) : "—");
  row("최소 ~ 최대", (p) => p.minimum === null || p.minimum === undefined ? "—" : num(p.minimum) + " ~ " + num(p.maximum));
  row("평균 · 표준편차", (p) => p.mean === null || p.mean === undefined ? "—" : num(p.mean) + " · " + num(p.standard_deviation));
  row(item.kind === "history" ? "사용 가능 / 기록" : "특징 / 전달된 획득", (p) => num(p.usable_count) + " / " + num(p.observation_count));
  if (item.kind === "history") {
    row("값 없음 · 품질 문제 · 충돌", (p) => num(p.missing_count) + " · " + num(p.non_good_count) + " · " + num(p.conflict_count));
    row("평소 간격 · 가장 긴 공백", (p) => duration(p.median_interval_seconds) + " · " + duration(p.largest_gap?.seconds));
  } else {
    row("빠진 번호 · 분석 안 됨", (p) => num(p.missing_count) + " · " + num(p.unanalyzed_count));
  }
  row("같은 값이 이어진 최대 기록", (p) => num(p.longest_constant?.count));
  card.append(table);
  return card;
}

// Shared-axis histogram (A outlined, B filled) above two box plots, one per period.
function chart(item) {
  const width = 900, height = 168, left = 30, right = 884;
  const svg = svgNode("svg", {viewBox: "0 0 " + width + " " + height, class: "explore-chart", role: "img",
    "aria-label": item.label + " 구간 A와 B의 분포 비교"});
  const histogram = item.histogram;
  const low = histogram ? histogram.low : Math.min(item.periods.a.minimum, item.periods.b.minimum);
  const high = histogram ? histogram.high : Math.max(item.periods.a.maximum, item.periods.b.maximum);
  const x = (value) => high > low ? left + (value - low) / (high - low) * (right - left) : (left + right) / 2;
  if (histogram) {
    const peak = Math.max(...["a", "b"].map((name) => {
      const total = (histogram[name] || []).reduce((sum, value) => sum + value, 0) || 1;
      return Math.max(0, ...(histogram[name] || []).map((value) => value / total));
    })) || 1;
    const binWidth = (right - left) / histogram.bins;
    for (const [name, className] of [["a", "explore-bar-a"], ["b", "explore-bar-b"]]) {
      const counts = histogram[name] || [];
      const total = counts.reduce((sum, value) => sum + value, 0) || 1;
      counts.forEach((count, index) => {
        if (!count) return;
        const share = count / total, barHeight = share / peak * 84;
        const bar = svgNode("rect", {x: left + index * binWidth + (name === "b" ? binWidth / 2 : 0), y: 92 - barHeight,
          width: Math.max(1, binWidth / 2 - 1), height: barHeight, class: className});
        bar.append(svgNode("title"));bar.firstChild.textContent = "구간 " + name.toUpperCase() + " · " + count + "개";
        svg.append(bar);
      });
    }
  }
  svg.append(svgNode("path", {d: "M" + left + " 94 H" + right, class: "axis"}));
  for (const [name, y] of [["a", 116], ["b", 144]]) {
    const p = item.periods[name];
    if (!p.quantiles) continue;
    const [p05, p25, p50, p75, p95] = p.quantiles;
    const group = svgNode("g", {class: "explore-box explore-box-" + name});
    group.append(svgNode("line", {x1: x(p.minimum), x2: x(p.maximum), y1: y, y2: y}));
    group.append(svgNode("rect", {x: x(p25), y: y - 8, width: Math.max(1, x(p75) - x(p25)), height: 16}));
    group.append(svgNode("line", {x1: x(p50), x2: x(p50), y1: y - 10, y2: y + 10, class: "median"}));
    for (const value of [p05, p95]) group.append(svgNode("circle", {cx: x(value), cy: y, r: 2.5}));
    const label = svgNode("text", {x: 2, y: y + 4});label.textContent = name.toUpperCase();group.append(label);
    svg.append(group);
  }
  for (const [value, anchor] of [[low, "start"], [high, "end"]]) {
    const text = svgNode("text", {x: anchor === "start" ? left : right, y: 106, "text-anchor": anchor, class: "explore-axis-label"});
    text.textContent = num(value);svg.append(text);
  }
  return svg;
}

// From two acquisition ranges to the model results that read them.
function modelLinks(data) {
  if (data.kind !== "acquisition") return null;
  const models = (sources.acquisition.models || []).filter((model) => model.task === "anomaly-score" || model.task === "rul-estimate");
  if (!models.length) return null;
  const box = create("p", "explore-links");
  const seen = new Set();
  for (const model of models) {
    const view = model.task === "anomaly-score" ? "anomaly" : "rul";
    if (seen.has(view)) continue;
    seen.add(view);
    const url = new URL(location.href);
    url.searchParams.set("phm_binding", model.binding_id);url.searchParams.set("phm_position", data.periods.b.to);
    url.searchParams.set("phm_view", view);url.searchParams.set("phm_compare", data.periods.a.to);
    url.hash = view;
    const link = create("a", null, (view === "anomaly" ? "이상 탐지" : "잔여 수명") + "에서 #" + data.periods.a.to + " → #" + data.periods.b.to + " 비교 보기");
    link.href = url.pathname + url.search + url.hash;
    box.append(link);
  }
  return box;
}
