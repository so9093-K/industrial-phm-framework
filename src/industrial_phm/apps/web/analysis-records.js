import { byId, create, clear, fmt, num, rows, empty, getJSON, presentError, checkWorkspaceWriterConflict, record } from "./web-utils.js";
import { currentAsset, setAsset } from "./asset-context.js";
import { navigate } from "./navigation.js";
import { formatTime } from "./time.js";

// Exact asset/Run/Evidence links, with writes delegated to the existing Supervisor.
export function createAnalysisRecords({getMonitor, refresh, setNotice}) {
  let reviewWritesAllowed = false;
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
      setNotice("확인 기록을 저장했습니다.");
      await refresh();
      if (route === "/api/v1/reviews/request"
          && typeof outcome.finding_id === "string" && outcome.finding_id) {
        const item = rows(getMonitor(), "review_requests")
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
        ? "확인 상태가 이미 바뀌었습니다. 화면을 새로 불러온 뒤 다시 선택하세요."
        : error.message === "review-not-found"
        ? "선택한 분석이나 확인 기록을 찾지 못했습니다. 화면을 새로 불러오세요."
        : error.message === "read-only"
        ? "이 화면에서는 확인 기록을 바꿀 수 없습니다. 감독형 Web에서 다시 시도하세요."
        : presentError(error);
      setNotice(explanation, true);
    } finally {
      button.disabled = false;
    }
  }
  const reviewStates = {open: "확인 필요", acknowledged: "확인함", closed: "완료"};
  function focusSelectedReview(findingId) {
    const article = [...byId("review-results").querySelectorAll(".review-record")]
      .find((item) => item.dataset.findingId === findingId);
    if (!article) {
      setNotice("해당 확인 기록을 찾지 못했습니다. 화면을 새로 불러오세요.", true);
      return;
    }
    navigate("#evidence", article);
  }
  function openReviewRecord(assetId, findingId) {
    // Never swap in a different finding, analysis or asset when the bounded
    // current monitor snapshot does not contain this exact review.
    if (!rows(getMonitor(), "review_requests").some((item) => item.asset_id === assetId && item.finding_id === findingId)) {
      setNotice("이 설비의 해당 확인 기록을 찾지 못했습니다. 화면을 새로 불러오세요.", true);
      return;
    }
    setAsset(assetId);
    evidenceViews();
    focusSelectedReview(findingId);
  }
  function evidenceViews() {
    const monitor = getMonitor(), selectedAsset = currentAsset();
    if (!monitor) return;
    const analyses = [...rows(getMonitor(), "phase_unbalance_analyses"), ...rows(getMonitor(), "file_feature_analyses")]
      .filter((r) => r.asset_id === selectedAsset);
    const attempts = rows(getMonitor(), "skipped_analysis_attempts").filter((r) => r.asset_id === selectedAsset);
    const reviews = rows(getMonitor(), "review_requests").filter((r) => r.asset_id === selectedAsset);
    const evidence = byId("evidence-results");
    const review = byId("review-results");
    // Match both persisted identifiers within the selected asset. A Run ID alone
    // cannot establish that a review refers to the evidence currently displayed.
    const evidenceTargets = new Map();
    clear(evidence); clear(review);
    if (!analyses.length && !attempts.length) empty(evidence, selectedAsset ? "이 설비에 저장된 분석 기록이 없습니다. 데이터 연결의 등록된 소스에서 신호 통계·3상 분석을 실행할 수 있습니다." : "설비를 선택하세요.");
    analyses.forEach((run) => {
      const metrics = Array.isArray(run.quantities) ? run.quantities : [];
      const article = create("article", "record evidence-target");
      article.tabIndex = -1;
      article.dataset.analysisRunId = run.analysis_run_id;article.dataset.evidenceId = run.evidence_id;
      if (typeof run.analysis_run_id === "string" && typeof run.evidence_id === "string"
          && run.analysis_run_id && run.evidence_id) {
        evidenceTargets.set(JSON.stringify([run.analysis_run_id, run.evidence_id]), article);
      }
      article.append(create("h3", null, Array.isArray(run.quantities) ? "3상 불평형 분석" : "신호 통계 분석"));
      article.append(create("p", "muted", "분석 구간 · " + formatTime(run.observed_start_at) + " → " + formatTime(run.observed_end_at)));
      const lines = [
        ["분석 기록 ID", run.analysis_run_id],
        ["Capability", run.capability_id],
        ["계산 버전", run.algorithm_version],
        ["원본 측정 구간", formatTime(run.observed_start_at) + " → " + formatTime(run.observed_end_at)],
        ["Evidence ID", run.evidence_id],
      ];
      const calculation = create("details", "analysis-calculation");
      calculation.append(create("summary", null, "계산 정보"));
      lines.forEach(([label, value]) => {
        const p = create("p"); p.append(create("strong", null, label + "  "), document.createTextNode(fmt(value))); calculation.append(p);
      });
      article.append(calculation);
      if (Array.isArray(run.features)) {
        const digest = create("p");digest.append(create("strong", null, "원본 SHA-256  "), document.createTextNode(fmt(run.source_snapshot_sha256)));
        calculation.append(digest);
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
        const showReview = create("button", "review-link", "확인 기록 보기");
        showReview.type = "button";
        showReview.addEventListener("click", () => focusSelectedReview(relatedReview.finding_id));
        article.append(showReview);
      }
      if (reviewWritesAllowed && !relatedReview) {
        const button = create("button", null, "확인·메모 시작");
        button.type = "button";
        button.addEventListener("click", () => postReview("/api/v1/reviews/request", {
          analysis_run_id: run.analysis_run_id,
          evidence_id: run.evidence_id,
        }, button));
        article.append(button);
      }
      evidence.append(article);
    });
    attempts.forEach((run) => record(evidence, "실행되지 않은 분석 · " + fmt(run.capability_id), [
      ["이유", fmt(run.reason)],
      ["분석 구간", formatTime(run.observed_start_at) + " → " + formatTime(run.observed_end_at)],
    ]));
    if (!reviews.length) empty(review, "남긴 확인·메모가 없습니다.");
    reviews.forEach((reviewItem) => {
      const article = record(review, "확인 기록 · " + fmt(reviewStates[reviewItem.status] || reviewItem.status), []);
      article.classList.add("review-record");
      article.dataset.findingId = reviewItem.finding_id;
      article.tabIndex = -1;
      const identifiers = create("details", "analysis-calculation");
      identifiers.append(create("summary", null, "기록 식별자"),
        create("p", "mono", "Finding " + fmt(reviewItem.finding_id)),
        create("p", "mono", "Run " + fmt(reviewItem.analysis_run_id)),
        create("p", "mono", "Evidence " + (reviewItem.evidence_ids || []).join(", ")));
      article.append(identifiers);
      const linkedIds = Array.isArray(reviewItem.evidence_ids) ? reviewItem.evidence_ids : [];
      const links = linkedIds.map((id) => [id,
        evidenceTargets.get(JSON.stringify([reviewItem.analysis_run_id, id]))]
      ).filter(([, target]) => target);
      if (links.length) {
        links.forEach(([id, target]) => {
          const button = create("button", "evidence-link", "분석 결과로 이동");
          button.type = "button";
          button.setAttribute("aria-label", "분석 결과로 이동 · " + id);
          button.addEventListener("click", () => navigate("#evidence", target));
          article.append(button);
        });
      } else {
        article.append(create("p", "review-evidence-unavailable", "연결된 분석 결과가 이번 조회에 없습니다."));
      }
      if (!reviewWritesAllowed || reviewItem.status === "closed") return;
      const form = create("form", "review-form");
      const label = create("label", null, "메모");
      const field = create("textarea");
      field.rows = 2; field.maxLength = 1000; field.required = true;
      label.append(field);
      const save = create("button", null, "메모 저장");
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
      const button = create("button", null, next === "close" ? "완료로 표시" : "확인함으로 표시");
      button.type = "button";
      button.addEventListener("click", () => {
        if (next === "close" && !window.confirm("이 확인 기록을 완료로 표시할까요?")) return;
        postReview("/api/v1/reviews/action", {
          finding_id: reviewItem.finding_id, action: next, note: "",
        }, button);
      });
      article.append(button);
    });
    if (monitor.system_error_scopes && monitor.system_error_scopes.length) {
      setNotice("일부 저장소를 읽지 못해 빠진 기록이 있을 수 있습니다 (" + monitor.system_error_scopes.join(", ") + ").", true);
    }
  }
  async function initializeReviewAccess() {
    try {
      const session = await getJSON("/api/v1/session");
      reviewWritesAllowed = session.write_scope === "supervisor-owned-source-control";
    } catch (_) {
      reviewWritesAllowed = false;
    }
    await refresh();
  }
  function openSavedAnalysis(saved, collection) {
    if (!rows(getMonitor(), collection).some((run) => run.asset_id === saved.asset_id
        && run.analysis_run_id === saved.analysis_run_id && run.evidence_id === saved.evidence_id)) return;
    setAsset(saved.asset_id);evidenceViews();navigate("#evidence");
    const target = [...byId("evidence-results").querySelectorAll(".evidence-target")]
      .find((item) => item.dataset.analysisRunId === saved.analysis_run_id && item.dataset.evidenceId === saved.evidence_id);
    if (target) {target.focus({preventScroll: true});target.scrollIntoView({block: "center"});}
  }
  return {render: evidenceViews, initialize: initializeReviewAccess, openSavedAnalysis};
}
