// Condition and remaining margin of the selected signal: how far it has moved from its own early
// baseline, how fast it moves, since when it stays outside its usual range, what the asset's
// anomaly model says, and how much room is left before the management level and the end
// condition the user set (the remaining life under that definition), read four ways. The server
// computes every number; this module words and lays them out.
import { modelFamily } from "./phm-connect.js";
import { formatTime } from "./time.js";
import { byId, canChange, clear, create, num, OPERATIONS_REQUIRED } from "./web-utils.js";

let shownKey = "", request = 0, current = null, briefingTicket = 0, refreshedAt = 0;
function briefingSelection() {
  const query = new URLSearchParams(shownKey);
  if (current?.data_version) query.set("data_version", current.data_version);
  return query.toString();
}
const READING = {current: "현재 설정", recent: "최근 구간만 학습", responsive: "추세 변화에 민감", linear: "최근 변화 속도 유지"};
const REASON = {
  "few-points": "유효한 값이 20개 이상 있어야 상태 전망을 계산합니다.",
  "short-history": "기록이 짧아 기준까지의 여유를 계산할 수 없습니다.",
  "engine-unavailable": "예측 엔진이 설치되지 않았습니다. make up으로 다시 시작하면 설치됩니다.",
  "unknown-interval": "획득 간격이 기록되지 않았습니다.",
};
const one = (value) => typeof value === "number" && Number.isFinite(value)
  ? value.toLocaleString("ko-KR", {maximumFractionDigits: 1}) : "—";
const signed = (value) => (value > 0 ? "+" : "") + num(value);
const span = (seconds) => seconds >= 86400 ? one(seconds / 86400) + "일" : seconds >= 3600 ? one(seconds / 3600) + "시간"
  : seconds >= 60 ? one(seconds / 60) + "분" : one(seconds) + "초";

export function currentOutlook() {return current;}

// Where a point of the record sits, in the record's own terms.
const place = (data, value) => data.axis === "acquisition" ? "#" + value : formatTime(value, {seconds: false});
const range = (data, part) => data.axis === "acquisition" ? "#" + part.from + "–#" + part.to
  : formatTime(part.from, {seconds: false}) + " ~ " + formatTime(part.to, {seconds: false, zone: false});
// An offset after the last measurement: acquisitions or seconds.
const after = (data, offset) => data.offset_unit === "acquisition" ? num(offset) + "개 획득" : span(offset);
const reachedAt = (data, offset) => data.offset_unit === "acquisition" ? "#" + (data.record.last + offset)
  : formatTime(new Date(Date.parse(data.record.last) + offset * 1000).toISOString(), {seconds: false});
const rateText = (data, rate) => ({acquisition: "획득당 ", hour: "시간당 ", day: "하루 "})[data.rate_unit] + signed(rate);
const conditionName = (data, name) => (name === "end" ? "종료 기준 " : "관리 " + (data.conditions.direction === "lower" ? "하한 " : "상한 "))
  + num(data.conditions[name]);
const searchText = (data) => data.offset_unit === "acquisition" ? num(data.search.acquisitions) + "개 획득" : span(data.search.seconds);

function change(data) {
  const d = data.degradation;
  return d.change_ratio !== null && d.change_ratio !== undefined
    ? signed(Math.round(d.change_ratio * 1000) / 10) + "%" : signed(d.change);
}

// The margin to one condition under one reading, as a headline and a detail line.
function margin(data, reached) {
  if (!reached) return ["—", ""];
  if (reached.state === "already") return ["이미 도달", "마지막 측정 " + num(data.degradation.latest)];
  if (reached.state === "expected") {
    const bounds = [reached.earliest !== null && reached.earliest !== reached.expected ? "빠르면 " + after(data, reached.earliest) : "",
      reached.latest !== null && reached.latest !== reached.expected ? "늦으면 " + after(data, reached.latest) : ""].filter(Boolean);
    return [after(data, reached.expected) + " 뒤", [reachedAt(data, reached.expected), ...bounds].join(" · ")];
  }
  if (reached.state === "possible") return ["예측 범위에서만 도달", "범위 상단 기준 " + after(data, reached.earliest) + " 뒤"];
  return [searchText(data) + " 안 도달 없음", "기록 길이의 절반까지 계산"];
}

function figures(data) {
  const list = create("dl", "outlook-figures");
  const add = (term, value, detail) => {
    const item = create("div");
    item.append(create("dt", null, term), create("dd", null, value));
    if (detail) item.append(create("dd", "outlook-figure-detail", detail));
    list.append(item);
  };
  const d = data.degradation;
  add("기준 구간 대비 최근", change(data), num(d.baseline.median) + " → " + num(d.recent.median) + " · " + range(data, d.baseline) + " → " + range(data, d.recent));
  const now = data.scenarios.find((item) => item.id === "current");
  for (const name of ["management", "end"]) {
    if (data.conditions[name] === null) continue;
    const [value, detail] = margin(data, now?.limits[name]);
    add((name === "end" ? "잔여수명 · " : "") + conditionName(data, name) + "까지", value, detail);
  }
  if (data.conditions.management === null && data.conditions.end === null)
    add("기준까지 여유", "기준 없음", "관리 기준이나 종료 기준을 입력하면 계산");
  return list;
}

function details(data) {
  const list = create("dl", "forecast-summary outlook-details");
  const add = (term, text) => {const item = create("div");item.append(create("dt", null, term), create("dd", null, text));list.append(item);};
  const d = data.degradation;
  add("변화 속도", "최근 " + rateText(data, d.rate) + (d.earlier_rate === null ? "" : " · 그 전 " + rateText(data, d.earlier_rate)));
  if (d.spread_ratio !== null) add("변동폭", "최근 구간이 기준 구간의 " + one(d.spread_ratio) + "배");
  if (d.departure) {
    const p = d.departure;
    add("기준 범위 이탈", (p.since !== null ? place(data, p.since) + "부터 계속 벗어남" : p.outside ? "벗어난 값 " + num(p.outside) + "개 · 계속되지 않음" : "벗어난 값 없음")
      + " · 마지막 측정 " + num(d.latest) + " (기준 변동폭의 " + one(Math.abs(p.latest_distance)) + "배)");
  }
  const model = data.anomaly_model;
  if (model?.latest) {
    const l = model.latest;
    add("이상 탐지 모델", modelFamily(model.package_id, "anomaly-score", model.step_kind).replace(/^.*· /, "") + " · "
      + (data.axis === "acquisition" ? "#" + l.position : formatTime(l.at, {seconds: false}))
      + " 점수 " + num(l.score) + (typeof l.threshold === "number" ? (l.exceeds ? " · 모델 기준 " + num(l.threshold) + " 초과" : " · 모델 기준 " + num(l.threshold) + " 이하") : "")
      + (model.first_exceeding ? " · 처음 초과 " + (model.step_kind === "acquisition-snapshot" ? "#" + model.first_exceeding.position : formatTime(model.first_exceeding.at, {seconds: false})) : "")
      + " · 최근 " + model.recent.results + "개 중 " + model.recent.exceeding + "개 초과");
  }
  return list;
}

function scenarioTable(data) {
  const names = ["management", "end"].filter((name) => data.conditions[name] !== null);
  const table = create("table", "outlook-scenarios");
  const caption = create("caption", null, "예측 조건별 잔여 여유 · " + place(data, data.search.until) + "까지 계산");table.append(caption);
  const head = create("tr");head.append(create("th", null, "읽는 방법"));
  for (const name of names) head.append(Object.assign(create("th", null, conditionName(data, name)), {scope: "col"}));
  table.append(create("thead"), create("tbody"));
  table.tHead.append(head);
  for (const scenario of data.scenarios) {
    const row = create("tr");
    const how = create("th", null, READING[scenario.id]);how.scope = "row";
    const note = scenario.id === "linear" ? "마지막 측정에서 " + rateText(data, data.degradation.rate)
      : scenario.id === "recent" ? "최근 " + num(scenario.training_points) + "개 학습"
      : scenario.id === "responsive" ? "추세 민감도 " + num(scenario.changepoint_prior_scale)
      : "민감도 " + num(scenario.changepoint_prior_scale) + " · " + num(scenario.training_points) + "개 학습";
    how.append(create("span", "outlook-reading-note", note));
    row.append(how);
    for (const name of names) {
      const reached = scenario.limits[name];
      const cell = create("td");
      cell.textContent = reached.state === "already" ? "이미 도달" : reached.state === "expected"
        ? after(data, reached.expected) + (reached.earliest !== null && reached.earliest !== reached.expected ? " (빠르면 " + after(data, reached.earliest) + ")" : "")
        : reached.state === "possible" ? "범위에서만 " + after(data, reached.earliest) : "도달 없음";
      cell.dataset.state = reached.state;
      row.append(cell);
    }
    table.tBodies[0].append(row);
  }
  return table;
}

function evidence(data, context) {
  const box = create("details", "outlook-evidence");box.id = "outlook-evidence";
  box.append(create("summary", null, "계산 근거"));
  const list = create("ul");
  const add = (text) => list.append(create("li", null, text));
  const d = data.degradation;
  add("측정값: " + data.label + (data.unit ? " (" + data.unit + ")" : "") + " · 출처 " + data.source_id
    + (data.measurement_point_id ? " · 측정점 " + data.measurement_point_id : "")
    + " · " + (data.axis === "acquisition" ? "#" + data.record.first + "–#" + data.record.last : range(data, {from: data.record.first, to: data.record.last}))
    + " · 값 " + num(data.record.points) + "개"
    + (data.axis === "acquisition" ? (data.time_basis === "ordinal" ? " · 획득 간격 기록 없음" : " · " + (data.time_basis === "assumed" ? "가정" : "기록") + " 획득 간격 " + span(data.period_seconds))
      : data.raw_count > data.record.points ? " (원본 " + num(data.raw_count) + "개의 구간 평균)" : ""));
  add("기준 구간: " + range(data, d.baseline) + " (기록의 처음 30%) · 중앙값 " + num(d.baseline.median) + " · 변동폭 " + num(d.baseline.spread)
    + (d.departure ? " · 기준 범위는 중앙값에서 변동폭의 " + num(d.departure.threshold) + "배 안" : ""));
  add("최근 구간: " + range(data, d.recent) + " · 중앙값 " + num(d.recent.median) + " · 변화 속도는 이 구간 기울기의 중앙값");
  const now = data.scenarios.find((item) => item.id === "current");
  if (now) add("예측: Prophet · 추세 민감도 " + num(now.changepoint_prior_scale) + " · 변화점 범위 " + num(data.settings.changepoint_range)
    + " · " + num(now.training_points) + "개 학습 · 예측 시작값 " + num(now.start) + " (마지막 측정 " + num(d.latest) + ")"
    + " · " + place(data, data.search.until) + "까지 계산 (학습 기록 길이의 절반)");
  if (data.conditions.end !== null) add("잔여수명은 입력한 종료 기준 " + num(data.conditions.end) + "까지 남은 거리입니다.");
  if (data.anomaly_model) add("이상 탐지 모델: " + modelFamily(data.anomaly_model.package_id, "anomaly-score", data.anomaly_model.step_kind)
    + " · 결과 " + num(data.anomaly_model.results) + "개 · 기준 초과 " + num(data.anomaly_model.exceeding) + "개"
    + (data.anomaly_model.read < data.anomaly_model.results ? " (" + num(data.anomaly_model.read) + "개를 고르게 읽음)" : ""));
  if (context) add(context);
  box.append(list);
  box.append(links(data));
  return box;
}

function links(data) {
  const root = create("p", "forecast-explore-links");
  const add = (label, hash, values) => {
    const url = new URL(location.href);url.hash = hash;
    for (const [key, value] of Object.entries(values)) url.searchParams.set(key, value);
    const link = create("a", null, label);link.href = url.pathname + url.search + url.hash;root.append(link);
  };
  const d = data.degradation;
  // Period comparison reads at most 31 days per period; a longer window keeps its last 31 days.
  const period = (part) => {
    if (data.axis === "acquisition") return part.from + "~" + part.to;
    const end = Date.parse(part.to) + 1000, start = Math.max(Date.parse(part.from), end - 31 * 86400000);
    return new Date(start).toISOString() + "~" + new Date(end).toISOString();
  };
  add("기준 구간과 최근 구간 비교", "signals", {explore_kind: data.kind, explore_series: data.series, explore_a: period(d.baseline), explore_b: period(d.recent)});
  if (data.anomaly_model?.latest) add("이상 탐지 결과 보기", "anomaly", {phm_binding: data.anomaly_model.binding_id, phm_position: String(data.anomaly_model.latest.position), phm_view: "anomaly"});
  else if (data.kind === "history") add("기준 범위를 벗어난 구간 보기", "anomaly", {forecast_anomaly_series: data.series});
  return root;
}

// An AI briefing of this selection: the supervisor recomputes the outlook, asks the configured
// model and keeps the answer whose numbers match the computed facts.
const QUESTIONS = ["최근 어떤 변화가 있었어?", "기준까지 얼마나 남았어?", "예측 조건에 따라 왜 달라져?"];
const SOURCE = {
  model: "AI 답변 · 수치는 계산 결과와 대조함",
  "model-trimmed": "AI 답변 일부 · 계산 결과와 맞지 않는 문장은 뺌",
  computed: "계산된 요약",
};

function briefing() {
  const root = create("section", "outlook-briefing");root.id = "outlook-briefing";
  root.append(create("h4", null, "AI 브리핑"));
  const suggestions = create("div", "phm-suggestions");
  const label = create("label", null, "궁금한 점");
  const question = create("textarea");question.rows = 2;question.maxLength = 600;question.id = "outlook-question";
  question.value = "이 설비의 상태와 기준까지 남은 여유를 설명해 주세요.";label.append(question);
  const ask = create("button", null, "AI에 질문");ask.type = "button";ask.id = "outlook-ask";
  const status = create("p", "muted");status.setAttribute("role", "status");
  const answer = create("div", "outlook-answer");
  for (const text of QUESTIONS) {
    const button = create("button", "secondary", text);button.type = "button";
    button.addEventListener("click", () => {question.value = text;ask.click();});
    suggestions.append(button);
  }
  root.append(suggestions, label, ask, status, answer);
  const buttons = [ask, ...suggestions.querySelectorAll("button")];
  for (const button of buttons) button.disabled = true;
  const selection = briefingSelection();
  void (async () => {
    let writable = false;
    try {writable = canChange(await (await fetch("/api/v1/session", {cache: "no-store"})).json());} catch {}
    if (selection !== briefingSelection()) return;
    for (const button of buttons) button.disabled = !writable;
    if (!writable) status.textContent = OPERATIONS_REQUIRED;
    const stored = await briefings(selection);
    const done = stored.find((item) => item.status === "complete");
    if (done && selection === briefingSelection()) showAnswer(answer, done);
    const pending = stored.find((item) => item.status === "pending");
    if (pending && selection === shownKey) void follow(selection, pending.id, status, answer, buttons);
  })();
  ask.addEventListener("click", async () => {
    const text = question.value.trim();
    if (!text) {status.textContent = "질문을 입력하세요.";return;}
    for (const button of buttons) button.disabled = true;
    status.textContent = "AI 브리핑을 요청합니다.";
    try {
      const session = await (await fetch("/api/v1/session", {cache: "no-store"})).json();
      const response = await fetch("/api/v1/outlook/briefings/request", {method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: JSON.stringify({...Object.fromEntries(new URLSearchParams(selection)), question: text})});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || "request_failed");
      await follow(selection, body.briefing_id, status, answer, buttons);
    } catch {
      if (selection === briefingSelection()) {status.textContent = "AI 브리핑을 요청하지 못했습니다.";for (const button of buttons) button.disabled = false;}
    }
  });
  return root;
}

async function briefings(selection) {
  try {
    const response = await fetch("/api/v1/outlook/briefings?" + selection, {cache: "no-store"});
    return response.ok ? (await response.json()).briefings : [];
  } catch {return [];}
}

// Wait for one requested briefing of this selection; a newer selection ends the wait.
async function follow(selection, id, status, answer, buttons) {
  const ticket = ++briefingTicket;
  status.textContent = "AI가 계산 결과를 읽고 있습니다.";
  for (let attempt = 0; attempt < 120; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, attempt < 10 ? 500 : 1500));
    if (ticket !== briefingTicket || selection !== briefingSelection()) return;
    const record = (await briefings(selection)).find((item) => item.id === id);
    if (!record || record.status === "pending") continue;
    for (const button of buttons) button.disabled = false;
    if (record.status === "complete") {status.textContent = "";showAnswer(answer, record);}
    else status.textContent = "AI 브리핑을 만들지 못했습니다. 위 요약과 계산 근거는 그대로입니다.";
    return;
  }
  for (const button of buttons) button.disabled = false;
  status.textContent = "AI 브리핑이 늦어지고 있습니다. 잠시 뒤 다시 열면 이어서 보입니다.";
}

function showAnswer(root, record) {
  const result = record.answer;
  const parts = [create("p", "outlook-answer-question", "질문 · " + record.question), create("p", "outlook-answer-summary", result.summary)];
  if (result.points.length) {
    const list = create("ul", "outlook-answer-points");
    for (const point of result.points) {
      const item = create("li", null, point.text);
      const chips = create("span", "outlook-chips");
      for (const key of point.evidence) {
        const fact = result.evidence[key];
        const chip = create("span", "outlook-chip", fact?.label || key);chip.title = fact?.text || "";chips.append(chip);
      }
      item.append(chips);list.append(item);
    }
    parts.push(list);
  }
  const facts = create("details", "outlook-answer-facts");
  facts.append(create("summary", null, "사용한 사실"));
  const factList = create("dl", "forecast-summary");
  for (const fact of Object.values(result.evidence)) {
    const row = create("div");row.append(create("dt", null, fact.label), create("dd", null, fact.text));factList.append(row);
  }
  facts.append(factList);
  const source = result.checks?.source === "computed" && result.checks?.model_unavailable
    ? "AI 응답이 없어 계산된 요약" : SOURCE[result.checks?.source] || "";
  parts.push(facts, create("p", "muted outlook-answer-source", source + (record.model ? " · " + record.model : "")
    + (record.finished_at ? " · " + formatTime(record.finished_at, {seconds: false}) : "")));
  root.replaceChildren(...parts);
}

export function renderOutlook(data, context = "") {
  const root = byId("outlook");
  current = data;
  root.hidden = false;
  const body = byId("outlook-body");
  // The server words the summary once, so the AI briefing's fallback reads the same.
  const parts = [create("p", "outlook-lead", data.sentences.join(" ")), figures(data), details(data)];
  if (data.scenarios.length) parts.push(scenarioTable(data));
  parts.push(briefing(), evidence(data, context));
  body.replaceChildren(...parts);
  document.dispatchEvent(new CustomEvent("outlook-shown", {detail: data}));
}

// Read the outlook for one selection; the same selection is not read twice in a row.
export async function refreshOutlook(query, context = "") {
  const key = query.toString();
  const root = byId("outlook"), body = byId("outlook-body");
  if (key === shownKey && current && Date.now() - refreshedAt < 10000) {
    renderOutlook(current, context);return;
  }
  const ticket = ++request;
  shownKey = key;current = null;
  root.hidden = false;
  body.replaceChildren(create("p", "muted", "상태와 기준까지의 여유를 계산합니다."));
  try {
    const response = await fetch("/api/v1/outlook?" + key, {cache: "no-store", credentials: "same-origin"});
    const data = await response.json().catch(() => ({}));
    if (ticket !== request) return;
    if (!response.ok) {
      shownKey = "";
      body.replaceChildren(create("p", "muted", response.status === 422 ? REASON[data.reason] || "상태 전망을 계산할 수 없습니다." : "상태 전망을 계산하지 못했습니다."));
      return;
    }
    refreshedAt = Date.now();
    renderOutlook(data, context);
  } catch {
    if (ticket === request) {shownKey = "";body.replaceChildren(create("p", "muted", "상태 전망을 계산하지 못했습니다."));}
  }
}

export function clearOutlook() {
  request++;shownKey = "";current = null;
  const root = byId("outlook");
  if (root) {root.hidden = true;clear(byId("outlook-body"));}
}
