/** Building an anomaly model from a person's stored record (ADR-0032). The server reads the record,
 * fits the model and binds it; the browser only says which signals and which period. */
import {object, postWrite} from "./writes.ts";
import {parseHistoryStreams, type HistoryStream} from "./history.ts";

export type ReferenceChoice = "first-30" | "first-50" | "custom";
export const WINDOW_CHOICES = [
  {seconds: 300, label: "5분"}, {seconds: 600, label: "10분"},
  {seconds: 1800, label: "30분"}, {seconds: 3600, label: "1시간"},
] as const;
export const MAX_SIGNALS = 8;

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

/** A first value on or after the exclusive end cannot contribute to the reference period. */
export function signalsForReference(stream: HistoryStream, end: string): string[] {
  const stop = Date.parse(end);
  return stream.channels.filter(channel => {
    const first = stream.valuedSince?.[channel];
    return first === undefined || (first !== null && Date.parse(first) < stop);
  });
}

/** How a model learned each operating level of its stream's current (ADR-0034). */
export type LearnedLevels = {judged: string[]; unjudged: {name: string; windows: number}[]};
export type BuildResult =
  | {built: true; bindingId: string; referenceWindows: number; skippedWindows: number; reused: boolean; levels: LearnedLevels | null}
  | {built: false; reason: string; referenceWindows: number; skippedWindows: number};

const about = (value: number) => value.toLocaleString("ko-KR", {maximumSignificantDigits: 2});
/** The levels a model learned and those it does not judge, as the screens name levels
 * ("약 62 A 운전", "정지"); null for a model that learned its whole period as one. */
export function learnedLevels(raw: unknown): LearnedLevels | null {
  const root = object(raw);
  const typical = root?.typical, counts = object(root?.reference_windows), learned = root?.learned;
  if (!root || !Array.isArray(typical) || !counts || !Array.isArray(learned)
    || !typical.every(value => typeof value === "number" && Number.isFinite(value))) return null;
  const name = (band: number) => band === 0 ? "정지" : "약 " + about(typical[band - 1] as number) + " A 운전";
  const bands = Object.keys(counts).map(Number).filter(band => Number.isInteger(band) && band >= 0 && band <= typical.length);
  return {
    judged: bands.filter(band => learned.includes(String(band))).map(name),
    unjudged: bands.filter(band => !learned.includes(String(band)))
      .map(band => ({name: name(band), windows: typeof counts[String(band)] === "number" ? counts[String(band)] as number : 0})),
  };
}
// '약 62 A 운전을', '정지를': 마지막 이름의 받침에 맞춘 조사.
const particle = (names: string[], withFinal: string, without: string) =>
  names.at(-1)?.endsWith("정지") ? without : withFinal;
/** "약 62 A 운전을 판정 · 약 11 A·31 A 운전은 기준 기간에 없어 판정하지 않음". */
export function levelsText(levels: LearnedLevels): string {
  const parts = [levels.judged.join("·") + particle(levels.judged, "을", "를")
    + (levels.judged.length > 1 ? " 각각" : "") + " 판정"];
  const absent = levels.unjudged.filter(row => row.windows === 0).map(row => row.name);
  if (absent.length) parts.push(absent.join("·") + particle(absent, "은", "는") + " 기준 기간에 없어 판정하지 않음");
  for (const row of levels.unjudged.filter(row => row.windows > 0))
    parts.push(row.name + particle([row.name], "은", "는") + " 기준 기간에 " + row.windows + "개뿐이라 판정하지 않음");
  return parts.join(" · ");
}

export function parseBuildResult(raw: unknown): BuildResult {
  const root = object(raw);
  const count = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
  const windows = count(root?.reference_windows), skipped = count(root?.skipped_windows);
  if (!root || root.schema_version !== 1 || windows === null || skipped === null)
    throw new Error("모델 만들기 응답을 해석하지 못했습니다.");
  if (root.built === true && typeof root.binding_id === "string" && root.binding_id)
    return {built: true, bindingId: root.binding_id, referenceWindows: windows, skippedWindows: skipped,
      reused: root.reused === true, levels: learnedLevels(root.levels)};
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
