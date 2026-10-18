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
  if (typeof value !== "string" || !value) throw new Error("기준 이탈 결과의 식별 정보가 올바르지 않습니다.");
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
    throw new Error("기준 이탈 결과의 값을 확인할 수 없습니다.");
  return value;
}

function total(value: unknown): number {
  const n = amount(value);
  if (!Number.isSafeInteger(n) || n < 0) throw new Error("기준 이탈 결과의 건수가 올바르지 않습니다.");
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
    throw new Error("받은 결과가 고른 설비·신호·기준 구간과 맞지 않아 표시하지 않았습니다.");
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
    throw new Error("벗어난 구간 수가 허용 범위를 넘었습니다.");
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

export type Band = { x: number; width: number };
export type DepartureChart = {
  width: number; height: number; max: number; first: string; last: string;
  path: string; thresholdY: number; baseline: Band; intervals: Band[];
};

/** The departure size over time on a stretchable plot: the chosen baseline span, the
 * threshold and the intervals found are drawn where they are; a time gap breaks the line. */
export function departureChart(data: Departures): DepartureChart | null {
  if (!data.score.length) return null;
  const width = 800, height = 200, top = 8, bottom = 192;
  const times = data.score.map((item) => Date.parse(item.at));
  const first = times[0], last = Math.max(times[times.length - 1], first + 1);
  const max = Math.max(data.threshold * 1.4, ...data.score.map((item) => item.distance));
  const x = (at: number) => ((at - first) / (last - first)) * width;
  const y = (value: number) => bottom - (value / max) * (bottom - top);
  const steps = times.slice(1).map((at, i) => at - times[i]).sort((a, b) => a - b);
  const gap = (steps[Math.floor(steps.length / 2)] ?? 0) * 1.5;
  let path = "";
  data.score.forEach((item, i) => {
    const joinedBefore = i > 0 && times[i] - times[i - 1] <= gap;
    const joinedAfter = i + 1 < times.length && times[i + 1] - times[i] <= gap;
    const px = x(times[i]), py = y(item.distance).toFixed(1);
    // A point with no neighbour is drawn as a short tick so it does not vanish.
    if (!joinedBefore && !joinedAfter) path += "M" + (px - 3).toFixed(1) + " " + py + " L" + (px + 3).toFixed(1) + " " + py + " ";
    else path += (joinedBefore ? "L" : "M") + px.toFixed(1) + " " + py + " ";
  });
  const band = (from: string, to: string): Band => {
    const start = Math.max(0, x(Date.parse(from))), end = Math.min(width, x(Date.parse(to)));
    return { x: start, width: Math.max(2, end - start) };
  };
  return {
    width, height, max, first: data.score[0].at, last: data.score[data.score.length - 1].at,
    path: path.trim(), thresholdY: y(data.threshold),
    baseline: band(data.baseline.from, data.baseline.to),
    intervals: data.intervals.map((item) => band(item.start, item.end)),
  };
}

export async function readDepartures(
  assetId: string, series: string, baseline: Baseline, signal: AbortSignal,
): Promise<Departures> {
  const query = new URLSearchParams({ asset_id: assetId, series, baseline });
  const response = await fetch("/api/v1/explore/anomaly?" + query, {
    signal, cache: "no-store", credentials: "same-origin",
  });
  if (response.status === 404) {
    const error = await response.json().catch(() => null) as unknown;
    if (obj(error)?.error === "nothing_to_explore") {
      throw new NoStoredEvidenceError("이 설비에는 비교할 저장 기록이 없습니다.");
    }
    throw new Error("결과를 찾을 위치를 확인하지 못했습니다. 기록이 없다는 뜻은 아닙니다.");
  }
  if (!response.ok) throw new Error("기준 이탈 결과를 읽지 못했습니다. 이상이 없다는 뜻은 아닙니다.");
  return parseDepartures(await response.json() as unknown, assetId, series, baseline);
}
