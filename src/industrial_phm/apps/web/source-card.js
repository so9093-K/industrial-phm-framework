import { assetName } from "./asset-context.js";
import { openMonitorAsset } from "./monitor.js";
import { navigate } from "./navigation.js";
import { formatTime } from "./time.js";

const node = (tag, text = "", className = "") => {
  const item = document.createElement(tag);
  item.textContent = text;
  if (className) item.className = className;
  return item;
};
const known = (value) => value == null || value === "" ? "미확인" : String(value);
const disclosures = new Map();

export function renderSourceCard(item, actions) {
  const card = node("article", "", "source-record");
  card.dataset.sourceId = item.source_id;
  const live = item.source_type === "opcua", job = item.file_history_job;
  const disconnected = live && item.opcua_session_last_state && String(item.opcua_session_last_state).toUpperCase() !== "CONNECTED";
  const stored = actions.stored || item.last_live_history_snapshot_id != null || job?.state === "succeeded";
  const status = item.live_telemetry_read_error ? "수신 상태 조회 실패"
    : live ? disconnected ? "현재 연결 미확인" : item.last_live_receive_fresh ? "수신 확인됨"
      : item.last_live_received_at ? "최근 수신 미확인"
      : item.receipt_confirmed ? "1회 수신 확인 · 연속 수신 미확인" : "수신 미확인"
    : item.receipt_confirmed ? "파일 읽기 확인됨" : "파일 확인 대기";
  card.append(node("strong", item.name), node("span", (live ? "OPC UA" : "CSV") + " · " + assetName(item.asset_id)),
    node("span", status, item.live_telemetry_read_error ? "error" : item.receipt_confirmed || item.last_live_receive_fresh ? "receipt-confirmed" : "receipt-missing"),
    node("span", "마지막 수신: " + formatTime(live ? item.last_live_received_at : item.last_accepted_received_at)));
  if (item.last_accepted_observed_at) {
    card.append(node("span", "원래 측정한 시각: " + formatTime(item.last_accepted_observed_at)));
    if (!live) card.append(node("span", "파일을 읽은 시각과 원래 측정한 시각은 다를 수 있습니다. 과거 측정 기록이 현재 설비 상태를 뜻하지는 않습니다.", "source-time-explanation"));
  }
  if (job?.state === "running") card.append(node("span", "측정 이력 저장 중"));
  if (["failed", "interrupted"].includes(job?.state)) card.append(node("span", "측정 이력 저장 " + (job.state === "failed" ? "실패" : "중단"), "error"));
  const primary = node("div", "", "source-actions source-primary");
  const secondary = node("div", "", "source-actions");
  const buttons = [];
  const action = (text, run, key) => {
    const button = node("button", text);
    button.type = "button";
    button.addEventListener("click", () => run(button));
    buttons.push({button, key});
  };
  const next = item.lifecycle_state !== "active" ? "activate" : live
    ? item.collection_desired_state === "running" ? "stop" : "start"
    : !item.receipt_confirmed ? "receive" : !stored ? "store" : null;
  const graph = node("button", "측정 신호 보기", "source-next");
  graph.type = "button";
  graph.addEventListener("click", () => {
    openMonitorAsset(item.asset_id, {sourceId: item.source_id});
    navigate("#monitor", document.getElementById("monitor-signal-title"));
  });
  primary.append(graph);
  if (item.lifecycle_state) {
    const activate = item.lifecycle_state !== "active";
    action(activate ? "이 연결 사용하기" : "연결 일시정지", (b) => actions.controlSource(item.source_id, "lifecycle", activate ? "active" : "paused", b), activate ? "activate" : "pause");
  }
  if (item.source_type === "file" && item.lifecycle_state === "active") {
    action("파일 읽기 확인", (b) => actions.receiveFile(item.source_id, b), "receive");
    if (item.receipt_confirmed) {
      action("측정 이력 저장", (b) => actions.backfillFile(item.source_id, b), "store");
      action("신호 통계 분석", (b) => actions.analyzeFile(item.source_id, b), "analyze");
      if (item.phase_binding_count >= 3) action("저장된 3상 이력 분석 실행", (b) => actions.analyzeFilePhase(item.source_id, b), "phase");
    }
  }
  if (live && item.lifecycle_state === "active") {
    action("OPC UA 1회 수신 진단", (b) => actions.diagnoseOpcua(item.source_id, b), "diagnose");
    if (item.continuous_collection_supported) {
      const start = item.collection_desired_state !== "running";
      action(start ? "수집 시작 요청" : "수집 중지 요청", (b) => actions.controlSource(item.source_id, "collection", start ? "running" : "stopped", b), start ? "start" : "stop");
    }
  }
  for (const {button, key} of buttons) (key === next ? primary : secondary).append(button);
  card.append(primary);
  const settings = node("details", "", "source-settings");
  settings.append(node("summary", "연결 설정"), node("p", "소스 ID: " + item.source_id), node("p", "관리 상태: " + known(item.lifecycle_state)), secondary);
  const diagnostic = node("details", "", "source-diagnostics");
  diagnostic.append(node("summary", "기술 진단 · 수집·저장 상태"), node("p", "원본 측정 시각: " + formatTime(item.last_accepted_observed_at)));
  if (live) {
    diagnostic.append(node("p", "연속 수집 요청: " + known(item.collection_desired_state) + " · 요청만 기록됨"),
      node("p", "요청 세대: " + known(item.collection_request_generation) + " · " + formatTime(item.collection_requested_at)),
      node("p", "수집 서비스: " + known(item.collection_service_state) + " · heartbeat " + formatTime(item.collection_service_heartbeat_at)),
      node("p", "OPC UA 세션 마지막 기록: " + known(item.opcua_session_last_state) + " · " + formatTime(item.opcua_session_state_changed_at)
        + (item.recent_connected_evidence ? " · 최근 연결 확인" : " · 현재 연결 미확인")),
      node("p", "OPC UA 이력 저장(DuckLake 커밋): " + formatTime(item.last_live_history_committed_at) + " · snapshot " + known(item.last_live_history_snapshot_id) + " · 소스 이벤트 " + known(item.last_live_history_batch_event_count)));
  } else if (job) diagnostic.append(node("p", "이력 저장 작업: " + job.state + " · 시작 " + formatTime(job.started_at) + " · 종료 " + formatTime(job.finished_at)));
  if (item.phase_binding_count) diagnostic.append(node("p", "등록된 3상 역할 " + item.phase_binding_count + "개"));
  const progress = node("ol", "", "source-progress");
  progress.setAttribute("aria-label", "단계별 처리 근거");
  for (const text of ["등록 확인", item.receipt_confirmed ? "검증 수신 확인" : "검증 수신 미확인", stored ? "저장 이력 근거 있음" : "저장 이력 미확인", actions.analyzed ? "분석 근거 있음" : "분석 근거 미확인"]) progress.append(node("li", text));
  diagnostic.append(progress);card.append(settings, diagnostic);
  const key = JSON.stringify([item.asset_id, item.source_id]);
  const expanded = disclosures.get(key) || {};
  settings.open = Boolean(expanded.settings);diagnostic.open = Boolean(expanded.diagnostic);
  for (const [name, disclosure] of [["settings", settings], ["diagnostic", diagnostic]]) disclosure.addEventListener("toggle", () => {
    if (disclosure.isConnected) disclosures.set(key, {...disclosures.get(key), [name]: disclosure.open});
  });
  return card;
}
