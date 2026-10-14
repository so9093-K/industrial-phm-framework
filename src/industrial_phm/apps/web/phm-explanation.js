// Optional AI text and human disposition never modify persisted model numbers.
const states = new Map();
const element = (tag, text = "") => {const e = document.createElement(tag);e.textContent = text;return e;};
const session = () => fetch("/api/v1/session").then((r) => r.json());
async function get(url) {
  const response = await fetch(url);const body = await response.json();
  if (!response.ok) throw new Error(body.error || "read_failed");return body;
}
async function post(url, payload) {
  const auth = await session();
  const response = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": auth.csrf_token}, body: JSON.stringify(payload)});
  const body = await response.json();if (!response.ok) throw new Error(body.error || "write_failed");return body;
}

import { modelFamily } from "./phm-connect.js";

const SHAPE = /\.(mean|skewness|excess_kurtosis)$/;
const TREND = {increasing: "대체로 증가", decreasing: "대체로 감소", mixed: "오르내림", flat: "변화 없음", insufficient: "기록 부족"};
const trendText = (shape) => (shape.steady ? TREND[shape.trend].replace("대체로", "꾸준히") : TREND[shape.trend]) || shape.trend;
const STEP_ARROW = {increase: "↑", decrease: "↓"};
const ARROW = {increased: "↑ 증가", decreased: "↓ 감소", unchanged: "→ 거의 같음"};

export function renderPhmExplanation(view, bindingId, position, pin = () => {}, stepName = "#" + position, options = {}) {
  const root = document.getElementById(view + "-explanation");
  const assistant = document.getElementById(view + "-assistant");
  let state = states.get(view);
  const key = bindingId && position !== null ? bindingId + ":" + position : "";
  if (state && state.key === key) {
    if (state.explanation?.status === "pending" && !state.timer) state.refresh?.();
    return;
  }
  if (state) clearTimeout(state.timer);
  state = {key, timer: null, explanation: null};states.set(view, state);root.replaceChildren();assistant.replaceChildren();
  if (!key) return;
  const current = () => states.get(view) === state;
  const heading = element("h3", "분석 " + stepName + " · 사람 검토");
  const reviewStatus = element("p", "검토 상태를 조회 중입니다.");reviewStatus.className = "phm-review-status";
  reviewStatus.setAttribute("role", "status");
  const status = element("p", "저장된 AI 설명을 조회 중입니다.");status.setAttribute("role", "status");
  const answerBox = element("div");answerBox.className = "phm-answer";
  const generate = element("button", "AI에 질문");generate.type = "button";
  const steps = options.steps || [];
  const selectedStep = steps.find((step) => step.position === position);
  const earlier = steps.filter((step) => step.position < position).slice(-128).reverse();
  const label = (name) => options.featureLabel ? options.featureLabel(name) : name;
  const stepText = (at) => options.stepLabel ? options.stepLabel(at) : "#" + at;
  const compareLabel = element("label", "비교 시점");
  const compare = element("select");compare.setAttribute("aria-label", "비교 시점");
  for (const step of earlier) {
    const item = element("option", stepText(step.position));
    item.value = String(step.position);compare.append(item);
  }
  if (!earlier.length) {compare.append(element("option", "이전 분석 없음"));compare.disabled = true;}
  const savedCompare = new URL(location.href).searchParams.get("phm_compare");
  if (earlier.some((step) => String(step.position) === savedCompare)) compare.value = savedCompare;
  compareLabel.append(compare);
  const questionLabel = element("label", "궁금한 점");
  const question = element("textarea");question.rows = 2;question.maxLength = 600;
  question.value = "이전 시점과 비교해 어떤 측정 신호가 함께 변했는지 설명해 주세요.";
  question.setAttribute("aria-label", "분석 질문");questionLabel.append(question);
  state.askedQuestion = null;
  let mentioned = [], nextSignals = [];
  const summary = element("div");summary.className = "phm-comparison";
  const comparisonPosition = () => earlier.length ? Number(compare.value) : null;
  const format = (value) => typeof value === "number" ? value.toLocaleString("ko-KR", {maximumSignificantDigits: 4}) : "—";
  // A ratio only where the feature is a positive magnitude; otherwise the signed difference.
  const changeText = (before, after, name) => {
    if (typeof before !== "number" || typeof after !== "number") return "—";
    if (before > 0 && after >= 0 && !SHAPE.test(name)) {
      const percent = 100 * (after - before) / before;
      return (percent > 0 ? "+" : "") + percent.toLocaleString("ko-KR", {maximumFractionDigits: 1}) + "%";
    }
    return (after - before > 0 ? "+" : "") + format(after - before);
  };
  const inputText = (output, at) => {
    const sequence = output?.sequence_positions;
    return sequence?.length ? stepText(sequence[0]) + "–" + stepText(sequence.at(-1)) + " (" + sequence.length + "개 획득)" : stepText(at) + " 한 입력";
  };
  const openButton = (name, text = label(name)) => {
    const open = element("button", text);open.type = "button";
    if (options.openSignal) open.addEventListener("click", () => options.openSignal(position, name));
    else open.disabled = true;
    return open;
  };
  function featureTable(names, prior) {
    const table = element("table");table.className = "phm-table";
    const head = element("tr");for (const title of ["측정 특징", "비교 시점", "선택 시점", "변화"]) head.append(element("th", title));table.append(head);
    for (const name of names) {
      const row = element("tr"), value = selectedStep.features[name], previous = prior?.features?.[name];
      if (mentioned.includes(name)) row.className = "phm-ai-mentioned";
      const cell = element("td");cell.append(openButton(name));
      row.append(cell, element("td", format(previous)), element("td", format(value)), element("td", changeText(previous, value, name)));
      table.append(row);
    }
    return table;
  }
  function renderComparison() {
    summary.replaceChildren();
    const prior = steps.find((step) => step.position === comparisonPosition());
    const output = selectedStep?.output || {};
    const before = prior?.output || {};
    const valueKey = view === "rul" ? "estimate" : "score";
    const unit = view === "rul" ? output.unit === "acquisition-interval" ? "개 기록 구간" : output.unit || "단위 미기록" : "";
    summary.append(element("p", (view === "rul" ? "기록 종료까지 남은 구간 추정" : "모델 점수") + " · "
      + (prior ? format(before[valueKey]) + " → " : "") + format(output[valueKey]) + " " + unit
      + (prior ? " · " + stepText(prior.position) + " → " + stepText(position) : "")
      + (output.sequence_positions ? " · 입력 " + inputText(output, position) : "")));
    const names = Object.keys(selectedStep?.features || {});
    const difference = (name) => Math.abs((selectedStep.features[name] - (prior?.features?.[name] ?? selectedStep.features[name])))
      / Math.max(Math.abs(selectedStep.features[name]), Math.abs(prior?.features?.[name] || 0), 1e-12);
    const primary = (name) => /\.rms$|unbalance.*percent$/.test(name) ? 2 : /standard_deviation$|absolute_peak$|std_a$/.test(name) ? 1 : 0;
    names.sort((a, b) => primary(b) - primary(a) || difference(b) - difference(a) || a.localeCompare(b));
    // Features the answer names are always on screen, next to the five largest changes.
    const shown = names.filter((name, index) => index < 5 || mentioned.includes(name) || nextSignals.includes(name));
    const rest = names.filter((name) => !shown.includes(name));
    if (names.length) summary.append(element("p", "측정 특징 비교 · 두 시점의 관측값"), featureTable(shown, prior));
    else summary.append(element("p", "이 분석에는 저장된 측정 특징이 없습니다."));
    if (rest.length) {
      const more = element("details");more.className = "phm-options";
      more.append(element("summary", "나머지 측정 특징 " + rest.length + "개"), featureTable(rest, prior));summary.append(more);
    }
    if (options.openSignal && prior) {
      const open = element("button", "비교 시점의 원본 신호 보기");open.type = "button";
      open.addEventListener("click", () => options.openSignal(prior.position));summary.append(open);
    }
    if (prior) summary.append(rangeBox);
  }
  // How the values moved between the two ends, from every analyzed result in between.
  const rangeBox = element("div");rangeBox.className = "phm-range";
  const ranges = new Map();
  const moment = (at, text) => {
    const go = element("button", text);go.type = "button";
    if (options.openSignal) go.addEventListener("click", () => options.openSignal(at));else go.disabled = true;
    return go;
  };
  async function renderRange() {
    const from = comparisonPosition();
    rangeBox.replaceChildren();
    if (from === null) return;
    const rangeKey = from + ":" + position;
    try {
      if (!ranges.has(rangeKey)) ranges.set(rangeKey, await get("/api/v1/phm/range?binding_id=" + encodeURIComponent(bindingId) + "&from=" + from + "&to=" + position));
    } catch {rangeBox.append(element("p", "구간 흐름을 불러오지 못했습니다."));return;}
    if (!current() || comparisonPosition() !== from) return;
    const data = ranges.get(rangeKey);
    rangeBox.append(element("p", "구간 흐름 · " + stepText(from) + " → " + stepText(position) + " · 분석 " + data.steps + "개"
      + (data.sampled ? " · 흐름은 " + data.points + "개 표본, 최대 변화는 전체 기록" : "")));
    const table = element("table");table.className = "phm-table";
    const head = element("tr");for (const title of ["항목", "흐름", "수준이 바뀐 지점", "가장 큰 단일 변화"]) head.append(element("th", title));table.append(head);
    const rows = [[view === "rul" ? "잔여 구간 추정" : "모델 점수", data.primary],
      ...Object.entries(data.features).slice(0, 3).map(([name, shape]) => [label(name), shape])];
    for (const [title, shape] of rows) {
      const row = element("tr");
      const shift = element("td"), jump = element("td");
      if (shape.level_shift) shift.append(moment(shape.level_shift.at, stepText(shape.level_shift.at) + " " + STEP_ARROW[shape.level_shift.direction]));
      else shift.textContent = "—";
      if (shape.largest_step) jump.append(moment(shape.largest_step.to, stepText(shape.largest_step.from) + " → " + stepText(shape.largest_step.to) + " " + STEP_ARROW[shape.largest_step.direction]));
      else jump.textContent = "—";
      row.append(element("td", title), element("td", trendText(shape)), shift, jump);
      table.append(row);
    }
    rangeBox.append(table);
  }
  function renderAnswer(item) {
    answerBox.replaceChildren();
    const answer = item?.status === "complete" ? item.answer : null;
    mentioned = answer ? answer.observations.map((o) => o.feature) : [];
    nextSignals = answer ? answer.next_signals : [];
    renderComparison();
    if (!item || item.status !== "complete") return;
    if (!answer) {
      // Stored before answers were checked reference by reference.
      const legacy = element("p", item.text);legacy.className = "phm-ai-text";
      if (!item.warnings?.length) {answerBox.append(legacy);return;}
      const folded = element("details");folded.append(element("summary", "확인되지 않은 이전 응답 보기"), legacy);answerBox.append(folded);return;
    }
    const prior = steps.find((step) => step.position === comparisonPosition());
    const asked = element("p", item.context?.question || "");asked.className = "phm-answer-question";
    const text = element("p", answer.summary);text.className = "phm-ai-text";
    answerBox.append(asked, text);
    if (answer.observations.length) {
      const list = element("ul");list.className = "phm-answer-signals";
      for (const {feature, relation} of answer.observations) {
        const row = element("li");
        row.append(openButton(feature), element("span", ARROW[relation] || ""),
          element("strong", changeText(prior?.features?.[feature], selectedStep?.features?.[feature], feature)));
        list.append(row);
      }
      answerBox.append(element("h4", "함께 확인할 신호"), list);
    }
    if (answer.next_step || answer.next_signals.length) {
      answerBox.append(element("h4", "다음 탐색"));
      if (answer.next_step) answerBox.append(element("p", answer.next_step));
      if (answer.next_signals.length) {
        const next = element("div");next.className = "phm-answer-next";
        for (const feature of answer.next_signals) next.append(openButton(feature));
        answerBox.append(next);
      }
    }
    const related = item.context?.related_models || [];
    if (related.length) {
      const list = element("ul");list.className = "phm-answer-related";
      for (const other of related) {
        const key = other.output.task === "rul-estimate" ? "estimate" : "score";
        list.append(element("li", modelFamily(other.package_id, other.output.task, item.context.input_reference?.kind) + " · "
          + (other.previous_output ? format(other.previous_output[key]) + " → " : "") + format(other.output[key])
          + " · 입력 " + inputText(other.output, position)));
      }
      answerBox.append(element("h4", "같은 입력을 쓴 다른 모델"), list);
    }
    if (answer.checks?.summary_source && answer.checks.summary_source !== "model" && !answer.checks.model_unavailable) {
      answerBox.append(Object.assign(element("p", "확인되지 않은 문장은 빼고 저장된 비교로 채웠습니다."), {className: "muted"}));
    }
  }
  assistant.append(element("h3", "선택 시점의 변화 분석"), compareLabel, summary, questionLabel, generate, status, answerBox);
  renderComparison();
  renderRange();
  compare.addEventListener("change", () => {
    const url = new URL(location.href);url.searchParams.set("phm_compare", compare.value);
    window.history.replaceState(null, "", url);state.askedQuestion = null;state.explanation = null;renderAnswer(null);renderRange();refreshExplanation();});
  const review = element("button", "검토 요청");review.type = "button";
  const ack = element("button", "검토 확인");ack.type = "button";
  const close = element("button", "검토 종료");close.type = "button";
  const memoLabel = element("label", "검토 메모");const input = element("textarea");input.maxLength = 1000;
  input.setAttribute("aria-label", "검토 메모");memoLabel.append(input);
  const save = element("button", "메모 저장");save.type = "button";
  const history = element("div");history.className = "phm-review-history";
  const reviewHistory = element("details");reviewHistory.className = "phm-review-details";
  reviewHistory.append(element("summary", "검토 처리 이력 보기"), history);
  root.append(heading, reviewStatus, review, ack, close, memoLabel, save, reviewHistory);
  let finding = null, writable = false;
  for (const button of [generate, review, ack, close, save]) {button.disabled = true;button.hidden = true;}
  memoLabel.hidden = true;
  const url = (part) => "/api/v1/phm/" + part + "?binding_id=" + encodeURIComponent(bindingId) + "&position=" + position;
  async function refreshReview() {
    const data = await get(url("review"));if (!current()) return;
    finding = data.finding_id;
    const currentStep = data.status;
    // A review is a workflow, not three competing actions on the same screen.
    review.hidden = !writable || Boolean(finding);
    ack.hidden = !writable || !finding || currentStep !== "open";
    close.hidden = !writable || !finding || currentStep !== "acknowledged";
    save.hidden = !writable || !finding;
    memoLabel.hidden = !writable || !finding;
    review.disabled = review.hidden;ack.disabled = ack.hidden;
    close.disabled = close.hidden;save.disabled = save.hidden;
    const labels = {open: "검토 요청됨 · 확인 대기", acknowledged: "검토 확인됨 · 종료 가능",
      closed: "검토 완료"};
    const stateText = finding ? labels[currentStep] || "검토 상태를 확인할 수 없음" : "아직 검토 요청이 없습니다.";
    reviewStatus.textContent = stateText;
    history.replaceChildren(element("p", stateText));
    for (const event of data.events || []) history.append(element("p", event.action + (event.note ? " · " + event.note : "")));
  }
  async function refreshExplanation() {
    try {
      clearTimeout(state.timer);
      const selection = comparisonPosition(), asked = state.askedQuestion;
      const data = await get(url("explanations"));
      if (!current() || selection !== comparisonPosition() || asked !== state.askedQuestion) return;
      const item = data.explanations.find((item) => item.context?.signal_comparison?.previous_position === selection
        && (asked === null || item.context?.question === asked));state.explanation = item || null;
      if (item && asked === null) {question.value = item.context.question;state.askedQuestion = item.context.question;}
      renderAnswer(item);
      status.textContent = !item ? writable ? "측정 신호를 비교하거나 궁금한 점을 질문하세요." : "측정 신호 비교 · AI 질문은 감독형 Web에서 사용할 수 있습니다."
        : item.status === "pending" ? "선택한 두 시점의 신호와 모델 결과를 비교하고 있습니다."
        : item.status === "failed" ? "AI 설명을 사용할 수 없습니다. 분석 조회와 직접 검토는 계속할 수 있습니다."
        : item.answer?.checks?.model_unavailable ? "AI 응답 없음 · 저장된 비교로 답했습니다 · 선택 시점 " + stepName
        : "AI 분석 답변 · " + item.model + " · 선택 시점 " + stepName;
      question.disabled = !writable;generate.hidden = !writable;
      generate.disabled = !writable || Boolean(item && item.status === "pending");
      if (item && item.status === "pending" && !document.hidden && document.body.dataset.view === view) {
        state.timer = setTimeout(() => {state.timer = null;refreshExplanation();}, 1000);
      }
    } catch {if (current()) status.textContent = "AI 설명 조회 불가 · 모델 수치는 그대로 확인할 수 있습니다.";}
  }
  state.refresh = refreshExplanation;
  generate.addEventListener("click", async () => {
    if (!question.value.trim()) {question.focus();return;}
    pin();generate.disabled = true;state.askedQuestion = question.value.trim();
    state.explanation = null;renderAnswer(null);
    try {await post("/api/v1/phm/explanations/request", {binding_id: bindingId, position,
      compare_position: comparisonPosition(), question: state.askedQuestion});await refreshExplanation();}
    catch {if (current()) {status.textContent = "AI 설명 생성 불가 · 직접 검토는 계속할 수 있습니다.";generate.disabled = false;}}
  });
  review.addEventListener("click", async () => {
    pin();review.disabled = true;
    try {
      const explanationId = state.explanation && state.explanation.status === "complete" ? state.explanation.id : null;
      await post("/api/v1/phm/reviews/request", {binding_id: bindingId, position, explanation_id: explanationId});
      await refreshReview();
    } catch {if (current()) {status.textContent = "검토 요청을 기록할 수 없습니다.";review.disabled = false;}}
  });
  const action = async (name) => {
    if (!finding) return;
    try {await post("/api/v1/reviews/action", {finding_id: finding, action: name, note: input.value.trim()});input.value = "";await refreshReview();}
    catch {if (current()) status.textContent = "검토 기록을 저장할 수 없습니다.";}
  };
  ack.addEventListener("click", () => action("acknowledge"));close.addEventListener("click", () => action("close"));
  save.addEventListener("click", () => action("note"));
  session().then((auth) => {
    if (!current()) return;
    writable = auth.write_scope === "supervisor-owned-source-control";
    if (!writable) reviewStatus.after(Object.assign(element("p", "검토 기록은 감독형 Web에서만 바꿀 수 있습니다."), {className: "muted"}));
    refreshExplanation();refreshReview().catch(() => {reviewStatus.textContent = "검토 상태를 조회하지 못했습니다.";});
  });

}
