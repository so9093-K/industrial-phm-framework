import { byId, create, clear, fmt, getJSON, presentError, checkWorkspaceWriterConflict } from "./web-utils.js";
import { setAsset } from "./asset-context.js";
import { formatTime } from "./time.js";

// Explicit loopback browse/mapping/diagnostic; registration does not prove continuous receipt.
export function initializeOpcuaRegistration({loadSources, refresh}) {
  async function opcuaPost(path, payload) {
    const session = await getJSON("/api/v1/session");
    const response = await fetch(path, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      await checkWorkspaceWriterConflict(response);
      throw new Error("http-" + response.status);
    }
    const result = await response.json();
    if (result.schema_version !== 1) throw new Error("schema-mismatch");
    return result;
  }
  async function browseOpcua() {
    const endpoint = byId("opcua-endpoint").value.trim();
    const startNode = byId("opcua-browse-start").value.trim() || "i=85";
    const resultNode = byId("opcua-browse-result");
    const button = byId("browse-opcua");
    clear(resultNode);
    button.disabled = true;
    resultNode.textContent = "로컬 OPC UA 주소공간 탐색 중";
    try {
      const result = await opcuaPost("/api/v1/sources/opcua/browse",
        {endpoint_url: endpoint, start_node_id: startNode});
      if (result.meaning !== "address-space-candidates-not-received-or-registered"
          || !Array.isArray(result.variables) || !Array.isArray(result.objects)
          || result.start_node_id !== startNode) throw new Error("schema-mismatch");
      clear(resultNode);
      resultNode.append(create("p", "hint", "변수 후보 " + result.variables.length
        + "개 · 객체 후보 " + result.objects.length
        + "개 (탐색 노드 " + fmt(result.visited_node_count) + "개)"
        + (result.truncated ? " · 결과 일부만 표시 · 객체를 선택해 범위를 좁히세요" : "")
        + " · 수신 근거 아님"));
      result.objects.forEach((item) => {
        const row = create("p");
        const button = create("button", null, fmt(item.browse_name) + " 객체 내부 탐색");
        button.type = "button";
        button.addEventListener("click", () => {
          byId("opcua-browse-start").value = item.node_id;
          browseOpcua();
        });
        row.append(button, create("code", null, " " + fmt(item.node_id)));
        resultNode.append(row);
      });
      result.variables.forEach((item) => {
        const row = create("p");
        row.append(create("strong", null, fmt(item.display_name) + " · "),
          create("code", null, fmt(item.node_id)));
        resultNode.append(row);
      });
    } catch (error) {
      clear(resultNode);
      resultNode.append(create("p", "error", error.message === "http-400"
        ? "로컬 127.0.0.1 OPC UA 주소와 탐색 시작 NodeId를 확인하세요."
        : error.message === "workspace-writer-busy"
        ? presentError(error)
        : "탐색 실패 · 로컬 OPC UA 서버 실행 및 접속을 확인하세요. 수신 근거는 없습니다."));
    } finally {button.disabled = false;}
  }
  async function registerOpcua(event) {
    event.preventDefault();
    const form = byId("opcua-form"), button = byId("register-opcua");
    const resultNode = byId("opcua-register-result");
    const data = new FormData(form);
    const lines = String(data.get("node_mappings") || "").trim().split("\n");
    const mappings = lines.map((line) => {
      const sep = line.indexOf("=");
      return sep < 1 ? null : {
        channel_id: line.slice(0, sep).trim(), node_id: line.slice(sep + 1).trim(),
      };
    });
    if (!mappings.length || mappings.length > 12
        || mappings.some((x) => !x || !x.channel_id || !x.node_id)) {
      resultNode.className = "error";
      resultNode.textContent = "channel_id=NodeId 형식으로 1~12줄 입력하세요.";
      return;
    }
    const payload = {
      source_id: String(data.get("source_id") || "").trim(),
      name: String(data.get("name") || "").trim(),
      asset_id: String(data.get("asset_id") || "").trim(),
      measurement_point_id: String(data.get("measurement_point_id") || "").trim(),
      endpoint_url: String(data.get("endpoint_url") || "").trim(),
      node_mappings: mappings,
    };
    button.disabled = true;
    resultNode.className = "";
    resultNode.textContent = "매핑 등록 중";
    let saved = false;
    try {
      const result = await opcuaPost("/api/v1/sources/opcua", payload);
      if (result.registration_state !== "registered") throw new Error("schema-mismatch");
      saved = true;
      resultNode.textContent = "OPC UA " + result.source_id + " 등록 완료. 소스를 활성화하고 1회 수신 진단을 실행하세요.";
      form.reset();
    } catch (error) {
      resultNode.className = "error";
      resultNode.textContent = error.message === "workspace-writer-busy"
        ? presentError(error)
        : error.message === "http-409"
        ? "이미 등록된 소스 ID입니다."
        : "등록 실패 · 로컬 OPC UA 주소·NodeId·신호 매핑을 확인하세요.";
    } finally {button.disabled = false;}
    if (saved) await Promise.allSettled([loadSources(), refresh()]);
  }
  async function diagnoseOpcua(sourceId, button) {
    const output = byId("source-control-result");
    if (!window.confirm(sourceId + " · OPC UA 서버에 1회 연결·읽기를 시도합니다.\n성공한 경우에만 receipt가 기록됩니다. 연속 수집·저장 시계열·분석은 시작하지 않습니다.")) return;
    button.disabled = true;
    output.className = "";
    output.textContent = sourceId + " · OPC UA 실제 읽기 진단 중";
    try {
      const result = await opcuaPost("/api/v1/sources/opcua/diagnose", {source_id: sourceId});
      if (result.source_id !== sourceId
          || result.meaning !== "one-shot-opcua-read-not-continuous-collection-or-history"
          || !["succeeded", "failed", "skipped"].includes(result.cycle_state)) {
        throw new Error("schema-mismatch");
      }
      if (result.cycle_state === "succeeded" && result.accepted_new_receipt === true) {
        output.textContent = sourceId + " · OPC UA 1회 읽기/수신 근거 기록 완료 · 수신 "
          + formatTime(result.accepted_received_at) + " · 연속 수집·이력 저장 아님";
      } else {
        output.className = "error";
        output.textContent = sourceId + " · 읽기 진단 실패 · 범위 "
          + fmt(result.failure_scope) + " · 최근 저장된 receipt가 있다면 이번 진단 성공과 혼동하지 마세요.";
      }
    } catch (error) {
      output.className = "error";
      output.textContent = error.message === "workspace-writer-busy"
        ? presentError(error)
        : error.message === "http-409"
        ? "진단 불가 · ACTIVE OPC UA 소스 및 로컬 서버 주소를 확인하세요."
        : "진단 호출 실패 · 접속 상태와 작업공간을 확인하세요.";
    } finally {button.disabled = false;}
    await Promise.allSettled([loadSources(), refresh()]);
  }
  byId("opcua-form").addEventListener("submit", registerOpcua);
  byId("browse-opcua").addEventListener("click", browseOpcua);

  return {diagnoseOpcua};
}
