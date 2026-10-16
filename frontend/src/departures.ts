/**
 * Read-only, model-free departures from a user-selected baseline.
 * Results are a server-owned exploration aid, never health, fault probability,
 * root-cause evidence, or a calibrated anomaly-model score.
 */
export type Baseline = "first-30" | "first-50" | "all";

export type ScoredSignal = {
  id: string;
  state: "scored" | "short-baseline" | "constant";
  median: number | null;
  spread: number | null;
  marked: number;
};

export type DepartureInterval = {
  start: string;
  end: string;
  channel: string;
  channels: string[];
  direction: "up" | "down";
  median: number;
  value: number;
  distance: number;
};

export type Departures = {
  assetId: string;
  selectedChannel: string;
  baseline: { name: Baseline; from: string; to: string };
  threshold: number;
  unit: string | null;
  bucketSeconds: number;
  scored: ScoredSignal;
  score: Array<{ at: string; distance: number }>;
  intervals: DepartureInterval[];
  intervalCount: number;
};

export class NoStoredEvidenceError extends Error {}

function obj(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function nonEmpty(value: unknown): string {
  if (typeof value !== "string" || !value) throw new Error("서버 분석의 식별자가 올바르지 않습니다.");
  return value;
}

function instant(value: unknown): string {
  const at = nonEmpty(value);
  if (!/([zZ]|[+-]\d\d:\d\d)$/.test(at) || !Number.isFinite(Date.parse(at)))
    throw new Error("기준 구간의 관측 시각을 확인할 수 없습니다.");
  return at;
}

function amount(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value))
    throw new Error("서버 분석값을 확인할 수 없습니다.");
  return value;
}

function total(value: unknown): number {
  const n = amount(value);
  if (!Number.isSafeInteger(n) || n < 0) throw new Error("서버 분석 건수가 올바르지 않습니다.");
  return n;
}

export function parseDepartures(
  value: unknown, assetId: string, selectedChannel: string, baselineName: Baseline,
): Departures {
  const data = obj(value), baseline = obj(data?.baseline), units = obj(data?.units);
  if (!data || data.schema_version !== 1
    || data.meaning !== "departures-from-a-chosen-baseline-not-fault-diagnosis"
    || data.asset_id !== assetId
    || !Array.isArray(data.series) || data.series.length !== 1
    || data.series[0] !== selectedChannel
    || !baseline || baseline.name !== baselineName
    || !Array.isArray(data.channels) || !Array.isArray(data.score)
    || !Array.isArray(data.intervals) || !units) {
    throw new Error("선택한 설비·신호·기준 구간과 서버 분석 결과가 일치하지 않습니다.");
  }
  const rawScored = data.channels.map(obj).find(row => row?.key === selectedChannel);
  if (!rawScored || !["scored", "short-baseline", "constant"].includes(String(rawScored.state)))
    throw new Error("선택한 신호의 계산 상태를 확인할 수 없습니다.");
  const state = rawScored.state as ScoredSignal["state"];
  const scored = {
    id: selectedChannel,
    state,
    median: typeof rawScored.median === "number" ? amount(rawScored.median) : null,
    spread: typeof rawScored.spread === "number" ? amount(rawScored.spread) : null,
    marked: total(rawScored.marked),
  };
  const score = data.score.map((entry: unknown) => {
    if (!Array.isArray(entry) || entry.length !== 3 || entry[2] !== selectedChannel)
      throw new Error("다른 신호의 기준 이탈 점수가 섞였습니다.");
    return { at: instant(entry[0]), distance: amount(entry[1]) };
  });
  const intervals = data.intervals.map((raw: unknown) => {
    const item = obj(raw);
    if (!item || item.channel !== selectedChannel || !Array.isArray(item.channels)
      || !item.channels.includes(selectedChannel)
      || (item.direction !== "up" && item.direction !== "down")) {
      throw new Error("선택하지 않은 신호의 비교 구간이 포함됐습니다.");
    }
    const start = instant(item.start), end = instant(item.end);
    if (Date.parse(end) < Date.parse(start)) throw new Error("이상 구간의 시작과 끝이 뒤바뀌었습니다.");
    return {
      start, end, channel: selectedChannel, channels: item.channels.map(nonEmpty),
      direction: item.direction as DepartureInterval["direction"],
      median: amount(item.median), value: amount(item.value), distance: amount(item.distance),
    };
  });
  const intervalCount = total(data.interval_count);
  if (intervals.length > intervalCount || intervals.length > 50)
    throw new Error("분석 구간 수가 서버 제한과 맞지 않습니다.");
  const from = instant(baseline.from), to = instant(baseline.to);
  if (Date.parse(to) < Date.parse(from)) throw new Error("기준 시각 범위가 올바르지 않습니다.");
  const threshold = amount(data.threshold), bucketSeconds = amount(data.bucket_seconds);
  if (threshold <= 0 || bucketSeconds < 0 || score.some(x => x.distance < 0))
    throw new Error("기준 이탈 계산 조건을 확인할 수 없습니다.");
  const unit = units[selectedChannel];
  return {
    assetId, selectedChannel, baseline: {name: baselineName, from, to},
    threshold, unit: typeof unit === "string" ? unit : null,
    bucketSeconds, scored, score, intervals, intervalCount,
  };
}

export function scoreDots(data: Departures): Array<{ at: string; distance: number; x: number; y: number }> {
  if (!data.score.length) return [];
  const first = Date.parse(data.score[0].at);
  const last = Date.parse(data.score[data.score.length - 1].at);
  const end = last > first ? last : first + 1;
  const max = Math.max(data.threshold * 1.4, ...data.score.map(x => x.distance));
  return data.score.map(item => ({
    ...item,
    x: 36 + 590 * (Date.parse(item.at) - first) / (end - first),
    y: 112 - 91 * item.distance / max,
  }));
}

export async function readDepartures(
  assetId: string, series: string, baseline: Baseline, signal: AbortSignal,
): Promise<Departures> {
  const query = new URLSearchParams({ asset_id: assetId, series, baseline });
  const response = await fetch("/api/v1/explore/anomaly?" + query, {
    signal, cache: "no-store", credentials: "same-origin",
  });
  if (response.status === 404) throw new NoStoredEvidenceError("해당 설비의 저장된 비교 근거가 없습니다.");
  if (!response.ok) throw new Error("기준 이탈 분석 근거를 읽지 못했습니다. 조회 오류를 정상 상태로 해석하지 않습니다.");
  return parseDepartures(await response.json() as unknown, assetId, series, baseline);
}
