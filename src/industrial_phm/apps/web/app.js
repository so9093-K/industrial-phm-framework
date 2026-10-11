// Opt-in Operations Web preview. All server strings enter the DOM as text, never HTML.
// Source mutations are explicit and protected; there is no polling or fallback sample.
const byId = (id) => document.getElementById(id);
const create = (tag, className, content) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined && content !== null) element.textContent = String(content);
  return element;
};
const clear = (node) => node.replaceChildren();
const fmt = (value) => (value === null || value === undefined || value === "" ? "확인된 값 없음" : String(value));
const num = (value) => (typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("ko-KR", {maximumFractionDigits: 3}) : "—");
const utc = (value) => value ? String(value) : "시각 없음";
const list = (root, rows) => rows.forEach((row) => root.append(row));
const withText = (name, value) => {
  const item = create("div", "fact");
  item.append(create("span", null, name), create("strong", null, fmt(value)));
  return item;
};
let monitor = null;
let selectedAsset = "";
let selectedChannels = [];
let generation = 0;
let trendSequence = 0;
let reviewWritesAllowed = false;
function setNotice(message, error = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.className = message ? "notice" + (error ? " error" : "") : "notice hidden";
}
function trendState(message, error = false) {
  const node = byId("trend-state");
  node.textContent = message;
  node.className = message ? "state" + (error ? " error" : "") : "state hidden";
}
function setActiveSection() {
  const selected = location.hash || "#monitor";
  document.querySelectorAll(".sidebar nav a").forEach((item) => {
    if (item.getAttribute("href") === selected) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
}
function rows(payload, key) {
  const collection = payload && payload[key];
  return collection && Array.isArray(collection.items) ? collection.items : [];
}
function empty(target, message) {
  clear(target);
  target.append(create("p", "empty", message));
}
async function getJSON(url) {
  const response = await fetch(url, {cache:"no-store",credentials:"same-origin"});
  if (!response.ok) throw new Error("http-" + response.status);
  const value = await response.json();
  if (value.schema_version !== 1) throw new Error("schema-mismatch");
  return value;
}
function presentError(error) {
  if (error.message === "workspace-writer-busy") return "다른 Operations 또는 Web 작업이 현재 작업공간을 사용 중입니다. 변경 작업이 끝난 뒤 다시 시도하세요. 조회는 계속 가능합니다.";
  if (error.message === "http-503") return "이력 저장소를 확인할 수 없습니다. 시스템과 데이터 연결 상태를 확인하세요.";
  if (error.message === "schema-mismatch") return "지원되지 않는 API 응답입니다. 서버 버전을 확인하세요.";
  return "조회에 실패했습니다. 네트워크와 로컬 서버 상태를 확인하고 다시 시도하세요.";
}
async function checkWorkspaceWriterConflict(response) {
  if (response.status !== 409) return;
  const payload = await response.json().catch(() => null);
  if (payload && payload.error && payload.error.code === "workspace_writer_busy") {
    throw new Error("workspace-writer-busy");
  }
}
function assetDetails() {
  const item = rows(monitor, "assets").find((row) => row.asset_id === selectedAsset);
  const box = byId("asset-facts"); clear(box);
  if (!item) {empty(box, "선택한 설비의 관측 요약이 없습니다."); return;}
  list(box, [
    withText("데이터 흐름 (설비 건강 아님)", item.data_flow_status),
    withText("마지막 관측 시각 · UTC", utc(item.last_data_at)),
    withText("마지막 분석 완료 · UTC", utc(item.latest_analysis_at)),
    withText("연결된 source 수", item.source_count),
    withText("확인할 항목", item.attention_count),
    withText("미처리 검토", item.pending_review_count),
  ]);
}
function record(target, heading, details) {
  const section = create("article", "record");
  section.append(create("h3", null, heading));
  details.forEach(([label, value]) => {
    const line = create("p");
    line.append(create("strong", null, label + "  "), document.createTextNode(fmt(value)));
    section.append(line);
  });
  target.append(section);
  return section;
}
async function postReview(route, payload, button) {
  button.disabled = true;
  try {
    const session = await getJSON("/api/v1/session");
    if (session.write_scope !== "supervisor-owned-source-control") throw new Error("read-only");
    const response = await fetch(route, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      await checkWorkspaceWriterConflict(response);
      const errorBody = await response.json().catch(() => null);
      const code = errorBody && errorBody.error && errorBody.error.code;
      if (code === "command_outcome_unknown") throw new Error("outcome-unknown");
      if (response.status === 409) throw new Error("review-conflict");
      if (response.status === 404) throw new Error("review-not-found");
      throw new Error("http-" + response.status);
    }
    const outcome = await response.json();
    if (outcome.schema_version !== 1) throw new Error("schema-mismatch");
    if (route === "/api/v1/reviews/request") {
      if (outcome.analysis_run_id !== payload.analysis_run_id
          || !Array.isArray(outcome.evidence_ids)
          || !outcome.evidence_ids.includes(payload.evidence_id)
          || !outcome.finding_id) throw new Error("schema-mismatch");
    } else if (outcome.finding_id !== payload.finding_id
        || outcome.action !== payload.action
        || !["open", "acknowledged", "closed"].includes(outcome.status)) {
      throw new Error("schema-mismatch");
    }
    setNotice("사람의 검토 기록이 저장됐습니다. 물리 정비 수행 또는 설비 진단을 뜻하지 않습니다.");
    await refresh();
    if (route === "/api/v1/reviews/request"
        && typeof outcome.finding_id === "string" && outcome.finding_id) {
      const item = rows(monitor, "review_requests")
        .find((review) => review.finding_id === outcome.finding_id
          && review.analysis_run_id === payload.analysis_run_id
          && Array.isArray(review.evidence_ids)
          && review.evidence_ids.includes(payload.evidence_id));
      if (item) openReviewRecord(item.asset_id, item.finding_id);
    }
  } catch (error) {
    const explanation = error.message === "outcome-unknown"
      ? "명령 응답을 확인하지 못했습니다. 중복 전송하지 말고 기록을 새로 조회하세요."
      : error.message === "review-conflict"
      ? "검토 상태가 이미 변경됐습니다. 기록을 새로 조회한 뒤 다시 선택하세요."
      : error.message === "review-not-found"
      ? "선택한 분석 근거나 검토 기록이 저장소에 없습니다. 화면을 새로 조회하세요."
      : error.message === "read-only"
      ? "감독형 Web 제어 모드에서만 사람의 검토 기록을 변경할 수 있습니다."
      : presentError(error);
    setNotice(explanation, true);
  } finally {
    button.disabled = false;
  }
}
const reviewStates = {
  open: "열림 · 검토 필요",
  acknowledged: "확인됨 · 종료 전",
  closed: "종료 기록 · 실제 정비 완료 아님",
};
function focusSelectedReview(findingId) {
  const article = [...byId("review-results").querySelectorAll(".review-record")]
    .find((item) => item.dataset.findingId === findingId);
  if (!article) {
    setNotice("이번 조회에서 해당 검토 기록을 찾지 못했습니다. 저장소와 조회 범위를 다시 확인하세요.", true);
    return;
  }
  location.hash = "#review";
  article.focus({preventScroll: true});
  article.scrollIntoView({block: "center"});
}
function openReviewRecord(assetId, findingId) {
  // Never swap in a different finding, analysis or asset when the bounded
  // current monitor snapshot does not contain this exact review.
  const match = rows(monitor, "review_requests")
    .some((item) => item.asset_id === assetId && item.finding_id === findingId);
  const selector = byId("asset-select");
  const available = [...selector.options].some((item) => item.value === assetId);
  if (!match || !available) {
    setNotice("이번 조회 범위에 이 설비의 정확한 검토 기록이 없습니다. 조회를 새로고침하세요.", true);
    return;
  }
  if (selectedAsset !== assetId) {
    selector.value = assetId;
    void selectAsset();
  }
  focusSelectedReview(findingId);
}
function renderReviewInbox() {
  const summary = byId("review-inbox-summary");
  const root = byId("review-inbox-list");
  clear(root);
  if (!monitor) {
    summary.textContent = "검토 저장소를 조회할 수 없습니다. 미처리 요청이 없다고 판단하지 마세요.";
    return;
  }
  const reviews = rows(monitor, "review_requests");
  const stored = monitor.review_requests;
  const pending = reviews.filter((item) => item.status === "open" || item.status === "acknowledged");
  const filter = byId("review-filter").value;
  const visible = reviews.filter((item) => (
    filter === "all" || (filter === "closed" ? item.status === "closed" : item.status !== "closed")
  ));
  const limited = Boolean(stored && stored.truncated);
  const incomplete = Array.isArray(monitor.system_error_scopes) && monitor.system_error_scopes.length > 0;
  summary.textContent = "표시 범위: 미처리 " + pending.length + "건 · 전체 "
    + fmt(stored && stored.total) + "건"
    + (limited ? " · 100건까지만 표시 (추가 기록 존재)" : "")
    + (incomplete ? " · 일부 저장소 읽기 오류, 누락 가능" : "");
  if (!visible.length) {
    empty(root, incomplete
      ? "이번 조회에서 해당 상태의 검토를 확인할 수 없습니다. 저장소 조회 오류가 있어 없다고 단정할 수 없습니다."
      : "표시 조건에 맞는 검토 기록이 없습니다.");
    return;
  }
  const knownAssets = new Set(rows(monitor, "assets").map((asset) => asset.asset_id));
  visible.forEach((item) => {
    const card = create("article", "review-inbox-item");
    card.append(
      create("strong", null, fmt(item.asset_id) + " · " + fmt(reviewStates[item.status] || item.status)),
      create("p", "mono", "Finding " + fmt(item.finding_id)),
      create("p", "mono", "Run " + fmt(item.analysis_run_id)),
      create("p", "mono", "Evidence " + (
        Array.isArray(item.evidence_ids) ? item.evidence_ids.join(", ") : "미확인"
      )),
    );
    const open = create("button", null, "해당 설비의 검토 열기");
    open.type = "button";
    open.disabled = !knownAssets.has(item.asset_id)
      || typeof item.finding_id !== "string" || !item.finding_id;
    if (open.disabled) {
      card.append(create("p", "hint", "이번 설비 조회 범위에 없어 이동할 수 없습니다. 다른 기록으로 대체하지 않습니다."));
    } else {
      open.setAttribute("aria-label", "검토 열기 · " + item.asset_id + " · " + item.finding_id);
      open.addEventListener("click", () => openReviewRecord(item.asset_id, item.finding_id));
    }
    card.append(open);
    root.append(card);
  });
}
function evidenceViews() {
  const analyses = [...rows(monitor, "phase_unbalance_analyses"), ...rows(monitor, "file_feature_analyses")]
    .filter((r) => r.asset_id === selectedAsset);
  const attempts = rows(monitor, "skipped_analysis_attempts").filter((r) => r.asset_id === selectedAsset);
  const reviews = rows(monitor, "review_requests").filter((r) => r.asset_id === selectedAsset);
  const evidence = byId("evidence-results");
  const review = byId("review-results");
  // Match both persisted identifiers within the selected asset. A Run ID alone
  // cannot establish that a review refers to the evidence currently displayed.
  const evidenceTargets = new Map();
  clear(evidence); clear(review);
  if (!analyses.length && !attempts.length) empty(evidence, "이 설비의 저장된 분석 기록이 없습니다. 분석 결과 없음은 정상 상태를 의미하지 않습니다.");
  analyses.forEach((run) => {
    const metrics = Array.isArray(run.quantities) ? run.quantities : [];
    const article = create("article", "record evidence-target");
    article.tabIndex = -1;
    if (typeof run.analysis_run_id === "string" && typeof run.evidence_id === "string"
        && run.analysis_run_id && run.evidence_id) {
      evidenceTargets.set(JSON.stringify([run.analysis_run_id, run.evidence_id]), article);
    }
    article.append(create("h3", null, "분석 근거 · " + fmt(run.analysis_run_id)));
    const lines = [
      ["Capability", run.capability_id],
      ["계산 버전", run.algorithm_version],
      ["관측 구간 · UTC", utc(run.observed_start_at) + " → " + utc(run.observed_end_at)],
      ["Evidence ID", run.evidence_id],
    ];
    lines.forEach(([label, value]) => {
      const p = create("p"); p.append(create("strong", null, label + "  "), document.createTextNode(fmt(value))); article.append(p);
    });
    if (Array.isArray(run.features)) {
      article.append(create("p", "hint",
        "CSV 통계 특징값 · 이 화면은 원본 신호의 물리 단위나 진동 의미를 확인하지 않으며, 고장 진단·경보가 아닙니다."));
      article.append(create("p", null, "원본 SHA-256: " + fmt(run.source_snapshot_sha256)));
      run.features.forEach((item) => {
        article.append(create("p", "stat", fmt(item.name) + " · " + num(item.value)));
      });
    }
    metrics.forEach((m) => {
      const counts = Object.entries(m.excluded_samples || {}).map(([reason, count]) => reason + ": " + count).join(" · ");
      const p = create("p", "stat", fmt(m.quantity) + " 불평형률 · 중앙값 " + num(m.median_percent) + "% · p95 " + num(m.p95_percent) + "%");
      article.append(p);
      article.append(create("p", null, "평가 표본 " + fmt(m.evaluated_samples) + " · 제외 " + (counts || "없음")));
    });
    const relatedReview = reviews.find((item) => item.analysis_run_id === run.analysis_run_id
      && Array.isArray(item.evidence_ids) && item.evidence_ids.includes(run.evidence_id));
    if (relatedReview) {
      const showReview = create("button", "review-link", "이 분석의 검토 기록 열기");
      showReview.type = "button";
      showReview.addEventListener("click", () => focusSelectedReview(relatedReview.finding_id));
      article.append(showReview);
    }
    if (reviewWritesAllowed && !relatedReview) {
      const button = create("button", null, "이 근거에 사람 검토 요청");
      button.type = "button";
      button.addEventListener("click", () => postReview("/api/v1/reviews/request", {
        analysis_run_id: run.analysis_run_id,
        evidence_id: run.evidence_id,
      }, button));
      article.append(button);
    }
    evidence.append(article);
  });
  attempts.forEach((run) => record(evidence, "미수행 분석 · " + fmt(run.capability_id), [
    ["상태 / 이유", fmt(run.state) + " / " + fmt(run.reason)],
    ["관측 기간 · UTC", utc(run.observed_start_at) + " → " + utc(run.observed_end_at)],
  ]));
  if (!reviews.length) empty(review, "이 설비에 기록된 검토 요청이 없습니다. 검토 없음은 정비 완료를 뜻하지 않습니다.");
  reviews.forEach((reviewItem) => {
    const article = record(review, "검토 요청 · " + fmt(reviewItem.finding_id), [
      ["검토 상태", reviewItem.status],
      ["분석 Run", reviewItem.analysis_run_id],
      ["근거 ID", (reviewItem.evidence_ids || []).join(", ")],
    ]);
    article.classList.add("review-record");
    article.dataset.findingId = reviewItem.finding_id;
    article.tabIndex = -1;
    const meanings = {
      open: "검토 요청이 기록됐습니다. 아직 사람이 검토를 완료했다는 뜻이 아닙니다.",
      acknowledged: "검토 확인이 기록됐습니다. 실제 정비 수행이나 설비 정상 확인은 아닙니다.",
      closed: "검토 기록 종료됨 · 실제 정비 완료, 고장 해결 또는 설비 안전 확인의 근거가 아닙니다.",
    };
    if (Object.hasOwn(meanings, reviewItem.status)) {
      article.append(create("p", "review-meaning", meanings[reviewItem.status]));
    }
    const linkedIds = Array.isArray(reviewItem.evidence_ids) ? reviewItem.evidence_ids : [];
    const links = linkedIds.map((id) => [id,
      evidenceTargets.get(JSON.stringify([reviewItem.analysis_run_id, id]))]
    ).filter(([, target]) => target);
    if (links.length) {
      links.forEach(([id, target]) => {
        const button = create("button", "evidence-link", "연결된 분석 근거 확인");
        button.type = "button";
        button.setAttribute("aria-label", "연결된 분석 근거 확인 · " + id);
        button.addEventListener("click", () => {
          location.hash = "#evidence";
          target.focus({preventScroll: true});
          target.scrollIntoView({block: "center"});
        });
        article.append(button);
      });
    } else {
      article.append(create("p", "review-evidence-unavailable",
        "이번 조회에 Run ID와 Evidence ID가 모두 일치하는 분석 근거가 표시되지 않았습니다. "
        + "다른 분석으로 대체하지 않습니다. 설비·조회 범위와 저장소 오류를 확인하세요."));
    }
    if (!reviewWritesAllowed || reviewItem.status === "closed") return;
    const form = create("form", "review-form");
    const label = create("label", null, "검토 메모 (물리 정비 완료 기록 아님)");
    const field = create("textarea");
    field.rows = 2; field.maxLength = 1000; field.required = true;
    label.append(field);
    const save = create("button", null, "메모 기록");
    save.type = "submit";
    form.append(label, save);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (field.value.trim()) postReview("/api/v1/reviews/action", {
        finding_id: reviewItem.finding_id, action: "note", note: field.value.trim(),
      }, save);
    });
    article.append(form);
    const next = reviewItem.status === "open" ? "acknowledge" : "close";
    const button = create("button", null, next === "close" ? "검토 기록 종료" : "확인됨으로 표시");
    button.type = "button";
    button.addEventListener("click", () => {
      if (next === "close" && !window.confirm("검토 기록만 종료합니다. 물리 정비 완료나 정상 상태를 의미하지 않습니다. 계속할까요?")) return;
      postReview("/api/v1/reviews/action", {
        finding_id: reviewItem.finding_id, action: next, note: "",
      }, button);
    });
    article.append(button);
  });
  if (monitor.system_error_scopes && monitor.system_error_scopes.length) {
    setNotice("일부 저장소를 읽지 못했습니다 (" + monitor.system_error_scopes.join(", ") + "). 표시되지 않은 근거가 있을 수 있습니다.", true);
  }
}
function checkedChannels() {
  return [...byId("channel-options").querySelectorAll('input[type="checkbox"]:checked')].map((n) => n.value);
}
function changeChannelSelection() {
  const ids = checkedChannels();
  byId("channel-options").querySelectorAll('input[type="checkbox"]:not(:checked)').forEach((node) => {
    node.disabled = ids.length >= 6;
  });
  selectedChannels = ids;
  byId("show-trend").disabled = !selectedAsset || !selectedChannels.length;
}
async function loadChannels(id, token) {
  const box = byId("channel-options");
  clear(box);
  const legend = create("legend", null, "비교할 신호 (최대 6개)");
  box.append(legend, create("p", "muted", "저장된 신호를 조회 중입니다."));
  try {
    const url = "/api/v1/history/channels?asset_id=" + encodeURIComponent(id);
    const response = await getJSON(url);
    if (token !== generation) return;
    clear(box); box.append(legend);
    const ids = rows(response, "channels");
    if (!ids.length) {box.append(create("p", "empty", "저장된 신호가 없습니다. 연결과 수신 기록을 확인하세요.")); return;}
    const choices = create("div", "choices");
    ids.forEach((channel, index) => {
      const label = create("label", "choice");
      const input = create("input"); input.type = "checkbox"; input.value = channel;
      input.checked = index === 0; input.addEventListener("change", changeChannelSelection);
      label.append(input, document.createTextNode(channel));
      choices.append(label);
    });
    box.append(choices);
    if (response.channels.truncated) box.append(create("p", "muted", "신호가 100개를 초과합니다. 목록에 표시되지 않는 항목이 있습니다."));
    changeChannelSelection();
    if (selectedChannels.length) await loadTrend(token);
  } catch (error) {
    if (token !== generation) return;
    clear(box);box.append(legend);
    box.append(create("p", "empty", presentError(error)));
    trendState("신호 목록을 확인할 수 없습니다.", true);
  }
}
const svgNode = (name) => document.createElementNS("http://www.w3.org/2000/svg", name);
function drawSeries(entries, group) {
  const root = create("div", "trend-group");
  root.append(create("div", "trend-title", group.channel_id + " · " + group.source_id));
  root.append(create("div", "trend-meta", "측정 지점: " + fmt(group.measurement_point_id) + " · 단위: " + fmt(group.semantics && group.semantics.unit) + " · " + fmt(group.semantics && group.semantics.observed_property)));
  const svg = svgNode("svg");
  svg.setAttribute("class", "trend-svg"); svg.setAttribute("viewBox", "0 0 640 130");
  svg.setAttribute("role", "img");svg.setAttribute("aria-label", "연속선을 그리지 않은 관측 버킷 평균 점 그래프. 비어 있는 시간대는 공백입니다.");
  const axis = svgNode("path");axis.setAttribute("d","M28 12 V110 H628");axis.setAttribute("class","axis");svg.append(axis);
  const vals = entries.map((e) => e.mean).filter((n) => typeof n === "number" && Number.isFinite(n));
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 0;
  const pad = hi === lo ? 1 : (hi - lo) * .16;
  const min = lo - pad, max = hi + pad;
  const start = Date.parse(group.start_at), end = Date.parse(group.end_at);
  entries.forEach((bucket) => {
    const t = Date.parse(bucket.bucket_start);
    const v = bucket.mean;
    if (!Number.isFinite(t) || !Number.isFinite(start) || end <= start) return;
    const x = 28 + (t - start) / (end - start) * 600;
    if (typeof v === "number" && Number.isFinite(v) && bucket.usable_count > 0) {
      const y = 106 - (v - min) / (max - min) * 87;
      const circle = svgNode("circle");
      circle.setAttribute("cx", String(x));circle.setAttribute("cy", String(y));circle.setAttribute("r", "4");circle.setAttribute("class", "trend-dot");
      const label = svgNode("title");label.textContent = bucket.bucket_start + " · mean " + num(v) + " · valid " + bucket.usable_count;
      circle.append(label);svg.append(circle);
    } else {
      const circle = svgNode("circle");
      circle.setAttribute("cx",String(x));circle.setAttribute("cy","105");circle.setAttribute("r","3.5");circle.setAttribute("class","trend-dot missing");
      svg.append(circle);
    }
  });
  root.append(svg);
  root.append(create("p", "legend", "버킷 " + entries.length + "개 · 원본 결측/품질/충돌 건수 확인 · 평균은 실시간 값이 아닙니다"));
  const quality = entries.reduce((acc, item) => {
    ["usable_count","null_count","non_good_count","conflict_count"].forEach((key) => acc[key] = (acc[key] || 0) + (Number(item[key]) || 0));
    return acc;
  },{});
  root.append(create("p", "trend-meta", "사용 가능 " + quality.usable_count + " · 결측 " + quality.null_count + " · 비정상 원본 품질 " + quality.non_good_count + " · 충돌 " + quality.conflict_count));
  return root;
}
function showTrend(data) {
  const box = byId("trend-results");const latest = byId("last-values");
  clear(box);clear(latest);
  const buckets = Array.isArray(data.buckets) ? data.buckets : [];
  if (!buckets.length) empty(box,"선택한 기간에 저장된 측정값이 없습니다. 최근 저장값은 별도 확인하세요.");
  const grouped = new Map();
  buckets.forEach((item) => {
    const key = [item.channel_id,item.source_id,item.measurement_point_id,item.interpretation_id].map(String).join("\u0000");
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(item);
  });
  grouped.forEach((items) => box.append(drawSeries(items, {...items[0], start_at:data.start_at, end_at:data.end_at})));
  const points = Array.isArray(data.latest_stored) ? data.latest_stored : [];
  if (points.length) latest.append(create("h3", null, "마지막 저장된 측정값 · 현재 상태가 아님"));
  points.forEach((p) => {
    const item = create("div","latest-item");
    item.append(create("small",null,p.channel_id + " / " + p.source_id));
    item.append(create("strong",null, p.usable_for_display ? num(p.value) : "표시 신뢰 불가"));
    item.append(create("small",null,utc(p.event_at)));
    item.append(create("small",null,"원본 품질 " + fmt(p.source_quality) + " · " + (p.conflicting_duplicate ? "충돌 있음" : "충돌 없음")));
    item.append(create("small",null,"evidence: " + fmt(p.raw_evidence_id)));
    latest.append(item);
  });
  trendState("이력 snapshot " + fmt(data.snapshot_id) + " · " + utc(data.start_at) + " ~ " + utc(data.end_at) + " · " + grouped.size + "개 신호/출처 조합");
}
async function loadTrend(token = generation) {
  if (!selectedAsset || !selectedChannels.length) return;
  const request = ++trendSequence;
  trendState("실제 측정 이력을 읽는 중입니다.");
  clear(byId("trend-results"));clear(byId("last-values"));
  const params = new URLSearchParams({asset_id:selectedAsset,range:byId("range-select").value,buckets:"60"});
  selectedChannels.forEach((channel) => params.append("channel_id",channel));
  try {
    const data = await getJSON("/api/v1/history/trend?" + params.toString());
    if (token !== generation || request !== trendSequence) return;
    showTrend(data);
  } catch (error) {
    if (token !== generation || request !== trendSequence) return;
    trendState(presentError(error),true);
  }
}
async function selectAsset() {
  generation += 1;
  selectedAsset = byId("asset-select").value;
  selectedChannels = [];
  assetDetails();
  evidenceViews();
  clear(byId("trend-results"));clear(byId("last-values"));
  byId("show-trend").disabled = true;
  trendState("설비의 저장된 신호 목록을 확인합니다.");
  if (selectedAsset) await loadChannels(selectedAsset, generation);
}
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
async function loadRuntimeStatus() {
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
      ? "로컬 서비스의 프로세스·heartbeat·Web listener 준비 근거가 확인됐습니다. 실제 데이터 수신 또는 설비 정상 판정은 아닙니다."
      : "로컬 서비스가 완전히 준비됐는지 확인되지 않습니다. 아래 구성 요소 상태를 확인하고 필요하면 CLI 로그를 조회하세요.";
    facts.append(
      withText("평가 시각 · UTC", utc(data.assessed_at)),
      withText("Supervisor", runtimeConditions[supervisor.condition]),
      withText("Supervisor PID (조회 시점)", supervisor.pid),
      withText("Supervisor heartbeat · UTC", utc(supervisor.heartbeat_at)),
    );
    data.components.forEach((part) => {
      if (!Object.hasOwn(runtimeNames, part.kind)
          || !Object.hasOwn(runtimeConditions, part.condition)) throw new Error("schema-mismatch");
      const card = create("article", "source-record");
      card.append(
        create("strong", null, runtimeNames[part.kind] + " · " + runtimeConditions[part.condition]),
        create("span", null, "프로세스 PID: " + fmt(part.pid)),
        create("span", null, "프로세스별 런타임 상태: " + fmt(part.runtime_state)),
        create("span", null, "마지막 heartbeat · UTC: " + utc(part.heartbeat_at)),
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
function systemViews(snapshot) {
  const status = byId("system-status");
  const details = byId("system-facts");
  clear(details);
  const scopes = Array.isArray(snapshot.system_error_scopes) ? snapshot.system_error_scopes : [];
  status.className = scopes.length ? "state error" : "state";
  status.textContent = scopes.length
    ? "일부 저장소 조회 범위에 오류가 있습니다. 표시되지 않은 관측·분석·검토 근거가 있을 수 있습니다."
    : "이번 조회에서 저장소 오류 범위가 보고되지 않았습니다. 수집기 가동·실시간 연결·설비 정상 또는 안전 판정이 아닙니다.";
  details.append(
    withText("조회 평가 시각 · UTC", utc(snapshot.assessed_at)),
    withText("조회된 설비 수", snapshot.assets && snapshot.assets.total),
    withText("조회된 분석 기록 수", (snapshot.phase_unbalance_analyses?.total ?? 0) + (snapshot.file_feature_analyses?.total ?? 0)),
    withText("조회된 검토 요청 수", snapshot.review_requests && snapshot.review_requests.total),
  );
  if (scopes.length) details.append(withText("확인되지 않은 저장소 범위", scopes.join(", ")));
}
function renderMonitorAttention(snapshot) {
  const target = byId("monitor-attention");
  clear(target);
  const entries = rows(snapshot, "attention");
  if (!entries.length) {
    target.append(create("p", "muted", "현재 조회 근거에 별도 운영 상태 확인 항목이 없습니다. 이는 설비 정상 또는 안전 판정이 아닙니다."));
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
async function refresh() {
  const token = ++generation;
  trendSequence += 1;
  selectedChannels = [];
  byId("show-trend").disabled = true;
  clear(byId("trend-results"));
  clear(byId("last-values"));
  trendState("현재 설비의 측정 이력을 다시 확인합니다.");
  byId("refresh").disabled = true;
  setNotice("저장된 관측 현황을 불러오는 중입니다.");
  try {
    const data = await getJSON("/api/v1/monitor");
    if (token !== generation) return;
    monitor = data;
    renderMonitorAttention(data);
    systemViews(data);
    renderReviewInbox();
    byId("asset-count").textContent = fmt(data.assets && data.assets.total);
    byId("analysis-count").textContent = fmt((data.phase_unbalance_analyses?.total ?? 0) + (data.file_feature_analyses?.total ?? 0));
    byId("review-count").textContent = fmt(data.review_requests && data.review_requests.total);
    byId("assessed-at").textContent = utc(data.assessed_at);
    const assets = rows(data,"assets");
    const select = byId("asset-select");
    const previous = selectedAsset;
    clear(select);
    if (!assets.length) {
      const option = create("option", null, "저장된 설비 없음");option.value = "";
      select.append(option);select.disabled = true; selectedAsset = "";
      empty(byId("asset-facts"),"현재 조회된 설비가 없습니다. 먼저 데이터 연결과 수신을 확인하세요.");
      empty(byId("evidence-results"),"설비를 선택한 뒤 기록된 분석 근거를 확인할 수 있습니다.");
      empty(byId("review-results"),"설비를 선택한 뒤 검토 기록을 확인할 수 있습니다.");
      clear(byId("channel-options"));byId("channel-options").append(create("legend",null,"비교할 신호 (최대 6개)"));
      trendState("관측 설비가 없습니다.");
      byId("show-trend").disabled = true;
    } else {
      assets.forEach((asset) => {
        const option = create("option",null,asset.asset_id);option.value=asset.asset_id;select.append(option);
      });
      select.disabled = false;
      selectedAsset = assets.some((a) => a.asset_id === previous) ? previous : assets[0].asset_id;
      select.value = selectedAsset;
      assetDetails();evidenceViews();
      await loadChannels(selectedAsset, token);
    }
    if (data.system_error_scopes && data.system_error_scopes.length) {
      setNotice("일부 저장소를 읽지 못했습니다 (" + data.system_error_scopes.join(", ") + "). 표시되지 않은 근거가 있을 수 있습니다.", true);
    } else if (data.assets && data.assets.truncated) {
      setNotice("설비 목록이 100건으로 제한되었습니다. 추가 설비 조회는 후속 페이지 API가 필요합니다.");
    } else {
      setNotice("");
    }
  } catch (error) {
    if (token !== generation) return;
    monitor = null;setNotice(presentError(error),true);
    byId("monitor-attention").textContent = "운영 상태 조회 실패 · 이전 확인 항목을 현재 상태로 표시하지 않습니다.";
    renderReviewInbox();
    byId("system-status").className = "state error";
    byId("system-status").textContent = "시스템 조회 실패 · 정상 상태로 판단할 수 없습니다.";
    clear(byId("system-facts"));
    for (const id of ["asset-facts","evidence-results","review-results"]) empty(byId(id),"조회 실패 · 이전 데이터를 현재 상태로 표시하지 않습니다.");
    for (const id of ["asset-count","analysis-count","review-count","assessed-at"]) byId(id).textContent = "—";
    clear(byId("asset-select"));byId("asset-select").disabled = true;selectedAsset = "";selectedChannels = [];
    clear(byId("trend-results"));clear(byId("last-values"));trendState(presentError(error),true);
    byId("show-trend").disabled = true;
  } finally {
    byId("refresh").disabled = false;
  }
}
byId("refresh").addEventListener("click",() => {refresh();loadSources();loadRuntimeStatus();});
byId("runtime-refresh").addEventListener("click",loadRuntimeStatus);
byId("asset-select").addEventListener("change",selectAsset);
byId("review-filter").addEventListener("change",renderReviewInbox);
byId("show-trend").addEventListener("click",() => loadTrend());
byId("range-select").addEventListener("change",() => loadTrend());
window.addEventListener("hashchange",setActiveSection);
setActiveSection();
async function initializeReviewAccess() {
  try {
    const session = await getJSON("/api/v1/session");
    reviewWritesAllowed = session.write_scope === "supervisor-owned-source-control";
  } catch (_) {
    reviewWritesAllowed = false;
  }
  await refresh();
}
initializeReviewAccess();
loadRuntimeStatus();

// Source reads can overlap after control actions. Only the newest successful read
// may decide whether the operator sees an evidence-backed Monitor handoff.
let sourcesRequestSequence = 0;
let selectedOnboardingSourceId = "";
let onboardingSources = [];
let onboardingIncomplete = false;
function onboardingStepFor(source) {
  if (["registered", "paused", "error"].includes(source.lifecycle_state)) {
    return ["소스 활성화", "현재 관리 상태는 " + source.lifecycle_state
      + "입니다. 활성화는 연결·수신 성공을 뜻하지 않습니다."];
  }
  if (source.lifecycle_state !== "active") {
    return [null, "관리 상태가 확인되지 않았습니다. 상태를 새로 조회하세요."];
  }
  if (source.source_type === "file") {
    return source.receipt_confirmed
      ? ["FILE 이력 적재", "검증 수신 근거가 있습니다. DuckLake 이력 커밋은 아직 확인되지 않았습니다. 필요한 경우 FILE 이력 적재 버튼으로 이동하세요."]
      : ["FILE 수신 확인", "등록·활성화만 확인됐습니다. CSV의 실제 검증 수신 결과를 별도로 확인하세요."];
  }
  if (source.source_type === "opcua") {
    if (!source.receipt_confirmed) {
      return ["OPC UA 1회 수신 진단", "활성 소스에서 로컬 OPC UA 1회 읽기·수신 근거를 확인하세요. 연속 수집과 별도입니다."];
    }
    if (source.collection_desired_state !== "running") {
      return ["수집 시작 요청", "1회 수신 근거가 있습니다. 연속 수집의 원하는 상태를 요청할 수 있으나 실제 연결·저장 성공은 별도 확인해야 합니다."];
    }
    return [null, "수집 시작 요청이 기록됐습니다. 현재 접속·최근 live 수신·저장 이력은 아래 소스 상태와 관측 화면에서 별도로 확인하세요."];
  }
  return [null, "이 소스 유형은 화면에서 다음 작업을 안내할 수 없습니다."];
}
function renderOnboardingGuide() {
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
  button.textContent = action ? action + " 버튼 찾기" : "관측 화면으로 이동";
  button.disabled = !action && item.lifecycle_state !== "active";
}
function scrollToOnboardingTarget(target, hash) {
  if (!target) {
    byId("onboarding-action-detail").textContent =
      "해당 작업 버튼이 현재 목록에 없습니다. 소스 목록을 새로 조회하세요.";
    return;
  }
  location.hash = hash;
  target.focus({preventScroll: true});
  target.scrollIntoView({block: "center"});
}
byId("onboarding-source-select").addEventListener("change", (event) => {
  selectedOnboardingSourceId = event.target.value;
  renderOnboardingGuide();
});
byId("onboarding-action").addEventListener("click", () => {
  const item = onboardingSources.find((source) => source.source_id === selectedOnboardingSourceId);
  if (!item) {
    scrollToOnboardingTarget(byId("file-form").querySelector('input[name="source_id"]'), "#connect");
    return;
  }
  const [action] = onboardingStepFor(item);
  if (!action) {
    scrollToOnboardingTarget(byId("asset-select"), "#monitor");
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
    "수신 준비 여부를 확인할 수 없습니다. 저장된 기록을 읽을 수 있어도 현재 수신이 확인됐다는 뜻은 아닙니다.";
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
    "등록된 소스: " + data.sources.total + "개 (설정만 확인)",
    "관리 상태 active: " + active + "개 (연결·수집 성공 아님)",
    "검증 수신: " + accepted + "개 · active와 수신을 모두 확인한 소스 "
      + ready + "개 (DuckLake 이력 적재 아님)",
    "DuckLake 저장 이력·분석: 관측·분석 근거에서 따로 확인",
  ].forEach((line) => steps.append(create("li", null, line)));
  if (data.sources.truncated || evidenceReadError) {
    next.textContent = "소스 목록 일부 또는 live 수신 근거를 완전히 읽지 못했습니다. "
      + "준비 여부를 확정할 수 없으므로 조회 범위와 저장소 상태를 확인하세요.";
  } else if (!items.length) {
    next.textContent = "다음: FILE CSV 또는 로컬 OPC UA 소스를 등록하세요.";
  } else if (!active) {
    next.textContent = "다음: 등록된 소스를 활성화하세요. 과거 수신 기록이 있어도 일시정지 상태는 준비 완료가 아닙니다. 활성화만으로 실제 연결·수신을 증명하지 않습니다.";
  } else if (!ready) {
    next.textContent = "다음: active 소스에서 실제 검증 수신 근거를 확인하세요. "
      + "기존 수신 기록이 있어도 일시정지 상태는 준비 완료가 아닙니다.";
  } else {
    next.textContent = "active 소스의 검증 수신 근거가 확인됐습니다. "
      + "이 버튼은 관측 근거 조회로 이동하며, 이력 저장·분석·설비 정상 판정은 보증하지 않습니다.";
    handoff.classList.remove("hidden");
  }
}

async function loadSources() {
  const token = ++sourcesRequestSequence;
  const state = byId("source-status"), list = byId("source-list");
  state.textContent = "저장된 등록 상태를 조회 중입니다.";
  byId("onboarding-monitor-link").classList.add("hidden");
  byId("onboarding-next").textContent = "등록·수신 근거를 다시 확인 중입니다.";
  clear(list);
  try {
    const data = await getJSON("/api/v1/sources");
    if (token !== sourcesRequestSequence) return;
    const items = rows(data, "sources");
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
      && item.last_live_received_at).length;
    const summary = "1회 검증 수신 확인 " + received + "개 · OPC UA 연속 live 수신 기록 "
      + liveReceived + "개 (표시 범위 기준; 서로 다른 근거)";
    if (!items.length) {
      state.textContent = "등록된 소스가 없습니다. 작업공간에 CSV 또는 이 화면에서 로컬 OPC UA 소스를 등록하세요.";
      empty(list, "데이터 수신을 확인할 등록 소스가 없습니다.");
      byId("onboarding-state").textContent = "1단계 · 소스 미등록 — FILE CSV 또는 로컬 OPC UA 소스를 등록하세요.";
    } else {
      state.textContent = "등록된 소스 " + data.sources.total + "개 · " + summary
        + (evidenceReadError ? " · 일부 live 근거 조회 실패" : "");
      byId("onboarding-state").textContent = "등록 " + data.sources.total + "개 · "
        + summary + " · 저장된 시계열은 별도로 확인해야 합니다."
        + (evidenceReadError ? " · live 근거 일부 미확인" : "");
    }
    byId("onboarding-state").className = "";
    setOnboardingEvidence(items, data, evidenceReadError);
    onboardingSources = items;
    onboardingIncomplete = evidenceReadError || Boolean(data.sources.truncated);
    renderOnboardingGuide();
    items.forEach((item) => {
      const card = create("article", "source-record");
      card.dataset.sourceId = item.source_id;
      card.append(create("strong", null, item.name + " · " + item.source_id));
      card.append(create("span", null, "설비: " + item.asset_id + " · 유형: " + item.source_type));
      card.append(create("span", null, "관리 상태: " + fmt(item.lifecycle_state) + " (접속 상태 아님)"));
      const evidenceMeaning = !item.receipt_confirmed
        ? "현재 확인된 단계: 소스 등록 정보만 확인. 활성화는 실제 연결·수신·이력 저장의 근거가 아닙니다."
        : item.source_type === "file"
        ? "현재 확인된 단계: FILE 검증 수신 근거 확인. 이력 저장·연속 수집·분석 성공 여부는 별도 확인이 필요합니다."
        : "현재 확인된 단계: 수신 근거 확인. 현재 연결·최근 live 수신·이력 저장 여부는 각각 별도로 확인하세요.";
      card.append(create("p", "source-meaning", evidenceMeaning));
      const receipt = create("span", item.receipt_confirmed ? "receipt-confirmed" : "receipt-missing",
        item.receipt_confirmed
          ? (item.source_type === "file" ? "FILE 검증 수신 근거 있음 · 이력 적재는 별도" : "실제 수신 근거 있음")
          : "수신 근거 미확인");
      card.append(receipt);
      card.append(create("span", null, "마지막 수신 · UTC: " + utc(item.last_accepted_received_at)));
      card.append(create("span", null, "원본 관측 · UTC: " + utc(item.last_accepted_observed_at)));
      if (item.continuous_collection_supported) {
        card.append(create("span", null, "연속 수집 요청: " + fmt(item.collection_desired_state || "미요청") + " (실제 수집 상태 아님)"));
        card.append(create("span", null, "요청 세대: " + fmt(item.collection_request_generation) + " · UTC " + utc(item.collection_requested_at)));
        card.append(create("span", null, "수집 서비스 마지막 기록: " + fmt(item.collection_service_state)
          + " · heartbeat UTC " + utc(item.collection_service_heartbeat_at)
          + (item.collection_service_heartbeat_fresh ? " · 최근 확인" : " · 실행 미확인/오래됨")));
        card.append(create("span", null, "OPC UA 세션 마지막 기록: " + fmt(item.opcua_session_last_state)
          + " · 변경 UTC " + utc(item.opcua_session_state_changed_at)
          + (item.recent_connected_evidence ? " · 최근 연결 근거 있음" : " · 현재 연결 미확인")));
        card.append(create("span", null, "live 이벤트 마지막 수신: UTC " + utc(item.last_live_received_at)
          + " · " + (item.last_live_receive_fresh
            ? "30초 이내 수신 근거 있음" : "최근 수신 근거 미확인")
          + " (1회 읽기 receipt와 별개)"));
        card.append(create("span", null, "OPC UA DuckLake 커밋: UTC "
          + utc(item.last_live_history_committed_at)
          + " · snapshot " + fmt(item.last_live_history_snapshot_id)
          + " · 소스 이벤트 " + fmt(item.last_live_history_batch_event_count)
          + " (live 배치 이력; live 수신과 별개)"));
        if (item.live_telemetry_read_error) {
          card.append(create("span", "error", "live 수집 근거 저장소 조회 실패 · 값이 없다고 판단할 수 없습니다."));
        }
      } else {
        card.append(create("span", null, "FILE 소스 · 연속 수집 시작 요청 미지원. 기존 FILE 처리 경로를 사용하세요."));
        if (item.phase_binding_count) {
          card.append(create("span", null, "검증할 3상 역할 " + item.phase_binding_count
            + "개 등록됨 · V/A 단위·R/S/T 해석 근거는 backfill 원본 행에 고정"));
        }
      }
      const actions = create("div", "source-actions");
      if (item.lifecycle_state) {
        const next = item.lifecycle_state === "active" ? "paused" : "active";
        const lifecycle = create("button", null, next === "active" ? "소스 활성화" : "소스 일시정지");
        lifecycle.type = "button";
        lifecycle.addEventListener("click", () => controlSource(item.source_id, "lifecycle", next, lifecycle));
        actions.append(lifecycle);
      }
      if (item.source_type === "file" && item.lifecycle_state === "active") {
        const receive = create("button", null, "FILE 수신 확인");
        receive.type = "button";
        receive.addEventListener("click", () => receiveFile(item.source_id, receive));
        actions.append(receive);
        if (item.receipt_confirmed) {
          const backfill = create("button", null, "FILE 이력 적재");
          backfill.type = "button";
          backfill.addEventListener("click", () => backfillFile(item.source_id, backfill));
          actions.append(backfill);
          const analyze = create("button", null, "CSV 특징 분석 실행");
          analyze.type = "button";
          analyze.addEventListener("click", () => analyzeFile(item.source_id, analyze));
          actions.append(analyze);
          if (item.phase_binding_count >= 3) {
            const phase = create("button", null, "저장된 3상 이력 분석 실행");
            phase.type = "button";
            phase.addEventListener("click", () => analyzeFilePhase(item.source_id, phase));
            actions.append(phase);
          }
        }
      }
      if (item.source_type === "opcua" && item.lifecycle_state === "active") {
        const diagnostic = create("button", null, "OPC UA 1회 수신 진단");
        diagnostic.type = "button";
        diagnostic.addEventListener("click", () => diagnoseOpcua(item.source_id, diagnostic));
        actions.append(diagnostic);
      }
      if (item.continuous_collection_supported && item.lifecycle_state === "active") {
        const target = item.collection_desired_state === "running" ? "stopped" : "running";
        const collection = create("button", null, target === "running" ? "수집 시작 요청" : "수집 중지 요청");
        collection.type = "button";
        collection.addEventListener("click", () => controlSource(item.source_id, "collection", target, collection));
        actions.append(collection);
      }
      card.append(actions);
      list.append(card);
    });
    if (data.sources.truncated) list.append(create("p", "hint", "소스 100건만 표시됩니다. 전체 수신 상태를 뜻하지 않습니다."));
  } catch (error) {
    if (token !== sourcesRequestSequence) return;
    state.textContent = presentError(error);
    state.className = "state error";
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
  if (!window.confirm(sourceId + " · 준비된 FILE을 다시 검증하고 수신 근거를 기록합니다.\n이력 적재·연속 수집·분석은 실행하지 않습니다.")) return;
  button.disabled = true;
  result.className = "";
  result.textContent = sourceId + " · FILE 검증 수신 요청 중";
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
      ? sourceId + " · FILE 검증 수신 근거 기록 완료 · 이력 적재는 별도"
      : sourceId + " · FILE 검증 수신 실패 (" + fmt(outcome.failure_scope) + ") · 저장된 수신 근거를 다시 확인하세요.";
  } catch (error) {
    result.className = "error";
    if (error.message === "control-conflict") {
      result.textContent = "FILE 수신 불가 · ACTIVE 상태, 소스 유형 및 작업공간 내부 CSV 경로를 확인하세요.";
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

async function analyzeFile(sourceId, button) {
  const output = byId("source-control-result");
  if (!window.confirm(sourceId + " · 등록한 CSV 스냅샷의 통계 특징을 새로 계산해 Run/Evidence를 기록합니다.\nDuckLake 이력 적재나 설비 고장 진단은 실행하지 않습니다.")) return;
  button.disabled = true;
  output.className = "";
  output.textContent = sourceId + " · CSV 특징 분석 실행 중";
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
    output.textContent = sourceId + " · 신규 분석 근거 저장 완료 · Run " + saved.analysis_run_id
      + " · Evidence " + saved.evidence_id + " · 이력 적재·고장 진단 아님";
    await refresh();
    if (rows(monitor, "file_feature_analyses").some((run) =>
      run.analysis_run_id === saved.analysis_run_id && run.evidence_id === saved.evidence_id)) {
      selectedAsset = saved.asset_id;
      byId("asset-select").value = selectedAsset;
      assetDetails();
      evidenceViews();
      location.hash = "#evidence";
      const target = [...byId("evidence-results").querySelectorAll(".evidence-target")]
        .find((node) => node.textContent.includes(saved.analysis_run_id));
      if (target) {
        target.focus({preventScroll: true});
        target.scrollIntoView({block: "center"});
      }
    }
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
  if (!window.confirm(sourceId + " · 명시적 V/A·R/S/T 의미가 저장된 DuckLake FILE 이력으로 3상 불평형률을 분석합니다.\\n이 계산은 고장 진단이나 자동 경보가 아닙니다.")) return;
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
      + " · Evidence " + saved.evidence_id + " · 고장 진단 아님";
    await refresh();
    if (rows(monitor, "phase_unbalance_analyses").some((run) =>
      run.analysis_run_id === saved.analysis_run_id && run.evidence_id === saved.evidence_id)) {
      selectedAsset = saved.asset_id;
      byId("asset-select").value = selectedAsset;
      assetDetails();
      evidenceViews();
      location.hash = "#evidence";
      const target = [...byId("evidence-results").querySelectorAll(".evidence-target")]
        .find((node) => node.textContent.includes(saved.analysis_run_id));
      if (target) target.focus({preventScroll: true});
    }
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
  if (!window.confirm(sourceId + " · CSV의 타임스탬프를 사용해 DuckLake에 실제 이력을 적재합니다.\n같은 파일의 재시도는 기존 배치 커밋을 재사용합니다. 수집·분석은 시작하지 않습니다.")) return;
  button.disabled = true;
  output.className = "";
  output.textContent = sourceId + " · FILE 이력 적재 요청 중";
  let saved = false;
  try {
    const session = await getJSON("/api/v1/session");
    const response = await fetch("/api/v1/sources/file/backfill", {
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
    const result = await response.json();
    if (result.schema_version !== 1 || result.source_id !== sourceId
        || result.meaning !== "persisted-file-history-not-live-collection-or-analysis"
        || !Number.isSafeInteger(result.history_snapshot_id)
        || !Number.isSafeInteger(result.event_count)
        || !Number.isSafeInteger(result.recovered_segment_count)) {
      throw new Error("schema-mismatch");
    }
    saved = true;
    output.textContent = sourceId + " · DuckLake 이력 적재 완료 · "
      + result.event_count + "개 이벤트 · snapshot #" + result.history_snapshot_id
      + " · 재사용 배치 " + result.recovered_segment_count + "개 · 분석·실시간 수집 아님";
  } catch (error) {
    output.className = "error";
    if (error.message === "control-conflict") {
      output.textContent = "적재 불가 · ACTIVE FILE, 검증 receipt, 시간 컬럼, CSV 크기(1MiB 이하) 및 작업공간 경계를 확인하세요.";
    } else if (error.message === "source-missing") {
      output.textContent = "등록되지 않은 소스입니다.";
    } else {
      output.textContent = presentError(error);
    }
  } finally {
    button.disabled = false;
  }
  if (saved) await Promise.allSettled([loadSources(), refresh()]);
}

const MAX_CSV_UPLOAD = 1024 * 1024;
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
    preview.textContent = "선택한 파일은 1MiB 이하의 비어 있지 않은 .csv 파일이어야 합니다.";
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
    throw new Error("업로드할 CSV는 1MiB 이하의 비어 있지 않은 .csv 파일이어야 합니다.");
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
    if (session.write_scope !== "supervisor-owned-source-control") throw new Error("preflight-supervisor-required");
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
      ? "사전 점검은 감독형 Web에서 실행하세요. 독립 Preview에서는 불가능합니다."
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
    if (upload && session.write_scope !== "supervisor-owned-source-control") {
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
    feedback.textContent = "소스 " + result.source_id + " 등록 완료 · 수신 근거 미확인. 수집은 기존 Operations에서 별도 실행하세요.";
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
      feedback.textContent = "PC 파일 업로드는 감독형 기본 Web에서만 가능합니다. 독립 Preview에서는 변경할 수 없습니다.";
    } else {
      feedback.textContent = presentError(error);
    }
  } finally {
    button.disabled = false;
  }
}

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
  const resultNode = byId("opcua-browse-result");
  const button = byId("browse-opcua");
  clear(resultNode);
  button.disabled = true;
  resultNode.textContent = "로컬 OPC UA 주소공간 탐색 중 · 수신이나 등록이 아닙니다.";
  try {
    const result = await opcuaPost("/api/v1/sources/opcua/browse", {endpoint_url: endpoint});
    if (result.meaning !== "address-space-candidates-not-received-or-registered"
        || !Array.isArray(result.variables)) throw new Error("schema-mismatch");
    clear(resultNode);
    resultNode.append(create("p", "hint", "변수 후보 " + result.variables.length
      + "개 (탐색 노드 " + fmt(result.visited_node_count) + "개)"
      + (result.truncated ? " · 결과 일부만 표시" : "") + " · 수신 근거 아님"));
    result.variables.forEach((item) => {
      const row = create("p");
      row.append(create("strong", null, fmt(item.display_name) + " · "),
        create("code", null, fmt(item.node_id)));
      resultNode.append(row);
    });
  } catch (error) {
    clear(resultNode);
    resultNode.append(create("p", "error", error.message === "http-400"
      ? "로컬 127.0.0.1 OPC UA 주소만 허용됩니다."
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
  resultNode.textContent = "매핑 등록 중 · 네트워크 연결이나 수신은 확인하지 않습니다.";
  let saved = false;
  try {
    const result = await opcuaPost("/api/v1/sources/opcua", payload);
    if (result.registration_state !== "registered") throw new Error("schema-mismatch");
    saved = true;
    resultNode.textContent = "OPC UA " + result.source_id + " 등록 완료 · 수신 근거 미확인. 소스를 활성화하고 1회 수신 진단을 실행하세요.";
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
      output.textContent = sourceId + " · OPC UA 1회 읽기/수신 근거 기록 완료 · UTC "
        + utc(result.accepted_received_at) + " · 연속 수집·이력 저장 아님";
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
      || !/^http:\/\/127\.0\.0\.1:\d{2,5}$/.test(payload.url)
      || Number(payload.url.split(":").pop()) > 65535) throw new Error("schema-mismatch");
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
sampleCommand("status");

byId("file-form").addEventListener("input", () => {
  csvPreflightRevision += 1;
  const output = byId("csv-preflight-result");
  output.className = "state";
  output.textContent = "파일 또는 매핑이 변경됐습니다. 최신 내용으로 다시 점검하세요.";
});
byId("preflight-file").addEventListener("click", preflightFile);
byId("file-form").addEventListener("submit", registerFile);
byId("opcua-form").addEventListener("submit", registerOpcua);
byId("browse-opcua").addEventListener("click", browseOpcua);
loadSources();
