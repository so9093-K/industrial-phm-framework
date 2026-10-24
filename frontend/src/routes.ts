/** Browser location is selection context, never a source of measured or calculated facts.
 * Pages are user tasks (docs/product/overview.md); analysis methods live inside an asset. */
export const PAGES = ["monitor", "assets", "investigations", "maintenance", "system"] as const;
export type Page = (typeof PAGES)[number];
/** Primary PHM tasks; records and human review remain available through exact deep links. */
export const PRIMARY_PAGES = ["monitor", "assets", "system"] as const;
export const TABS = ["summary", "anomaly", "signals", "change", "outlook"] as const;
export type Tab = (typeof TABS)[number];
export const METHODS = {anomaly: ["model", "baseline"], change: ["compare", "relation", "spectrum", "electrical"]} as const;
export type Method = (typeof METHODS)[keyof typeof METHODS][number];
export type DataKind = "history" | "vibration";
export type Route = {page: Page; assetId: string; tab: Tab; method: Method | null; data: DataKind | null};

export const PAGE_INFO: Record<Page, {label: string; description: string}> = {
  monitor: {label: "관측 현황", description: "어느 설비에서 무엇이 언제 들어왔고, 먼저 확인할 설비가 어디인지 봅니다."},
  assets: {label: "설비·신호", description: "설비를 고르면 상태 요약부터 이상 징후·신호·변화·전망을 차례로 봅니다."},
  investigations: {label: "분석 기록", description: "어떤 입력과 모델로 언제 분석 결과가 나왔는지 확인합니다."},
  maintenance: {label: "정비 검토", description: "검토 요청한 분석 결과와 전망을 사람이 확인하고 종료합니다."},
  system: {label: "운영 관리", description: "로컬 서비스 실행 상태, 데이터 연결과 저장소 조회 상태를 확인합니다."},
};
export const TAB_INFO: Record<Tab, string> = {
  summary: "상태 요약", anomaly: "이상 징후", signals: "신호", change: "변화 분석", outlook: "상태 전망",
};
export const METHOD_INFO: Record<Method, string> = {
  model: "모델 점수", baseline: "기준 구간 이탈",
  compare: "두 기간 비교", relation: "신호 관계", spectrum: "주파수 분석", electrical: "부하·불평형",
};
export const DATA_INFO: Record<DataKind, string> = {history: "시계열 기록", vibration: "진동 측정"};

function oneOf<T extends string>(values: readonly T[], raw: string | null): T | null {
  return values.find((value) => value === raw) ?? null;
}
export function methodsOf(tab: Tab): readonly Method[] {
  return tab === "anomaly" || tab === "change" ? METHODS[tab] : [];
}
/** Spectrum exists only for vibration waveforms and load/unbalance only for 3-phase history;
 * the other methods choose a data kind. */
export function usesDataKind(tab: Tab, method: Method | null): boolean {
  return tab === "outlook" || (tab === "change" && method !== "spectrum" && method !== "electrical");
}

export function parseRoute(search: string): {route: Route} {
  const params = new URLSearchParams(search);
  const assetId = params.get("monitor_asset") ?? "";
  const page = oneOf(PAGES, params.get("page")) ?? "monitor";
  const tab = oneOf(TABS, params.get("tab")) ?? "summary";
  const method = oneOf(methodsOf(tab), params.get("method"));
  const data = usesDataKind(tab, method) ? oneOf(["history", "vibration"] as const, params.get("data")) : null;
  return {route: {page, assetId, tab, method, data}};
}

/** Only the route itself and an asset's chosen signal travel between screens; a previous
 * workflow's period, threshold, binding, version or review identity never does. */
export function routeUrl(route: Route, channel: string | null = null): string {
  const params = new URLSearchParams();
  if (route.page !== "monitor") params.set("page", route.page);
  if (route.page === "assets") {
    if (route.tab !== "summary") params.set("tab", route.tab);
    if (route.method && methodsOf(route.tab).includes(route.method)) params.set("method", route.method);
    if (route.data && usesDataKind(route.tab, route.method)) params.set("data", route.data);
  }
  if (route.assetId) params.set("monitor_asset", route.assetId);
  if (route.page === "assets" && channel) params.set("monitor_channel", channel);
  return "/web/" + (params.size ? "?" + params.toString() : "");
}

/** Resolve tab links when activated, after the child may have changed its URL selection.
 * Only the selected signal/feature follows; forecast settings and comparison ranges do not. */
export function tabSelectionUrl(href: string, currentHref: string): string {
  const current = new URL(currentHref), next = new URL(href, current);
  const from = parseRoute(current.search).route, to = parseRoute(next.search).route;
  if (next.origin !== current.origin) return next.href;
  if (to.page !== "assets" || from.page !== "assets"
    || !from.assetId || from.assetId !== to.assetId) return next.pathname + next.search + next.hash;
  const channel = current.searchParams.get("monitor_channel");
  if (channel) next.searchParams.set("monitor_channel", channel);
  const keys = {signals: "vibration_feature", change: "acquisition_feature", outlook: "acq_forecast_feature"};
  const sourceKey = keys[from.tab as keyof typeof keys], targetKey = keys[to.tab as keyof typeof keys];
  const feature = (sourceKey ? current.searchParams.get(sourceKey) : null)
    ?? Object.values(keys).map(key => current.searchParams.get(key)).find(value => value);
  if (feature) next.searchParams.set(targetKey ?? "vibration_feature", feature);
  return next.pathname + next.search + next.hash;
}

/** Never reuse any old-asset query parameter, including parameters added by future
 * workflows. This is safer than maintaining an incomplete delete list. */
export function assetUrl(currentHref: string, assetId: string): string {
  if (!assetId) throw new Error("설비 식별자가 필요합니다.");
  const {route} = parseRoute(new URL(currentHref).search);
  const page = route.page === "monitor" ? "assets" : route.page;
  return routeUrl({...route, page, assetId, data: null});
}

/** Workflow links inside an asset (e.g. from a signal to its outlook). */
export function assetTabUrl(
  assetId: string, tab: Tab, method: Method | null = null,
  data: DataKind | null = null, channel: string | null = null,
): string {
  return routeUrl({page: "assets", assetId, tab, method, data}, channel);
}

export type SystemSection = "connections" | "status";
/** Which part of 운영 관리 an address opens; data connections unless it asks for status. */
export function systemSection(search: string): SystemSection {
  return new URLSearchParams(search).get("section") === "status" ? "status" : "connections";
}
export function systemUrl(section: SystemSection): string {
  return "/web/?" + new URLSearchParams({page: "system", section});
}

/** The one review subject a maintenance address names; the server still checks its asset. */
export function reviewFocus(search: string): {captureId: string | null; findingId: string | null} {
  const params = new URLSearchParams(search);
  if (params.get("page") !== "maintenance") return {captureId: null, findingId: null};
  return {captureId: params.get("capture_id"), findingId: params.get("finding_id")};
}
