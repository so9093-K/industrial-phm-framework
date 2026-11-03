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
  /** Other signals outside their own range somewhere in the same merged interval; not
   * necessarily at the same moment. */
  within: string[];
};
/** Whether a signal was judged, and if not why; a signal not judged never reads as unchanged. */
export type SignalState = "scored" | "short-baseline" | "constant" | "no-values";
export type CheckedSignal = {
  channel: string; label: string; unit: string | null; state: SignalState;
  /** For a baseline held at one value: that value, and the range the record took afterwards. */
  held: number | null; later: {low: number; high: number} | null;
};
export type RecordFindings = {
  assetId: string;
  baseline: {from: string; to: string} | null;
  /** Each value is a mean over this many seconds; null when nothing was read. */
  bucketSeconds: number | null;
  signals: CheckedSignal[]; judged: number; unchecked: number;
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
    || !Array.isArray(root.intervals) || !Array.isArray(root.signals)) invalid();
  const range = (value: unknown) => {
    if (value === null) return null;
    const row = object(value);
    return row ? {from: instant(row.from), to: instant(row.to)} : invalid();
  };
  const intervals = root.intervals.map((item: unknown): FoundInterval => {
    const row = object(item), usual = object(row?.usual);
    if (!row || !usual || (row.direction !== "up" && row.direction !== "down") || !Array.isArray(row.within)) invalid();
    const low = finite(usual.low), high = finite(usual.high);
    if (low > high) invalid();
    return {start: instant(row.start), end: instant(row.end), channel: text(row.channel), label: text(row.label),
      unit: typeof row.unit === "string" && row.unit.trim() ? row.unit : null, direction: row.direction,
      value: finite(row.value), usual: {low, high}, within: row.within.map(text)};
  });
  const states: readonly SignalState[] = ["scored", "short-baseline", "constant", "no-values"];
  const signals = root.signals.map((item: unknown): CheckedSignal => {
    const row = object(item);
    if (!row || !states.includes(row.state as SignalState)) invalid();
    const later = row.later === undefined || row.later === null ? null : object(row.later);
    if (row.later !== undefined && row.later !== null && !later) invalid();
    return {channel: text(row.channel), label: text(row.label),
      unit: typeof row.unit === "string" && row.unit.trim() ? row.unit : null, state: row.state as SignalState,
      held: row.held === undefined || row.held === null ? null : finite(row.held),
      later: later ? {low: finite(later.low), high: finite(later.high)} : null};
  });
  const judged = finite(root.judged);
  if (judged !== signals.filter((row) => row.state === "scored").length) invalid();
  if (intervals.length && !judged) invalid();
  const count = finite(root.interval_count);
  if (count < intervals.length) invalid();
  return {assetId, baseline: range(root.baseline),
    bucketSeconds: root.bucket_seconds === null ? null : finite(root.bucket_seconds),
    signals, judged, unchecked: finite(root.unchecked), intervals, count};
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
      + value(item.value, item.unit) + (item.within.length ? " · 같은 구간 안에서 평소 범위를 벗어난 다른 신호: " + item.within.join(", ") : ""),
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

const WHY: Record<Exclude<SignalState, "scored">, string> = {
  "short-baseline": "기록 처음 30%의 값이 너무 적어 평소 범위를 정하지 못함",
  constant: "기록 처음 30% 동안 값이 일정해 벗어난 정도를 계산할 수 없음",
  "no-values": "저장된 값이 없음",
};
/** Why a signal was not judged, with what a held baseline and the record afterwards showed. */
export function unjudgedText(signal: CheckedSignal): string {
  if (signal.state === "scored") return signal.label;
  const held = signal.state === "constant" && signal.held !== null
    ? " · 처음 30%는 " + value(signal.held, signal.unit) + (signal.later
      ? ", 그 뒤 " + value(signal.later.low, null) + "~" + value(signal.later.high, signal.unit) : "")
    : "";
  return signal.label + "(" + WHY[signal.state] + held + ")";
}
