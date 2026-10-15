import { byId, create, clear, fmt, getJSON, presentError, checkWorkspaceWriterConflict, canChange, OPERATIONS_REQUIRED } from "./web-utils.js";
import { setAsset } from "./asset-context.js";
import { formatTime } from "./time.js";

// Advanced CSV mapping/preflight; the first-use flow stays in csv-start.js.
export function initializeFileRegistration({loadSources, refresh}) {
  const MAX_CSV_UPLOAD = 20 * 1024 * 1024;
  byId("csv-upload").addEventListener("change", async () => {
    csvPreflightRevision += 1;
    byId("csv-preflight-result").className = "state";
    byId("csv-preflight-result").textContent = "선택한 파일이 변경됐습니다. CSV 분석 전 점검을 다시 실행하세요.";
    const chosen = byId("csv-upload").files[0];
    const pathInput = byId("file-form").elements.namedItem("file_path");
    pathInput.required = !chosen;
    pathInput.disabled = Boolean(chosen);
    const preview = byId("csv-file-preview");
    if (!chosen) {
      preview.textContent = "작업공간 내부 CSV의 상대 경로를 입력하세요.";
      return;
    }
    if (!/\.csv$/i.test(chosen.name) || !chosen.size || chosen.size > MAX_CSV_UPLOAD) {
      preview.textContent = "선택한 파일은 20MiB 이하의 비어 있지 않은 .csv 파일이어야 합니다.";
      preview.className = "hint error wide";
      return;
    }
    preview.className = "hint wide";
    try {
      const head = (await chosen.slice(0, 8192).text()).replace(/^\uFEFF/, "");
      const first = head.split(/\r?\n/, 1)[0];
      const columns = first.split(",").map((column) => column.trim().replace(/^"(.*)"$/, "$1"));
      const time = columns.find((column) => /^(timestamp|time|event_time|observed_at)$/i.test(column));
      const channels = columns.filter((column) => column && column !== time);
      preview.textContent = "파일: " + chosen.name + " (" + chosen.size + "B) · 헤더 후보: "
        + columns.join(", ") + " · 실제 CSV 검증은 등록 시 수행합니다.";
      const form = byId("file-form");
      if (time && !form.elements.namedItem("timestamp_column").value) {
        form.elements.namedItem("timestamp_column").value = time;
      }
      if (channels.length && channels.length <= 12 && !form.elements.namedItem("channel_columns").value) {
        form.elements.namedItem("channel_columns").value = channels.join(",");
      }
    } catch (_error) {
      preview.textContent = "첫 행을 읽을 수 없습니다. 신호·시간 컬럼을 직접 입력한 뒤 등록하세요.";
    }
  });
  function csvBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    const parts = [];
    for (let offset = 0; offset < bytes.length; offset += 8192) {
      parts.push(String.fromCharCode(...bytes.subarray(offset, offset + 8192)));
    }
    return btoa(parts.join(""));
  }

  function declaredPhaseBindings(value, channels) {
    if (!value.trim()) return [];
    const lines = value.trim().split(/\r?\n/).filter((line) => line.trim());
    if (![3, 6].includes(lines.length)) throw new Error("invalid-phase-bindings");
    const found = new Set();
    const mapped = new Set();
    const bindings = lines.map((line) => {
      const cells = line.split(",").map((cell) => cell.trim());
      if (cells.length !== 5 || cells.some((cell) => !cell || cell.length > 128)) {
        throw new Error("invalid-phase-bindings");
      }
      const [channel_id, quantity, phase, unit_evidence, interpretation_evidence] = cells;
      if (!channels.includes(channel_id) || !["voltage", "current"].includes(quantity)
          || !["R", "S", "T"].includes(phase) || mapped.has(channel_id)
          || found.has(quantity + ":" + phase)) throw new Error("invalid-phase-bindings");
      found.add(quantity + ":" + phase);
      mapped.add(channel_id);
      return {channel_id, quantity, phase, unit_evidence, interpretation_evidence};
    });
    for (const quantity of ["voltage", "current"]) {
      const count = ["R", "S", "T"].filter((phase) => found.has(quantity + ":" + phase)).length;
      if (count && count !== 3) throw new Error("invalid-phase-bindings");
    }
    return bindings;
  }

  function csvRegistrationInput() {
    const form = byId("file-form");
    const values = new FormData(form);
    const channels = String(values.get("channel_columns") || "").split(",").map((x) => x.trim());
    if (channels.some((x) => !x) || channels.length > 12 || new Set(channels).size !== channels.length) {
      throw new Error("중복되지 않는 신호 컬럼 1~12개를 쉼표로 입력하세요.");
    }
    let phaseBindings;
    try {
      phaseBindings = declaredPhaseBindings(String(values.get("phase_bindings") || ""), channels);
    } catch (_error) {
      throw new Error("3상 매핑 오류: 채널,voltage|current,R|S|T,단위 근거,해석 근거를 3개 또는 6개 줄에 모두 입력하세요.");
    }
    const payload = {
      source_id: String(values.get("source_id") || "").trim(),
      name: String(values.get("name") || "").trim(),
      asset_id: String(values.get("asset_id") || "").trim(),
      measurement_point_id: String(values.get("measurement_point_id") || "").trim(),
      file_path: String(values.get("file_path") || "").trim(),
      channel_columns: channels,
      timestamp_column: String(values.get("timestamp_column") || "").trim(),
      ...(phaseBindings.length ? {phase_channels: phaseBindings} : {}),
    };
    const chosen = byId("csv-upload").files[0];
    if (chosen && (!/\.csv$/i.test(chosen.name) || !chosen.size || chosen.size > MAX_CSV_UPLOAD)) {
      throw new Error("업로드할 CSV는 20MiB 이하의 비어 있지 않은 .csv 파일이어야 합니다.");
    }
    if (!payload.timestamp_column) {
      throw new Error("Web의 CSV 이력·3상 분석에는 명시적 시간 컬럼이 필요합니다.");
    }
    return {payload, chosen, phaseBindings};
  }

  function csvRequest(payload, chosen, phaseBindings, preflight) {
    const upload = Boolean(chosen);
    const url = upload
      ? (preflight ? "/api/v1/sources/file/upload/preflight" : "/api/v1/sources/file/upload")
      : (preflight ? "/api/v1/sources/file/preflight" : "/api/v1/sources/file");
    return {
      url,
      upload,
      body: upload
        ? chosen.arrayBuffer().then((buffer) => JSON.stringify({
            setup: {
              source_id: payload.source_id, name: payload.name, asset_id: payload.asset_id,
              measurement_point_id: payload.measurement_point_id,
              channel_columns: payload.channel_columns, timestamp_column: payload.timestamp_column,
              ...(phaseBindings.length ? {phase_channels: phaseBindings} : {}),
            },
            csv_base64: csvBase64(buffer),
          }))
        : Promise.resolve(JSON.stringify(payload)),
    };
  }

  function describeCsvPreflight(result) {
    if (result.schema_version !== 1
        || result.meaning !== "csv-preflight-only-not-registered-or-ingested"
        || !["ready", "needs_input", "blocked"].includes(result.status)) {
      throw new Error("schema-mismatch");
    }
    const lines = [];
    if (result.status === "blocked") {
      lines.push("점검 결과: 실행 불가 · 원본 또는 설정을 수정한 뒤 다시 점검하세요.");
    } else {
      lines.push(result.status === "ready"
        ? "점검 결과: CSV 구조와 이력 적재의 필수 조건 확인"
        : "점검 결과: 추가 확인 필요 · 이력 적재를 시작하지 마세요.");
      lines.push("표본 " + result.sample_count + "행 · "
        + result.channel_columns.join(", ") + " · "
        + (result.first_timestamp || "시작 시각 없음") + " ~ "
        + (result.last_timestamp || "마지막 시각 없음"));
      lines.push("원본 식별 SHA-256: " + result.source_sha256.slice(0, 16) + "…");
      lines.push(result.phase_mapping_ready
        ? "3상 R/S/T 매핑 3개 이상 제출됨 · 물리적 단위·배선 근거는 현장 확인 필요"
        : "3상 분석: 명시적 V/A·R/S/T 매핑과 근거를 모두 제출해야 합니다 (통계 특징 분석과 별개).");
      if (Array.isArray(result.quality_warnings) && result.quality_warnings.length) {
        lines.push("데이터 품질 주의: " + result.quality_warnings.join(", ") + " · 실제 측정 간격을 확인하세요.");
      }
    }
    if (result.issue) {
      const issue = result.issue;
      const location = issue.row_number
        ? " · " + issue.row_number + "행" + (issue.column ? " / " + issue.column + " 컬럼" : "")
        : "";
      lines.push("수정 사항 [" + issue.code + "]" + location + ": " + issue.guidance);
    }
    lines.push("사전 점검만 수행됨 · 소스 등록·수신·DuckLake 저장·분석은 아직 하지 않았습니다.");
    return lines.join("\n");
  }

  let csvPreflightRevision = 0;

  async function preflightFile() {
    const button = byId("preflight-file"), output = byId("csv-preflight-result");
    let input;
    try {
      input = csvRegistrationInput();
    } catch (error) {
      output.className = "state error";
      output.textContent = error.message;
      return;
    }
    const revision = ++csvPreflightRevision;
    button.disabled = true;
    output.className = "state";
    output.textContent = "현재 CSV와 매핑을 점검합니다. 기록은 저장하지 않습니다.";
    try {
      const session = await getJSON("/api/v1/session");
      if (!canChange(session)) throw new Error("preflight-supervisor-required");
      const request = csvRequest(input.payload, input.chosen, input.phaseBindings, true);
      const response = await fetch(request.url, {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: await request.body,
      });
      if (!response.ok) {
        await checkWorkspaceWriterConflict(response);
        if (response.status === 400) throw new Error("invalid-csv");
        throw new Error("http-" + response.status);
      }
      const report = await response.json();
      if (revision !== csvPreflightRevision) return;
      output.className = report.status === "ready" ? "state" : "state error";
      output.textContent = describeCsvPreflight(report);
    } catch (error) {
      if (revision !== csvPreflightRevision) return;
      output.className = "state error";
      output.textContent = error.message === "preflight-supervisor-required"
        ? "사전 점검을 할 수 없습니다. " + OPERATIONS_REQUIRED
        : error.message === "invalid-csv"
        ? "CSV 사전 점검 요청이 잘못됐습니다. 파일 크기·인코딩·선택한 컬럼을 확인하세요."
        : presentError(error);
    } finally {
      button.disabled = false;
    }
  }

  async function registerFile(event) {
    event.preventDefault();
    const button = byId("register-file"), feedback = byId("register-result");
    const form = byId("file-form");
    let input;
    try {
      input = csvRegistrationInput();
    } catch (error) {
      feedback.className = "error";
      feedback.textContent = error.message;
      return;
    }
    const {payload, chosen, phaseBindings} = input;
    button.disabled = true;
    feedback.className = "";
    feedback.textContent = "CSV 형식과 등록 조건을 검증합니다. 이 단계에서 수집은 시작하지 않습니다.";
    try {
      const session = await getJSON("/api/v1/session");
      const upload = Boolean(chosen);
      if (upload && !canChange(session)) {
        throw new Error("upload-supervisor-required");
      }
      const request = csvRequest(payload, chosen, phaseBindings, false);
      const url = request.url;
      const body = await request.body;
      const response = await fetch(url, {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body,
      });
      if (!response.ok) {
        await checkWorkspaceWriterConflict(response);
        if (response.status === 409) throw new Error("duplicate-source");
        if (response.status === 400) throw new Error("invalid-csv");
        throw new Error("http-" + response.status);
      }
      const result = await response.json();
      if (result.schema_version !== 1 || result.registration_state !== "registered") {
        throw new Error("schema-mismatch");
      }
      feedback.textContent = "소스 " + result.source_id + " 등록 완료. 아래 등록된 소스에서 활성화한 뒤 수신을 확인하세요.";
      form.reset();
      csvPreflightRevision += 1;
      byId("csv-preflight-result").textContent =
        "이 CSV는 등록됐습니다. 다음 파일을 점검할 때 새로 실행하세요.";
      const pathInput = form.elements.namedItem("file_path");
      pathInput.disabled = false;
      pathInput.required = true;
      byId("csv-file-preview").textContent = "등록된 CSV는 서버 작업공간에 보존됩니다. 소스 활성화·수신 검증·이력 적재는 별도로 진행하세요.";
      await loadSources();
      await refresh();
    } catch (error) {
      feedback.className = "error";
      if (error.message === "duplicate-source") {
        feedback.textContent = "이미 등록된 소스 ID입니다. 다른 ID를 사용하세요.";
      } else if (error.message === "invalid-csv") {
        feedback.textContent = "등록 실패: CSV 경로·헤더·신호 컬럼과 작업공간 내부 경로 여부를 확인하세요.";
      } else if (error.message === "upload-supervisor-required") {
        feedback.textContent = "PC 파일을 올릴 수 없습니다. " + OPERATIONS_REQUIRED;
      } else {
        feedback.textContent = presentError(error);
      }
    } finally {
      button.disabled = false;
    }
  }

  byId("file-form").addEventListener("input", () => {
    csvPreflightRevision += 1;
    const output = byId("csv-preflight-result");
    output.className = "state";
    output.textContent = "파일 또는 매핑이 변경됐습니다. 최신 내용으로 다시 점검하세요.";
  });
  byId("preflight-file").addEventListener("click", preflightFile);
  byId("file-form").addEventListener("submit", registerFile);
}
