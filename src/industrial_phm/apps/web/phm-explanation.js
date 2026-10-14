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

// Warnings are numbers the stored result does not contain, or status verdicts it never makes.
function warningText(warnings) {
  const numbers = warnings.filter((item) => /^-?\d/.test(item));
  const claims = warnings.filter((item) => /^(내용|표현) 확인:/.test(item));
  const verdicts = warnings.filter((item) => !/^-?\d/.test(item) && !claims.includes(item));
  const parts = [];
  if (numbers.length) parts.push("근거 대조 경고: 저장된 분석에 없는 수치 " + numbers.join(", ") + " 가 설명에 포함되어 있습니다. 이 수치는 사용하지 마세요.");
  if (verdicts.length) parts.push("판정 표현 경고: 설명이 '" + verdicts.join("', '") + "'처럼 설비 상태를 판정했습니다. 저장된 분석은 정상·고장을 판정하지 않으므로 원본 신호로 사람이 확인하세요.");
  if (claims.length) parts.push(claims.join(" · "));
  return parts.join(" ");
}

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
  const text = element("p");text.className = "phm-ai-text";
  const grounding = element("p");grounding.className = "phm-ai-warning";grounding.setAttribute("role", "alert");
  const generate = element("button", "AI에 질문");generate.type = "button";
  const steps = options.steps || [];
  const selectedStep = steps.find((step) => step.position === position);
  const earlier = steps.filter((step) => step.position < position).slice(-128).reverse();
  const compareLabel = element("label", "비교 시점");
  const compare = element("select");compare.setAttribute("aria-label", "비교 시점");
  for (const step of earlier) {
    const item = element("option", options.stepLabel ? options.stepLabel(step.position) : "#" + step.position);
    item.value = String(step.position);compare.append(item);
  }
  if (!earlier.length) {compare.append(element("option", "이전 분석 없음"));compare.disabled = true;}
  compareLabel.append(compare);
  const questionLabel = element("label", "궁금한 점");
  const question = element("textarea");question.rows = 2;question.maxLength = 600;
  question.value = "이전 시점과 비교해 어떤 측정 신호가 함께 변했는지 설명해 주세요.";
  question.setAttribute("aria-label", "분석 질문");questionLabel.append(question);
  state.askedQuestion = null;
  const summary = element("div");summary.className = "phm-comparison";
  const comparisonPosition = () => earlier.length ? Number(compare.value) : null;
  const format = (value) => typeof value === "number" ? value.toLocaleString("ko-KR", {maximumSignificantDigits: 4}) : "—";
  function renderComparison() {
    summary.replaceChildren();
    const prior = steps.find((step) => step.position === comparisonPosition());
    const output = selectedStep?.output || {};
    const before = prior?.output || {};
    const valueKey = view === "rul" ? "estimate" : "score";
    const unit = view === "rul" && output.unit === "acquisition-interval" ? "개 기록 구간" : "";
    summary.append(element("p", (view === "rul" ? "기록 종료까지 남은 구간 추정" : "모델 점수") + " · "
      + (prior ? format(before[valueKey]) + " → " : "") + format(output[valueKey]) + " " + unit));
    const table = element("table");table.className = "phm-table";
    const head = element("tr");for (const title of ["측정 특징", "비교 시점", "선택 시점", "변화 (+ 증가 / − 감소)"]) head.append(element("th", title));table.append(head);
    const names = Object.keys(selectedStep?.features || {});
    const difference = (name) => Math.abs((selectedStep.features[name] - (prior?.features?.[name] ?? selectedStep.features[name])))
      / Math.max(Math.abs(selectedStep.features[name]), Math.abs(prior?.features?.[name] || 0), 1e-12);
    const primary = (name) => /\.rms$|unbalance.*percent$/.test(name) ? 2 : /standard_deviation$|absolute_peak$|std_a$/.test(name) ? 1 : 0;
    names.sort((a, b) => primary(b) - primary(a) || difference(b) - difference(a) || a.localeCompare(b));
    for (const name of names.slice(0, 5)) {
      const row = element("tr"), value = selectedStep.features[name], previous = prior?.features?.[name];
      const label = element("td");
      if (options.openSignal) {
        const open = element("button", options.featureLabel ? options.featureLabel(name) : name);open.type = "button";
        open.addEventListener("click", () => options.openSignal(position, name));label.append(open);
      } else label.textContent = options.featureLabel ? options.featureLabel(name) : name;
      row.append(label, element("td", format(previous)), element("td", format(value)),
        element("td", typeof previous === "number" ? format(value - previous) : "—"));table.append(row);
    }
    if (names.length) summary.append(element("p", "측정 특징 비교 · " + Math.min(names.length, 5) + "개 · 두 시점의 관측값"), table);
    else summary.append(element("p", "이 분석에는 저장된 측정 특징이 없습니다."));
    if (options.openSignal && prior) {
      const open = element("button", "비교 시점의 원본 신호 보기");open.type = "button";
      open.addEventListener("click", () => options.openSignal(prior.position));summary.append(open);
    }
  }
  assistant.append(element("h3", "선택 시점의 변화 분석"), compareLabel, summary, questionLabel, generate, status, grounding, text);
  renderComparison();
  compare.addEventListener("change", () => {state.askedQuestion = null;text.textContent = "";grounding.textContent = "";renderComparison();refreshExplanation();});
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
      text.textContent = item && item.status === "complete" ? item.text : "";
      grounding.textContent = item && item.status === "complete" ? warningText(item.warnings || []) : "";
      status.textContent = !item ? writable ? "측정 신호를 비교하거나 궁금한 점을 질문하세요." : "측정 신호 비교 · AI 질문은 감독형 Web에서 사용할 수 있습니다."
        : item.status === "pending" ? "선택한 두 시점의 신호와 모델 결과를 비교하고 있습니다."
        : item.status === "failed" ? "AI 설명을 사용할 수 없습니다. 분석 조회와 직접 검토는 계속할 수 있습니다."
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
