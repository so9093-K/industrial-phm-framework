// Keep routes independent of browser data reads and writes.
const views = {
  monitor: ["설비 모니터링", "설비의 부하 변화와 불평형, 기준 운전 패턴과의 차이를 확인합니다."],
  connect: ["데이터 연결", "소스를 선택하고 수신·저장·분석 근거를 차례로 확인합니다."],
  signals: ["설비 · 신호", "선택한 설비의 기록 시각, 출처와 측정 신호를 확인합니다."],
  anomaly: ["이상 탐지", "모델 이상 점수와 검토 구간을 입력 특징·원본 파형과 같은 축에서 확인합니다."],
  rul: ["RUL 모니터링", "잔여 수명 추정이 시점마다 어떻게 갱신됐는지와 모델의 검증 범위를 확인합니다."],
  evidence: ["분석 결과", "선택한 설비의 분석 결과와 적용 범위를 확인합니다."],
  review: ["검토 작업", "확인이 필요한 분석을 선택하고 검토합니다."],
  research: ["연구 · 검증 결과", "저장소의 연구 평가 결과입니다. 현재 설비 관측과 구분합니다."],
  system: ["운영 관리", "로컬 실행 상태와 저장소 조회 오류를 확인합니다."],
};

export function renderView() {
  let route = location.hash.slice(1) || "monitor";
  if (route === "main") route = document.body.dataset.view || "monitor";
  if (!Object.hasOwn(views, route)) {
    route = "monitor";
    history.replaceState(null, "", "#monitor");
  }
  document.body.dataset.view = route;
  document.querySelectorAll("[data-views]").forEach((element) => {
    element.hidden = !element.dataset.views.split(" ").includes(route);
  });
  document.querySelectorAll(".sidebar nav a").forEach((link) => {
    if (link.hash === "#" + route) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const [title, description] = views[route];
  document.getElementById("view-title").textContent = title;
  document.getElementById("view-description").textContent = description;
  document.title = "Industrial PHM · " + title;
}

export function navigate(hash, target = null) {
  if (location.hash !== hash) location.hash = hash;
  // Reveal the view before focusing a cross-view review or workflow target.
  renderView();
  if (target) {
    target.focus({preventScroll: true});
    target.scrollIntoView({block: "center"});
  }
}

export function initializeNavigation() {
  window.addEventListener("hashchange", () => {
    renderView();
  });
  window.addEventListener("popstate", renderView);
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    if (link.classList.contains("skip-link")) return;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(link.hash);
      window.scrollTo(0, 0);
      document.getElementById("view-title").focus({preventScroll: true});
    });
  });
  renderView();
}
