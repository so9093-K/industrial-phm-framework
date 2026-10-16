/**
 * Read-only, bounded stored signal history.
 * Groups MUST retain source + measurement point + semantic interpretation.
 * No chart point is an interpolated measurement or equipment-health diagnosis.
 */
export type RangePreset = "15m" | "1h" | "24h" | "7d";
export type TimeAnchor = "latest" | "now";

export type ChannelList = {
  assetId: string;
  ids: string[];
  truncated: boolean;
};

export type HistoryBucket = {
  channelId: string;
  sourceId: string;
  pointId: string;
  interpretationId: string;
  bucketStart: string;
  mean: number | null;
  usableCount: number;
  nullCount: number;
  nonGoodCount: number;
  conflictCount: number;
  unit: string | null;
  observedProperty: string | null;
};

export type HistoryTrend = {
  assetId: string;
  startAt: string;
  endAt: string;
  assessedAt: string | null;
  buckets: HistoryBucket[];
  latest: {
    channelId: string; sourceId: string; pointId: string;
    eventAt: string | null; value: number | null;
    usable: boolean; quality: string;
  }[];
};

export type HistoryGroup = {
  key: string;
  sourceId: string;
  pointId: string;
  unit: string | null;
  observedProperty: string | null;
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
  return { assetId, ids: [...new Set(ids)], truncated: list.truncated === true };
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
      pointId: nonEmpty(b.measurement_point_id),
      interpretationId: nonEmpty(b.interpretation_id),
      bucketStart: time(b.bucket_start),
      mean: numberOrNull(b.mean),
      usableCount: count(b.usable_count),
      nullCount: count(b.null_count),
      nonGoodCount: count(b.non_good_count),
      conflictCount: count(b.conflict_count),
      unit: typeof semantics?.unit === "string" ? semantics.unit : null,
      observedProperty: typeof semantics?.observed_property === "string"
        ? semantics.observed_property : null,
    };
  });
  const latest = response.latest_stored.map((raw: unknown) => {
    const b = object(raw);
    if (!b || b.channel_id !== channelId) throw new Error("최근 관측 신호 식별자가 일치하지 않습니다.");
    return {
      channelId, sourceId: nonEmpty(b.source_id), pointId: nonEmpty(b.measurement_point_id),
      eventAt: b.event_at === null ? null : time(b.event_at),
      value: numberOrNull(b.value), usable: b.usable_for_display === true,
      quality: typeof b.source_quality === "string" ? b.source_quality : "미확인",
    };
  });
  return {
    assetId, startAt, endAt,
    assessedAt: typeof response.assessed_at === "string" ? response.assessed_at : null,
    buckets, latest,
  };
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

export function pointsForChart(group: HistoryGroup, startAt: string, endAt: string): {
  bucket: HistoryBucket; x: number; y: number;
}[] {
  // Do not connect points or display non-usable buckets as measured values.
  const entries = group.buckets.slice(-120).filter(
    b => b.usableCount > 0 && b.mean !== null,
  );
  if (!entries.length) return [];
  const values = entries.map(b => b.mean!);
  const low = Math.min(...values), high = Math.max(...values);
  const padding = low === high ? 1 : (high - low) * 0.16;
  const lo = low - padding, hi = high + padding;
  const start = Date.parse(startAt), end = Date.parse(endAt);
  return entries.map(bucket => ({
    bucket,
    x: Math.max(28, Math.min(628, 28 + (Date.parse(bucket.bucketStart) - start) * 600 / (end - start))),
    y: 114 - ((bucket.mean! - lo) / (hi - lo)) * 90,
  }));
}

async function json(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal, cache: "no-store" });
  if (!response.ok) throw new Error("저장 이력 서버에서 요청을 확인하지 못했습니다.");
  return await response.json() as unknown;
}

export async function readChannels(assetId: string, signal: AbortSignal): Promise<ChannelList> {
  const params = new URLSearchParams({asset_id: assetId});
  return parseChannels(await json("/api/v1/history/channels?" + params, signal), assetId);
}

export async function readTrend(
  assetId: string, channelId: string, range: RangePreset, anchor: TimeAnchor, signal: AbortSignal,
): Promise<HistoryTrend> {
  const params = new URLSearchParams({
    asset_id: assetId, channel_id: channelId, range, anchor, buckets: "60",
  });
  return parseTrend(await json("/api/v1/history/trend?" + params, signal), assetId, channelId);
}
