/** Browser location is selection context, never a source of measured or calculated facts.
 * Pages are user tasks (docs/product/overview.md); analysis methods live inside an asset. */
export const PAGES = ["monitor", "assets", "investigations", "maintenance", "system"] as const;
export type Page = (typeof PAGES)[number];
/** Primary PHM tasks; records and human review remain available through exact deep links. */
export const PRIMARY_PAGES = ["monitor", "assets", "system"] as const;
export const TABS = ["summary", "signals", "change", "anomaly", "outlook"] as const;
export type Tab = (typeof TABS)[number];
export const METHODS = {anomaly: ["model", "baseline"], change: ["compare", "relation", "spectrum", "electrical"]} as const;
export type Method = (typeof METHODS)[keyof typeof METHODS][number];
export type DataKind = "history" | "vibration";
export type Route = {page: Page; assetId: string; tab: Tab; method: Method | null; data: DataKind | null};

export const PAGE_INFO: Record<Page, {label: string; description: string}> = {
  monitor: {label: "관측 현황", description: "설비별 주요 변화 · 모델 결과 · 검토 상태"},
  assets: {label: "설비·신호", description: "설비별 모니터링과 변화 분석 · 이상 징후 · 원본 신호 · 신호 추세 전망"},
  investigations: {label: "분석 기록", description: "분석 결과별 입력 · 모델 · 분석 시각"},
  maintenance: {label: "정비 검토", description: "저장한 분석 결과와 전망의 판단 · 메모 기록"},
  system: {label: "운영 관리", description: "로컬 서비스 실행 상태 · 데이터 연결 · 저장소 조회 상태"},
};
export const TAB_INFO: Record<Tab, string> = {
  summary: "모니터링", anomaly: "이상 징후", signals: "원본 신호", change: "변화 분석", outlook: "신호 추세 전망",
};
export const METHOD_INFO: Record<Method, string> = {
  model: "모델 이상 점수", baseline: "기록 변화 찾기",
  compare: "두 기간 비교", relation: "신호 관계", spectrum: "주파수 분석", electrical: "3상 전력·불평형",
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

export function parseRoute(search: string): Route {
  const params = new URLSearchParams(search);
  const assetId = params.get("monitor_asset") ?? "";
  const page = oneOf(PAGES, params.get("page")) ?? "monitor";
  const tab = oneOf(TABS, params.get("tab")) ?? "summary";
  const method = oneOf(methodsOf(tab), params.get("method"));
  const data = usesDataKind(tab, method) ? oneOf(["history", "vibration"] as const, params.get("data")) : null;
  return {page, assetId, tab, method, data};
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
 * Measurements, compared results and periods follow; calculation settings and review identities do not. */
const OBSERVATION_PARAMS = ["monitor_channel","record_key","monitor_source","monitor_point","monitor_interpretation","monitor_range","monitor_from","monitor_to","monitor_pick","compare_a","compare_b","compare_origin","compare_level","relation_x","relation_y","summary_change","summary_kind",
  "vibration_feature","vibration_at","acquisition_feature","acq_forecast_feature","acq_relation_x","acq_relation_y",
  "feature_a_from","feature_a_to","feature_b_from","feature_b_to","acq_a_from","acq_a_to","acq_b_from","acq_b_to",
  "spectrum_a_from","spectrum_a_to","spectrum_b_from","spectrum_b_to","spectrum_hz_from","spectrum_hz_to","spectrum_hz","spectrum_channel",
  "spectrum_band","spectrum_measurement","spectrum_view","spectrum_scale","acquisition_binding",
  "model_binding","model_position","model_compare"];

/** Remember a summary choice in the address without navigating or carrying a prior change's filters. */
export function summarySelectionUrl(currentHref: string, selectionHref: string, key: string, kind: DataKind): string {
  const current=new URL(currentHref), selection=new URL(selectionHref,current);
  if(selection.origin!==current.origin||parseRoute(current.search).assetId!==parseRoute(selection.search).assetId)
    throw new Error("같은 설비의 변화만 이어서 볼 수 있습니다.");
  for(const name of OBSERVATION_PARAMS) current.searchParams.delete(name);
  for(const name of OBSERVATION_PARAMS) if(selection.searchParams.has(name)) current.searchParams.set(name,selection.searchParams.get(name)!);
  current.searchParams.set("summary_change",key);
  current.searchParams.set("summary_kind",kind);
  return current.pathname+current.search+current.hash;
}

export function tabSelectionUrl(href: string, currentHref: string): string {
  const current = new URL(currentHref), next = new URL(href, current);
  const from = parseRoute(current.search), to = parseRoute(next.search);
  if (next.origin !== current.origin) return next.href;
  if (to.page !== "assets" || from.page !== "assets"
    || !from.assetId || from.assetId !== to.assetId) return next.pathname + next.search + next.hash;
  for(const key of OBSERVATION_PARAMS)
    if(current.searchParams.has(key))next.searchParams.set(key,current.searchParams.get(key)!);
  const selectedKind=to.data??from.data??current.searchParams.get("summary_kind");
  if((selectedKind==="history"||selectedKind==="vibration")&&usesDataKind(to.tab,to.method)) {
    next.searchParams.set("data",selectedKind);
    if(current.searchParams.has("summary_kind"))next.searchParams.set("summary_kind",selectedKind);
  }
  // Feature comparison and relationship screens name the same acquisition periods differently.
  if(from.tab==="change"&&(from.method===null||["compare","relation","spectrum"].includes(from.method))) {
    const prefix=from.method==="relation"?"acq_":from.method==="spectrum"?"spectrum_":"feature_";
    for(const span of ["a_from","a_to","b_from","b_to"])
      if(current.searchParams.has(prefix+span))for(const target of ["feature_","acq_","spectrum_"])
        next.searchParams.set(target+span,current.searchParams.get(prefix+span)!);
  }
  if(to.tab==="anomaly"&&from.tab==="signals"&&current.searchParams.has("vibration_at")) {
    next.searchParams.set("model_position",current.searchParams.get("vibration_at")!);
    const binding=current.searchParams.get("acquisition_binding");
    if(binding)next.searchParams.set("model_binding",binding);
  }
  const keys = {signals: "vibration_feature", change: "acquisition_feature", outlook: "acq_forecast_feature"};
  const sourceKey = keys[from.tab as keyof typeof keys], targetKey = keys[to.tab as keyof typeof keys];
  const feature = (from.tab==="change"&&from.method==="relation"?current.searchParams.get("acq_relation_x"):null)
    ?? (sourceKey ? current.searchParams.get(sourceKey) : null)
    ?? Object.values(keys).map(key => current.searchParams.get(key)).find(value => value);
  if (feature) next.searchParams.set(targetKey ?? "vibration_feature", feature);
  if(to.method==="relation"&&!(from.tab==="change"&&from.method==="relation")) {
    const channel=current.searchParams.get("monitor_channel");
    if(channel)next.searchParams.set("relation_x",channel);
    if(feature)next.searchParams.set("acq_relation_x",feature);
  }
  return next.pathname + next.search + next.hash;
}

/** Never reuse any old-asset query parameter, including parameters added by future
 * workflows. This is safer than maintaining an incomplete delete list. */
export function assetUrl(currentHref: string, assetId: string): string {
  if (!assetId) throw new Error("설비 식별자가 필요합니다.");
  const route = parseRoute(new URL(currentHref).search);
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
