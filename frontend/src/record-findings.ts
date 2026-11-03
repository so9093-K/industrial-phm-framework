/** What one asset's whole stored record held: where its signals left the first 30% of the record,
 * largest first (GET /api/v1/explore/findings). The summary says these as observed facts: when,
 * for how long, which signal, against which range, and how far. It never names a cause. */
import {assetTabUrl} from "./routes.ts";
import {elapsedText} from "./time-axis.ts";
import {validatePeriods} from "./comparison.ts";
import {periodParams, windowParams, zoomWindow} from "./signal-selection.ts";
import {object} from "./writes.ts";

export type FoundInterval = {
  start: string; end: string; channel: string; label: string; unit: string | null;
  direction: "up" | "down"; value: number;
  /** The range the departure was judged by: the first 30% median ± its spread times the threshold. */
  usual: {low: number; high: number};
  /** Other signals outside their own range in the same interval. */
  with: string[];
};
export type RecordFindings = {
  assetId: string;
  baseline: {from: string; to: string} | null;
  /** Each value is a mean over this many seconds; null when nothing was read. */
  bucketSeconds: number | null;
  checked: string[]; unchecked: number;
  intervals: FoundInterval[]; count: number;
};

function invalid(): never { throw new Error("기록에서 찾은 변화의 형식이 올바르지 않습니다."); }
const finite = (raw: unknown): number => typeof raw === "number" && Number.isFinite(raw) ? raw : invalid();
const text = (raw: unknown): string => typeof raw === "string" && raw ? raw : invalid();
const instant = (raw: unknown): string => Number.isFinite(Date.parse(text(raw))) ? raw as string : invalid();

export function parseRecordFindings(raw: unknown, assetId: string): RecordFindings {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.asset_id !== assetId
    || root.meaning !== "departures-from-the-first-30-percent-not-fault-diagnosis"
    || !Array.isArray(root.intervals) || !Array.isArray(root.checked)) invalid();
  const range = (value: unknown) => {
    if (value === null) return null;
    const row = object(value);
    return row ? {from: instant(row.from), to: instant(row.to)} : invalid();
  };
  const intervals = root.intervals.map((item: unknown): FoundInterval => {
    const row = object(item), usual = object(row?.usual);
    if (!row || !usual || (row.direction !== "up" && row.direction !== "down") || !Array.isArray(row.with)) invalid();
    const low = finite(usual.low), high = finite(usual.high);
    if (low > high) invalid();
    return {start: instant(row.start), end: instant(row.end), channel: text(row.channel), label: text(row.label),
      unit: typeof row.unit === "string" && row.unit.trim() ? row.unit : null, direction: row.direction,
      value: finite(row.value), usual: {low, high}, with: row.with.map(text)};
  });
  const count = finite(root.interval_count);
  if (count < intervals.length) invalid();
  return {assetId, baseline: range(root.baseline),
    bucketSeconds: root.bucket_seconds === null ? null : finite(root.bucket_seconds),
    checked: root.checked.map(text), unchecked: finite(root.unchecked), intervals, count};
}

export async function readRecordFindings(assetId: string, signal: AbortSignal): Promise<RecordFindings> {
  const response = await fetch("/api/v1/explore/findings?" + new URLSearchParams({asset_id: assetId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("기록에서 찾은 변화를 읽지 못했습니다.");
  }
  return parseRecordFindings(await response.json() as unknown, assetId);
}

const clock = (iso: string) => new Date(iso).toLocaleString("ko-KR", {timeZone: "Asia/Seoul",
  month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false});
const value = (number: number, unit: string | null) =>
  number.toLocaleString("ko-KR", {maximumSignificantDigits: 3}) + (unit ? " " + unit : "");

/** When, for how long, and what was observed; a value is a bucket mean, so it says so. */
export function findingText(item: FoundInterval, bucketSeconds: number | null): {when: string; what: string} {
  const seconds = (Date.parse(item.end) - Date.parse(item.start)) / 1000;
  const down = item.direction === "down";
  const mean = bucketSeconds ? elapsedText(bucketSeconds) + " 평균으로 " : "";
  return {
    when: clock(item.start) + " ~ " + clock(item.end) + (seconds >= 60 ? " (약 " + elapsedText(seconds) + ")" : ""),
    what: item.label + " · 기록 처음 30%의 평소 범위(" + value(item.usual.low, null) + "~" + value(item.usual.high, item.unit)
      + ")보다 " + (down ? "낮았습니다" : "높았습니다") + " · " + mean + "가장 " + (down ? "낮을" : "높을") + " 때 "
      + value(item.value, item.unit) + (item.with.length ? " · 같은 때 평소 범위를 벗어난 신호: " + item.with.join(", ") : ""),
  };
}

/** The interval in the signal graph, and compared with the first 30% it was judged against. */
export function findingLinks(assetId: string, item: FoundInterval, baseline: RecordFindings["baseline"],
  bucketSeconds: number | null): {signal: string | null; compare: string | null} {
  const link = (href: string, params: Record<string, string>) => {
    const url = new URL(href, "http://local");
    for (const [key, entry] of Object.entries(params)) url.searchParams.set(key, entry);
    return url.pathname + url.search;
  };
  const from = Date.parse(item.start);
  const span = {from, to: Math.max(Date.parse(item.end), from + Math.max((bucketSeconds ?? 0) * 1000, 1000))};
  const window = zoomWindow(span);
  const signal = window ? link(assetTabUrl(assetId, "signals", null, null, item.channel), windowParams(window, span)) : null;
  let compare: string | null = null;
  if (baseline) {
    const periods = {a: {from: baseline.from, to: baseline.to},
      b: {from: new Date(span.from).toISOString(), to: new Date(span.to).toISOString()}};
    try {
      validatePeriods(periods);
      compare = link(assetTabUrl(assetId, "change", "compare", "history", item.channel), periodParams(periods, "departure"));
    } catch { compare = null; }
  }
  return {signal, compare};
}
