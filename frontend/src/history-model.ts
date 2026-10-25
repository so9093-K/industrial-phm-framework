/** Building an anomaly model from a person's stored record (ADR-0032). The server reads the record,
 * fits the model and binds it; the browser only says which signals and which period. */
import {object, postWrite} from "./writes.ts";

export type HistoryFacts = {channels: string[]; sources: string[]; startAt: string; endAt: string};
export type ReferenceChoice = "first-30" | "first-50" | "custom";
export const WINDOW_CHOICES = [
  {seconds: 300, label: "5분"}, {seconds: 600, label: "10분"},
  {seconds: 1800, label: "30분"}, {seconds: 3600, label: "1시간"},
] as const;
export const MAX_SIGNALS = 8;

const strings = (raw: unknown): string[] =>
  Array.isArray(raw) ? raw.filter((item): item is string => typeof item === "string" && item.length > 0) : [];

/** The stored record's signals, sources and extent; null when the asset has no stored history. */
export function parseHistoryFacts(raw: unknown): HistoryFacts | null {
  const history = object(object(raw)?.history);
  if (!history || typeof history.start_at !== "string" || typeof history.end_at !== "string") return null;
  if (!Number.isFinite(Date.parse(history.start_at)) || !Number.isFinite(Date.parse(history.end_at))) return null;
  const channels = strings(history.channels), sources = strings(history.sources);
  return channels.length && sources.length
    ? {channels, sources, startAt: history.start_at, endAt: history.end_at} : null;
}

export async function readHistoryFacts(assetId: string, signal: AbortSignal): Promise<HistoryFacts | null> {
  const response = await fetch("/api/v1/explore/sources?" + new URLSearchParams({asset_id: assetId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("저장된 기록 정보를 읽지 못했습니다.");
  }
  return parseHistoryFacts(await response.json() as unknown);
}

/** The reference period as two instants: the first share of the record, or what was entered. */
export function referencePeriod(choice: ReferenceChoice, facts: HistoryFacts,
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

export async function buildHistoryModel(request: {
  assetId: string; sourceId: string; channels: string[]; from: string; to: string; windowSeconds: number;
}, signal: AbortSignal): Promise<BuildResult> {
  return parseBuildResult(await postWrite("/api/v1/phm/models/build", {
    asset_id: request.assetId, source_id: request.sourceId, channels: request.channels,
    reference_start: request.from, reference_end: request.to, window_seconds: request.windowSeconds,
  }, signal));
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
