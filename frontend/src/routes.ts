/** Browser location is selection context, never a source of measured or calculated facts.
 * Pages are user tasks (docs/product/overview.md); analysis methods live inside an asset. */
export const PAGES = ["monitor", "assets", "investigations", "maintenance", "system"] as const;
export type Page = (typeof PAGES)[number];
export const TABS = ["summary", "anomaly", "signals", "change", "outlook"] as const;
export type Tab = (typeof TABS)[number];
export const METHODS = {anomaly: ["model", "baseline"], change: ["compare", "relation", "spectrum"]} as const;
export type Method = (typeof METHODS)[keyof typeof METHODS][number];
export type DataKind = "history" | "vibration";
export type Route = {page: Page; assetId: string; tab: Tab; method: Method | null; data: DataKind | null};

export const PAGE_INFO: Record<Page, {label: string; description: string}> = {
  monitor: {label: "관측 현황", description: "어느 설비에서 무엇이 언제 들어왔고, 먼저 확인할 설비가 어디인지 봅니다."},
  assets: {label: "설비·신호", description: "설비를 고르면 상태 요약부터 이상 징후·신호·변화·전망을 차례로 봅니다."},
  investigations: {label: "분석 기록", description: "어떤 입력과 모델로 언제 분석 결과가 나왔는지 확인합니다."},
  maintenance: {label: "정비 검토", description: "분석 결과와 검토 요청한 전망을 사람이 확인하고 메모·종료를 남깁니다. 검토 종료는 정비 완료를 뜻하지 않습니다."},
  system: {label: "운영 관리", description: "로컬 서비스 실행 상태, 데이터 연결과 저장소 조회 상태를 확인합니다."},
};
export const TAB_INFO: Record<Tab, string> = {
  summary: "상태 요약", anomaly: "이상 징후", signals: "신호", change: "변화 분석", outlook: "상태 전망",
};
export const METHOD_INFO: Record<Method, string> = {
  model: "모델 점수", baseline: "기준 구간 이탈",
  compare: "두 기간 비교", relation: "신호 관계", spectrum: "주파수 분석",
};
export const DATA_INFO: Record<DataKind, string> = {history: "시계열 기록", vibration: "진동 측정"};

/** Addresses from before the task navigation keep working and land on the same workflow. */
const LEGACY: Record<string, Omit<Route, "assetId">> = {
  overview: {page: "monitor", tab: "summary", method: null, data: null},
  signals: {page: "assets", tab: "signals", method: null, data: null},
  departures: {page: "assets", tab: "anomaly", method: "baseline", data: null},
  "model-evidence": {page: "assets", tab: "anomaly", method: "model", data: null},
  compare: {page: "assets", tab: "change", method: "compare", data: "history"},
  features: {page: "assets", tab: "change", method: "compare", data: "vibration"},
  relation: {page: "assets", tab: "change", method: "relation", data: "history"},
  "acq-relation": {page: "assets", tab: "change", method: "relation", data: "vibration"},
  spectrum: {page: "assets", tab: "change", method: "spectrum", data: "vibration"},
  projection: {page: "assets", tab: "outlook", method: null, data: "history"},
  "acq-outlook": {page: "assets", tab: "outlook", method: null, data: "vibration"},
  reviews: {page: "maintenance", tab: "summary", method: null, data: null},
};

function oneOf<T extends string>(values: readonly T[], raw: string | null): T | null {
  return values.find((value) => value === raw) ?? null;
}
export function methodsOf(tab: Tab): readonly Method[] {
  return tab === "anomaly" || tab === "change" ? METHODS[tab] : [];
}
/** Spectrum exists only for vibration waveforms; the other methods choose a data kind. */
export function usesDataKind(tab: Tab, method: Method | null): boolean {
  return tab === "outlook" || (tab === "change" && method !== "spectrum");
}

export function parseRoute(search: string): {route: Route; legacy: boolean} {
  const params = new URLSearchParams(search);
  const assetId = params.get("monitor_asset") ?? "";
  const legacy = LEGACY[params.get("view") ?? ""];
  if (legacy && !params.has("page")) return {route: {...legacy, assetId}, legacy: true};
  const page = oneOf(PAGES, params.get("page")) ?? "monitor";
  const tab = oneOf(TABS, params.get("tab")) ?? "summary";
  const method = oneOf(methodsOf(tab), params.get("method"));
  const data = usesDataKind(tab, method) ? oneOf(["history", "vibration"] as const, params.get("data")) : null;
  return {route: {page, assetId, tab, method, data}, legacy: params.has("view")};
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
  return "/web-next/" + (params.size ? "?" + params.toString() : "");
}

/** The canonical address of a legacy link keeps the workflow's own parameters. */
export function canonicalUrl(search: string): string {
  const {route} = parseRoute(search);
  const target = new URL(routeUrl(route), "http://local");
  for (const [key, value] of new URLSearchParams(search)) {
    if (key !== "view" && !target.searchParams.has(key)) target.searchParams.set(key, value);
  }
  return target.pathname + target.search;
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

/** The one review subject a maintenance address names; the server still checks its asset. */
export function reviewFocus(search: string): {captureId: string | null; findingId: string | null} {
  const params = new URLSearchParams(search);
  if (params.get("page") !== "maintenance") return {captureId: null, findingId: null};
  return {captureId: params.get("capture_id"), findingId: params.get("finding_id")};
}
