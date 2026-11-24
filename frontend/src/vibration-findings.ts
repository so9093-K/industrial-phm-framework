import {scopeParams, type PlaybackScope} from "./record-playback.ts";
/** Representative changes in an asset's waveform-acquisition features, by acquisition number
 * (GET /api/v1/explore/vibration). Each is judged against the first 30% of the acquisitions and
 * said as observed: which feature, from which acquisition to which, against which values. */
import {assetTabUrl} from "./routes.ts";
import {object} from "./writes.ts";
import {lastJump} from "./change-story.ts";

export type VibrationChange = {
  reviewKey?:string;
  feature: string; label: string; unit: string | null; direction: "up" | "down";
  reason: "sustained" | "record-end" | "largest" | null; kind: "departure" | "level-change";
  from: number; to: number; baseline: {from: number; to: number};
  reference: number | null; typical: number | null; value: number;
  referenceSpread?: number | null; effectDistance?: number | null;
  usual: {low: number; high: number}; trace: {at: number; value: number; join?: boolean}[];
  /** Other features that moved over the same acquisitions. */
  related: {feature: string; label: string; unit: string | null; reference: number; current: number; state: "higher" | "lower"}[];
  /** 변화 구간 앞 절반과 뒤 절반에 측정값이 각각 움직인 양(측정이 6회 미만이면 없음). */
  halves?: Half[] | null;
};
export type Half = {from: number; to: number; change: number};
export type VibrationFindings = {
  sourceId:string|null; bindingId:string|null;
  assetId: string; first: number | null; last: number | null; periodSeconds: number | null;
  judged: number; features: number; intervals: VibrationChange[];
};

function invalid(): never { throw new Error("진동 측정 특이사항의 형식이 올바르지 않습니다."); }
const finite = (raw: unknown): number => typeof raw === "number" && Number.isFinite(raw) ? raw : invalid();
const whole = (raw: unknown): number => Number.isInteger(raw) && (raw as number) >= 0 ? raw as number : invalid();
const text = (raw: unknown): string => typeof raw === "string" && raw ? raw : invalid();
const optional = (raw: unknown): number | null => raw === null || raw === undefined ? null : finite(raw);

export function parseVibrationFindings(raw: unknown, assetId: string): VibrationFindings {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.asset_id !== assetId
    || root.meaning !== "departures-from-the-first-30-percent-not-fault-diagnosis" || !Array.isArray(root.intervals)) invalid();
  const intervals = root.intervals.map(parseVibrationChange);
  return {assetId,sourceId:typeof root.source_id==="string"?root.source_id:null,bindingId:typeof root.binding_id==="string"?root.binding_id:null, first: root.first === null ? null : whole(root.first), last: root.last === null ? null : whole(root.last),
    periodSeconds: optional(root.period_seconds), judged: whole(root.judged), features: whole(root.features), intervals};
}

/** A change and its trace always describe the same feature and acquisition record. */
export function parseVibrationChange(entry: unknown): VibrationChange {
  const row = object(entry), baseline = object(row?.baseline), usual = object(row?.usual);
  if (!row || !baseline || !usual || (row.direction !== "up" && row.direction !== "down") || !Array.isArray(row.trace)) invalid();
  if (row.trace_join !== undefined && (!Array.isArray(row.trace_join)
    || row.trace_join.length !== row.trace.length || !row.trace_join.every(value => typeof value === "boolean"))) invalid();
  const joins = Array.isArray(row.trace_join) ? row.trace_join : [];
  const from = whole(row.from), to = whole(row.to);
  if (to < from) invalid();
  return {reviewKey:typeof row.review_key==="string"?row.review_key:undefined,feature: text(row.feature), label: text(row.label), unit: typeof row.unit === "string" && row.unit ? row.unit : null,
    direction: row.direction, kind: row.kind === "level-change" ? "level-change" : "departure",
    reason: ["sustained", "record-end", "largest"].includes(String(row.reason)) ? row.reason as VibrationChange["reason"] : null,
    from, to, baseline: {from: whole(baseline.from), to: whole(baseline.to)},
    referenceSpread: optional(row.reference_spread), effectDistance: optional(row.change_distance),
    reference: optional(row.reference_value), typical: optional(row.typical_value), value: finite(row.value),
    usual: {low: finite(usual.low), high: finite(usual.high)},
    trace: row.trace.map((point: unknown, i: number) => {
      if (!Array.isArray(point) || point.length !== 2) invalid();
      return {at: whole(point[0]), value: finite(point[1]), ...(joins[i] === undefined ? {} : {join: joins[i] as boolean})};
    }),
    related: (Array.isArray(row.related) ? row.related : []).map((entry: unknown) => {
      const other = object(entry);
      if (!other || (other.state !== "higher" && other.state !== "lower")) invalid();
      return {feature: text(other.feature), label: text(other.label), unit: typeof other.unit === "string" && other.unit ? other.unit : null,
        reference: finite(other.reference), current: finite(other.current), state: other.state};
    }),
    halves: Array.isArray(row.halves) && row.halves.length === 2 ? row.halves.map((entry: unknown) => {
      const half = object(entry);
      if (!half) invalid();
      return {from: whole(half.from), to: whole(half.to), change: finite(half.change)};
    }) : null};
}

export async function readVibrationFindings(assetId: string, signal: AbortSignal, scope: PlaybackScope | null = null): Promise<VibrationFindings> {
  const response = await fetch("/api/v1/explore/vibration?" + new URLSearchParams({asset_id: assetId, ...scopeParams(scope)}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("진동 측정의 특이사항을 읽지 못했습니다.");
  }
  return parseVibrationFindings(await response.json() as unknown, assetId);
}

/** The feature at the change's first acquisition, and the change against the first 30%. */
export function vibrationLinks(assetId: string, change: VibrationChange): {signal: string; compare: string; spectrum:string;outlook:string} {
  const signal = new URL(assetTabUrl(assetId, "signals", null, "vibration"), "http://local");
  signal.searchParams.set("vibration_feature", change.feature);
  signal.searchParams.set("vibration_at", String(change.from));
  const compare = new URL(assetTabUrl(assetId, "change", "compare", "vibration"), "http://local");
  compare.searchParams.set("acquisition_feature", change.feature);
  compare.searchParams.set("feature_a_from", String(change.baseline.from));
  compare.searchParams.set("feature_a_to", String(change.baseline.to));
  compare.searchParams.set("feature_b_from", String(change.from));
  compare.searchParams.set("feature_b_to", String(change.to));
  // 비교 화면이 기간 이름을 중심 화면과 같게('초기'·'변화 구간') 쓰도록 출처를 함께 넘긴다.
  compare.searchParams.set("compare_origin", "summary");
  const spectrum=new URL(assetTabUrl(assetId,"change","spectrum"),"http://local");
  spectrum.searchParams.set("spectrum_channel",change.feature.slice(8,change.feature.lastIndexOf(".")));
  for(const period of ["a","b"] as const){const span=period==="a"?change.baseline:change;
    spectrum.searchParams.set("spectrum_"+period+"_from",String(span.from));
    spectrum.searchParams.set("spectrum_"+period+"_to",String(span.to));}
  const outlook=new URL(assetTabUrl(assetId,"outlook",null,"vibration"),"http://local");
  outlook.searchParams.set("acq_forecast_feature",change.feature);
  return {signal: signal.pathname + signal.search, compare: compare.pathname + compare.search,
    spectrum:spectrum.pathname+spectrum.search,outlook:outlook.pathname+outlook.search};
}

/** 진동 변화의 결론 모양과 그래프 표시: 변화가 시작된 측정, 그리고 기록 끝까지 이어졌으면 마지막 측정의 급변.
 * 결론 문장과 그래프가 같은 두 지점을 가리키게 한다. `last`는 기록의 마지막 측정 번호다. */
export function vibrationShape(change: VibrationChange, last: number | null): {
  span: string; now: boolean; jump: boolean; atEnd: boolean; marks: {at: number; value: number; label: string}[];
} {
  const atEnd = last !== null && change.to === last && change.trace.at(-1)?.at === last;
  const jump = atEnd ? lastJump(change.trace, change.direction) : null;
  const onset = change.trace.find(point => point.at >= change.from);
  const value = (number: number) => number.toLocaleString("ko-KR", {maximumSignificantDigits: 3}) + (change.unit ? " " + change.unit : "");
  return {
    atEnd, jump: jump !== null, now: atEnd && jump === null,
    span: jump ? change.from + "번째 측정부터" : atEnd ? change.from + "번째 측정부터 마지막 측정까지" : change.from + "~" + change.to + "번째 측정 동안",
    marks: [...(onset ? [{at: change.from, value: onset.value, label: change.from + "번째부터"}] : []),
      ...(jump ? [{at: jump.at, value: jump.value, label: jump.at + "번째 " + value(jump.value)}] : [])],
  };
}
