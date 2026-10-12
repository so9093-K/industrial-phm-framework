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

export function renderPhmExplanation(view, bindingId, position, pin = () => {}) {
  const root = document.getElementById(view + "-explanation");
  let state = states.get(view);
  const key = bindingId && position !== null ? bindingId + ":" + position : "";
  if (state && state.key === key) return;
  if (state) clearTimeout(state.timer);
  state = {key, timer: null, explanation: null};states.set(view, state);root.replaceChildren();
  if (!key) return;
  const current = () => states.get(view) === state;
  const heading = element("h3", "분석 #" + position + " · AI 설명과 사람 검토");
  const note = element("p", "AI 설명은 저장된 분석의 참고 해석입니다. 모델 수치와 분리되며 검토 종료는 정비 완료가 아닙니다.");note.className = "muted";
  const status = element("p", "저장된 설명을 조회 중입니다.");status.setAttribute("role", "status");
  const text = element("p");text.className = "phm-ai-text";
  const grounding = element("p");grounding.className = "phm-ai-warning";grounding.setAttribute("role", "alert");
  const generate = element("button", "AI 설명 생성");generate.type = "button";
  const review = element("button", "검토 요청");review.type = "button";
  const ack = element("button", "검토 확인");ack.type = "button";ack.disabled = true;
  const close = element("button", "검토 종료");close.type = "button";close.disabled = true;
  const label = element("label", "검토 메모");const input = element("textarea");input.maxLength = 1000;
  input.setAttribute("aria-label", "검토 메모");label.append(input);
  const save = element("button", "메모 저장");save.type = "button";save.disabled = true;
  const history = element("div");history.className = "phm-review-history";
  root.append(heading, note, generate, status, text, grounding, review, ack, close, label, save, history);
  let finding = null, writable = false;
  for (const button of [generate, review, ack, close, save]) button.disabled = true;
  const url = (part) => "/api/v1/phm/" + part + "?binding_id=" + encodeURIComponent(bindingId) + "&position=" + position;
  async function refreshReview() {
    const data = await get(url("review"));if (!current()) return;
    finding = data.finding_id;
    review.disabled = !writable || Boolean(finding);save.disabled = !writable || !finding;
    // FindingReviewStatus values are lowercase ("open", "acknowledged", "closed").
    ack.disabled = !writable || data.status !== "open";close.disabled = !writable || data.status !== "acknowledged";
    const label = {open: "검토 요청됨", acknowledged: "검토 확인됨", closed: "검토 종료 · 정비 완료 아님"};
    history.replaceChildren(element("p", finding ? "검토 상태: " + (label[data.status] || data.status) : "아직 사람 검토 요청이 없습니다."));
    for (const event of data.events || []) history.append(element("p", event.action + (event.note ? " · " + event.note : "")));
  }
  async function refreshExplanation() {
    try {
      const data = await get(url("explanations"));if (!current()) return;
      const item = data.explanations[0];state.explanation = item || null;
      text.textContent = item && item.status === "complete" ? item.text : "";
      grounding.textContent = item && item.status === "complete" && item.warnings && item.warnings.length
        ? "근거 대조 경고: 저장된 분석에 없는 수치 " + item.warnings.join(", ") + " 가 설명에 포함되어 있습니다. 이 수치는 사용하지 마세요."
        : "";
      status.textContent = !item ? "저장된 AI 설명이 없습니다. 직접 검토를 기록할 수 있습니다."
        : item.status === "pending" ? "선택한 분석의 AI 설명을 생성하고 있습니다. 분석은 계속 진행됩니다."
        : item.status === "failed" ? "AI 설명을 사용할 수 없습니다. 분석 조회와 직접 검토는 계속할 수 있습니다."
        : "AI 설명 · " + item.model + " · 저장된 분석 #" + item.position + " 참조";
      generate.disabled = !writable || Boolean(item && item.status === "pending");
      if (item && item.status === "pending" && document.body.dataset.view === view) {
        state.timer = setTimeout(refreshExplanation, 1000);
      }
    } catch {if (current()) status.textContent = "AI 설명 조회 불가 · 모델 수치는 그대로 확인할 수 있습니다.";}
  }
  generate.addEventListener("click", async () => {
    pin();generate.disabled = true;
    try {await post("/api/v1/phm/explanations/request", {binding_id: bindingId, position});await refreshExplanation();}
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
    if (!writable) note.textContent += " 기록 명령은 감독 실행 화면에서 사용할 수 있습니다.";
    refreshExplanation();refreshReview().catch(() => {});
  });

}
