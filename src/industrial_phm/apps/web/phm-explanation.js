// Optional AI text and human disposition never modify persisted model numbers.
import { canChange, OPERATIONS_REQUIRED } from "./web-utils.js";
import { navigate } from "./navigation.js";

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

// Use the same session decision as the actual question form; comparison stays read-only.
function updateAssistantAction(view, state) {
  const action = document.getElementById(view + "-ask");
  action.disabled = !state?.key;
  action.textContent = state?.writable ? "이 변화 질문하기" : "측정값 비교 보기";
}
export function openPhmAssistant(view) {
  const state = states.get(view);
  if (!state?.key) return;
  const assistant = document.getElementById(view + "-assistant");
  navigate("#" + view, assistant.querySelector(state.writable ? "textarea" : ".phm-comparison-details > summary"));
}

export function renderPhmExplanation(view, bindingId, position, pin = () => {}, stepName = "#" + position, options = {}) {
  const root = document.getElementById(view + "-explanation");
  const assistant = document.getElementById(view + "-assistant");
  let state = states.get(view);
  const key = bindingId && position !== null ? bindingId + ":" + position : "";
  if (state && state.key === key) {
    updateAssistantAction(view, state);
    if (state.explanation?.status === "pending" && !state.timer) state.refresh?.();
    return;
  }
  if (state) clearTimeout(state.timer);
  state = {key, timer: null, explanation: null, writable: false};updateAssistantAction(view, state);states.set(view, state);root.replaceChildren();assistant.replaceChildren();
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
  const allEarlier = steps.filter((step) => step.position < position);
  const earlier = allEarlier.slice(-128).reverse();
  if (allEarlier.length > 128) earlier.push(allEarlier[0]);
  const label = (name) => options.featureLabel ? options.featureLabel(name) : name;
  const stepText = (at) => options.stepLabel ? options.stepLabel(at) : "#" + at;
  const shortText = (at) => options.shortLabel ? options.shortLabel(at) : "#" + at;
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
  question.setAttribute("aria-label", "분석 질문");question.disabled = true;questionLabel.hidden = true;questionLabel.append(question);
  // One click asks a question that the stored comparison can answer.
  const suggestions = element("div");suggestions.className = "phm-suggestions";suggestions.hidden = true;
  const rangeHint = element("p");rangeHint.className = "phm-question-scope";
  state.range = null;
  function renderSuggestions() {
    suggestions.replaceChildren();
    const from = comparisonPosition();
    const texts = from === null ? ["이 기록에서 어떤 측정값을 확인할 수 있어?"]
      : ["이전보다 어떤 측정값이 달라졌어?", "점수가 변할 때 어떤 측정값도 함께 변했어?"];
    if (state.focus) texts.unshift("이 지점 전후로 무엇이 달라졌어?");
    if (state.range?.steps >= 5) {
      texts.push("구간 전체에서 어떤 흐름을 보였어?");
      if ([state.range.primary, ...Object.values(state.range.features)].some((shape) => shape.level_shift)) texts.push("어느 지점에서 수준이 달라졌어?");
    }
    if (Object.keys(selectedStep?.output?.feature_contributions || {}).length) texts.push("모델은 어떤 특징을 크게 반영했어?");
    for (const text of texts) {
      const ask = element("button", text);ask.type = "button";ask.disabled = generate.disabled;
      ask.addEventListener("click", () => {question.value = text;generate.click();});suggestions.append(ask);
    }
    rangeHint.textContent = from === null ? "선택한 기록 한 시점에 대한 질문입니다."
      : "선택 구간 " + shortText(from) + " → " + shortText(position) + (state.range?.steps >= 5
        ? " · 분석 " + state.range.steps + "개를 비교합니다."
        : " · 두 시점의 차이를 비교합니다. 흐름과 변화 지점을 보려면 비교 시점을 앞당기세요.");
  }
  // A point picked in the range table is what "this point" means in the next question.
  const focusChip = element("p");focusChip.className = "phm-focus";focusChip.hidden = true;
  state.focus = null;
  function setFocus(at, what, series) {
    state.focus = at === null ? null : {position: at, what, series};
    focusChip.replaceChildren();focusChip.hidden = state.focus === null;
    renderSuggestions();
    if (state.focus === null) return;
    const clear = element("button", "✕");clear.type = "button";clear.setAttribute("aria-label", "질문 기준 지점 해제");
    clear.addEventListener("click", () => setFocus(null));
    focusChip.append(element("span", "질문 기준 지점 · " + shortText(at) + " · " + what), clear);
  }
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
    return sequence?.length ? shortText(sequence[0]) + "–" + shortText(sequence.at(-1)) + " (" + sequence.length + "회 측정)" : shortText(at) + " 한 입력";
  };
  const openButton = (name, text = label(name)) => {
    const open = element("button", text + " · " + shortText(position) + " 원본");open.type = "button";
    if (options.openSignal) open.addEventListener("click", () => options.openSignal(position, name));
    else open.disabled = true;
    return open;
  };
  function featureTable(names, prior) {
    const table = element("table");table.className = "phm-table phm-feature-comparison";table.setAttribute("aria-label", "측정 특징 비교");
    const head = element("tr");for (const title of ["측정 특징", "비교 시점", "선택 시점", "변화"]) head.append(element("th", title));table.append(head);
    for (const name of names) {
      const row = element("tr"), value = selectedStep.features[name], previous = prior?.features?.[name];
      if (mentioned.includes(name)) row.className = "phm-ai-mentioned";
      const cell = element("td");cell.append(openButton(name));
      const span = element("small", (prior ? shortText(prior.position) + " → " : "") + shortText(position));span.className = "phm-feature-span";cell.append(span);
      const before = element("td", format(previous)), after = element("td", format(value)), delta = element("td", changeText(previous, value, name));
      before.dataset.label = "비교 값";after.dataset.label = "선택 값";delta.dataset.label = "변화";
      row.append(cell, before, after, delta);
      table.append(row);
    }
    return table;
  }
  function renderComparison() {
    summary.replaceChildren();
    const prior = steps.find((step) => step.position === comparisonPosition());
    const output = selectedStep?.output || {};
    const before = prior?.output || {};
    summary.append(element("p", "모델 점수 · "
      + (prior ? format(before.score) + " → " : "") + format(output.score)
      + (prior ? " · " + shortText(prior.position) + " → " + shortText(position) : "")
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
      const open = element("button", shortText(prior.position) + "의 비교 원본 신호 확인");open.type = "button";
      open.addEventListener("click", () => options.openSignal(prior.position));summary.append(open);
    }
    if (prior) summary.append(rangeBox);
  }
  // How the values moved between the two ends, from every analyzed result in between.
  const rangeBox = element("div");rangeBox.className = "phm-range";
  const ranges = new Map();
  const moment = (at, text, what, series) => {
    const go = element("button", text + " · 원본 확인");go.type = "button";
    go.addEventListener("click", () => {setFocus(at, what, series);options.openSignal?.(at, series === "primary" ? undefined : series);});
    return go;
  };
  async function renderRange() {
    const from = comparisonPosition();
    state.range = null;renderSuggestions();rangeBox.replaceChildren();
    if (from === null) return;
    const rangeKey = from + ":" + position;
    try {
      if (!ranges.has(rangeKey)) ranges.set(rangeKey, await get("/api/v1/phm/range?binding_id=" + encodeURIComponent(bindingId) + "&from=" + from + "&to=" + position));
    } catch {if (current() && comparisonPosition() === from) rangeBox.append(element("p", "구간 흐름을 불러오지 못했습니다."));return;}
    if (!current() || comparisonPosition() !== from) return;
    const data = ranges.get(rangeKey);state.range = data;renderSuggestions();
    rangeBox.append(element("p", "구간 흐름 · " + shortText(from) + " → " + shortText(position) + " · 분석 " + data.steps + "개"
      + (data.sampled ? " · 흐름은 " + data.points + "개 표본, 최대 변화는 전체 기록" : "")));

    const table = element("table");table.className = "phm-table phm-range-table";table.setAttribute("aria-label", "구간 흐름");
    const head = element("tr");for (const title of ["항목", "흐름", "주요 지점"]) head.append(element("th", title));table.append(head);
    const rows = [["모델 점수", data.primary, "primary"],
      ...Object.entries(data.features).slice(0, 3).map(([name, shape]) => [label(name), shape, name])];
    for (const [title, shape, series] of rows) {
      const row = element("tr");
      const points = element("td");points.className = "phm-range-points";
      if (shape.level_shift) points.append(moment(shape.level_shift.at, "수준 변화 " + shortText(shape.level_shift.at) + " " + STEP_ARROW[shape.level_shift.direction], title + " 수준 변화", series));
      if (shape.largest_step) points.append(moment(shape.largest_step.to, "가장 큰 변화 " + shortText(shape.largest_step.from) + " → " + shortText(shape.largest_step.to) + " " + STEP_ARROW[shape.largest_step.direction], title + " 가장 큰 변화", series));
      if (!points.childElementCount) points.textContent = shape.trend === "insufficient" ? "변화 지점을 계산할 기록 부족" : "표시할 변화 지점 없음";
      const trend = element("td", trendText(shape));trend.className = "phm-range-trend";
      row.append(element("td", title), trend, points);
      table.append(row);
    }
    rangeBox.append(table);
    const explore = exploreLink(from, data);
    if (explore) rangeBox.append(explore);
  }
  // The same range in the signal exploration: before vs after the picked point, level shift
  // or middle, as period A and period B of stored measurements.
  function exploreLink(from, data) {
    const between = steps.filter((step) => step.position >= from && step.position <= position);
    const split = state.focus?.position ?? data.primary?.level_shift?.at ?? between[Math.floor(between.length / 2)]?.position;
    const before = between.filter((step) => step.position < split), after = between.filter((step) => step.position >= split);
    if (!before.length || !after.length || !options.stepKind) return null;
    const url = new URL(location.href);
    if (options.stepKind === "acquisition-snapshot") {
      url.searchParams.set("explore_kind", "acquisition");
      url.searchParams.set("explore_a", before[0].position + "~" + before.at(-1).position);
      url.searchParams.set("explore_b", after[0].position + "~" + after.at(-1).position);
      const features = [...new Set([...mentioned, ...Object.keys(data.features || {})])].filter((name) => name.startsWith("feature.")).slice(0, 6);
      if (features.length) url.searchParams.set("explore_series", features.join(","));
      else url.searchParams.delete("explore_series");
    } else {
      const start = (step) => step.event_start, end = (step) => step.event_end || step.event_start;
      if (!start(before[0]) || !start(after[0])) return null;
      url.searchParams.set("explore_kind", "history");url.searchParams.delete("explore_series");
      url.searchParams.set("explore_a", start(before[0]) + "~" + start(after[0]));
      url.searchParams.set("explore_b", start(after[0]) + "~" + end(after.at(-1)));
    }
    url.hash = "signals";
    const link = element("a", "구간 비교에서 자세히 보기 · A " + shortText(before[0].position) + "–" + shortText(before.at(-1).position)
      + " / B " + shortText(after[0].position) + "–" + shortText(after.at(-1).position));
    link.href = url.pathname + url.search + url.hash;link.className = "phm-explore-link";
    return link;
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
    answerBox.append(asked);
    if (item.context?.focus) answerBox.append(Object.assign(element("p", "기준 지점 · " + shortText(item.context.focus.position) + (item.context.focus.series ? " · " + (item.context.focus.series === "primary" ? "모델 점수" : label(item.context.focus.series)) : "")), {className: "phm-answer-question"}));
    answerBox.append(text);
    if (answer.observations.length) {
      const list = element("ul");list.className = "phm-answer-signals";
      for (const {feature, relation} of answer.observations) {
        const row = element("li");
        row.append(openButton(feature), element("span", ARROW[relation] || ""),
          element("strong", changeText(prior?.features?.[feature], selectedStep?.features?.[feature], feature)));
        list.append(row);
      }
      answerBox.append(element("h4", (prior ? shortText(prior.position) + " → " : "") + shortText(position) + "에서 함께 확인할 신호"), list);
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
        list.append(element("li", modelFamily(other.package_id, other.output.task, item.context.input_reference?.kind) + " · "
          + (other.previous_output ? format(other.previous_output.score) + " → " : "") + format(other.output.score)
          + " · 입력 " + inputText(other.output, position)));
      }
      const more = element("details");more.className = "phm-options";
      more.append(element("summary", "같은 입력을 쓴 다른 모델"), list);answerBox.append(more);
    }
    if (answer.checks?.summary_source && answer.checks.summary_source !== "model" && !answer.checks.model_unavailable) {
      answerBox.append(Object.assign(element("p", "확인되지 않은 문장은 빼고 저장된 비교로 채웠습니다."), {className: "muted"}));
    }
    // The earlier turns this answer continued: exactly what the model received.
    const earlier = item.context?.history || [];
    if (earlier.length) {
      const thread = element("details");thread.className = "phm-answer-thread";
      thread.append(element("summary", "이어서 답한 앞선 질문 " + earlier.length + "개"));
      for (const turn of earlier) {
        const block = element("div");
        block.append(Object.assign(element("p", turn.question), {className: "phm-answer-question"}), element("p", turn.answer));
        thread.append(block);
      }
      answerBox.append(thread);
    }
  }
  const details = element("details");details.className = "phm-options phm-comparison-details";
  details.append(element("summary", "측정값 비교·구간 흐름 자세히 보기"), summary);
  const assistantHeading = element("h3", "측정값 비교");
  const assistantHelp = element("p", "저장된 측정 신호와 모델 결과를 선택한 시점끼리 비교합니다.");
  assistantHelp.className = "phm-assistant-help";
  assistant.append(assistantHeading, assistantHelp, compareLabel, rangeHint, questionLabel, focusChip, suggestions, generate, status, answerBox, details);
  renderComparison();
  renderRange();
  compare.addEventListener("change", () => {
    const url = new URL(location.href);url.searchParams.set("phm_compare", compare.value);
    window.history.replaceState(null, "", url);state.askedQuestion = null;state.explanation = null;setFocus(null);renderAnswer(null);renderRange();refreshExplanation();});
  const review = element("button", "검토 요청");review.type = "button";
  const ack = element("button", "검토 확인");ack.type = "button";
  const close = element("button", "검토 종료");close.type = "button";
  const memoLabel = element("label", "검토 메모");const input = element("textarea");input.maxLength = 1000;
  input.setAttribute("aria-label", "검토 메모");memoLabel.append(input);
  const save = element("button", "메모 저장");save.type = "button";
  const history = element("div");history.className = "phm-review-history";
  const reviewHistory = element("details");reviewHistory.className = "phm-review-details";
  reviewHistory.append(element("summary", "검토 처리 이력 보기"), history);
  const reviewHelp = element("p");reviewHelp.className = "phm-review-help";
  root.append(heading, reviewStatus, reviewHelp, review, ack, close, memoLabel, save, reviewHistory);
  if (new URL(location.href).searchParams.get("phm_review") === "1") {
    document.getElementById(view + "-review-options").open = true;root.tabIndex = -1;
    root.focus({preventScroll: true});root.scrollIntoView({block: "center"});
    const url = new URL(location.href);url.searchParams.delete("phm_review");window.history.replaceState(null, "", url);
  }
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
    reviewHelp.textContent = !finding ? "이 분석 결과를 사람이 확인할 항목으로 기록합니다."
      : currentStep === "open" ? "검토 확인은 담당자가 이 분석 기록을 확인했음을 남깁니다."
      : "검토 종료는 분석 기록에 대한 확인 작업을 마치는 것입니다. 설비 정상 판정이나 정비 완료를 뜻하지 않습니다.";
    history.replaceChildren(element("p", stateText));
    for (const event of data.events || []) history.append(element("p", event.action + (event.note ? " · " + event.note : "")));
  }
  async function refreshExplanation() {
    generate.hidden = !writable;
    try {
      clearTimeout(state.timer);
      const selection = comparisonPosition(), asked = state.askedQuestion;
      const data = await get(url("explanations"));
      if (!current() || selection !== comparisonPosition() || asked !== state.askedQuestion) return;
      // Answers of this comparison, newest first; the shown one continues the earlier ones.
      const thread = data.explanations.filter((item) => item.context?.signal_comparison?.previous_position === selection);
      const item = thread.find((item) => asked === null || item.context?.question === asked);state.explanation = item || null;
      if (item && asked === null) {question.value = item.context.question;state.askedQuestion = item.context.question;}
      renderAnswer(item);
      status.textContent = !item ? writable ? "측정 신호를 비교하거나 궁금한 점을 질문하세요." : "측정 신호를 비교할 수 있습니다. AI 질문은 make up으로 운영을 시작한 화면에서 할 수 있습니다."
        : item.status === "pending" ? "선택한 두 시점의 신호와 모델 결과를 비교하고 있습니다."
        : item.status === "failed" ? "AI 설명을 사용할 수 없습니다. 분석 조회와 직접 검토는 계속할 수 있습니다."
        : item.answer?.checks?.model_unavailable ? "AI 응답 없음 · 저장된 비교로 답했습니다 · 선택 시점 " + stepName
        : "AI 분석 답변 · " + item.model + " · 선택 시점 " + stepName;
      question.disabled = !writable;questionLabel.hidden = !writable;generate.hidden = !writable;suggestions.hidden = !writable;
      for (const button of suggestions.querySelectorAll("button")) button.disabled = Boolean(item && item.status === "pending");
      generate.disabled = !writable || Boolean(item && item.status === "pending");
      if (item && item.status === "pending" && !document.hidden && document.body.dataset.view === view) {
        state.timer = setTimeout(() => {state.timer = null;refreshExplanation();}, 1000);
      }
    } catch {if (current()) status.textContent = "AI 설명 조회 불가 · 모델 수치는 그대로 확인할 수 있습니다.";}
  }
  state.refresh = refreshExplanation;
  generate.addEventListener("click", async () => {
    if (!question.value.trim()) {question.focus();return;}
    const previous = state.explanation?.status === "complete" && state.explanation.answer ? state.explanation.id : null;
    pin();generate.disabled = true;state.askedQuestion = question.value.trim();
    state.explanation = null;renderAnswer(null);
    try {await post("/api/v1/phm/explanations/request", {binding_id: bindingId, position,
      compare_position: comparisonPosition(), question: state.askedQuestion, ...(previous ? {parent_id: previous} : {}),
      ...(state.focus ? {focus_position: state.focus.position, focus_series: state.focus.series} : {})});await refreshExplanation();}
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
    writable = canChange(auth);state.writable = writable;
    updateAssistantAction(view, state);questionLabel.hidden = !writable;question.disabled = !writable;
    assistantHeading.textContent = writable ? "이 변화에 대해 질문하기" : "측정값 비교";
    if (!writable) reviewStatus.after(Object.assign(element("p", "검토 기록은 make up으로 운영을 시작한 화면에서 바꿀 수 있습니다."), {className: "muted"}));
    refreshExplanation();refreshReview().catch(() => {reviewStatus.textContent = "검토 상태를 조회하지 못했습니다.";});
  }).catch(() => {
    if (!current()) return;
    state.writable = false;updateAssistantAction(view, state);
    status.textContent = "질문 권한을 확인하지 못했습니다. 저장된 측정값은 비교할 수 있습니다.";
    refreshReview().catch(() => {reviewStatus.textContent = "검토 상태를 조회하지 못했습니다.";});
  });

}
