// Asset-first monitoring reads persisted facts; it never runs analysis or calls AI.
const POLL_MS = 3000;
const byId = (id) => document.getElementById(id);
const node = (tag, text = "", className = "") => {
  const e = document.createElement(tag);e.textContent = text;e.className = className;return e;
};
const time = (at) => at ? at.replace("T", " ").replace(/\.\d+/, "").replace(/\+00:00|Z/, " UTC") : "미확인";
const number = (n) => typeof n === "number" ? n.toLocaleString("ko-KR", {maximumFractionDigits: 3}) : "미확인";
const active = () => document.body.dataset.view === "monitor" && !document.hidden;
const labels = {processed: "최근 입력 처리됨", pending: "새 입력 분석 대기", warmup: "LSTM 입력 준비",
  rejected: "최근 입력 분석 거부", waiting: "확정된 입력 대기", unavailable: "모델 실행 불가"};
const reviews = {open: "검토 요청됨", acknowledged: "검토 확인됨", closed: "검토 종료됨 · 정비 완료 아님"};
const cards = new Map();
let timer = null, running = false, refreshRequested = false, readOperations;

function metric(label, text) {
  const e = node("article", "", "condition-card");e.append(node("span", label), node("strong", text));return e;
}
function detailLink(item) {
  const view = item.task === "rul-estimate" ? "rul" : "anomaly";
  const url = new URL(location.href);
  url.searchParams.set("phm_binding", item.binding_id);
  url.searchParams.set("phm_position", item.latest_analyzed.position);
  url.hash = view;
  return url.pathname + url.search + url.hash;
}
function modelRow(item, base) {
  const row = node("div", "", "monitor-model");row.dataset.bindingId = item.binding_id;
  const task = item.task === "rul-estimate" ? "RUL" : item.task === "anomaly-score" ? "이상 탐지" : "모델 종류 미확인";
  row.append(node("h4", task + " · " + (item.recipe_id || item.package_id)));
  row.append(node("p", "소스 " + item.source_id + (item.measurement_point_id ? " · 측정점 " + item.measurement_point_id : ""), "muted"));
  const delivered = item.latest_delivered, last = item.latest_analyzed;
  if (item.recorded_replay || delivered?.replay || last?.replay) row.append(node("span", "기록 재생 · 현장 수신 아님", "tag replay"));
  const status = node("p", labels[item.processing_state] || "처리 상태 미확인", "monitor-processing");
  row.append(status);
  if (item.processing_reason && item.processing_state !== "processed") row.append(node("p", item.processing_reason, "monitor-reason"));
  const source = (base.sources?.sources?.items || []).find((s) => s.source_id === item.source_id && s.asset_id === item.asset_id);
  row.append(node("p", "수신 상태: " + (base.errors.length ? "일부 수신 근거 조회 실패" : source
    ? source.continuous_collection_supported
      ? (source.last_live_receive_fresh ? "30초 이내 수신 근거 있음" : "최근 수신 미확인")
        + (source.recent_connected_evidence ? " · 최근 연결 근거 있음" : " · 현재 연결 미확인")
      : "FILE 수신·저장 이력 (연속 수신 근거 아님)" : "획득 파일 전달 · 연결 상태 근거 없음"), "muted"));
  if (source) row.append(node("p", "소스 수신 " + time(source.last_live_received_at || source.last_accepted_received_at), "muted"));
  row.append(node("p", (item.step_kind === "observation-window" ? "최신 확정 윈도우 " + time(delivered?.event_at) : "최신 입력 " + (delivered ? "#" + delivered.position : "없음"))
    + " · 저장 " + time(delivered?.delivered_at), "monitor-input"));
  if (!last) {row.append(node("p", "저장된 분석 결과 없음 · RUL 지원 여부는 연결된 모델로 확인합니다."));return row;}
  const stale = item.processing_state !== "processed";
  const output = last.output;
  const result = node("p", "", "monitor-output");
  result.append(node("strong", (stale ? "이전 마지막 분석" : "최근 저장된 분석") + " · "));
  if (item.task === "anomaly-score") {
    result.append(document.createTextNode("이상 점수 " + number(output.score) + " · 참고 기준 " + number(output.threshold)
      + (output.exceeds_threshold ? " 초과" : " 이하")));
  } else if (item.task === "rul-estimate") {
    result.append(document.createTextNode("RUL " + number(output.estimate) + " " + (output.unit === "acquisition-interval" ? "획득 간격" : output.unit || "단위 미확인")));
    row.append(node("p", "기록 종료점까지의 추정 · 실제 고장 시각·정비 기한 아님 · 신뢰구간 미검증", "muted"));
  } else result.append(document.createTextNode("결과 의미는 모델 정보에서 확인하세요."));
  row.append(result);
  row.append(node("p", "분석 " + (last.event_start ? time(last.event_start) : "#" + last.position) + " · 처리 " + time(last.processed_at), "monitor-analyzed"));
  const acceptance = item.validation?.acceptance;
  if (acceptance) row.append(node("p", "성능 검증: " + acceptance + " · 기준 비교는 설비 정상·고장 판정이 아닙니다.", "muted"));
  row.append(node("p", "이 분석의 검토: " + (base.reviewError ? "조회 실패" : reviews[item.latest_review_status] || "요청 없음"), "muted"));
  if (["anomaly-score", "rul-estimate"].includes(item.task)) {
    const link = node("a", item.task === "rul-estimate" ? "이 시점의 RUL 상세 보기" : "이 시점의 추세·원본 입력 보기", "monitor-detail-link");
    link.href = detailLink(item);link.dataset.bindingId = item.binding_id;row.append(link);
  }
  return row;
}
function render(data, base) {
  const state = byId("phm-monitor-state");
  state.className = "state";
  state.textContent = "3초 자동 조회 · 화면 확인 " + time(data.assessed_at) + " · 모델 " + data.items.length + "/" + data.total
    + (data.truncated ? "개 표시 · 추가 모델은 조회 범위 밖" : "개")
    + (base.errors.length ? " · 운영 수신 상태 일부 조회 실패" : "")
    + (data.review_read_error ? " · PHM 검토 저장소 조회 실패" : "");
  base.reviewError = data.review_read_error;
  const summary = byId("phm-monitor-summary");
  summary.replaceChildren(
    metric("데이터 수신", base.errors.length ? "조회 미확인" : "소스 " + (base.sources?.sources?.total ?? "미확인") + "개"),
    metric("분석 처리 · 표시 모델", "대기 " + data.items.filter((i) => ["pending", "warmup", "waiting"].includes(i.processing_state)).length
      + " · 거부/불가 " + data.items.filter((i) => ["rejected", "unavailable"].includes(i.processing_state)).length),
    metric("저장된 기준 비교 · 표시 모델", "마지막 분석 초과 " + data.items.filter((i) => i.latest_analyzed?.output.exceeds_threshold).length),
    metric("PHM 검토 기록 · 전체", data.review_read_error ? "조회 미확인" : "요청 " + data.reviews.open + " · 확인 " + data.reviews.acknowledged + " · 종료 " + data.reviews.closed),
  );
  const grouped = new Map();
  for (const item of data.items) {
    if (!grouped.has(item.asset_id)) grouped.set(item.asset_id, []);
    grouped.get(item.asset_id).push(item);
  }
  // Registered/history assets without PHM packages remain visible, rather than implying RUL support.
  for (const asset of base.monitor?.assets?.items || []) if (!grouped.has(asset.asset_id)) grouped.set(asset.asset_id, []);
  const root = byId("phm-monitor-assets");
  for (const [assetId, items] of grouped) {
    const key = JSON.stringify([items, base.errors, base.reviewError, (base.monitor?.assets?.items || []).find((a) => a.asset_id === assetId),
      (base.sources?.sources?.items || []).filter((s) => s.asset_id === assetId)]);
    if (cards.get(assetId)?.key === key) continue;
    const card = node("article", "", "monitor-asset");card.dataset.assetId = assetId;
    card.append(node("h3", assetId));
    for (const item of items) card.append(modelRow(item, base));
    if (items.length && !items.some((i) => i.task === "rul-estimate")) card.append(node("p", "RUL 연결 근거 없음 · 추정하지 않습니다.", "muted"));
    if (!items.length) card.append(node("p", "PHM 모델 연결 없음 · 이상 점수·RUL을 생성하지 않습니다."));
    const previous = cards.get(assetId)?.element;
    const focused = previous?.contains(document.activeElement) ? document.activeElement.dataset.bindingId : null;
    if (previous) previous.replaceWith(card);else root.append(card);
    cards.set(assetId, {key, element: card});
    if (focused) [...card.querySelectorAll("a")].find((a) => a.dataset.bindingId === focused)?.focus({preventScroll: true});
  }
  for (const [assetId, card] of cards) if (!grouped.has(assetId)) {card.element.remove();cards.delete(assetId);}
  if (!grouped.size) root.replaceChildren(node("p", "연결된 PHM 모델과 관측 설비가 없습니다. 데이터 연결 화면에서 준비 상태를 확인하세요."));
  else for (const empty of root.querySelectorAll(":scope > p")) empty.remove();
}
function schedule() {
  clearTimeout(timer);
  if (active()) timer = setTimeout(refreshMonitor, POLL_MS);
}
export async function refreshMonitor() {
  if (!active()) return;
  if (running) {refreshRequested = true;return;}
  running = true;clearTimeout(timer);
  try {
    const [response, base] = await Promise.all([
      fetch("/api/v1/phm/monitor", {cache: "no-store", signal: AbortSignal.timeout(5000)}), readOperations(),
    ]);
    const data = await response.json();
    if (!response.ok || data.schema_version !== 1 || !Array.isArray(data.items)) throw new Error("read_failed");
    if (active()) render(data, base);
    document.dispatchEvent(new CustomEvent("phm-monitor-count", {detail: data.total}));
  } catch {
    if (active()) {
      byId("phm-monitor-state").className = "state error";
      byId("phm-monitor-state").textContent = "PHM 조회 실패 · 이전 분석값을 현재 상태로 표시하지 않습니다. 자동으로 재조회합니다.";
      byId("phm-monitor-summary").replaceChildren();byId("phm-monitor-assets").replaceChildren();cards.clear();
    }
  } finally {
    running = false;
    if (refreshRequested) {refreshRequested = false;void refreshMonitor();} else schedule();
  }
}
export function initializeMonitor(read) {
  readOperations = read;
  const start = () => {clearTimeout(timer);if (active()) void refreshMonitor();};
  window.addEventListener("hashchange", start);
  document.addEventListener("visibilitychange", start);
  schedule();
}
