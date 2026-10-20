/** Browser location is selection context, never a source of measured or calculated facts.
 * Pages are user tasks (docs/product/overview.md); analysis methods live inside an asset. */
export const PAGES = ["monitor", "assets", "investigations", "maintenance", "system"] as const;
export type Page = (typeof PAGES)[number];
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
/** Spectrum exists only for vibration waveforms and load/unbalance only for 3-phase history;
 * the other methods choose a data kind. */
export function usesDataKind(tab: Tab, method: Method | null): boolean {
  return tab === "outlook" || (tab === "change" && method !== "spectrum" && method !== "electrical");
}

const HASH_VIEWS: Record<string, Omit<Route,"assetId">> = {
  monitor: LEGACY.overview, research: LEGACY.overview,
  signals: LEGACY.signals,
  anomaly: LEGACY["model-evidence"],
  forecast: LEGACY.projection, rul: LEGACY.projection,
  connect: {page:"system",tab:"summary",method:null,data:null},
  system: {page:"system",tab:"summary",method:null,data:null},
  evidence: {page:"investigations",tab:"summary",method:null,data:null},
  review: {page:"maintenance",tab:"summary",method:null,data:null},
};
const PARAM_ALIASES: Record<string,string> = {phm_binding:"model_binding",phm_position:"model_position",phm_compare:"model_compare"};
export function parseRoute(search: string, hash = ""): {route: Route; legacy: boolean} {
  const params = new URLSearchParams(search);
  const assetId = params.get("monitor_asset") ?? "";
  const legacy = LEGACY[params.get("view") ?? ""];
  if (legacy && !params.has("page")) return {route: {...legacy, assetId}, legacy: true};
  let former=HASH_VIEWS[hash.replace(/^#/,"")];
  if((hash==="#forecast"||hash==="#rul")&&params.get("forecast_series")?.startsWith("acquisition|"))former=LEGACY["acq-outlook"];
  if(hash==="#signals"&&params.has("explore_kind"))former=params.get("explore_kind")==="acquisition"?LEGACY.features:LEGACY.compare;
  if(former&&!params.has("page"))return {route:{...former,assetId},legacy:true};
  const page = oneOf(PAGES, params.get("page")) ?? "monitor";
  const tab = oneOf(TABS, params.get("tab")) ?? "summary";
  const method = oneOf(methodsOf(tab), params.get("method"));
  const data = usesDataKind(tab, method) ? oneOf(["history", "vibration"] as const, params.get("data")) : null;
  return {route: {page, assetId, tab, method, data}, legacy: params.has("view")||Object.keys(PARAM_ALIASES).some(key=>params.has(key))};
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

/** The canonical address of a legacy link keeps the workflow's own parameters. */
export function canonicalUrl(search: string, hash = ""): string {
  const {route} = parseRoute(search,hash);
  const target = new URL(routeUrl(route), "http://local");
  for (const [key, value] of new URLSearchParams(search)) {
    if(key==="view"||key==="phm_view")continue;
    const next=PARAM_ALIASES[key]??key;
    if(!target.searchParams.has(next))target.searchParams.set(next,value);
  }
  const old=new URLSearchParams(search);
  if(hash==="#forecast"||hash==="#rul"){
    const series=old.get("forecast_series"),acq=series?.startsWith("acquisition|");
    if(series)target.searchParams.set(acq?"acq_forecast_feature":"monitor_channel",series.slice(series.indexOf("|")+1));
    const mapping=acq?{forecast_horizon:"acq_forecast_horizon",forecast_unit:"acq_forecast_unit",forecast_count:"acq_forecast_count",forecast_assumed_period:"acq_assumed_period",forecast_threshold:"acq_management",forecast_end:"acq_end",forecast_direction:"acq_direction"}
      :{forecast_horizon:"projection_horizon",forecast_threshold:"projection_management",forecast_end:"projection_end",forecast_direction:"projection_direction"};
    for(const [from,to] of Object.entries(mapping))if(old.has(from))target.searchParams.set(to,old.get(from)!);
    if(acq&&!old.has("forecast_unit"))target.searchParams.set("acq_forecast_unit","time");
  }
  if(hash==="#signals"&&old.has("explore_kind")){
    const acquisition=old.get("explore_kind")==="acquisition";
    if(old.has("explore_series"))target.searchParams.set(acquisition?"acquisition_feature":"monitor_channel",old.get("explore_series")!.split(",")[0]);
    for(const period of ["a","b"]){
      const span=old.get("explore_"+period);
      if(!span)continue;
      if(!acquisition)target.searchParams.set("compare_"+period,span);
      else {const [from,to]=span.split("~");if(from&&to){target.searchParams.set("feature_"+period+"_from",from);target.searchParams.set("feature_"+period+"_to",to);}}
    }
  }
  if(hash==="#system")target.searchParams.set("section","status");
  if(hash==="#connect")target.searchParams.set("section","connections");
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
