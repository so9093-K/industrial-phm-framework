/**
 * Read-only, bounded stored signal history.
 * Groups MUST retain source + measurement point + semantic interpretation.
 * No chart point is an interpolated measurement or equipment-health diagnosis.
 */
/** "all" spans the stored record of the chosen signal, from its first to its last measurement. */
import {yTicks, type Tick} from "./chart-axis.ts";
export type RangePreset = "all" | "15m" | "1h" | "24h" | "7d";
export const RANGE_PRESETS: readonly RangePreset[] = ["all", "15m", "1h", "24h", "7d"];
export type TimeAnchor = "latest" | "now";

export type SignalNames = Map<string, {label: string; unit: string | null}>;
export type ChannelList = {assetId: string; ids: string[]; truncated: boolean; names: SignalNames};

export type HistoryBucket = {
  channelId: string;
  sourceId: string;
  pointId: string | null;
  interpretationId: string;
  bucketStart: string;
  /** The first stored event inside the bucket; bucket starts are aligned to the window. */
  firstEventAt?: string | null;
  /** The last stored event inside the bucket, with this bucket's measurement meaning. */
  lastEventAt?: string | null;
  mean: number | null;
  /** Smallest and largest stored value inside the bucket; a short spike shows here. */
  minimum: number | null;
  maximum: number | null;
  usableCount: number;
  nullCount: number;
  nonGoodCount: number;
  conflictCount: number;
  unit: string | null;
  observedProperty: string | null;
  unitEvidence?: string | null;
  interpretationEvidence?: string | null;
};

export type HistoryTrend = {
  assetId: string;
  startAt: string;
  endAt: string;
  assessedAt: string | null;
  bucketSeconds: number | null;
  buckets: HistoryBucket[];
  latest: {
    channelId: string; sourceId: string; pointId: string | null;
    eventAt: string | null; value: number | null;
    usable: boolean; quality: string;
  }[];
};

export type HistoryGroup = {
  key: string;
  sourceId: string;
  pointId: string | null;
  unit: string | null;
  observedProperty: string | null;
  unitEvidence?: string | null;
  interpretationEvidence?: string | null;
  interpretationId: string;
  buckets: HistoryBucket[];
};

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function nonEmpty(value: unknown): string {
  if (typeof value !== "string" || !value) throw new Error("이력 응답의 식별자가 올바르지 않습니다.");
  return value;
}

function time(value: unknown): string {
  const s = nonEmpty(value);
  if (!Number.isFinite(Date.parse(s))) throw new Error("이력 응답의 관측 시간이 올바르지 않습니다.");
  return s;
}

function numberOrNull(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value))
    throw new Error("이력 응답에 유효하지 않은 수치가 포함됐습니다.");
  return value;
}

function count(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0)
    throw new Error("이력 응답에 유효하지 않은 품질 건수가 포함됐습니다.");
  return value;
}

export function parseChannels(payload: unknown, assetId: string): ChannelList {
  const response = object(payload), list = object(response?.channels);
  if (response?.asset_id !== assetId || !list || !Array.isArray(list.items))
    throw new Error("선택한 설비의 신호 목록을 확인할 수 없습니다.");
  const ids = list.items.map(nonEmpty);
  // What the person who registered the data called each channel; absent names stay IDs.
  const names: SignalNames = new Map();
  for (const [id, raw] of Object.entries(object(response.labels) ?? {})) {
    const entry = object(raw);
    if (ids.includes(id) && typeof entry?.label === "string" && entry.label.trim())
      names.set(id, {label: entry.label, unit: typeof entry.unit === "string" && entry.unit.trim() ? entry.unit : null});
  }
  return { assetId, ids: [...new Set(ids)], truncated: list.truncated === true, names };
}

export function parseTrend(payload: unknown, assetId: string, channelId: string): HistoryTrend {
  const response = object(payload);
  if (!response || response.asset_id !== assetId || !Array.isArray(response.channel_ids)
      || !response.channel_ids.includes(channelId)
      || !Array.isArray(response.buckets) || !Array.isArray(response.latest_stored)) {
    throw new Error("선택한 설비·신호의 저장 이력을 확인할 수 없습니다.");
  }
  const startAt = time(response.start_at), endAt = time(response.end_at);
  if (Date.parse(endAt) <= Date.parse(startAt)) throw new Error("이력 조회 시간이 뒤바뀌었습니다.");
  const buckets = response.buckets.map((raw: unknown) => {
    const b = object(raw), semantics = object(b?.semantics);
    if (!b || b.channel_id !== channelId) throw new Error("서로 다른 신호의 이력이 섞였습니다.");
    return {
      channelId: channelId,
      sourceId: nonEmpty(b.source_id),
      pointId: b.measurement_point_id === null ? null : nonEmpty(b.measurement_point_id),
      interpretationId: nonEmpty(b.interpretation_id),
      bucketStart: time(b.bucket_start),
      firstEventAt: typeof b.first_event_at === "string" ? time(b.first_event_at) : null,
      lastEventAt: typeof b.last_event_at === "string" ? time(b.last_event_at) : null,
      mean: numberOrNull(b.mean),
      minimum: b.minimum === undefined ? null : numberOrNull(b.minimum),
      maximum: b.maximum === undefined ? null : numberOrNull(b.maximum),
      usableCount: count(b.usable_count),
      nullCount: count(b.null_count),
      nonGoodCount: count(b.non_good_count),
      conflictCount: count(b.conflict_count),
      unit: typeof b.unit === "string" && b.unit ? b.unit
        : typeof semantics?.unit === "string" ? semantics.unit : null,
      unitEvidence: typeof semantics?.unit_evidence === "string" ? semantics.unit_evidence : null,
      interpretationEvidence: typeof semantics?.interpretation_evidence === "string" ? semantics.interpretation_evidence : null,
      observedProperty: typeof semantics?.observed_property === "string"
        ? semantics.observed_property : null,
    };
  });
  const latest = response.latest_stored.map((raw: unknown) => {
    const b = object(raw);
    if (!b || b.channel_id !== channelId) throw new Error("최근 관측 신호 식별자가 일치하지 않습니다.");
    return {
      channelId, sourceId: nonEmpty(b.source_id), pointId: b.measurement_point_id === null ? null : nonEmpty(b.measurement_point_id),
      eventAt: b.event_at === null ? null : time(b.event_at),
      value: numberOrNull(b.value), usable: b.usable_for_display === true,
      quality: typeof b.source_quality === "string" ? b.source_quality : "미확인",
    };
  });
  return {
    assetId, startAt, endAt,
    assessedAt: typeof response.assessed_at === "string" ? response.assessed_at : null,
    bucketSeconds: typeof response.bucket_seconds === "number" && response.bucket_seconds > 0
      ? response.bucket_seconds : null,
    buckets, latest,
  };
}

/** The unit of one stored last value, read from the bucket that ends at that very event.
 * The last value carries no meaning of its own; a unit seen elsewhere in the window may be
 * from before a change, so a value outside the window, or claimed by unlike units, gets none. */
export function latestUnit(trend: HistoryTrend, latest: HistoryTrend["latest"][number]): string | null {
  if (latest.eventAt === null) return null;
  const at = Date.parse(latest.eventAt);
  const units = new Set(trend.buckets
    .filter((bucket) => bucket.sourceId === latest.sourceId && bucket.pointId === latest.pointId
      && bucket.lastEventAt != null && Date.parse(bucket.lastEventAt) === at)
    .map((bucket) => bucket.unit));
  return units.size === 1 ? [...units][0] : null;
}

/** The last stored measurement the trend holds. A whole-record query ends one second after it,
 * since its end is exclusive, so that edge is not a measurement time. */
export function recordEnd(trend: HistoryTrend): string | null {
  let last: string | null = null;
  for (const bucket of trend.buckets)
    if (bucket.lastEventAt && (last === null || Date.parse(bucket.lastEventAt) > Date.parse(last))) last = bucket.lastEventAt;
  return last;
}

export function groupHistory(trend: HistoryTrend): HistoryGroup[] {
  const map = new Map<string, HistoryGroup>();
  for (const bucket of trend.buckets) {
    const key = JSON.stringify([
      bucket.channelId, bucket.sourceId, bucket.pointId, bucket.interpretationId,
    ]);
    let group = map.get(key);
    if (!group) {
      group = {
        key, sourceId: bucket.sourceId, pointId: bucket.pointId,
        unit: bucket.unit, observedProperty: bucket.observedProperty,
        unitEvidence: bucket.unitEvidence, interpretationEvidence: bucket.interpretationEvidence,
        interpretationId: bucket.interpretationId, buckets: [],
      };
      map.set(key, group);
    }
    group.buckets.push(bucket);
  }
  return [...map.values()].map(group => ({
    ...group,
    buckets: group.buckets.sort((a, b) => Date.parse(a.bucketStart) - Date.parse(b.bucketStart)),
  }));
}

export type SignalChart = {
  width: number; height: number; low: number; high: number;
  /** Where the plot starts: the window start, or the first stored bucket if later. */
  from: string;
  /** The plotted time span in epoch milliseconds, for the time axis. */
  start: number; end: number;
  /** Means joined only between adjacent buckets; a missing bucket breaks the line. */
  path: string;
  marks: {bucket: HistoryBucket; x: number; mean: number; min: number; max: number}[];
  ticks: Tick[];
};

/** Bucket means as a line with each bucket's min-max range, from the first stored bucket
 * (or the window start) to the window end. Unusable buckets are never drawn and nothing
 * is interpolated across them. */
/** How a chart drawn beside another lines up with it: the same plot start, and optionally the
 * same value range so like quantities (three phases of a current) read on one scale. */
export type ChartFrame = {start?: number; range?: {low: number; high: number}; height?: number};

/** The lowest and highest drawn value of a group, for a value range shared between charts. */
export function valueRange(group: HistoryGroup): {low: number; high: number} | null {
  const entries = group.buckets.filter(b => b.usableCount > 0 && b.mean !== null);
  if (!entries.length) return null;
  return {low: Math.min(...entries.map(b => b.minimum ?? b.mean!)), high: Math.max(...entries.map(b => b.maximum ?? b.mean!))};
}

export function signalChart(
  group: HistoryGroup, startAt: string, endAt: string, bucketSeconds: number | null, frame: ChartFrame = {},
): SignalChart | null {
  const entries = group.buckets.filter(b => b.usableCount > 0 && b.mean !== null);
  if (!entries.length) return null;
  const width = 800, height = frame.height ?? 200, top = 8, bottom = height - 8;
  const lows = entries.map(b => b.minimum ?? b.mean!), highs = entries.map(b => b.maximum ?? b.mean!);
  const low = frame.range?.low ?? Math.min(...lows), high = frame.range?.high ?? Math.max(...highs);
  const padding = low === high ? Math.max(Math.abs(low) * 0.05, 1) : (high - low) * 0.08;
  const lo = low - padding, hi = high + padding;
  const start = frame.start ?? Math.max(Date.parse(startAt), Date.parse(entries[0].bucketStart));
  const end = Math.max(Date.parse(endAt), start + 1);
  const x = (at: string) => ((Date.parse(at) - start) / (end - start)) * width;
  const y = (value: number) => bottom - ((value - lo) / (hi - lo)) * (bottom - top);
  const step = (bucketSeconds ?? 0) * 1000 * 1.5;
  let path = "", previous: number | null = null;
  const marks = entries.map(bucket => {
    const at = Date.parse(bucket.bucketStart);
    const joined = previous !== null && step > 0 && at - previous <= step;
    path += (joined ? "L" : "M") + x(bucket.bucketStart).toFixed(1) + " " + y(bucket.mean!).toFixed(1) + " ";
    previous = at;
    return {bucket, x: x(bucket.bucketStart), mean: y(bucket.mean!),
      min: y(bucket.minimum ?? bucket.mean!), max: y(bucket.maximum ?? bucket.mean!)};
  });
  return {width, height, low, high, from: new Date(start).toISOString(), start, end, path: path.trim(), marks,
    ticks: yTicks(lo, hi, top, bottom)};
}

async function json(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal, cache: "no-store" });
  if (!response.ok) {
    // An unread error body keeps the request open; close it before reporting the failure.
    await response.body?.cancel().catch(() => {});
    throw new Error("저장된 측정 기록을 불러오지 못했습니다.");
  }
  return await response.json() as unknown;
}

export async function readChannels(assetId: string, signal: AbortSignal): Promise<ChannelList> {
  const params = new URLSearchParams({asset_id: assetId});
  return parseChannels(await json("/api/v1/history/channels?" + params, signal), assetId);
}

/** A start and end chosen on the chart (ISO with offset); it replaces the preset. */
export type TrendWindow = {from: string; to: string};

export async function readTrend(
  assetId: string, channelId: string, range: RangePreset | TrendWindow, anchor: TimeAnchor, signal: AbortSignal,
  sourceId: string | null = null,
): Promise<HistoryTrend> {
  return (await readTrends(assetId, [channelId], range, anchor, signal, sourceId)).get(channelId)!;
}

/** Several signals read in one request, so they share one window and one bucket grid. */
export async function readTrends(
  assetId: string, channelIds: string[], range: RangePreset | TrendWindow, anchor: TimeAnchor, signal: AbortSignal,
  sourceId: string | null = null,
): Promise<Map<string, HistoryTrend>> {
  const params = new URLSearchParams({asset_id: assetId, buckets: "120"});
  for (const id of channelIds) params.append("channel_id", id);
  if (sourceId) params.set("source_id", sourceId);
  if (typeof range === "string") {params.set("range", range); params.set("anchor", anchor);}
  else {params.set("from", range.from); params.set("to", range.to);}
  return splitTrend(await json("/api/v1/history/trend?" + params, signal), assetId, channelIds);
}

/** One multi-signal trend read as one trend per signal, each checked as if read alone. */
export function splitTrend(payload: unknown, assetId: string, channelIds: string[]): Map<string, HistoryTrend> {
  const response = object(payload);
  if (!response || !Array.isArray(response.buckets) || !Array.isArray(response.latest_stored))
    throw new Error("선택한 설비·신호의 저장 이력을 확인할 수 없습니다.");
  const own = (rows: unknown[], id: string) => rows.filter((row) => object(row)?.channel_id === id);
  return new Map(channelIds.map((id) => [id, parseTrend({...response, buckets: own(response.buckets as unknown[], id),
    latest_stored: own(response.latest_stored as unknown[], id)}, assetId, id)]));
}

/** The same item on the other phases, by the R/S/T naming of three-phase channels
 * (R상전류 → S상전류, T상전류). A channel that names no phase has none. */
export function phaseSiblings(ids: string[], id: string): string[] {
  const match = /^([RST])(상?)(.+)$/.exec(id);
  if (!match) return [];
  return ["R", "S", "T"].filter(phase => phase !== match[1]).map(phase => phase + match[2] + match[3])
    .filter(other => ids.includes(other));
}

/** A channel as people read it: its declared name and unit, else its stored ID. */
export function signalName(names: SignalNames | null | undefined, id: string): string {
  const named = names?.get(id);
  return named ? named.label + (named.unit ? " (" + named.unit + ")" : "") : id;
}

const known = new Map<string, {at: number; names: Promise<SignalNames>}>();
/** Signal names for an asset, shared by the screens that list its channels for a short while. */
export function readSignalNames(assetId: string): Promise<SignalNames> {
  const cached = known.get(assetId);
  if (cached && Date.now() - cached.at < 30_000) return cached.names;
  const names = readChannels(assetId, new AbortController().signal).then((list) => list.names)
    .catch(() => new Map() as SignalNames);
  known.set(assetId, {at: Date.now(), names});
  return names;
}
