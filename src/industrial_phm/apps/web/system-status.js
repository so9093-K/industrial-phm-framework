import { byId, create, clear, fmt, rows, withText, getJSON, presentError } from "./web-utils.js";
import { formatTime } from "./time.js";

// Local process/storage diagnostics are separate from sensor receipt and asset condition.
const runtimeConditions = {
  running: "실행 근거 있음",
  "not-ready": "프로세스 있음 · 준비 미확인",
  stale: "heartbeat 오래됨",
  stopped: "중지됨",
  failed: "실패 · 로그 확인 필요",
  unavailable: "상태 미확인",
};
const runtimeNames = {
  collection: "데이터 수집기",
  analysis: "분석 실행기",
  ui: "Web 화면",
};
let runtimeRequestSequence = 0;
export async function loadRuntimeStatus() {
  const token = ++runtimeRequestSequence;
  const state = byId("runtime-status");
  const facts = byId("runtime-facts");
  const components = byId("runtime-components");
  const button = byId("runtime-refresh");
  button.disabled = true;
  state.className = "state";
  state.textContent = "로컬 Supervisor·수집기·분석기·Web 상태를 확인하고 있습니다.";
  clear(facts); clear(components);
  try {
    const data = await getJSON("/api/v1/system/runtime");
    if (token !== runtimeRequestSequence) return;
    if (data.meaning !== "local-process-readiness-not-collection-receipt-or-asset-health"
        || typeof data.ready !== "boolean" || !data.supervisor
        || !Array.isArray(data.components) || data.components.length !== 3) {
      throw new Error("schema-mismatch");
    }
    const supervisor = data.supervisor;
    if (!Object.hasOwn(runtimeConditions, supervisor.condition)) throw new Error("schema-mismatch");
    state.className = data.ready ? "state" : "state error";
    state.textContent = data.ready
      ? "로컬 서비스가 실행 중입니다."
      : "로컬 서비스가 완전히 준비됐는지 확인되지 않습니다. 아래 구성 요소 상태를 확인하고 필요하면 CLI 로그를 조회하세요.";
    facts.append(
      withText("조회 시각", formatTime(data.assessed_at)),
      withText("Supervisor", runtimeConditions[supervisor.condition]),
      withText("Supervisor PID (조회 시점)", supervisor.pid),
      withText("Supervisor heartbeat", formatTime(supervisor.heartbeat_at)),
    );
    data.components.forEach((part) => {
      if (!Object.hasOwn(runtimeNames, part.kind)
          || !Object.hasOwn(runtimeConditions, part.condition)) throw new Error("schema-mismatch");
      const card = create("article", "source-record");
      card.append(
        create("strong", null, runtimeNames[part.kind] + " · " + runtimeConditions[part.condition]),
        create("span", null, "프로세스 PID: " + fmt(part.pid)),
        create("span", null, "프로세스별 런타임 상태: " + fmt(part.runtime_state)),
        create("span", null, "마지막 heartbeat: " + formatTime(part.heartbeat_at)),
      );
      components.append(card);
    });
  } catch (error) {
    if (token !== runtimeRequestSequence) return;
    state.className = "state error";
    state.textContent = "실행 상태 조회 실패 · 현재 서비스 상태를 알 수 없습니다. CLI operations status·logs에서 확인하세요. (" + presentError(error) + ")";
    clear(facts); clear(components);
  } finally {
    if (token === runtimeRequestSequence) button.disabled = false;
  }
}
export function systemViews(snapshot) {
  const status = byId("system-status");
  const details = byId("system-facts");
  clear(details);
  const scopes = Array.isArray(snapshot.system_error_scopes) ? snapshot.system_error_scopes : [];
  status.className = scopes.length ? "state error" : "state";
  status.textContent = scopes.length
    ? "일부 저장소 조회 범위에 오류가 있습니다. 표시되지 않은 관측·분석·검토 근거가 있을 수 있습니다."
    : "저장소를 정상적으로 읽었습니다.";
  details.append(
    withText("조회 시각", formatTime(snapshot.assessed_at)),
    withText("조회된 설비 수", snapshot.assets && snapshot.assets.total),
    withText("조회된 분석 기록 수", (snapshot.phase_unbalance_analyses?.total ?? 0) + (snapshot.file_feature_analyses?.total ?? 0)),
    withText("조회된 검토 요청 수", snapshot.review_requests && snapshot.review_requests.total),
  );
  if (scopes.length) details.append(withText("확인되지 않은 저장소 범위", scopes.join(", ")));
}
export function renderMonitorAttention(snapshot) {
  const target = byId("monitor-attention");
  clear(target);
  const entries = rows(snapshot, "attention");
  target.classList.toggle("hidden", !entries.length);
  if (!entries.length) {
    target.append(create("p", "muted", "확인할 운영 항목이 없습니다."));
    return;
  }
  target.append(create("h2", null, "운영 상태 확인 필요 · " + entries.length + "건"));
  entries.forEach((item) => {
    const record = create("div", "source-record");
    record.dataset.attentionId = item.attention_id;
    record.append(
      create("strong", null, fmt(item.title)),
      create("span", null, "상태: " + fmt(item.status) + " · 확인 화면: " + fmt(item.destination)),
      create("span", null, "설비: " + fmt(item.asset_id) + " · 소스: " + fmt(item.source_id))
    );
    target.append(record);
  });
}
