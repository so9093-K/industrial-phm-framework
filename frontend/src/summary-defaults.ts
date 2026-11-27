/** What a screen opens on when nothing was chosen: the signal, record and periods the asset's state
 * summary leads with, so every screen starts from the change the summary names, else from the
 * current the operating levels are read from. */
import {bandName, departurePeriods, readRecordFindings, type FoundInterval, type RecordFindings} from "./record-findings.ts";
import {readDepartures} from "./monitor-attention.ts";
import type {RecordContext} from "./record-context.ts";
import type {Periods} from "./comparison.ts";
import type {SourceFocus} from "./signal-selection.ts";
import {readVibrationFindings, type VibrationFindings} from "./vibration-findings.ts";
import type {Spans} from "./spectrum.ts";

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
  {x: string; y: string; focus: SourceFocus | null; periods: Periods | null; note: string; band: {low: number; high: number | null} | null} | null {
  const {first, main} = summarySignals(found);
  const offered = (channel: string | undefined) => channel !== undefined && ids.includes(channel);
  const periods = first ? departurePeriods(first, found.baseline, found.bucketSeconds) : null;
  const label = (channel: string) => found.signals.find(row => row.channel === channel)?.label ?? channel;
  const during = periods ? " 기간 A는 변화를 판단한 기록 처음 30%, 기간 B는 특이사항 구간입니다." : "";
  if (first && main && first.channel !== main.channel && offered(first.channel) && offered(main.channel)
    && sameRecordPlace(first.context, main.context)) {
    // The change and the current share a place, so its level is one of this current's levels.
    const operation = found.operation[0];
    const level = first.band != null ? operation.levels[first.band - 1] ?? null : null;
    const band = first.band != null ? " · " + bandName(operation, first.band) + " 중 변화" : "";
    return {x: main.channel, y: first.channel, focus: contextFocus(main.context), periods,
      band: level ? {low: level.low, high: level.high} : null,
      note: "상태 요약의 대표 변화와 같은 기준입니다. 가로축 " + label(main.channel) + ", 세로축 " + first.label + band + "." + during};
  }
  if (first && offered(first.channel)) {
    const others = first.related.filter(row => offered(row.channel) && row.channel !== first.channel);
    const other = others.find(row => row.state !== "within") ?? others[0];
    if (other) return {x: first.channel, y: other.channel, focus: contextFocus(first.context ?? null), periods, band: null,
      note: "상태 요약의 대표 변화를 " + (other.state !== "within" ? "같은 구간에 함께 달라진 신호" : "같은 구간의 다른 신호")
        + "와 함께 봅니다. 가로축 " + first.label + ", 세로축 " + other.label + "." + during};
  }
  if (main && offered(main.channel)) {
    const other = found.signals.find(row => row.channel !== main.channel && offered(row.channel)
      && (row.state === "scored" || row.state === "level-change") && sameRecordPlace(row.context, main.context));
    if (other) return {x: main.channel, y: other.channel, focus: contextFocus(main.context), periods: null, band: null,
      note: "특이사항이 없어 기준 전류와 같은 위치의 다른 신호를 봅니다. 가로축 " + label(main.channel) + ", 세로축 " + other.label + "."};
  }
  return null;
}

/** 두 기간 비교를 탭에서 바로 열었을 때의 기본값: 상태 요약의 대표 변화와 같은 신호·기록·운전 수준과
 * 기간(판단에 쓴 기록 처음 30%를 A, 변화 구간을 B)을 쓴다. 대표 변화를 이 화면이 다룰 수 없으면 null. */
export function comparisonDefault(found: RecordFindings, ids: string[]):
  {channel: string; focus: SourceFocus | null; periods: Periods; level: number | null} | null {
  const first = found.intervals[0];
  if (!first || !ids.includes(first.channel)) return null;
  const periods = departurePeriods(first, found.baseline, found.bucketSeconds);
  return periods ? {channel: first.channel, focus: contextFocus(first.context ?? null), periods, level: first.band ?? null} : null;
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

/** 진동 탭이 상태 요약의 대표 변화를 그대로 이어받았을 때 함께 보여 주는 문장. */
/** 조사 화면이 넘긴 진동 두 기간(초기·특이사항 구간). 주소에 compare_origin=summary와 함께 실려 온다. */
export function handedSpans(search: string): Spans | null {
  const query = new URLSearchParams(search), keys = ["a_from", "a_to", "b_from", "b_to"].map(key => "acq_" + key);
  if (query.get("compare_origin") !== "summary" || !keys.every(key => query.has(key))) return null;
  const [aFrom, aTo, bFrom, bTo] = keys.map(key => Number(query.get(key)));
  return [aFrom, aTo, bFrom, bTo].every(Number.isSafeInteger) ? {a: {from: aFrom, to: aTo}, b: {from: bFrom, to: bTo}} : null;
}
/** 보이는 두 기간이 조사 화면이 넘긴 그 기간인지. 그렇다면 다른 화면과 같은 이름('초기'·'특이사항 구간')으로 부른다. */
export function isHanded(spans: Spans | null, handed: Spans | null): boolean {
  return !!spans && !!handed && spans.a.from === handed.a.from && spans.a.to === handed.a.to
    && spans.b.from === handed.b.from && spans.b.to === handed.b.to;
}
export const VIBRATION_SUMMARY_NOTE = "초기는 기록 처음 30%, 특이사항 구간은 모니터링 화면의 특이사항과 같은 기간입니다.";

/** 진동 탭을 바로 열었을 때의 기본값: 상태 요약이 앞세우는 진동 변화와 같은 특징과 기간(판단에 쓴
 * 기록 처음 30%를 A, 변화 구간을 B), 그리고 같은 측정에서 함께 달라진 특징 하나. 다른 모델 연결의
 * 기록이거나 이 화면이 그 특징을 다룰 수 없으면 null이고, 화면은 자기 기본값을 쓴다. */
export function vibrationDefault(found: VibrationFindings, bindingId: string, features: string[]):
  {feature: string; related: string | null; spans: Spans} | null {
  const first = found.intervals[0];
  if (!first || found.bindingId !== bindingId || !features.includes(first.feature)) return null;
  const related = first.related.find(row => row.feature !== first.feature && features.includes(row.feature))?.feature ?? null;
  return {feature: first.feature, related, spans: {a: {from: first.baseline.from, to: first.baseline.to}, b: {from: first.from, to: first.to}}};
}

/** The asset's vibration summary, or null when it is not ready within the wait or cannot be read. */
export function readVibrationSummary(assetId: string, signal: AbortSignal, waitMs = SUMMARY_WAIT_MS): Promise<VibrationFindings | null> {
  return readVibrationFindings(assetId, AbortSignal.any([signal, AbortSignal.timeout(waitMs)])).catch(() => null);
}
