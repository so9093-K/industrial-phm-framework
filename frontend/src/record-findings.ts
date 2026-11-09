/** What one asset's whole stored record held: where its signals left the first 30% of the record,
 * representative sustained, recent and large changes (GET /api/v1/explore/findings). The summary says these as observed facts: when,
 * for how long, which signal, against which range, and how far. It never names a cause. */
import {recordContext, recordParams, type RecordContext} from "./record-context.ts";
import {assetTabUrl} from "./routes.ts";
import {elapsedText} from "./time-axis.ts";
import {validatePeriods} from "./comparison.ts";
import {periodParams, windowParams, zoomWindow} from "./signal-selection.ts";
import {object} from "./writes.ts";

export type FoundInterval = {
  trace?:{at:string;value:number;join?:boolean}[]; reviewKey?: string; context?: RecordContext | null; kind?: "departure" | "level-change"; bucketSeconds?: number | null;
  start: string; end: string; channel: string; label: string; unit: string | null;
  direction: "up" | "down"; value: number;
  /** The range the departure was judged by: the first 30% median ± its spread times the threshold. */
  usual: {low: number; high: number};
  /** Other signals with a representative shift in this interval. */
  within: string[];
  reason: "sustained" | "record-end" | "largest" | null;
  baseline: {from: string; to: string} | null;
  reference: number | null; typical: number | null;
  related: {context?: RecordContext|null; channel: string; label: string; unit: string | null; reference: number; current: number; state: "higher" | "lower" | "within"}[];
};
/** Whether a signal was judged, and if not why; a signal not judged never reads as unchanged. */
export type SignalState = "scored" | "level-change" | "short-baseline" | "constant" | "cumulative" | "copied" | "no-values";
export type CheckedSignal = {
  context?: RecordContext | null; channel: string; label: string; unit: string | null; state: SignalState;
  /** For a baseline held at one value: that value, and the range the record took afterwards. */
  held: number | null; later: {low: number; high: number} | null;
  /** For a running total its source declares: where the record began and ended. */
  first?: number | null; last?: number | null;
  /** For a signal that held another item's values for a while: that item and the period. */
  copied?: {origin: string; from: string; to: string} | null;
  latest?:{at:string;value:number}|null; range?:{low:number;high:number}|null;
};
export type RecordFindings = {
  assetId: string;
  baseline: {from: string; to: string} | null;
  record: {from: string; to: string} | null;
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
    if(row.trace_join!==undefined&&(!Array.isArray(row.trace_join)||!Array.isArray(row.trace)||row.trace_join.length!==row.trace.length||!row.trace_join.every(value=>typeof value==="boolean")))invalid();
    const joins=Array.isArray(row.trace_join)?row.trace_join:[];
    const low = finite(usual.low), high = finite(usual.high);
    if (low > high) invalid();
    return {trace:Array.isArray(row.trace)?row.trace.map((v:unknown,i:number)=>{if(!Array.isArray(v)||v.length!==2)invalid();return {at:instant(v[0]),value:finite(v[1]),join:joins[i] as boolean|undefined};}):[],reviewKey: typeof row.review_key === "string" ? row.review_key : undefined, context: recordContext(row), kind: row.kind === "level-change" ? "level-change" : "departure",
      bucketSeconds: typeof row.bucket_seconds === "number" ? finite(row.bucket_seconds) : null, start: instant(row.start), end: instant(row.end), channel: text(row.channel), label: text(row.label),
      unit: typeof row.unit === "string" && row.unit.trim() ? row.unit : null, direction: row.direction,
      value: finite(row.value), usual: {low, high}, within: row.within.map(text),
      reason: ["sustained", "record-end", "largest"].includes(String(row.reason)) ? row.reason as FoundInterval["reason"] : null,
      baseline: range(row.baseline ?? null),
      reference: row.reference_value === undefined || row.reference_value === null ? null : finite(row.reference_value),
      typical: row.typical_value === undefined || row.typical_value === null ? null : finite(row.typical_value),
      related: (Array.isArray(row.related) ? row.related : []).map((entry: unknown) => {
        const other = object(entry);
        if (!other || !["higher", "lower", "within"].includes(String(other.state))) invalid();
        return {context:recordContext(other), channel: text(other.channel), label: text(other.label), unit: typeof other.unit === "string" ? other.unit : null,
          reference: finite(other.reference), current: finite(other.current), state: other.state as "higher" | "lower" | "within"};
      })};
  });
  const states: readonly SignalState[] = ["scored", "level-change", "short-baseline", "constant", "cumulative", "copied", "no-values"];
  const signals = root.signals.map((item: unknown): CheckedSignal => {
    const row = object(item);
    if (!row || !states.includes(row.state as SignalState)) invalid();
    const later = row.later === undefined || row.later === null ? null : object(row.later);
    if (row.later !== undefined && row.later !== null && !later) invalid();
    const latest=object(row.latest),extent=object(row.range),copy=object(row.copied);
    if (row.state === "copied" && !copy) invalid();
    return {latest:latest?{at:instant(latest.at),value:finite(latest.value)}:null,
      range:extent?{low:finite(extent.low),high:finite(extent.high)}:null,
      context: recordContext(row), channel: text(row.channel), label: text(row.label),
      unit: typeof row.unit === "string" && row.unit.trim() ? row.unit : null, state: row.state as SignalState,
      held: row.held === undefined || row.held === null ? null : finite(row.held),
      first: row.first === undefined || row.first === null ? null : finite(row.first),
      last: row.last === undefined || row.last === null ? null : finite(row.last),
      later: later ? {low: finite(later.low), high: finite(later.high)} : null,
      copied: copy ? {origin: text(copy.origin), from: instant(copy.from), to: instant(copy.to)} : null};
  });
  const judged = finite(root.judged);
  if (judged !== signals.filter((row) => (row.state === "scored" || row.state === "level-change" || row.state === "constant")).length) invalid();
  if (intervals.length && !judged) invalid();
  const count = finite(root.interval_count);
  if (count < intervals.length) invalid();
  return {assetId, baseline: range(root.baseline), record: range(root.record ?? null),
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

export const CHANGE_REASON = {sustained: "오래 이어진 변화", "record-end": "기록 끝까지 이어진 변화", largest: "변화 폭이 큰 구간"};
export const changeValue = value;

/** When, for how long, and what was observed; a value is a bucket mean, so it says so. */
export function findingText(item: FoundInterval, bucketSeconds: number | null): {when: string; what: string} {
  bucketSeconds = item.bucketSeconds ?? bucketSeconds;
  const seconds = (Date.parse(item.end) - Date.parse(item.start)) / 1000;
  const down = item.direction === "down";
  const mean = bucketSeconds ? elapsedText(bucketSeconds) + " 평균으로 " : "";
  return {
    when: clock(item.start) + " ~ " + clock(item.end) + (seconds >= 60 ? " (약 " + elapsedText(seconds) + ")" : ""),
    what: item.reference !== null && item.typical !== null
      ? (item.kind === "level-change" ? "일정하던 값의 변화 · " : "대표값 ") + value(item.reference, null) + " → " + value(item.typical, item.unit)
      : item.label + " · 기록 처음 30%의 비교 범위(" + value(item.usual.low, null) + "~" + value(item.usual.high, item.unit)
      + ")보다 " + (down ? "낮았습니다" : "높았습니다") + " · " + mean + "가장 " + (down ? "낮을" : "높을") + " 때 "
      + value(item.value, item.unit),
  };
}

/** The interval in the signal graph, and compared with the first 30% it was judged against. */
export function findingLinks(assetId: string, item: FoundInterval, baseline: RecordFindings["baseline"],
  bucketSeconds: number | null, record: RecordFindings["record"] = null): {signal: string | null; compare: string | null; previous: string | null; relation: {href: string; label: string} | null; outlook: string} {
  const link = (href: string, params: Record<string, string>) => {
    const url = new URL(href, "http://local");
    for (const [key, entry] of Object.entries({...recordParams(item.context), ...params})) url.searchParams.set(key, entry);
    return url.pathname + url.search;
  };
  record = item.context?.record ?? record;
  bucketSeconds = item.bucketSeconds ?? bucketSeconds;
  const from = Date.parse(item.start);
  const span = {from, to: Math.max(Date.parse(item.end), from + Math.max((bucketSeconds ?? 0) * 1000, 1000))};
  const inspection = {...span, to: Math.min(span.to, span.from + 31 * 86400000)};
  const window = zoomWindow(inspection);
  const signal = window ? link(assetTabUrl(assetId, "signals", null, null, item.channel), windowParams(window, inspection)) : null;
  let compare: string | null = null;
  let previous: string | null = null;
  const prior = {from: inspection.from - (inspection.to - inspection.from), to: inspection.from};
  if (record && prior.from >= Date.parse(record.from)) {
    const periods = {a: {from: new Date(prior.from).toISOString(), to: new Date(prior.to).toISOString()},
      b: {from: new Date(inspection.from).toISOString(), to: new Date(inspection.to).toISOString()}};
    previous = link(assetTabUrl(assetId, "change", "compare", "history", item.channel), periodParams(periods, "previous"));
  }
  baseline = item.baseline ?? baseline;
  if (baseline) {
    const periods = {a: {from: baseline.from, to: baseline.to},
      b: {from: new Date(span.from).toISOString(), to: new Date(span.to).toISOString()}};
    try {
      validatePeriods(periods);
      compare = link(assetTabUrl(assetId, "change", "compare", "history", item.channel), periodParams(periods, "departure"));
    } catch { compare = null; }
  }
  const other = item.related.find(row => row.state !== "within") ?? item.related[0];
  const compared = previous ?? compare;
  let relation: {href: string; label: string} | null = null;
  if (other && compared) {
    const url = new URL(compared, "http://local");
    url.searchParams.set("method", "relation");
    url.searchParams.set("relation_x", item.channel);
    url.searchParams.set("relation_y", other.channel);
    relation = {href: url.pathname + url.search, label: other.label + " 관계 비교"};
  }
  return {signal, compare, previous, relation, outlook: link(assetTabUrl(assetId, "outlook", null, "history", item.channel), {})};
}

const WHY: Record<Exclude<SignalState, "scored" | "level-change">, string> = {
  "short-baseline": "기록 처음 30%의 값이 너무 적어 평소 범위를 정하지 못함",
  constant: "기준 기간과 이후 기록에서 같은 값이 유지됨",
  cumulative: "누적값이라 기록 처음과 견준 변화로 판단하지 않음",
  copied: "일부 기간에 다른 항목의 값이 기록되어 변화로 판단하지 않음",
  "no-values": "저장된 값이 없음",
};
/** Why a signal was not judged, with what a held baseline and the record afterwards showed. */
export function unjudgedText(signal: CheckedSignal): string {
  if (signal.state === "scored" || signal.state === "level-change") return signal.label;
  const held = signal.state === "constant" && signal.held !== null
    ? " · 처음 30%는 " + value(signal.held, signal.unit) + (signal.later
      ? ", 그 뒤 " + value(signal.later.low, null) + "~" + value(signal.later.high, signal.unit) : "")
    : signal.state === "cumulative" && signal.first != null && signal.last != null
      ? " · " + value(signal.first, null) + " → " + value(signal.last, signal.unit) : "";
  return signal.label + "(" + WHY[signal.state] + held + ")";
}

/** Signals that held another item's values, grouped by the period so one recording change reads once. */
export function copiedGroups(signals: CheckedSignal[]): {from: string; to: string; items: {label: string; origin: string}[]}[] {
  const groups = new Map<string, {from: string; to: string; items: {label: string; origin: string}[]}>();
  for (const signal of signals) {
    if (signal.state !== "copied" || !signal.copied) continue;
    const key = signal.copied.from + "|" + signal.copied.to;
    const group = groups.get(key) ?? {from: signal.copied.from, to: signal.copied.to, items: []};
    group.items.push({label: signal.label, origin: signal.copied.origin});
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => Date.parse(a.from) - Date.parse(b.from));
}
