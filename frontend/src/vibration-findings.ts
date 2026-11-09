/** Representative changes in an asset's waveform-acquisition features, by acquisition number
 * (GET /api/v1/explore/vibration). Each is judged against the first 30% of the acquisitions and
 * said as observed: which feature, from which acquisition to which, against which values. */
import {assetTabUrl} from "./routes.ts";
import {object} from "./writes.ts";

export type VibrationChange = {
  feature: string; label: string; unit: string | null; direction: "up" | "down";
  reason: "sustained" | "record-end" | "largest" | null; kind: "departure" | "level-change";
  from: number; to: number; baseline: {from: number; to: number};
  reference: number | null; typical: number | null; value: number;
  usual: {low: number; high: number}; trace: {at: number; value: number}[];
  /** Other features that moved over the same acquisitions. */
  related: {feature: string; label: string; unit: string | null; reference: number; current: number; state: "higher" | "lower"}[];
};
export type VibrationFindings = {
  assetId: string; first: number | null; last: number | null; periodSeconds: number | null;
  judged: number; features: number; intervals: VibrationChange[];
};

function invalid(): never { throw new Error("진동 측정에서 찾은 변화의 형식이 올바르지 않습니다."); }
const finite = (raw: unknown): number => typeof raw === "number" && Number.isFinite(raw) ? raw : invalid();
const whole = (raw: unknown): number => Number.isInteger(raw) && (raw as number) >= 0 ? raw as number : invalid();
const text = (raw: unknown): string => typeof raw === "string" && raw ? raw : invalid();
const optional = (raw: unknown): number | null => raw === null || raw === undefined ? null : finite(raw);

export function parseVibrationFindings(raw: unknown, assetId: string): VibrationFindings {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.asset_id !== assetId
    || root.meaning !== "departures-from-the-first-30-percent-not-fault-diagnosis" || !Array.isArray(root.intervals)) invalid();
  const intervals = root.intervals.map((entry: unknown): VibrationChange => {
    const row = object(entry), baseline = object(row?.baseline), usual = object(row?.usual);
    if (!row || !baseline || !usual || (row.direction !== "up" && row.direction !== "down") || !Array.isArray(row.trace)) invalid();
    const from = whole(row.from), to = whole(row.to);
    if (to < from) invalid();
    return {feature: text(row.feature), label: text(row.label), unit: typeof row.unit === "string" && row.unit ? row.unit : null,
      direction: row.direction, kind: row.kind === "level-change" ? "level-change" : "departure",
      reason: ["sustained", "record-end", "largest"].includes(String(row.reason)) ? row.reason as VibrationChange["reason"] : null,
      from, to, baseline: {from: whole(baseline.from), to: whole(baseline.to)},
      reference: optional(row.reference_value), typical: optional(row.typical_value), value: finite(row.value),
      usual: {low: finite(usual.low), high: finite(usual.high)},
      trace: row.trace.map((point: unknown) => {
        if (!Array.isArray(point) || point.length !== 2) invalid();
        return {at: whole(point[0]), value: finite(point[1])};
      }),
      related: (Array.isArray(row.related) ? row.related : []).map((entry: unknown) => {
        const other = object(entry);
        if (!other || (other.state !== "higher" && other.state !== "lower")) invalid();
        return {feature: text(other.feature), label: text(other.label), unit: typeof other.unit === "string" && other.unit ? other.unit : null,
          reference: finite(other.reference), current: finite(other.current), state: other.state};
      })};
  });
  return {assetId, first: root.first === null ? null : whole(root.first), last: root.last === null ? null : whole(root.last),
    periodSeconds: optional(root.period_seconds), judged: whole(root.judged), features: whole(root.features), intervals};
}

export async function readVibrationFindings(assetId: string, signal: AbortSignal): Promise<VibrationFindings> {
  const response = await fetch("/api/v1/explore/vibration?" + new URLSearchParams({asset_id: assetId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("진동 측정에서 찾은 변화를 읽지 못했습니다.");
  }
  return parseVibrationFindings(await response.json() as unknown, assetId);
}

/** The feature at the change's first acquisition, and the change against the first 30%. */
export function vibrationLinks(assetId: string, change: VibrationChange): {signal: string; compare: string} {
  const signal = new URL(assetTabUrl(assetId, "signals", null, "vibration"), "http://local");
  signal.searchParams.set("vibration_feature", change.feature);
  signal.searchParams.set("vibration_at", String(change.from));
  const compare = new URL(assetTabUrl(assetId, "change", "compare", "vibration"), "http://local");
  compare.searchParams.set("acquisition_feature", change.feature);
  compare.searchParams.set("feature_a_from", String(change.baseline.from));
  compare.searchParams.set("feature_a_to", String(change.baseline.to));
  compare.searchParams.set("feature_b_from", String(change.from));
  compare.searchParams.set("feature_b_to", String(change.to));
  return {signal: signal.pathname + signal.search, compare: compare.pathname + compare.search};
}
