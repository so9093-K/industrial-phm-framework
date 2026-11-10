/** What a screen opens on when nothing was chosen: the signal, record and periods the asset's state
 * summary leads with, so every screen starts from the change the summary names, else from the
 * current the operating levels are read from. */
import {bandName, departurePeriods, readRecordFindings, type FoundInterval, type RecordFindings} from "./record-findings.ts";
import {readDepartures} from "./monitor-attention.ts";
import type {RecordContext} from "./record-context.ts";
import type {Periods} from "./comparison.ts";
import type {SourceFocus} from "./signal-selection.ts";

export type SummarySignal = {channel: string; context: RecordContext | null};
/** Long enough for an asset's summary to be computed the first time; a summary already computed
 * comes back at once. */
const SUMMARY_WAIT_MS = 12_000;

/** The summary's first change and the asset's main signal, the current its levels are read from. */
export function summarySignals(found: RecordFindings): {first: FoundInterval | null; main: SummarySignal | null} {
  const operation = found.operation[0];
  const own = operation ? found.signals.find(row => row.context?.key === operation.key) : undefined;
  return {first: found.intervals[0] ?? null, main: own ? {channel: own.channel, context: own.context ?? null} : null};
}

/** The summary's first change, else the main signal, among the signals a screen offers. */
export function summarySignal(found: RecordFindings, ids: string[]): SummarySignal | null {
  const {first, main} = summarySignals(found);
  const picks = [first ? {channel: first.channel, context: first.context ?? null} : null, main];
  return picks.find((pick): pick is SummarySignal => pick !== null && ids.includes(pick.channel)) ?? null;
}

/** The record a signal belongs to, as a screen narrows its groups to. */
export function contextFocus(context: RecordContext | null): SourceFocus | null {
  return context ? {source: context.sourceId, point: context.pointId, interpretation: context.interpretationId} : null;
}

const sameRecordPlace = (a: RecordContext | null | undefined, b: RecordContext | null | undefined) =>
  Boolean(a && b && a.sourceId === b.sourceId && a.pointId === b.pointId);

/** The pair the relation screen opens on, and a sentence saying why. The current is on x, so a
 * change the summary found at one operating level shows against the load it was measured at; the
 * periods are the first 30% the change was judged against and the change itself. Without a current
 * the change is paired with the signal that moved with it. */
export function relationPair(found: RecordFindings, ids: string[]):
  {x: string; y: string; focus: SourceFocus | null; periods: Periods | null; note: string} | null {
  const {first, main} = summarySignals(found);
  const offered = (channel: string | undefined) => channel !== undefined && ids.includes(channel);
  const periods = first ? departurePeriods(first, found.baseline, found.bucketSeconds) : null;
  const label = (channel: string) => found.signals.find(row => row.channel === channel)?.label ?? channel;
  const during = periods ? " 기간 A는 변화를 판단한 기록 처음 30%, 기간 B는 변화 구간입니다." : "";
  if (first && main && first.channel !== main.channel && offered(first.channel) && offered(main.channel)
    && sameRecordPlace(first.context, main.context)) {
    // The change and the current share a place, so its level is one of this current's levels.
    const operation = found.operation[0];
    const band = first.band != null ? " · " + bandName(operation, first.band) + " 중 변화" : "";
    return {x: main.channel, y: first.channel, focus: contextFocus(main.context), periods,
      note: "상태 요약의 첫 변화를 기준 전류와 함께 봅니다. 가로축 " + label(main.channel) + ", 세로축 " + first.label + band + "." + during};
  }
  if (first && offered(first.channel)) {
    const others = first.related.filter(row => offered(row.channel) && row.channel !== first.channel);
    const other = others.find(row => row.state !== "within") ?? others[0];
    if (other) return {x: first.channel, y: other.channel, focus: contextFocus(first.context ?? null), periods,
      note: "상태 요약의 첫 변화를 " + (other.state !== "within" ? "같은 구간에 함께 달라진 신호" : "같은 구간의 다른 신호")
        + "와 함께 봅니다. 가로축 " + first.label + ", 세로축 " + other.label + "." + during};
  }
  if (main && offered(main.channel)) {
    const other = found.signals.find(row => row.channel !== main.channel && offered(row.channel)
      && (row.state === "scored" || row.state === "level-change") && sameRecordPlace(row.context, main.context));
    if (other) return {x: main.channel, y: other.channel, focus: contextFocus(main.context), periods: null,
      note: "상태 요약에서 찾은 변화가 없어 기준 전류와 같은 위치의 다른 신호를 봅니다. 가로축 " + label(main.channel) + ", 세로축 " + other.label + "."};
  }
  return null;
}

/** The asset's summary, or null when it is not ready within the wait or cannot be read. */
export function readSummary(assetId: string, signal: AbortSignal, waitMs = SUMMARY_WAIT_MS): Promise<RecordFindings | null> {
  return readRecordFindings(assetId, AbortSignal.any([signal, AbortSignal.timeout(waitMs)])).catch(() => null);
}

/** The signal a screen opens on when none is chosen: the summary's first change, else the main
 * signal, else the one the baseline check of the latest values flagged, else the first. */
export async function defaultSignal(assetId: string, ids: string[], signal: AbortSignal, waitMs = SUMMARY_WAIT_MS): Promise<SummarySignal> {
  if (ids.length < 2) return {channel: ids[0], context: null};
  const found = await readSummary(assetId, signal, waitMs);
  const picked = found ? summarySignal(found, ids) : null;
  if (picked) return picked;
  const flagged = await readDepartures(AbortSignal.any([signal, AbortSignal.timeout(1200)]), assetId)
    .then(items => items.find(item => item.assetId === assetId)?.channel).catch(() => undefined);
  return {channel: flagged && ids.includes(flagged) ? flagged : ids[0], context: null};
}

export async function defaultChannel(assetId: string, ids: string[], signal: AbortSignal, waitMs = SUMMARY_WAIT_MS): Promise<string> {
  return (await defaultSignal(assetId, ids, signal, waitMs)).channel;
}
