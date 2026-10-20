/** One stored vibration feature per acquisition (GET /api/v1/acquisition/trend); nothing is fitted. */
import {yTicks, type Tick} from "./chart-axis.ts";

export type AcquisitionTrend = {
  assetId: string; sourceId: string; feature: string; label: string; unit: string | null;
  periodSeconds: number | null; analyzed: number; sampled: boolean;
  points: {ordinal: number; value: number}[];
};

function object(raw: unknown): Record<string, unknown> | null {
  return raw !== null && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : null;
}
function invalid(): never { throw new Error("진동 특징 기록의 형식이 올바르지 않습니다."); }

export function parseAcquisitionTrend(raw: unknown, assetId: string, feature: string): AcquisitionTrend {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.asset_id !== assetId || root.feature !== feature
    || typeof root.source_id !== "string" || typeof root.label !== "string" || !Array.isArray(root.points)
    || typeof root.analyzed !== "number" || typeof root.sampled !== "boolean"
    || (root.period_seconds !== null && (typeof root.period_seconds !== "number"
      || !Number.isFinite(root.period_seconds) || root.period_seconds <= 0))) invalid();
  let before = 0;
  const points = root.points.map((item: unknown) => {
    if (!Array.isArray(item) || item.length !== 2) invalid();
    const [ordinal, value] = item;
    if (typeof ordinal !== "number" || !Number.isSafeInteger(ordinal) || ordinal <= before
      || typeof value !== "number" || !Number.isFinite(value)) invalid();
    before = ordinal;
    return {ordinal, value};
  });
  return {assetId, sourceId: root.source_id, feature, label: root.label,
    unit: typeof root.unit === "string" && root.unit.trim() ? root.unit : null,
    periodSeconds: root.period_seconds as number | null, analyzed: root.analyzed, sampled: root.sampled, points};
}

export async function readAcquisitionTrend(assetId: string, feature: string, signal: AbortSignal): Promise<AcquisitionTrend> {
  const response = await fetch("/api/v1/acquisition/trend?" + new URLSearchParams({asset_id: assetId, feature}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("진동 특징 기록을 불러오지 못했습니다.");
  }
  return parseAcquisitionTrend(await response.json() as unknown, assetId, feature);
}

export type TrendChart = {width: number; height: number; low: number; high: number; first: number; last: number;
  line: string; ticks: Tick[]; marks: {ordinal: number; value: number; x: number; y: number}[]};
/** The stored values on the acquisition axis. */
export function trendChart(trend: AcquisitionTrend): TrendChart | null {
  const points = trend.points;
  if (points.length < 2) return null;
  const width = 800, height = 220, top = 8, bottom = 212;
  const values = points.map((point) => point.value);
  const low = Math.min(...values), high = Math.max(...values);
  const padding = low === high ? Math.max(Math.abs(low) * 0.05, 1) : (high - low) * 0.06;
  const lo = low - padding, hi = high + padding;
  const first = points[0].ordinal, last = points[points.length - 1].ordinal;
  const x = (at: number) => ((at - first) / Math.max(1, last - first)) * width;
  const y = (value: number) => bottom - ((value - lo) / (hi - lo)) * (bottom - top);
  return {width, height, low, high, first, last, ticks: yTicks(lo, hi, top, bottom),
    marks: points.map(point => ({...point, x: x(point.ordinal), y: y(point.value)})),
    line: points.map((point, i) => (i ? "L" : "M") + x(point.ordinal).toFixed(1) + " " + y(point.value).toFixed(1)).join(" ")};
}
