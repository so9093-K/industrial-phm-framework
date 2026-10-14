import { initializeFileRegistration } from "./file-registration.js";
import { initializeOpcuaRegistration } from "./opcua-registration.js";
import { byId, create, clear, fmt, rows, empty, getJSON, presentError, checkWorkspaceWriterConflict } from "./web-utils.js";
import { setAsset } from "./asset-context.js";
import { navigate } from "./navigation.js";
import { formatTime } from "./time.js";
import { renderSourceCard } from "./source-card.js";

// Source forms, protected commands and explicit progress; current monitor facts come from the app.
export function createSourceManagement({getMonitor, sourceHistory, onSourceRead, refresh, openSavedAnalysis}) {
  // Source reads can overlap after control actions. Only the newest successful read
  // may decide whether the operator sees an evidence-backed Monitor handoff.
  let sourcesRequestSequence = 0;
  let connectionTargetHandled = false;
  let selectedOnboardingSourceId = "";
  let onboardingSources = [];
  let onboardingIncomplete = false;
  function onboardingStepFor(source) {
    if (["registered", "paused", "error"].includes(source.lifecycle_state)) {
      return ["이 연결 사용하기", "현재 관리 상태는 " + source.lifecycle_state
        + "입니다."];
    }
    if (source.lifecycle_state !== "active") {
      return [null, "관리 상태가 확인되지 않았습니다. 상태를 새로 조회하세요."];
    }
    if (source.source_type === "file") {
      const savedAnalysis = [...rows(getMonitor(), "file_feature_analyses"), ...rows(getMonitor(), "phase_unbalance_analyses")]
        .some((run) => run.source_id === source.source_id);
      if (savedAnalysis) return [null, "저장된 분석이 있습니다. 설비의 분석 기록 탭에서 볼 수 있습니다."];
      if (sourceHistory.has(source.source_id)) return ["신호 통계 분석", "측정 이력이 저장됐습니다. 신호 통계 분석을 실행할 수 있습니다."];
      return source.receipt_confirmed
        ? ["측정 이력 저장", "수신을 확인했습니다. 측정 이력을 저장하면 모니터링에서 그래프로 볼 수 있습니다."]
        : ["파일 읽기 확인", "활성화됐습니다. 다음은 CSV 수신 확인입니다."];
    }
    if (source.source_type === "opcua") {
      if (!source.receipt_confirmed) {
        return ["OPC UA 1회 수신 진단", "OPC UA 서버에서 한 번 읽어 연결을 확인하세요."];
      }
      if (source.collection_desired_state !== "running") {
        return ["수집 시작 요청", "연결을 확인했습니다. 연속 수집을 시작할 수 있습니다."];
      }
      return [null, "수집을 요청했습니다. 수신 상태는 모니터링에서 볼 수 있습니다."];
    }
    return [null, "이 소스 유형은 화면에서 다음 작업을 안내할 수 없습니다."];
  }
  function updateSourceProgress() {
    byId("source-list").querySelectorAll(".source-record[data-source-id]").forEach((card) => {
      const source = onboardingSources.find((item) => item.source_id === card.dataset.sourceId);
      const progress = card.querySelector(".source-progress");
      if (!source || !progress) return;
      const analyzed = [...rows(getMonitor(), "file_feature_analyses"), ...rows(getMonitor(), "phase_unbalance_analyses")]
        .some((run) => run.source_id === source.source_id);
      progress.children[2].textContent = sourceHistory.has(source.source_id) || source.last_live_history_snapshot_id != null
        || source.file_history_job?.state === "succeeded"
        ? "저장 이력 근거 있음" : "저장 이력 미확인";
      progress.children[3].textContent = analyzed ? "분석 근거 있음" : "분석 근거 미확인";
    });
  }
  function renderOnboardingGuide() {
    updateSourceProgress();
    const selector = byId("onboarding-source-select");
    const detail = byId("onboarding-action-detail");
    const button = byId("onboarding-action");
    clear(selector);
    const none = !onboardingSources.length;
    if (none) {
      const option = create("option", null, "등록된 소스 없음");
      option.value = "";
      selector.append(option);
      selector.disabled = true;
      selectedOnboardingSourceId = "";
      button.disabled = false;
      button.textContent = "CSV 등록 양식으로 이동";
      detail.textContent = "첫 단계: 준비된 CSV를 등록하거나 아래의 로컬 OPC UA 등록 양식을 이용하세요. 파일은 작업공간 내부에 있어야 합니다.";
      return;
    }
    onboardingSources.forEach((source) => {
      const option = create("option", null, source.name + " · " + source.source_id + " (" + source.asset_id + ")");
      option.value = source.source_id;
      selector.append(option);
    });
    selector.disabled = false;
    if (!onboardingSources.some((item) => item.source_id === selectedOnboardingSourceId)) {
      selectedOnboardingSourceId = onboardingSources[0].source_id;
    }
    selector.value = selectedOnboardingSourceId;
    const item = onboardingSources.find((source) => source.source_id === selectedOnboardingSourceId);
    if (!item) return;
    const [action, next] = onboardingStepFor(item);
    detail.textContent = "소스 " + item.source_id + " · " + next
      + (onboardingIncomplete ? " 일부 수신 근거 조회 오류가 있어 현재 상태를 확정할 수 없습니다." : "");
    button.textContent = action ? action + " 버튼 찾기" : "분석·관측 근거 확인";
    button.disabled = !action && item.lifecycle_state !== "active";
  }
  function scrollToOnboardingTarget(target, hash) {
    if (!target) {
      byId("onboarding-action-detail").textContent =
        "해당 작업 버튼이 현재 목록에 없습니다. 소스 목록을 새로 조회하세요.";
      return;
    }
    navigate(hash, target);
  }
  byId("onboarding-source-select").addEventListener("change", (event) => {
    selectedOnboardingSourceId = event.target.value;
    renderOnboardingGuide();
  });
  byId("onboarding-action").addEventListener("click", () => {
    const item = onboardingSources.find((source) => source.source_id === selectedOnboardingSourceId);
    if (!item) {
      scrollToOnboardingTarget(byId("csv-start-file"), "#connect");
      return;
    }
    const [action] = onboardingStepFor(item);
    if (!action) {
      const hasAnalysis = [...rows(getMonitor(), "file_feature_analyses"), ...rows(getMonitor(), "phase_unbalance_analyses")]
        .some((run) => run.source_id === item.source_id);
      setAsset(item.asset_id);
      scrollToOnboardingTarget(byId("asset-switch"), hasAnalysis ? "#evidence" : "#signals");
      return;
    }
    const card = [...byId("source-list").querySelectorAll(".source-record")]
      .find((element) => element.dataset.sourceId === item.source_id);
    const target = card && [...card.querySelectorAll(".source-actions button")]
      .find((element) => element.textContent === action);
    scrollToOnboardingTarget(target, "#connect");
  });
  function setOnboardingUnknown(message) {
    onboardingSources = [];
    const selector = byId("onboarding-source-select");
    clear(selector);
    selector.disabled = true;
    byId("onboarding-action").disabled = true;
    byId("onboarding-action-detail").textContent = message;
    byId("onboarding-monitor-link").classList.add("hidden");
    const steps = byId("onboarding-steps");
    clear(steps);
    steps.append(create("li", null, message));
    byId("onboarding-next").textContent =
      "수신 준비 여부를 확인할 수 없습니다.";
  }
  function setOnboardingEvidence(items, data, evidenceReadError) {
    const steps = byId("onboarding-steps");
    const handoff = byId("onboarding-monitor-link");
    const next = byId("onboarding-next");
    clear(steps);
    handoff.classList.add("hidden");
    const active = items.filter((item) => item.lifecycle_state === "active").length;
    const accepted = items.filter((item) => item.receipt_confirmed === true).length;
    const ready = items.filter((item) =>
      item.lifecycle_state === "active" && item.receipt_confirmed === true).length;
    [
      "등록된 소스: " + data.sources.total + "개",
      "사용 중(active): " + active + "개",
      "수신 확인: " + accepted + "개 · 사용 중이면서 수신을 확인한 소스 " + ready + "개",
    ].forEach((line) => steps.append(create("li", null, line)));
    if (data.sources.truncated || evidenceReadError) {
      next.textContent = "소스 목록 일부 또는 live 수신 근거를 완전히 읽지 못했습니다. "
        + "준비 여부를 확정할 수 없으므로 조회 범위와 저장소 상태를 확인하세요.";
    } else if (!items.length) {
      next.textContent = "다음: FILE CSV 또는 로컬 OPC UA 소스를 등록하세요.";
    } else if (!active) {
      next.textContent = "다음: 등록된 소스를 활성화하세요. 일시정지 상태는 준비 완료가 아닙니다.";
    } else if (!ready) {
      next.textContent = "다음: 사용 중인 소스에서 수신을 확인하세요. 일시정지 상태는 준비 완료가 아닙니다.";
    } else {
      next.textContent = "수신이 확인됐습니다. 모니터링에서 측정값을 볼 수 있습니다.";
      handoff.classList.remove("hidden");
    }
  }

  async function loadSources() {
    const token = ++sourcesRequestSequence;
    onSourceRead("loading");
    const state = byId("source-status"), list = byId("source-list");
    state.textContent = "저장된 등록 상태를 조회 중입니다.";
    byId("onboarding-monitor-link").classList.add("hidden");
    byId("onboarding-next").textContent = "등록·수신 상태를 다시 확인 중입니다.";
    clear(list);
    try {
      const data = await getJSON("/api/v1/sources");
      if (token !== sourcesRequestSequence) return;
      onSourceRead("ready", data);
      const items = rows(data, "sources");
      const entry = byId("csv-entry");
      if (items.length && entry.dataset.userOpened !== "true" && !entry.contains(document.activeElement)
          && !byId("csv-start-file").files.length) entry.open = false;
      if (data.read_error_scopes && data.read_error_scopes.length) {
        state.textContent = "일부 소스 저장소를 읽지 못했습니다. 등록 상태와 수신 근거를 확정할 수 없습니다.";
        state.className = "state error";
        byId("onboarding-state").textContent = "조회 실패 · 등록이나 수신이 없다고 단정할 수 없습니다.";
        byId("onboarding-state").className = "notice error";
        setOnboardingUnknown("소스 저장소 조회 오류 · 준비 여부 미확인");
        return;
      }
      const evidenceReadError = Array.isArray(data.live_evidence_error_scopes)
        && data.live_evidence_error_scopes.length > 0;
      state.className = evidenceReadError ? "state error" : "state";
      const received = items.filter((item) => item.receipt_confirmed).length;
      const liveReceived = items.filter((item) => item.source_type === "opcua"
        && item.last_live_receive_fresh && item.recent_connected_evidence).length;
      const summary = "검증 수신 확인 " + received + "개 · 최근 연속 수신 확인 " + liveReceived + "개";
      if (!items.length) {
        state.textContent = "등록된 소스가 없습니다. 작업공간에 CSV 또는 이 화면에서 로컬 OPC UA 소스를 등록하세요.";
        empty(list, "데이터 수신을 확인할 등록 소스가 없습니다.");
        byId("onboarding-state").textContent = "1단계 · 소스 미등록 — FILE CSV 또는 로컬 OPC UA 소스를 등록하세요.";
      } else {
        state.textContent = "등록된 연결 " + data.sources.total + "개"
          + (evidenceReadError ? " · 일부 수신 상태 조회 실패" : "");
        byId("onboarding-state").textContent = "등록 " + data.sources.total + "개 · "
          + summary
          + (evidenceReadError ? " · live 근거 일부 미확인" : "");
      }
      byId("onboarding-state").className = "";
      setOnboardingEvidence(items, data, evidenceReadError);
      onboardingSources = items;
      onboardingIncomplete = evidenceReadError || Boolean(data.sources.truncated);
      renderOnboardingGuide();
      for (const item of items) list.append(renderSourceCard(item, {
        stored: sourceHistory.has(item.source_id),
        analyzed: [...rows(getMonitor(), "file_feature_analyses"), ...rows(getMonitor(), "phase_unbalance_analyses")]
          .some((run) => run.source_id === item.source_id),
        controlSource, receiveFile, backfillFile, analyzeFile, analyzeFilePhase, diagnoseOpcua,
      }));
      updateSourceProgress();
      const params = new URLSearchParams(location.search), asset = params.get("connect_asset"), source = params.get("connect_source");
      if (!connectionTargetHandled && asset && document.body.dataset.view === "connect") {
        connectionTargetHandled = true;setAsset(asset);
        const cards = [...list.querySelectorAll(".source-record")];
        const target = cards.find((card) => items.some((item) => item.source_id === card.dataset.sourceId && item.asset_id === asset && (!source || item.source_id === source)));
        if (target) {target.tabIndex = -1;target.classList.add("source-target");target.querySelector(".source-diagnostics").open = true;navigate("#connect", target);}
        else {state.tabIndex = -1;state.textContent += " · 선택한 연결을 찾지 못했습니다. 등록된 연결을 확인하세요.";navigate("#connect", state);}
      }
      if (data.sources.truncated) list.append(create("p", "hint", "소스 100건만 표시됩니다."));
    } catch (error) {
      if (token !== sourcesRequestSequence) return;
      state.textContent = presentError(error);
      state.className = "state error";
      onSourceRead("error", null);
      byId("onboarding-state").textContent = "소스 조회 실패 — 등록 여부와 수신 근거를 확인할 수 없습니다.";
      byId("onboarding-state").className = "notice error";
      setOnboardingUnknown("소스 조회 실패 · 등록·수신 상태를 알 수 없음");
    }
  }

  async function controlSource(sourceId, action, target, button) {
    const result = byId("source-control-result");
    const verb = action === "collection" ? "수집 상태 요청" : "관리 상태 변경";
    const confirmation = action === "collection"
      ? "이 요청은 기존 수집 서비스에 원하는 상태를 기록합니다. 실제 수집 성공이나 측정값 수신을 확인하는 동작이 아닙니다."
      : "이 변경은 소스의 관리 상태만 바꾸며 연결·수집 성공을 보장하지 않습니다.";
    if (!window.confirm(sourceId + " · " + verb + " (" + target + ")\n" + confirmation)) return;
    button.disabled = true;
    result.className = "";
    result.textContent = "소스 " + sourceId + " · " + verb + "을(를) 저장 중입니다.";
    let savedState = false;
    try {
      const session = await getJSON("/api/v1/session");
      const url = action === "collection" ? "/api/v1/sources/collection" : "/api/v1/sources/lifecycle";
      const response = await fetch(url, {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: JSON.stringify({source_id: sourceId, target_state: target}),
      });
      if (!response.ok) {
        await checkWorkspaceWriterConflict(response);
        if (response.status === 409) throw new Error("control-conflict");
        if (response.status === 404) throw new Error("source-missing");
        if (response.status === 400) throw new Error("control-invalid");
        throw new Error("http-" + response.status);
      }
      const saved = await response.json();
      if (saved.schema_version !== 1 || saved.source_id !== sourceId) throw new Error("schema-mismatch");
      savedState = true;
      result.textContent = sourceId + " · " + verb + " 저장됨 · "
        + (action === "collection" ? "수집 요청만 기록됨 · 실제 수신 미확인" : "관리 상태 변경됨 · 연결 확인 아님");
    } catch (error) {
      result.className = "error";
      if (error.message === "control-conflict") {
        result.textContent = "상태 변경 불가 · 관리 상태와 소스 유형을 확인하고 다시 조회하세요.";
      } else if (error.message === "source-missing") {
        result.textContent = "등록되지 않은 소스입니다. 목록을 다시 조회하세요.";
      } else if (error.message === "control-invalid") {
        result.textContent = "잘못된 상태 요청입니다. 목록을 새로 불러오세요.";
      } else {
        result.textContent = presentError(error);
      }
    } finally {
      button.disabled = false;
    }
    if (savedState) {
      // A failed follow-up read cannot undo a successfully persisted control request.
      await Promise.allSettled([loadSources(), refresh()]);
    }
  }

  async function receiveFile(sourceId, button) {
    const result = byId("source-control-result");
    if (!window.confirm(sourceId + " · 파일을 다시 읽고 결과를 기록합니다.\n측정 이력 저장·연속 수집·분석은 별도입니다.")) return;
    button.disabled = true;
    result.className = "";
    result.textContent = sourceId + " · 파일 읽기 확인 중";
    let accepted = false;
    try {
      const session = await getJSON("/api/v1/session");
      const response = await fetch("/api/v1/sources/file/receive", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: JSON.stringify({source_id: sourceId}),
      });
      if (!response.ok) {
        await checkWorkspaceWriterConflict(response);
        if (response.status === 409) throw new Error("control-conflict");
        if (response.status === 404) throw new Error("source-missing");
        if (response.status === 400) throw new Error("control-invalid");
        throw new Error("http-" + response.status);
      }
      const outcome = await response.json();
      if (outcome.schema_version !== 1 || outcome.source_id !== sourceId
          || !["succeeded", "failed", "skipped"].includes(outcome.cycle_state)) {
        throw new Error("schema-mismatch");
      }
      accepted = outcome.cycle_state === "succeeded" && outcome.accepted_new_receipt === true;
      result.className = accepted ? "" : "error";
      result.textContent = accepted
        ? sourceId + " · 파일 읽기 확인 완료 · 측정 이력 저장은 별도"
        : sourceId + " · 파일 읽기 확인 실패 (" + fmt(outcome.failure_scope) + ") · 저장된 수신 근거를 다시 확인하세요.";
    } catch (error) {
      result.className = "error";
      if (error.message === "control-conflict") {
        result.textContent = "파일을 읽을 수 없습니다. 이 연결을 사용 중인지, CSV 경로가 작업공간 안에 있는지 확인하세요.";
      } else if (error.message === "source-missing") {
        result.textContent = "등록되지 않은 소스입니다. 목록을 다시 조회하세요.";
      } else {
        result.textContent = presentError(error);
      }
    } finally {
      button.disabled = false;
    }
    await Promise.allSettled([loadSources(), refresh()]);
  }

  async function analyzeFile(sourceId, button, output = byId("source-control-result")) {
    button.disabled = true;
    output.className = "";
    output.textContent = sourceId + " · 신호 통계 분석 중";
    try {
      const session = await getJSON("/api/v1/session");
      if (session.write_scope !== "supervisor-owned-source-control") throw new Error("read-only");
      const response = await fetch("/api/v1/analysis/file", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: JSON.stringify({source_id: sourceId}),
      });
      if (!response.ok) {
        await checkWorkspaceWriterConflict(response);
        const errorBody = await response.json().catch(() => null);
        const code = errorBody && errorBody.error && errorBody.error.code;
        if (code === "command_outcome_unknown") throw new Error("outcome-unknown");
        if (response.status === 409) throw new Error("analysis-conflict");
        if (response.status === 400) throw new Error("analysis-input-invalid");
        throw new Error("http-" + response.status);
      }
      const saved = await response.json();
      if (saved.schema_version !== 1 || saved.source_id !== sourceId
          || saved.meaning !== "persisted-file-statistical-features-not-diagnosis-or-history"
          || typeof saved.analysis_run_id !== "string" || !saved.analysis_run_id
          || typeof saved.evidence_id !== "string" || !saved.evidence_id
          || typeof saved.source_snapshot_sha256 !== "string") throw new Error("schema-mismatch");
      output.textContent = sourceId + " · 신호 통계 분석 저장 완료";
      await refresh();
      openSavedAnalysis(saved, "file_feature_analyses");
    } catch (error) {
      output.className = "error";
      output.textContent = error.message === "outcome-unknown"
        ? "분석 명령 결과가 불명확합니다. 다시 실행하지 말고 저장된 분석 목록을 새로 조회하세요."
        : error.message === "analysis-conflict"
        ? "분석 불가 · 활성 FILE, 검증 수신 및 1MiB 이하 원본 파일을 확인하세요."
        : error.message === "analysis-input-invalid"
        ? "분석 불가 · 시간대가 포함된 시각 컬럼, 서로 다른 값이 있는 두 개 이상 표본과 유한한 수치를 확인하세요."
        : error.message === "read-only"
        ? "신규 분석은 감독형 Web에서만 실행할 수 있습니다."
        : presentError(error);
    } finally {
      button.disabled = false;
    }
  }

  async function analyzeFilePhase(sourceId, button) {
    const output = byId("source-control-result");
    if (!window.confirm(sourceId + " · 명시적 V/A·R/S/T 의미가 저장된 DuckLake FILE 이력으로 3상 불평형률을 분석합니다.")) return;
    button.disabled = true;
    output.className = "";
    output.textContent = sourceId + " · 저장된 3상 이력 분석 중";
    try {
      const session = await getJSON("/api/v1/session");
      if (session.write_scope !== "supervisor-owned-source-control") throw new Error("read-only");
      const response = await fetch("/api/v1/analysis/phase-file", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: JSON.stringify({source_id: sourceId}),
      });
      if (!response.ok) {
        await checkWorkspaceWriterConflict(response);
        const body = await response.json().catch(() => null);
        const code = body && body.error && body.error.code;
        if (code === "command_outcome_unknown") throw new Error("outcome-unknown");
        if (response.status === 409) throw new Error("phase-conflict");
        if (response.status === 400) throw new Error("phase-ineligible");
        throw new Error("http-" + response.status);
      }
      const saved = await response.json();
      if (saved.schema_version !== 1 || saved.source_id !== sourceId
          || saved.meaning !== "persisted-phase-unbalance-from-bound-file-history-not-fault-diagnosis"
          || !Number.isSafeInteger(saved.history_snapshot_id)
          || typeof saved.analysis_run_id !== "string" || !saved.analysis_run_id
          || typeof saved.evidence_id !== "string" || !saved.evidence_id) {
        throw new Error("schema-mismatch");
      }
      output.textContent = sourceId + " · 신규 3상 분석 기록 완료 · snapshot #"
        + saved.history_snapshot_id + " · Run " + saved.analysis_run_id
        + " · Evidence " + saved.evidence_id;
      await refresh();
      openSavedAnalysis(saved, "phase_unbalance_analyses");
    } catch (error) {
      output.className = "error";
      output.textContent = error.message === "outcome-unknown"
        ? "분석 응답을 확인하지 못했습니다. 재실행 전에 저장된 Run 목록을 조회하세요."
        : error.message === "phase-conflict"
        ? "분석 불가 · ACTIVE FILE, 확인된 수신, DuckLake 적재, 등록한 V/A·R/S/T 근거와 원본 SHA를 확인하세요."
        : error.message === "phase-ineligible"
        ? "3상 분석 대상 없음 · 완전한 R/S/T 표본, 같은 시각의 유효 측정값과 신호 임계조건을 확인하세요."
        : error.message === "read-only"
        ? "3상 분석은 감독형 Web에서만 실행할 수 있습니다."
        : presentError(error);
    } finally {
      button.disabled = false;
    }
  }

  async function backfillFile(sourceId, button) {
    const output = byId("source-control-result");
    if (!window.confirm(sourceId + " · CSV의 측정 시각과 값을 이력으로 저장합니다.\nSupervisor가 백그라운드에서 저장하며, 같은 파일의 재시도는 기존 배치 커밋을 재사용합니다. 수집·분석은 시작하지 않습니다.")) return;
    button.disabled = true;
    output.className = "";
    output.textContent = sourceId + " · 측정 이력 저장 요청 중";
    try {
      const session = await getJSON("/api/v1/session");
      // The supervisor owns long history writes as a background job. A standalone preview keeps
      // the existing synchronous path, which is bounded to small files.
      const background = session.write_scope === "supervisor-owned-source-control";
      const response = await fetch(background ? "/api/v1/sources/file/backfill/start" : "/api/v1/sources/file/backfill", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: JSON.stringify({source_id: sourceId}),
      });
      if (!response.ok) {
        await checkWorkspaceWriterConflict(response);
        if (response.status === 409) throw new Error("control-conflict");
        if (response.status === 404) throw new Error("source-missing");
        if (response.status === 400) throw new Error("control-invalid");
        throw new Error("http-" + response.status);
      }
      const started = await response.json();
      if (!background) {
        if (started.schema_version !== 1 || started.source_id !== sourceId
            || started.meaning !== "persisted-file-history-not-live-collection-or-analysis"
            || !Number.isSafeInteger(started.event_count)) throw new Error("schema-mismatch");
      } else if (started.schema_version !== 1 || started.source_id !== sourceId
          || !["running", "succeeded"].includes(started.state)) throw new Error("schema-mismatch");
      // Poll the supervisor job; a failed status read is not a failed write.
      const begun = Date.now();
      let job = !background ? {...started, state: "succeeded"} : started.state === "succeeded" ? started : null;
      while (!job || job.state === "running") {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        output.textContent = sourceId + " · 측정 이력 저장 중 · 경과 " + Math.round((Date.now() - begun) / 1000) + "초";
        try {
          const data = await getJSON("/api/v1/sources");
          job = rows(data, "sources").find((item) => item.source_id === sourceId)?.file_history_job || job;
        } catch (_) { /* keep waiting */ }
        if (Date.now() - begun > 15 * 60 * 1000) throw new Error("history-unknown");
      }
      if (job.state === "interrupted") throw new Error("history-interrupted");
      if (job.state !== "succeeded" || !Number.isSafeInteger(job.event_count)) throw new Error("history-failed");
      output.textContent = sourceId + " · 측정 이력 저장 완료 · "
        + job.event_count + "개 이벤트 · snapshot #" + job.history_snapshot_id
        + " · 재사용 배치 " + job.recovered_segment_count + "개 · 분석·실시간 수집 아님";
    } catch (error) {
      output.className = "error";
      if (error.message === "control-conflict") {
        output.textContent = "이력을 저장할 수 없습니다. 파일 읽기 확인, 시각 컬럼, CSV 크기(감독형 Web 20MiB·독립 Preview 1MiB 이하), 작업공간 안의 경로와 다른 저장 작업의 진행 여부를 확인하세요.";
      } else if (error.message === "source-missing") {
        output.textContent = "등록되지 않은 소스입니다.";
      } else if (error.message === "history-interrupted") {
        output.textContent = "서비스 재시작으로 이력 적재가 중단됐습니다. 다시 실행하면 이어서 저장합니다.";
      } else if (error.message === "history-failed") {
        output.textContent = "이력 적재에 실패했습니다. 시간대가 있는 시각과 원본 파일을 확인한 뒤 다시 실행하세요.";
      } else if (error.message === "history-unknown") {
        output.textContent = "적재 결과를 확인하지 못했습니다. 소스 목록의 이력 저장 상태를 새로 조회하세요.";
      } else {
        output.textContent = presentError(error);
      }
    } finally {
      button.disabled = false;
    }
    await Promise.allSettled([loadSources(), refresh()]);
  }

  initializeFileRegistration({loadSources, refresh});
  byId("csv-entry").querySelector("summary").addEventListener("click", () => {byId("csv-entry").dataset.userOpened = "true";});
  const {diagnoseOpcua} = initializeOpcuaRegistration({loadSources, refresh});
  return {loadSources, renderOnboardingGuide, analyzeFile};
}
