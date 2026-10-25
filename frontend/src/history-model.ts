/** Building an anomaly model from a person's stored record (ADR-0032). The server reads the record,
 * fits the model and binds it; the browser only says which signals and which period. */
import {object, postWrite} from "./writes.ts";

/** One source and measurement point of the asset's record: the signals and period it holds. */
export type HistoryStream = {sourceId: string; pointId: string | null; channels: string[]; startAt: string; endAt: string};
export type ReferenceChoice = "first-30" | "first-50" | "custom";
export const WINDOW_CHOICES = [
  {seconds: 300, label: "5분"}, {seconds: 600, label: "10분"},
  {seconds: 1800, label: "30분"}, {seconds: 3600, label: "1시간"},
] as const;
export const MAX_SIGNALS = 8;

const strings = (raw: unknown): string[] =>
  Array.isArray(raw) ? raw.filter((item): item is string => typeof item === "string" && item.length > 0) : [];

const instant = (raw: unknown): raw is string => typeof raw === "string" && Number.isFinite(Date.parse(raw));

/** The stored record's streams; empty when the asset has no stored history. */
export function parseHistoryStreams(raw: unknown): HistoryStream[] {
  const root = object(raw);
  if (!root || root.schema_version !== 1) throw new Error("저장된 기록 정보의 형식이 올바르지 않습니다.");
  const history = object(root.history);
  if (!history || !Array.isArray(history.streams)) return [];
  return history.streams.flatMap((item: unknown): HistoryStream[] => {
    const row = object(item);
    const channels = strings(row?.channels), point = row?.measurement_point_id;
    if (!row || typeof row.source_id !== "string" || !row.source_id || !channels.length
      || !instant(row.start_at) || !instant(row.end_at) || (point !== null && (typeof point !== "string" || !point))) return [];
    return [{sourceId: row.source_id, pointId: point, channels, startAt: row.start_at, endAt: row.end_at}];
  });
}

/** How a stream is named when an asset has more than one. */
export const streamLabel = (stream: HistoryStream) =>
  stream.sourceId + (stream.pointId ? " · 측정 위치 " + stream.pointId : "");

export async function readHistoryStreams(assetId: string, signal: AbortSignal): Promise<HistoryStream[]> {
  const response = await fetch("/api/v1/explore/sources?" + new URLSearchParams({asset_id: assetId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("저장된 기록 정보를 읽지 못했습니다.");
  }
  return parseHistoryStreams(await response.json() as unknown);
}

/** The reference period as two instants: the first share of the stream's record, or what was entered. */
export function referencePeriod(choice: ReferenceChoice, facts: Pick<HistoryStream, "startAt" | "endAt">,
  custom: {from: string; to: string} | null = null): {from: string; to: string} {
  if (choice === "custom") {
    if (!custom || !custom.from || !custom.to) throw new Error("기준 기간의 시작과 끝을 입력하세요.");
    if (Date.parse(custom.to) <= Date.parse(custom.from)) throw new Error("기준 기간의 끝이 시작보다 뒤여야 합니다.");
    return custom;
  }
  const start = Date.parse(facts.startAt), end = Date.parse(facts.endAt);
  const share = choice === "first-50" ? 0.5 : 0.3;
  return {from: new Date(start).toISOString(), to: new Date(start + (end - start) * share).toISOString()};
}

export type BuildResult =
  | {built: true; bindingId: string; referenceWindows: number; skippedWindows: number; reused: boolean}
  | {built: false; reason: string; referenceWindows: number; skippedWindows: number};

export function parseBuildResult(raw: unknown): BuildResult {
  const root = object(raw);
  const count = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
  const windows = count(root?.reference_windows), skipped = count(root?.skipped_windows);
  if (!root || root.schema_version !== 1 || windows === null || skipped === null)
    throw new Error("모델 만들기 응답을 해석하지 못했습니다.");
  if (root.built === true && typeof root.binding_id === "string" && root.binding_id)
    return {built: true, bindingId: root.binding_id, referenceWindows: windows, skippedWindows: skipped,
      reused: root.reused === true};
  if (root.built === false && typeof root.reason === "string")
    return {built: false, reason: root.reason, referenceWindows: windows, skippedWindows: skipped};
  throw new Error("모델 만들기 응답을 해석하지 못했습니다.");
}

export type BuildRequest = {
  assetId: string; stream: HistoryStream; channels: string[]; from: string; to: string; windowSeconds: number;
};
/** The build request names the stream exactly: its source and, when it has one, its measurement point. */
export function buildPayload(request: BuildRequest): Record<string, unknown> {
  return {
    asset_id: request.assetId, source_id: request.stream.sourceId,
    ...(request.stream.pointId ? {measurement_point_id: request.stream.pointId} : {}),
    channels: request.channels,
    reference_start: request.from, reference_end: request.to, window_seconds: request.windowSeconds,
  };
}

export async function buildHistoryModel(request: BuildRequest, signal: AbortSignal): Promise<BuildResult> {
  return parseBuildResult(await postWrite("/api/v1/phm/models/build", buildPayload(request), signal));
}

const STATS: Record<string, string> = {mean: "평균", std: "표준편차", min: "최소", max: "최대",
  평균: "평균", 표준편차: "표준편차", 최소: "최소", 최대: "최대"};
/** A stored-history window statistic ("motor_temp_c 표준편차" or "motor_temp_c.std") named by the
 * signal's display name; any other label is returned as it is. */
export function historyFeatureLabel(label: string, names: Map<string, {label: string; unit: string | null}> | null): string {
  const match = /^(.+?)(?: |\.)(mean|std|min|max|평균|표준편차|최소|최대)$/.exec(label);
  const named = match ? names?.get(match[1]) : undefined;
  return match && named ? named.label + (named.unit ? " (" + named.unit + ")" : "") + " " + STATS[match[2]] : label;
}
