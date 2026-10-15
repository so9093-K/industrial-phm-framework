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
let sources = null, kind = null, loadedKey = "", request = 0, loadTicket = 0;
// A question chosen elsewhere (the overview's list of what the data supports) runs once the
// comparison for its asset is ready.
let readyFor = "", pendingGoal = null;
export function requestExploreGoal(goal) {
  pendingGoal = goal ? {goal, asset: currentAsset()} : null;
  if (pendingGoal && readyFor === pendingGoal.asset) runPendingGoal();
}
function runPendingGoal() {
  const {goal, asset} = pendingGoal;
  pendingGoal = null;
  if (asset !== currentAsset()) return;
  const button = byId("explore-goals").querySelector(`[data-explore-goal="${goal}"]`);
  if (button && !button.hidden && !button.disabled) button.click();
}
// An answer belongs to the comparison it was asked for: a newer comparison, asset or
// axis choice makes it stale.
const stale = (owner, box) => owner !== request || !box.isConnected;

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
  onAssetChange(() => {
    // A comparison's signals and ranges belong to the asset they were chosen for.
    const url = new URL(location.href);
    for (const key of ["explore_kind", "explore_series", "explore_a", "explore_b"]) url.searchParams.delete(key);
    history.replaceState(history.state, "", url);
    loadedKey = "";if (document.body.dataset.view === "signals") void load();
  });
  // The signal flow hands over its window and signals as two halves to compare.
  document.addEventListener("explore-request", (event) => {
    const url = new URL(location.href);
    for (const [key, value] of Object.entries(event.detail)) url.searchParams.set("explore_" + key, value);
    history.replaceState(history.state, "", url);
    void load().then(() => byId("explore")?.scrollIntoView({block: "start"}));
  });
  window.addEventListener("hashchange", () => {if (document.body.dataset.view === "signals" && loadedKey !== viewKey()) void load();});
  if (document.body.dataset.view === "signals") void load();
}

async function load() {
  const asset = currentAsset(), ticket = ++loadTicket;
  loadedKey = viewKey();readyFor = "";
  request++;
  for (const id of ["explore-controls", "explore-quality", "explore-results"]) clear(byId(id));
  byId("explore-guide").hidden = true;
  byId("explore-result-intro").hidden = true;
  if (!asset) {state("설비를 선택하세요.");return;}
  state("비교할 수 있는 측정을 확인합니다.");
  let found;
  try {found = await getJson("/api/v1/explore/sources?asset_id=" + encodeURIComponent(asset));}
  catch {if (ticket === loadTicket) state("비교할 측정 목록을 읽지 못했습니다.", true);return;}
  // A slower answer for an asset left behind must not replace the current one.
  if (ticket !== loadTicket || asset !== currentAsset()) return;
  sources = found;
  const kinds = ["history", "acquisition"].filter((name) => sources[name]);
  if (!kinds.length) {state("이 설비에는 비교할 저장 측정이 없습니다. 측정 이력을 저장하거나 모델을 연결하면 여기서 비교할 수 있습니다.");return;}
  kind = kinds.includes(params().get("explore_kind")) ? params().get("explore_kind") : kinds[0];
  renderControls(kinds);
  byId("explore-guide").hidden = false;
  await compare();
  if (ticket !== loadTicket || asset !== currentAsset()) return;
  readyFor = asset;
  if (pendingGoal) runPendingGoal();
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
  // A range written for the other kind of data (numbers vs times) is not this one's.
  const fits = (value) => kind === "acquisition" ? /^\d+$/.test(value) : /^\d{4}-\d{2}-\d{2}T/.test(value);
  const parse = (value) => {const parts = (value || "").split("~");return parts.length === 2 && parts.every(fits) ? parts : [];};
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
  initializeGuidedGoals(choices);
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

function initializeGuidedGoals(choices) {
  const root = byId("explore-goals"), hint = byId("explore-goal-hint");
  for (const button of root.querySelectorAll("[data-explore-goal]")) {
    const goal = button.dataset.exploreGoal;
    button.hidden = goal === "spectrum" && kind !== "acquisition";
    button.disabled = goal === "relation" && choices.length < 2;
    button.onclick = async () => {
      for (const other of root.querySelectorAll("[data-explore-goal]")) {
        other.setAttribute("aria-pressed", String(other === button));
      }
      if (goal === "trend") {
        hint.textContent = "위 신호 흐름에서 측정 신호와 기간을 고르면 실제 측정 시각을 따라 확인할 수 있습니다.";
        const target = byId("signals");
        target.scrollIntoView({block: "start"});
        target.tabIndex = -1;
        target.focus({preventScroll: true});
        return;
      }
      if (goal === "compare") {
        setPeriods([0, 0.25, 0.75, 1]);
        hint.textContent = "처음 1/4과 마지막 1/4 구간을 비교합니다. 필요하면 아래에서 기간을 직접 수정하세요.";
      }
      if (goal === "relation") {
        const boxes = [...byId("explore-series").querySelectorAll("input[type=checkbox]")];
        const selected = boxes.filter((box) => box.checked);
        for (const box of boxes) {
          if (selected.length >= 2) break;
          if (!box.checked) {box.checked = true;selected.push(box);}
        }
        boxes[0]?.dispatchEvent(new Event("change"));
        hint.textContent = "동일한 시각·획득의 관측을 짝지어 비교합니다. 상관관계는 고장 원인을 증명하지 않습니다.";
      }
      if (goal === "spectrum") {
        hint.textContent = "원본 진동 파형을 사용하는 주파수 분석입니다. 특정 고장 주파수나 고장 원인을 확정하지 않습니다.";
      }
      const success = await compare();
      if (!success) return;
      const target = byId("explore-results")?.querySelector(goal === "relation" ? ".explore-relation" : goal === "spectrum" ? ".explore-spectrum" : ".explore-series");
      if (goal === "spectrum") target?.querySelector("button")?.click();
      if (target) {
        target.scrollIntoView({block: "start"});
        target.tabIndex = -1;
        target.focus({preventScroll: true});
      }
    };
  }
}

async function compare() {
  const asset = currentAsset();
  const series = [...byId("explore-series").querySelectorAll("input:checked")].map((input) => input.value);
  if (!series.length) {state("비교할 항목을 하나 이상 고르세요.", true);return false;}
  const values = {};
  try {
    for (const id of ["a-0", "a-1", "b-0", "b-1"]) {
      const raw = byId("explore-" + id).value;
      values[id] = kind === "history" ? kstInputToInstant(raw) : String(Math.trunc(Number(raw)));
      if (kind === "acquisition" && !/^\d+$/.test(values[id])) throw new Error("bad");
    }
  } catch {state("구간의 시작과 끝을 확인하세요.", true);return false;}
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
    if (ticket !== request || asset !== currentAsset()) return false;
    render(data);
    return true;
  } catch (error) {
    if (ticket !== request) return;
    clear(byId("explore-quality"));clear(byId("explore-results"));
    state(error.status === 400 ? "구간을 확인하세요. 각 구간은 시작이 끝보다 앞서야 하고 31일을 넘을 수 없습니다." : "구간 비교를 계산하지 못했습니다.", true);
    byId("explore-result-intro").hidden = true;
    return false;
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
  const intro = byId("explore-result-intro");
  const comparable = data.series.filter((item) => item.periods.a?.quantiles && item.periods.b?.quantiles).length;
  intro.hidden = false;
  intro.textContent = "선택한 " + data.series.length + "개 항목 중 " + comparable + "개에서 두 구간의 대표값을 비교할 수 있습니다. "
    + "구간 A는 사용자가 고른 비교 구간이며 정상·안전 기준이 아닙니다. 값의 차이가 곧 설비 고장 원인은 아닙니다.";
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
  const owner = request;
  let drawn = 0;
  const draw = async () => {
    const ticket = ++drawn;
    if (x.value === y.value) {output.replaceChildren(create("p", "muted", "서로 다른 두 항목을 고르세요."));return;}
    output.replaceChildren(create("p", "muted", "짝지은 관측을 계산합니다."));
    const query = new URLSearchParams({asset_id: currentAsset(), kind: data.kind, x: x.value, y: y.value, ...periodQuery(data)});
    try {
      const relation = await getJson("/api/v1/explore/relation?" + query.toString());
      if (ticket !== drawn || stale(owner, box)) return;
      output.replaceChildren(...relationView(relation, choices));
    } catch {if (ticket === drawn && !stale(owner, box)) output.replaceChildren(create("p", "muted", "관계를 계산하지 못했습니다."));}
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
  // A channel whose unit or meaning changed is computed per meaning; only one meaning is drawn,
  // so the scatter never puts values of different units on one axis.
  const place = (group) => [group.period, group.source_id, group.measurement_point_id || ""].join("\u0000");
  const meanings = new Map();
  for (const group of relation.groups) meanings.set(place(group), (meanings.get(place(group)) || new Set()).add(group.meaning_id));
  const split = [...meanings.values()].some((ids) => ids.size > 1);
  const main = groups.reduce((best, group) => group.pair_count > best.pair_count ? group : best).meaning_id;
  const several = new Set(relation.groups.map((group) => group.source_id + "\u0000" + (group.measurement_point_id || ""))).size > 1;
  const all = groups.filter((group) => !split || group.meaning_id === main).flatMap((group) => group.points);
  const xs = all.map((point) => point[1]), ys = all.map((point) => point[2]);
  const bounds = (values) => {const low = Math.min(...values), high = Math.max(...values);return high > low ? [low, high] : [low - 1, high + 1];};
  const [x0, x1] = bounds(xs), [y0, y1] = bounds(ys);
  const svg = svgNode("svg", {viewBox: "0 0 420 260", class: "explore-scatter", role: "img",
    "aria-label": name(relation.x) + "와 " + name(relation.y) + "의 짝지은 관측 산점도"});
  svg.append(svgNode("path", {d: "M40 10 V224 H410", class: "axis"}));
  for (const group of groups) {
    if (split && group.meaning_id !== main) continue;
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
    const where = several ? " · " + group.source_id + (group.measurement_point_id ? " / " + group.measurement_point_id : "") : "";
    const units = split ? " · 단위 " + (group.x_unit || "없음") + " / " + (group.y_unit || "없음") : "";
    row.append(create("th", null, "구간 " + group.period.toUpperCase() + where + units),
      create("td", null, num(group.pair_count) + " / " + num(Math.max(group.x_usable_count, group.y_usable_count))),
      create("td", null, r(group.pearson)), create("td", null, r(group.spearman)));
    table.append(row);
  }
  const how = relation.pairing === "same-acquisition" ? "같은 획득의 두 특징을 짝지었습니다." : "같은 출처·측정 지점·시각의 관측만 짝지었습니다.";
  const notes = [create("p", "muted", how + " 상관은 함께 움직인 정도이며 원인을 뜻하지 않습니다."),
    create("p", "explore-interpretation", "Pearson은 직선 관계, Spearman은 값의 순서가 함께 변하는 경향을 요약합니다. 같은 방향으로 움직여도 한 신호가 다른 신호의 원인이라는 뜻은 아닙니다.")];
  if (split) notes.push(create("p", "muted", "측정 해석(단위·의미)이 바뀐 기록은 따로 계산했고, 산점도에는 짝이 가장 많은 해석만 그렸습니다."));
  for (const group of relation.groups.filter((item) => item.sampled)) {
    notes.push(create("p", "muted", "구간 " + group.period.toUpperCase() + "은 분석된 획득 " + num(group.analyzed_count)
      + "개가 많아 구간 전체에서 고르게 고른 " + num(group.pair_count) + "개로 계산했습니다."));
  }
  return [svg, create("p", "muted", "세로축 " + name(relation.y) + " · 회색 구간 A, 청록 구간 B"), table, ...notes];
}

// Where vibration energy sits and how it moved, from verified raw waveforms of both ranges.
function spectrumSection(data) {
  const box = create("section", "explore-spectrum");
  box.append(create("h3", null, "진동 주파수 성분"));
  // Reading raw waveforms takes a moment, so it runs when asked, not with every comparison.
  const output = create("div");
  const start = create("button", "secondary", "주파수 성분 계산");start.type = "button";
  output.append(create("p", "explore-interpretation",
    "실제 진동 파형을 주파수별로 나누어 두 구간의 차이를 살펴봅니다. 특정 부품 고장이나 고장 원인을 확정하는 분석은 아닙니다."),
    create("p", "muted", "구간마다 처음부터 끝까지 고르게 고른 원본 파형 최대 8개로 계산합니다."), start);
  box.append(output);
  const owner = request;
  const run = async () => {
    start.disabled = true;start.textContent = "계산 중";
    const query = new URLSearchParams({asset_id: currentAsset(), ...periodQuery(data)});
    let spectrum;
    try {spectrum = await getJson("/api/v1/explore/spectrum?" + query.toString());}
    catch {
      if (stale(owner, box)) return;
      start.disabled = false;start.textContent = "다시 계산";
      output.replaceChildren(create("p", "muted", "원본 파형을 읽지 못해 주파수 성분을 계산하지 못했습니다."), start);
      return;
    }
    if (stale(owner, box)) return;
    const channel = create("select");channel.setAttribute("aria-label", "주파수 채널");
    spectrum.channels.forEach((item, index) => channel.append(Object.assign(create("option", null, item.label), {value: String(index)})));
    const view = create("div");
    const show = () => view.replaceChildren(...spectrumView(spectrum, spectrum.channels[Number(channel.value)]));
    channel.addEventListener("change", show);
    const field = create("label", null, "채널");field.append(channel);
    output.replaceChildren(field, view);show();
    output.append(create("p", "muted", "Welch PSD · " + num(spectrum.segment) + "점 구간 · 샘플링 " + num(spectrum.sampling_rate_hz / 1000) + " kHz · 구간 A 획득 "
      + spectrum.acquisitions.a.map((n) => "#" + n).join(" ") + " / 구간 B 획득 " + spectrum.acquisitions.b.map((n) => "#" + n).join(" ") + " 평균"));
  };
  start.addEventListener("click", () => void run());
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
      ["분석된 획득", Math.max(...periods.map((item) => item.analyzed_count || 0))],
      ["빠진 획득 번호", Math.max(...periods.map((item) => item.missing_count || 0))],
      ["분석되지 않은 획득", Math.max(...periods.map((item) => item.unanalyzed_count || 0))]];
  const list = create("dl");
  for (const [term, value] of lines) list.append(create("dt", null, term), create("dd", null, typeof value === "number" ? num(value) : value));
  card.append(list);
  if (data.kind === "history" && data.series.length > 1) card.append(create("p", "muted",
    "여러 신호를 선택한 경우 이 카드의 측정 개수는 신호별 집계의 합입니다. 같은 시각의 기록이 여러 번 포함될 수 있습니다."));
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
    const difference = typeof change.median_change_percent === "number" ? percent(change.median_change_percent)
      : "차이 " + (change.median_change > 0 ? "+" : "") + num(change.median_change);
    lead.append(create("span", null, "중앙값 " + num(a.quantiles[2]) + " → " + num(b.quantiles[2])),
      create("strong", null, " " + difference));
    if (typeof change.b_outside_a_band_percent === "number") {
      lead.append(create("span", null, " · B 값의 " + change.b_outside_a_band_percent.toLocaleString("ko-KR", {maximumFractionDigits: 0}) + "%가 A의 5–95% 범위 밖"));
    }
    card.append(lead);
    const direction = b.quantiles[2] > a.quantiles[2] ? "높습니다" : b.quantiles[2] < a.quantiles[2] ? "낮습니다" : "같습니다";
    card.append(create("p", "explore-interpretation",
      "살펴볼 구간 B의 중앙값은 비교 구간 A보다 " + direction
      + ". 중앙값은 값을 크기순으로 놓았을 때 가운데 값이며, 증가·감소만으로 설비의 이상이나 원인을 확정할 수 없습니다."));
    card.append(chart(item));
  } else {
    card.append(create("p", "empty", !a.quantiles && !b.quantiles ? "두 구간 모두 사용할 수 있는 값이 없습니다." : (a.quantiles ? "구간 B" : "구간 A") + "에 사용할 수 있는 값이 없습니다."));
  }
  const sampled = ["a", "b"].filter((name) => item.periods[name]?.sampled);
  if (sampled.length) {
    card.append(create("p", "muted", sampled.map((name) => "구간 " + name.toUpperCase() + "은 분석된 획득 "
      + num(item.periods[name].analyzed_count) + "개 중 구간 전체에서 고르게 고른 " + num(item.periods[name].usable_count) + "개로").join(", ")
      + " 계산했습니다. 개수·빠진 번호는 전체 기준입니다."));
  }
  const table = create("table", "phm-table explore-table");
  const head = create("tr");for (const text of ["", "구간 A", "구간 B"]) head.append(create("th", null, text));table.append(head);
  const row = (name, read) => {const tr = create("tr");tr.append(create("th", null, name), create("td", null, read(a)), create("td", null, read(b)));table.append(tr);};
  const q = (index) => (p) => p.quantiles ? num(p.quantiles[index]) : "—";
  row("중앙값", q(2));
  row("25–75%", (p) => p.quantiles ? num(p.quantiles[1]) + " ~ " + num(p.quantiles[3]) : "—");
  row("최소 ~ 최대", (p) => p.minimum === null || p.minimum === undefined ? "—" : num(p.minimum) + " ~ " + num(p.maximum));
  row("평균 · 표준편차", (p) => p.mean === null || p.mean === undefined ? "—" : num(p.mean) + " · " + num(p.standard_deviation));
  row(item.kind === "history" ? "사용 가능 / 기록" : "분석된 / 전달된 획득", (p) => num(item.kind === "history" ? p.usable_count : p.analyzed_count) + " / " + num(p.observation_count));
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
