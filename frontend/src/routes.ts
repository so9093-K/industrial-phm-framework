/** Browser location is selection context, never a source of measured or calculated facts. */
export const VIEWS = [
  "overview", "signals", "departures", "compare", "projection",
  "relation", "reviews", "spectrum", "features",
] as const;
export type View = (typeof VIEWS)[number];

type ViewInfo = { navigation: string; document: string; eyebrow: string;
  title: string; description: string };
export const VIEW_INFO: Record<View, ViewInfo> = {
  overview: {
    navigation: "새 관측 화면 검증", document: "관측 현황",
    eyebrow: "관측 · 사실 확인", title: "설비 관측 현황",
    description: "마지막으로 기록된 관측과 출처의 상태를 구분해서 확인합니다.",
  },
  signals: {
    navigation: "저장 신호 탐색", document: "저장 신호 탐색",
    eyebrow: "설비 조사 · 저장된 측정", title: "설비 신호 탐색",
    description: "선택한 신호의 원본 의미·시간 구간·품질을 구분해서 확인합니다.",
  },
  departures: {
    navigation: "기준 구간 이탈 조사", document: "기준 이탈 조사",
    eyebrow: "설비 조사 · 모델 없는 변화", title: "기준 구간 이탈 조사",
    description: "고른 신호가 선택한 기록 구간에서 얼마나 달라졌는지 탐색합니다. 설비 고장 진단이 아닙니다.",
  },
  compare: {
    navigation: "두 기간의 측정 비교", document: "두 구간 비교",
    eyebrow: "설비 조사 · 구간 A/B", title: "두 기간의 측정 비교",
    description: "측정 근거가 같은 두 기간의 대표값·결측·품질을 비교합니다. 구간 A는 검증된 정상 범위가 아닙니다.",
  },
  projection: {
    navigation: "조건부 상태 전망", document: "버전 연계 전망",
    eyebrow: "설비 전망 · 계산 근거", title: "조건부 상태 전망 검토",
    description: "같은 측정 버전일 때만 미래 신호 예측과 사용자 입력 기준 도달 전망을 함께 표시합니다.",
  },
  relation: {
    navigation: "동일 시각 신호 관계", document: "신호 관계",
    eyebrow: "설비 조사 · 신호 관계", title: "동일 시각 신호 관계 조사",
    description: "정확히 같은 출처·시각에 기록된 두 신호의 관측 짝을 비교합니다.",
  },
  reviews: {
    navigation: "사람 검토 기록", document: "검토 작업함",
    eyebrow: "검토 · 근거 일치 확인", title: "사람 검토 기록",
    description: "저장된 Finding과 정확히 연결된 AnalysisRun·Evidence를 확인합니다.",
  },
  spectrum: {
    navigation: "획득 원본 파형 PSD", document: "획득 원본 PSD",
    eyebrow: "획득 회차 · 원본 주파수", title: "획득 원본 파형 PSD 비교",
    description: "검증된 파형 원본으로부터 서버가 계산한 Welch PSD만 비교합니다.",
  },
  features: {
    navigation: "획득 특징값 2기간 비교", document: "획득 특징 비교",
    eyebrow: "획득 회차 · 저장 특징", title: "획득 특징값 A/B 비교",
    description: "서버 저장 획득 회차별 특징 통계와 수신·분석 누락을 구분해 비교합니다.",
  },
};

export function parseRoute(search: string): { view: View; assetId: string } {
  const params = new URLSearchParams(search);
  const requested = params.get("view");
  return {
    view: VIEWS.find((view) => view === requested) ?? "overview",
    assetId: params.get("monitor_asset") ?? "",
  };
}

/** Cross-workflow navigation carries only an asset and a chosen signal, not a
 * previous workflow's period, threshold, binding, version or review identity. */
export function viewUrl(view: View, assetId: string, channel: string | null): string {
  const params = new URLSearchParams();
  if (view !== "overview") params.set("view", view);
  if (assetId) params.set("monitor_asset", assetId);
  if (view !== "overview" && channel) params.set("monitor_channel", channel);
  return "/web-next/" + (params.size ? "?" + params.toString() : "");
}

/** Never reuse any old-asset query parameter, including parameters added by future
 * workflows. This is safer than maintaining an incomplete delete list. */
export function assetUrl(currentHref: string, assetId: string): string {
  if (!assetId) throw new Error("설비 식별자가 필요합니다.");
  const current = new URL(currentHref);
  return viewUrl(parseRoute(current.search).view, assetId, null);
}
