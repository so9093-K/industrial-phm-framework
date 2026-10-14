// Keep routes independent of browser data reads and writes.
const views = {
  monitor: ["설비 모니터링", "설비를 고르고 실제 측정 신호와 변화를 확인합니다."],
  signals: ["설비 모니터링", "선택 설비의 여러 신호를 같은 기간으로 비교합니다."],
  anomaly: ["설비 모니터링", "선택 설비의 이상 점수와 기준 초과 구간, 관련 신호를 확인합니다."],
  rul: ["설비 모니터링", "선택 설비의 잔여 수명 추정과 시점별 변화를 확인합니다."],
  evidence: ["설비 모니터링", "선택 설비의 저장된 분석 결과를 확인하고 메모를 남깁니다."],
  connect: ["데이터 연결", "CSV 파일이나 OPC UA 설비를 연결하고 저장 상태를 확인합니다."],
  system: ["시스템 상태", "로컬 서비스와 저장소 상태를 확인합니다."],
};
// Asset views are tabs of one Monitor; retired routes open their replacement.
const ASSET_VIEWS = new Set(["monitor", "signals", "anomaly", "rul", "evidence"]);
const RETIRED = {review: "evidence", research: "monitor"};

export function renderView() {
  let route = location.hash.slice(1) || "monitor";
  if (route === "main") route = document.body.dataset.view || "monitor";
  if (Object.hasOwn(RETIRED, route)) {
    route = RETIRED[route];
    history.replaceState(history.state, "", "#" + route);
  }
  if (!Object.hasOwn(views, route)) {
    route = "monitor";
    history.replaceState(null, "", "#monitor");
  }
  document.body.dataset.view = route;
  document.querySelectorAll("[data-views]").forEach((element) => {
    element.hidden = !element.dataset.views.split(" ").includes(route);
  });
  const section = ASSET_VIEWS.has(route) ? "monitor" : route;
  document.querySelectorAll(".sidebar nav a").forEach((link) => {
    if (link.hash === "#" + section) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  document.querySelectorAll(".asset-tabs a").forEach((link) => {
    if (link.dataset.tab === route) link.setAttribute("aria-current", "page");
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
    for (let parent = target.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") parent.open = true;
    }
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
