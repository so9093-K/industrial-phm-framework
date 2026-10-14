import { byId, create, getJSON } from "./web-utils.js";
import { navigate } from "./navigation.js";

export function initializeSyntheticDemo() {
  // Only the supervisor can launch a real synthetic process. An unknown command
  // outcome must be rechecked, never retried as another start automatically.
  let sampleRequestPending = false;
  let sampleSupervisorAvailable = false;
  let sampleStatusKind = "unknown";
  let sampleValidatedUrl = null;
  function setSampleState(value, message) {
    sampleStatusKind = value;
    const start = byId("sample-start"), stop = byId("sample-stop");
    const status = byId("sample-status"), open = byId("sample-open");
    start.disabled = sampleRequestPending || !sampleSupervisorAvailable || value !== "stopped";
    stop.disabled = sampleRequestPending || !sampleSupervisorAvailable || value !== "running";
    status.className = value === "unknown" ? "error" : "";
    status.textContent = message;
    open.classList.add("hidden");
    open.removeAttribute("href");
    if (value === "running" && sampleValidatedUrl) {
      open.href = sampleValidatedUrl;
      open.classList.remove("hidden");
    }
  }
  function showSampleState(payload) {
    if (payload.schema_version !== 1 || payload.synthetic !== true
        || !["running", "stopped"].includes(payload.state)) throw new Error("schema-mismatch");
    if (payload.state === "stopped") {
      sampleValidatedUrl = null;
      setSampleState("stopped", "격리 샘플이 실행 중이지 않습니다. 실제 작업공간은 변경되지 않았습니다.");
      return;
    }
    // Allow only the already checked, local loopback URL returned by the supervisor.
    if (payload.separate_workspace !== true || typeof payload.url !== "string"
        || !/^http:\/\/127\.0\.0\.1:\d{2,5}\/web\/$/.test(payload.url)
        || Number(payload.url.split("/")[2].split(":")[1]) > 65535) throw new Error("schema-mismatch");
    sampleValidatedUrl = payload.url;
    setSampleState("running", "격리 샘플 실행 중 · 별도 synthetic 작업공간 · 기존 데모 화면입니다.");
  }
  async function sampleCommand(action) {
    if (sampleRequestPending) return;
    sampleRequestPending = true;
    setSampleState("unknown", "데모 명령 응답을 확인하고 있습니다. 중복 실행하지 마세요.");
    byId("sample-refresh").disabled = true;
    try {
      const session = await getJSON("/api/v1/session");
      if (session.write_scope !== "supervisor-owned-source-control") {
        sampleSupervisorAvailable = false;
        setSampleState("unknown", "샘플은 감독형 Web에서만 실행할 수 있습니다. 이 화면은 읽기 전용입니다.");
        return;
      }
      sampleSupervisorAvailable = true;
      const response = await fetch("/api/v1/demo/synthetic/" + action, {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: "{}",
      });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => null);
        const code = errorBody && errorBody.error && errorBody.error.code;
        if (code === "command_outcome_unknown") throw new Error("outcome-unknown");
        throw new Error("http-" + response.status);
      }
      showSampleState(await response.json());
    } catch (error) {
      const explain = error.message === "outcome-unknown"
        ? "샘플 명령 결과를 확인할 수 없습니다. 시작·종료를 다시 보내지 말고 상태만 새로 확인하세요."
        : error.message === "schema-mismatch"
        ? "지원되지 않는 샘플 상태 응답입니다. 실제 데이터 연결로 처리하지 마세요."
        : "샘플 실행 상태 확인에 실패했습니다. 중복 요청 없이 상태 다시 확인을 이용하세요.";
      setSampleState("unknown", explain);
    } finally {
      sampleRequestPending = false;
      byId("sample-refresh").disabled = false;
      // Re-render button enabled state after the pending flag clears, but never
      // infer a successful command from a failed or incomplete transport.
      setSampleState(sampleStatusKind, byId("sample-status").textContent);
    }
  }
  byId("sample-start").addEventListener("click", () => {
    if (window.confirm("실제 작업공간과 분리된 synthetic 모터 데모를 새 로컬 프로세스로 시작합니다. 계속할까요?")) sampleCommand("start");
  });
  byId("sample-stop").addEventListener("click", () => {
    if (window.confirm("이 Web Supervisor가 시작한 격리 synthetic 데모를 중지합니다. 계속할까요?")) sampleCommand("stop");
  });
  byId("sample-refresh").addEventListener("click", () => sampleCommand("status"));
  document.addEventListener("isolated-example-request", async () => {
    byId("connection-progress").open = true;
    navigate("#connect", byId("sample-status"));
    await sampleCommand("status");
    if (sampleStatusKind === "stopped") await sampleCommand("start");
    if (sampleStatusKind === "running" && sampleValidatedUrl) {
      const url = new URL(sampleValidatedUrl);url.searchParams.set("return_to", location.origin + "/web/#monitor");
      location.assign(url);
    }
  });
  sampleCommand("status");

  getJSON("/api/v1/session").then((session) => {
    if (session.workspace_kind !== "synthetic-demo") return;
    const notice = create("section", "notice synthetic-context", "합성 예시 데이터 · 별도 작업공간 · 읽기 전용 ");
    const target = new URLSearchParams(location.search).get("return_to");
    if (target && /^http:\/\/127\.0\.0\.1:\d{2,5}\/web\/#monitor$/.test(target)) {
      const link = create("a", null, "내 작업공간으로 돌아가기");link.href = target;notice.append(link);
    }
    byId("phm-monitor").before(notice);
  }).catch(() => {});

}
