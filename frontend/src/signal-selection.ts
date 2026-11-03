/**
 * A time span the user picked on a stored-signal chart, and the analyses it can hand over to.
 * Every number is summed from the server's buckets inside the span; nothing is interpolated,
 * and a span that only partly covers the read window says so instead of guessing the rest.
 */
import type {HistoryBucket, HistoryGroup} from "./history.ts";
import type {Periods} from "./comparison.ts";

const iso = (ms: number) => new Date(Math.round(ms)).toISOString();

/** Bucket starts arrive with microseconds and parse to whole milliseconds, so a start can read
 * up to a millisecond before the grid; edges are compared with this slack. */
export const EDGE_MS = 2;

/** Epoch milliseconds, start inclusive and end exclusive. */
export type Span = {from: number; to: number};
/** The longest window the server reads at once and the longest period it compares. */
export const MAX_SPAN_MS = 31 * 86400 * 1000;

export type SpanSummary = {
  buckets: number;
  usable: number;
  missing: number;
  nonGood: number;
  conflict: number;
  /** Mean of every usable value in the span: bucket means weighted by their usable counts. */
  mean: number | null;
  minimum: number | null;
  maximum: number | null;
};

/** Snap a dragged or clicked time range to whole buckets of the chart (buckets start at the
 * read window's start and share one width), clamped to the read window. */
export function snapSpan(a: number, b: number, origin: number, end: number, stepMs: number | null): Span {
  const lo = Math.max(origin, Math.min(a, b)), hi = Math.min(end, Math.max(a, b));
  if (!stepMs || stepMs <= 0) return {from: lo, to: Math.min(end, Math.max(hi, lo + 1000))};
  const from = origin + Math.floor((lo - origin + EDGE_MS) / stepMs) * stepMs;
  const to = Math.min(end, Math.max(from + stepMs, origin + Math.ceil((hi - origin - EDGE_MS) / stepMs) * stepMs));
  return {from, to};
}

/** A picked span on a finer grid (after zooming): the whole buckets inside it, so the
 * reading never reaches past what was picked. A span narrower than one bucket keeps its bucket. */
export function snapInside(span: Span, origin: number, end: number, stepMs: number | null): Span {
  if (!stepMs || stepMs <= 0) return span;
  const from = origin + Math.ceil((span.from - origin - EDGE_MS) / stepMs) * stepMs;
  const to = Math.min(end, origin + Math.floor((span.to - origin + EDGE_MS) / stepMs) * stepMs);
  return to > from ? {from, to} : snapSpan(span.from, span.from, origin, end, stepMs);
}

/** The buckets of one source group that start inside the span, summed. */
export function summarize(group: HistoryGroup, span: Span): SpanSummary | null {
  const inside = group.buckets.filter((bucket: HistoryBucket) => {
    const at = Date.parse(bucket.bucketStart);
    return at > span.from - EDGE_MS && at < span.to - EDGE_MS;
  });
  if (!inside.length) return null;
  let usable = 0, weighted = 0, minimum: number | null = null, maximum: number | null = null;
  for (const bucket of inside) {
    if (bucket.usableCount > 0 && bucket.mean !== null) {
      usable += bucket.usableCount;
      weighted += bucket.mean * bucket.usableCount;
      const low = bucket.minimum ?? bucket.mean, high = bucket.maximum ?? bucket.mean;
      minimum = minimum === null ? low : Math.min(minimum, low);
      maximum = maximum === null ? high : Math.max(maximum, high);
    }
  }
  const sum = (key: "nullCount" | "nonGoodCount" | "conflictCount") =>
    inside.reduce((total, bucket) => total + bucket[key], 0);
  return {
    buckets: inside.length, usable,
    missing: sum("nullCount"), nonGood: sum("nonGoodCount"), conflict: sum("conflictCount"),
    mean: usable ? weighted / usable : null, minimum, maximum,
  };
}

/** The same length right before the span: the usual "what was it just before?" reference. */
export function previousSpan(span: Span): Span {
  return {from: span.from - (span.to - span.from), to: span.from};
}

/** Whether a span lies wholly inside the window the chart has read. */
export function covers(window: Span, span: Span): boolean {
  return span.from >= window.from && span.to <= window.to;
}

/** A closer look that also holds the same length right before the span (what the card
 * compares with) and a little after it, or the span itself when that would exceed what the
 * server reads at once. Null when even the span is too long. */
export function zoomWindow(span: Span): Span | null {
  const length = span.to - span.from;
  if (length <= 0 || length > MAX_SPAN_MS) return null;
  // A quarter more before, so the span still holds the period before it after snapping to buckets.
  if (length * 2.75 > MAX_SPAN_MS) return span;
  return {from: span.from - length * 1.25, to: span.to + length / 2};
}

/** A narrow look around one moment of a period: a tenth of the period but at least an hour,
 * so the neighbouring stored measurements show at full detail without losing the moment. */
export function momentWindow(at: number, periodMs: number): Span {
  const width = Math.min(MAX_SPAN_MS, Math.max(3600000, periodMs / 10));
  return {from: at - width / 2, to: at + width / 2};
}

/** Whether the chart already shows about one stored value per bucket, so zooming in
 * further cannot reveal more measurements. */
export function atFinest(buckets: {usableCount: number}[]): boolean {
  const drawn = buckets.filter((bucket) => bucket.usableCount > 0);
  return drawn.length > 0 && drawn.reduce((total, bucket) => total + bucket.usableCount, 0) / drawn.length <= 1.5;
}

/** Two-period comparison of the span (B) against the same length right before it (A). */
export function periodsBefore(span: Span): Periods | null {
  if (span.to - span.from <= 0 || span.to - span.from > MAX_SPAN_MS) return null;
  const before = previousSpan(span);
  return {a: {from: iso(before.from), to: iso(before.to)}, b: {from: iso(span.from), to: iso(span.to)}};
}

/** Where handed-over periods were picked; the target screen names it until they are edited. */
export type PeriodOrigin = "signal" | "departure";
export const ORIGIN_TEXT: Record<PeriodOrigin, string> = {
  signal: "신호 그래프에서 고른 구간을 기간 B로, 바로 앞 같은 길이를 기간 A로 가져왔습니다.",
  departure: "기준 구간 이탈에서 고른 구간을 기간 B로, 그때 쓴 기준 구간을 기간 A로 가져왔습니다.",
};
export function periodOrigin(search: string): PeriodOrigin | null {
  const raw = new URLSearchParams(search).get("compare_origin");
  return raw === "signal" || raw === "departure" ? raw : null;
}

/** URL parameters that open another analysis on explicit periods; the target screen says so. */
export function periodParams(periods: Periods, origin: PeriodOrigin = "signal"): Record<string, string> {
  return {
    compare_a: periods.a.from + "~" + periods.a.to,
    compare_b: periods.b.from + "~" + periods.b.to,
    compare_origin: origin,
  };
}

/** The signals screen zoomed to a window with a moment or span already picked in it. */
export function windowParams(window: Span, pick: Span | null = null): Record<string, string> {
  return {
    monitor_range: "window", monitor_from: iso(window.from), monitor_to: iso(window.to),
    ...(pick ? {monitor_pick: iso(pick.from) + "~" + iso(pick.to)} : {}),
  };
}
/** A picked moment or span read back from the address; from = to picks the bucket holding it. */
export function pickFrom(raw: string | null): Span | null {
  const [from, to] = (raw ?? "").split("~").map((value) => Date.parse(value));
  return Number.isFinite(from) && Number.isFinite(to) && to >= from && to - from <= MAX_SPAN_MS ? {from, to} : null;
}
