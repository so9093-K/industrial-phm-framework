/** 전망 그래프가 무엇을 어디까지 그리는지: 관제·조사 화면과 같은 규칙(처음 수준·처음 범위·찾은 변화)에
 * 예측과 기준선, 기준에 닿는 자리를 더한다. 그리기는 OutlookChart가, 계산은 여기서 한다. */
import type {Reach} from "./projections.ts";

export type OutlookPoint = {x: number; value: number};
export type OutlookFuture = {x: number; estimate: number; lower: number | null; upper: number | null};
export type OutlookLimits = {management: number | null; end: number | null};
export type OutlookWindow = {from: number; to: number};

/** 보이는 기간: 예측 길이의 두 배 앞부터. 조사에서 넘어온 변화가 있으면 그 변화가 보이도록 더 앞에서 시작한다. */
export function outlookWindow(history: OutlookPoint[], future: OutlookFuture[], change: OutlookWindow | null): OutlookWindow {
  const first = history[0]?.x ?? future[0]?.x ?? 0;
  const last = history.at(-1)?.x ?? first;
  const end = Math.max(future.at(-1)?.x ?? last, last);
  const span = Math.max(end - last, 1);
  let from = last - 2 * span;
  if (change) from = Math.min(from, change.from - Math.max(span, (last - change.from) * .15));
  return {from: Math.max(first, from), to: Math.max(end, Math.max(first, from) + 1)};
}

/** 세로 범위: 보이는 측정·예측·처음 범위와 기준선. 기준이 자료 폭의 세 배보다 멀면 그래프에 넣지 않고 밖에 있다고 표시한다. */
export function outlookScale(values: number[], baseline: {median: number | null; low: number | null; high: number | null} | null,
  limits: OutlookLimits): {low: number; high: number; outside: {management: boolean; end: boolean}} {
  const own = values.filter(Number.isFinite);
  const extra = baseline ? [baseline.median, baseline.low, baseline.high].filter((v): v is number => v !== null && Number.isFinite(v)) : [];
  const dataLow = Math.min(...own, ...extra), dataHigh = Math.max(...own, ...extra);
  const width = Math.max(dataHigh - dataLow, Math.abs(dataHigh) * .02, 1e-9);
  const near = (limit: number | null) => limit !== null && limit >= dataLow - 3 * width && limit <= dataHigh + 3 * width;
  const shown = [limits.management, limits.end].filter((limit): limit is number => near(limit));
  return {
    low: Math.min(dataLow, ...shown), high: Math.max(dataHigh, ...shown),
    outside: {management: limits.management !== null && !near(limits.management), end: limits.end !== null && !near(limits.end)},
  };
}

/** 기준에 닿는 자리(가로축 값): 예측선이 닿으면 그 시점, 예측 범위만 닿으면 가장 이른 시점. 이미 넘었으면 마지막 측정. */
export function reachAt(reach: Reach | null | undefined, last: number, axis: "time" | "acquisition"): {x: number; sure: boolean; already?: boolean} | null {
  if (!reach) return null;
  if (reach.state === "already") return {x: last, sure: true, already: true};
  const offset = reach.state === "expected" ? reach.expected : reach.state === "possible" ? reach.earliest : null;
  if (offset === null || !Number.isFinite(offset) || offset < 0) return null;
  return {x: last + (axis === "time" ? offset * 1000 : offset), sure: reach.state === "expected"};
}

/** 조사 화면에서 고른 변화(summary_change)가 이 신호의 것이면 그 구간. 다른 신호의 변화는 그리지 않는다. */
export function investigatedChange(search: string, kind: "history" | "vibration", key: string | undefined): OutlookWindow | null {
  if (!key) return null;
  try {
    const raw: unknown = JSON.parse(new URLSearchParams(search).get("summary_change") ?? "null");
    if (!Array.isArray(raw) || raw.length !== 4 || raw[0] !== kind || raw[1] !== key) return null;
    const [from, to] = kind === "history" ? [Date.parse(String(raw[2])), Date.parse(String(raw[3]))] : [Number(raw[2]), Number(raw[3])];
    return Number.isFinite(from) && Number.isFinite(to) && from <= to ? {from, to} : null;
  } catch { return null; }
}

/** 가장 가까운 측정·예측 한 점(포인터를 올린 자리의 값 읽기). */
export function nearestAt(history: OutlookPoint[], future: OutlookFuture[], at: number):
  {kind: "measured"; point: OutlookPoint} | {kind: "forecast"; point: OutlookFuture} | null {
  let best: {kind: "measured"; point: OutlookPoint} | {kind: "forecast"; point: OutlookFuture} | null = null, distance = Infinity;
  for (const point of history) { const d = Math.abs(point.x - at); if (d < distance) { distance = d; best = {kind: "measured", point}; } }
  for (const point of future) { const d = Math.abs(point.x - at); if (d < distance) { distance = d; best = {kind: "forecast", point}; } }
  return best;
}

export type LimitSuggestion = {label: string; value: number; direction: "upper" | "lower"; source: string};
const round3 = (n: number) => Number(n.toPrecision(3));
/** 기준을 비워 둔 사람에게 한 번에 고를 수 있는 기준. 처음 범위(이 기록의 처음 30%가 흔들린 폭)의 끝과,
 * 220 V 계통 전압이면 공급 전압 허용 범위(표준전압 220 V ± 13 V)를 낸다. 값은 화면에서 고쳐 쓸 수 있다. */
export function limitSuggestions(unit: string | null, baseline: {median: number | null; low: number | null; high: number | null} | null,
  label: string): LimitSuggestion[] {
  const out: LimitSuggestion[] = [];
  if (unit === "V" && baseline?.median != null && baseline.median >= 200 && baseline.median <= 240 && /전압/.test(label) && !/선간/.test(label))
    out.push({label: "공급 전압 상한 233 V", value: 233, direction: "upper", source: "표준전압 220 V의 허용 범위 207~233 V(전기사업법 시행규칙 별표 3)"},
      {label: "공급 전압 하한 207 V", value: 207, direction: "lower", source: "표준전압 220 V의 허용 범위 207~233 V(전기사업법 시행규칙 별표 3)"});
  if (baseline?.high != null) out.push({label: "처음 범위 상단 " + round3(baseline.high) + (unit ? " " + unit : ""), value: round3(baseline.high), direction: "upper",
    source: "이 기록 처음 30%의 값이 흔들린 범위의 위쪽 끝"});
  if (baseline?.low != null && baseline.low > 0) out.push({label: "처음 범위 하단 " + round3(baseline.low) + (unit ? " " + unit : ""), value: round3(baseline.low), direction: "lower",
    source: "이 기록 처음 30%의 값이 흔들린 범위의 아래쪽 끝"});
  return out;
}

/** 지금까지 이어서 기준을 넘고 있는 구간의 시작(마지막 측정이 기준 안이면 null). '이미 넘음'을 측정 사실로 말한다. */
export function crossedSince(history: OutlookPoint[], limit: number, direction: "upper" | "lower"): number | null {
  const beyond = (value: number) => direction === "upper" ? value > limit : value < limit;
  let since: number | null = null;
  for (let i = history.length - 1; i >= 0 && beyond(history[i].value); i--) since = history[i].x;
  return since;
}

const duration = (seconds: number) => {
  const hours = seconds / 3600;
  return hours < 1 ? "약 " + Math.max(1, Math.round(seconds / 60)) + "분" : hours < 48 ? "약 " + hours.toFixed(1) + "시간" : "약 " + (hours / 24).toFixed(1) + "일";
};
/** 기준까지의 여유를 큰 글씨 한 줄과 설명 한 줄로. 시간 간격을 모르는 진동 기록은 측정 횟수로 말한다. */
export function reachSummary(reach: Reach | null | undefined, axis: "time" | "acquisition", period: number | null,
  place: (x: number) => string, last: number, since: number | null): {headline: string; detail: string} {
  if (!reach) return {headline: "계산 안 됨", detail: ""};
  if (reach.state === "already") return {headline: "이미 넘음", detail: since !== null ? place(since) + "부터 이어서 넘음" : "마지막 측정이 기준 밖"};
  const offset = reach.state === "expected" ? reach.expected : reach.state === "possible" ? reach.earliest : null;
  if (offset === null || !Number.isFinite(offset)) return {headline: "계산한 범위 안에서 닿지 않음", detail: ""};
  const seconds = axis === "time" ? offset : period !== null ? offset * period : null;
  const when = seconds !== null ? duration(seconds) + " 뒤" : "추가 측정 " + Math.round(offset) + "회 뒤";
  const at = place(last + (axis === "time" ? offset * 1000 : offset));
  return reach.state === "expected" ? {headline: when, detail: "예측선 도달 · " + at}
    : {headline: "빠르면 " + when, detail: "예측 범위에서만 닿음 · " + at};
}
