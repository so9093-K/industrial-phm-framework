// Package-owned summaries only. No local path input, dataset download or analysis writes.
const node = (tag, text, className = "") => {
  const element = document.createElement(tag);
  element.textContent = text;
  element.className = className;
  return element;
};
const stageNames = {
  Dataset: "데이터셋", Input: "입력", Preprocessing: "전처리", Model: "모델",
  Evaluation: "평가", Capability: "적용 범위", Provenance: "실행 출처",
};
let sequence = 0;

async function loadResearch() {
  const token = ++sequence;
  const state = document.getElementById("research-state");
  const root = document.getElementById("research-results");
  const button = document.getElementById("research-refresh");
  root.replaceChildren();
  button.disabled = true;
  state.textContent = "저장소의 연구 결과를 읽는 중입니다.";
  try {
    const response = await fetch("/web/research-results.json", {cache: "no-store"});
    if (!response.ok) throw new Error("read-failed");
    const data = await response.json();
    if (token !== sequence) return;
    if (data.schema_version !== 1 || data.meaning !== "research-evaluation-not-workspace-data"
        || !Array.isArray(data.items)) throw new Error("schema-mismatch");
    for (const item of data.items) {
      const card = node("article", "", "record research-result");
      card.append(node("h3", item.dataset + " · " + item.title), node("p", item.id, "muted"),
        node("p", "연구 평가 결과 · 현재 설비 상태 또는 현장 진단이 아닙니다.", "tag"));
      const details = node("details", "");
      details.append(node("summary", "평가·출처·적용 범위 확인"));
      details.append(node("p", "원본 데이터는 함께 배포되지 않습니다. 이 PC의 원본 보유 여부와 재실행 가능 여부는 별도 확인이 필요합니다.", "hint"));
      details.append(node("p", "결과 파일: " + item.artifact_path),
        node("p", "결과 SHA-256: " + item.artifact_sha256));
      if (item.inspection) {
        for (const stage of item.inspection.stages) {
          details.append(node("h4", stageNames[stage.name] || stage.name));
          const facts = node("dl", "", "facts");
          for (const fact of stage.facts) {
            const entry = node("div", "", "fact");
            entry.append(node("dt", fact.label), node("dd", String(fact.value)));
            facts.append(entry);
          }
          details.append(facts);
          for (const warning of stage.warnings) details.append(node("p", warning, "hint"));
        }
        details.append(node("h4", "Analysis Explorer에서 상세 확인"));
        details.append(node("pre", "INDUSTRIAL_PHM_ANALYSIS_ARTIFACT=" + item.artifact_path
          + " uv run --locked --group research marimo run apps/analysis_explorer.py"));
      } else {
        details.append(node("p", "이 결과 형식은 Web 요약·Analysis Explorer 검사를 지원하지 않습니다. 원본 JSON과 연구 문서에서 확인하세요.", "hint"));
      }
      const link = node("a", "저장소의 원본 결과 열기 (외부 GitHub)");
      const url = new URL(item.source_url);
      if (url.origin !== "https://github.com" || !url.pathname.startsWith("/so9093-K/industrial-phm-framework/blob/main/docs/research/results/")) throw new Error("invalid-source");
      link.href = url.href;link.target = "_blank";link.rel = "noopener noreferrer";
      details.append(link);card.append(details);root.append(card);
    }
    state.className = "state";
    state.textContent = "저장된 연구 결과 " + data.items.length + "건 · 현재 작업공간 기록과 별도";
  } catch (_) {
    if (token !== sequence) return;
    root.replaceChildren();
    state.className = "state error";
    state.textContent = "연구 결과 조회 실패 · 결과가 없다고 판단할 수 없습니다. 다시 불러오세요.";
  } finally {
    if (token === sequence) button.disabled = false;
  }
}

export function initializeResearch() {
  document.getElementById("research-refresh").addEventListener("click", loadResearch);
  loadResearch();
}
