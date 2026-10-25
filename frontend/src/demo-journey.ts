/** Selection context for the real Operations pages; observations always come from their APIs. */
export type DemoJourney = {
  dataset: "synthetic" | "xjtu-sy"; assetId: string; bindings: string[];
  first: number; last: number; feature: string; otherFeature: string;
};
export function parseDemoJourney(raw: unknown): DemoJourney | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const value = raw as Record<string, unknown>;
  const text = (key: string) => typeof value[key] === "string" && (value[key] as string).length > 0
    && (value[key] as string).length <= 256;
  if (!text("asset_id") || !text("feature") || !text("other_feature")
    || (value.dataset !== "synthetic" && value.dataset !== "xjtu-sy")
    || !Array.isArray(value.bindings) || value.bindings.length !== 2
    || value.bindings.some(item => typeof item !== "string" || !item || item.length > 256)
    || !Number.isSafeInteger(value.first) || !Number.isSafeInteger(value.last)
    || Number(value.first) < 1 || Number(value.last) <= Number(value.first)) return null;
  return {dataset: value.dataset, assetId: value.asset_id as string,
    bindings: value.bindings as string[], first: Number(value.first), last: Number(value.last),
    feature: value.feature as string, otherFeature: value.other_feature as string};
}

export function bearingSteps(journey: DemoJourney, search = "") {
  const split = Math.floor((journey.first + journey.last) / 2);
  const current = new URLSearchParams(search);
  const sameAsset = current.get("monitor_asset") === journey.assetId;
  const value = (key: string) => sameAsset ? current.get(key) : null;
  const featureKey = current.get("tab") === "signals" ? "vibration_feature"
    : current.get("method") === "relation" ? "acq_relation_x" : "acquisition_feature";
  const candidate = value(featureKey) ?? value("demo_feature") ?? journey.feature;
  const feature = candidate.startsWith("feature.") && candidate.length <= 256 ? candidate : journey.feature;
  const other = feature === journey.otherFeature ? journey.feature : journey.otherFeature;
  const requestedBinding = value("model_binding") ?? value("demo_binding");
  const binding = requestedBinding && journey.bindings.includes(requestedBinding) ? requestedBinding : journey.bindings[0];
  const bounded = (key: string, fallback: number) => {
    const text = value(key), number = text === null ? NaN : Number(text);
    return Number.isSafeInteger(number) && number >= journey.first && number <= journey.last ? number : fallback;
  };
  const position = bounded("model_position", bounded("demo_position", journey.last));
  const prefix = current.get("method") === "spectrum" ? "spectrum_"
    : current.get("method") === "relation" ? "acq_" : "feature_";
  const aFrom = bounded(prefix + "a_from", bounded("demo_a_from", journey.first));
  const aTo = bounded(prefix + "a_to", bounded("demo_a_to", split));
  const bFrom = bounded(prefix + "b_from", bounded("demo_b_from", split + 1));
  const bTo = bounded(prefix + "b_to", bounded("demo_b_to", journey.last));
  const spans = aFrom <= aTo && bFrom <= bTo ? {aFrom,aTo,bFrom,bTo}
    : {aFrom:journey.first,aTo:split,bFrom:split+1,bTo:journey.last};
  const returnPath = current.get("return_to");
  let returnTo: Record<string, string> = {};
  if (returnPath) {
    try {
      const back = new URL(returnPath);
      if (back.protocol === "http:" && (back.hostname === "127.0.0.1" || back.hostname === "localhost") && back.port
        && back.pathname === "/web/") returnTo = {return_to: back.origin + "/web/?page=system"};
    } catch { /* Invalid return destinations do not enter the guide links. */ }
  }
  const carried = {...returnTo,demo_feature:feature,demo_binding:binding,demo_position:position,
    demo_a_from:spans.aFrom,demo_a_to:spans.aTo,demo_b_from:spans.bFrom,demo_b_to:spans.bTo};
  const url = (selection: Record<string, string | number>, hash = "") => "/web/?" + new URLSearchParams(
    Object.entries({page: "assets", monitor_asset: journey.assetId, ...carried, ...selection})
      .map(([key, value]) => [key, String(value)])) + hash;
  const model = {tab: "anomaly", method: "model", model_binding: binding, model_position: position};
  return [
    {id: "data", label: "1. 기록 이해", title: "어떤 기록을 조사하나요?",
      question: journey.dataset === "synthetic"
        ? "기록의 출처와 두 모델을 확인하고, 변화 기록과 일정한 기록을 구분해 보세요."
        : `${journey.assetId}의 ${journey.first}~${journey.last}번째 실측 기록을 조사합니다. 두 모델이 다른 판단을 내린 측정부터 근거를 살펴보세요.`,
      href: url({}), evidence: journey.dataset === "synthetic"
        ? "별도의 일정한 합성 참조 기록으로 두 모델을 학습했습니다. 체험용 두 기록은 학습에 사용하지 않았습니다. 변화 기록의 후반부에는 진폭·주파수 성분·충격을 의도적으로 추가했습니다."
        : "XJTU-SY의 실제 베어링 진동 기록입니다. 두 모델을 학습한 베어링과 이 기록을 분리했습니다. 과거 기록의 재생이며 현재 현장 설비의 수신이 아닙니다."},
    {id: "models", label: "2. 모델 비교", title: "두 모델은 언제부터 다르게 보나요?",
      question: "모델별 점수를 각 모델의 기준 대비로 비교하세요. 모델을 바꿔도 같은 측정을 살펴봅니다.",
      href: url(model), evidence: "Isolation Forest와 LSTM 오토인코더의 실제 계산입니다. LSTM은 앞선 8회가 모인 뒤부터 점수를 계산합니다. 기준 초과는 고장 확률이나 확정 진단이 아닙니다."},
    {id: "signals", label: "3. 신호 확인", title: "실제 진동 특징도 달라졌나요?",
      question: "수평 RMS의 시간 흐름을 보고 수직 RMS로도 바꿔 보세요. 원본 파형은 모델 비교 화면의 선택 측정에서 확인합니다.",
      href: url({tab: "signals", vibration_feature: feature}),
      evidence: "특징값은 저장된 원본 파형에서 계산했습니다. 기록된 1분 간격으로 경과 시간을 표시하며, 실제 측정 날짜를 만들어내지 않습니다."},
    {id: "compare", label: "4. 두 기간 비교", title: "전반부와 후반부는 얼마나 다른가요?",
      question: "A와 B의 분포·중앙값·유효 측정 수를 비교하세요. 두 기간을 직접 조절해 다시 계산할 수 있습니다.",
      href: url({tab: "change", method: "compare", data: "vibration", acquisition_feature: feature,
        feature_a_from: spans.aFrom, feature_a_to: spans.aTo, feature_b_from: spans.bFrom, feature_b_to: spans.bTo}),
      evidence: "처음에는 A에 앞 절반, B에 뒤 절반을 선택합니다. 구간을 바꾸면 특징 관계·주파수 비교에도 같은 구간이 이어집니다. 실제 데이터에서 A를 검증된 정상 기준으로 가정하지 않습니다."},
    {id: "relation", label: "5. 특징 관계", title: "두 방향의 진동이 함께 변했나요?",
      question: "같은 측정의 수평·수직 RMS를 짝지은 산점도를 확인하세요. 축과 상관 계수를 함께 읽어 보세요.",
      href: url({tab: "change", method: "relation", data: "vibration", acq_relation_x: feature,
        acq_relation_y: other, acq_a_from: spans.aFrom, acq_a_to: spans.aTo,
        acq_b_from: spans.bFrom, acq_b_to: spans.bTo}),
      evidence: "같은 측정 번호의 두 특징만 비교합니다. 함께 증가하는 관계는 고장의 원인을 입증하지 않습니다."},
    {id: "spectrum", label: "6. 주파수 비교", title: "어떤 주파수 성분이 달라졌나요?",
      question: "같은 A/B 구간의 원본 파형을 주파수별로 비교하세요. 세로축을 dB로 바꾸면 세기가 작은 주파수의 변화도 보입니다.",
      href: url({tab: "change", method: "spectrum", spectrum_a_from: spans.aFrom,
        spectrum_a_to: spans.aTo, spectrum_b_from: spans.bFrom, spectrum_b_to: spans.bTo}),
      evidence: "원본 파형으로 계산한 Welch 스펙트럼입니다. 각 구간에서 최대 8회를 표본으로 사용하며 결함 주파수를 자동 진단하지 않습니다."},
    {id: "review", label: "7. 판단 남기기", title: "무엇을 더 확인해야 할까요?",
      question: "고른 모델·측정의 결과를 ‘검토 요청’으로 남기고, 정비 검토함에서 추가 점검·계속 관찰 같은 판단을 기록하세요. 검토할 측정은 모델 점수 화면의 측정 선택에서 바꿉니다.",
      href: url({...model, demo_step: "review"}, "#model-review"),
      evidence: "검토는 선택 사항입니다. 기록은 이 분리된 예시 작업공간에만 저장되며, 실제 정비 작업이 실행되는 것은 아닙니다. AI 해설 없이도 모델 비교·데이터 비교·검토를 마칠 수 있습니다."},
  ];
}

/** The guide step the current screen belongs to, or -1 on screens outside the investigation. */
export function bearingStep(search: string): number {
  const params = new URLSearchParams(search);
  if (params.get("demo_step") === "review" || params.get("page") === "maintenance") return 6;
  if (params.get("page") !== "assets") return -1;
  if (params.get("tab") === "anomaly") return 1;
  if (params.get("tab") === "signals") return 2;
  if (params.get("tab") === "change") return params.get("method") === "spectrum" ? 5
    : params.get("method") === "relation" ? 4 : 3;
  return 0;
}
