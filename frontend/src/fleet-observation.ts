/** 설비 관제 화면의 한 칸: 설비를 지켜보는 신호 묶음(같은 의미의 R·S·T상, 진동의 수평·수직)과 그 묶음에서 찾은 변화.
 * 저장 기록은 재생할 수 있다. 재생 위치까지 끝난 구간만 그리고, 변화는 그 위치까지의 기록으로 서버가 판정한다. */
import {readAssetData} from "./asset-data.ts";
import {episodes} from "./asset-timeline.ts";
import {groupHistory} from "./history.ts";
import {readObservation, recentAsset} from "./observation.ts";
import type {Asset} from "./monitor.ts";
import {routeUrl} from "./routes.ts";
import {object} from "./writes.ts";

export type FleetPoint = {x: number; value: number; join: boolean};
export type FleetSeries = {key: string; label: string; short: string; points: FleetPoint[]};
export type FleetGroup = {
  label: string; unit: string | null; axis: "time" | "acquisition"; focus: string;
  /** 기록의 처음과 끝(시각 ms 또는 측정 번호). 재생은 이 범위를 움직인다. */
  record: {from: number; to: number};
  /** 시간 기록의 한 점이 덮는 길이(ms). 점은 이 길이가 다 지난 뒤에만 그린다. */
  bucketMs: number | null; periodSeconds: number | null; series: FleetSeries[];
};
export type FleetChange = {key: string; label: string; from: number; to: number; up: boolean;
  before: number | null; after: number | null};
/** 한 설비 칸이 읽은 것. `live`는 실제로 수신 중인 출처의 최근 관측이다(저장 기록 재생이 아니다). */
export type FleetRead = {group: FleetGroup | null; changes: FleetChange[]; live: boolean; href: string};

function invalid(): never { throw new Error("설비 관측의 형식이 올바르지 않습니다."); }
const finite = (raw: unknown): number => typeof raw === "number" && Number.isFinite(raw) ? raw : invalid();
const text = (raw: unknown): string | null => typeof raw === "string" && raw ? raw : null;

export function parseGroup(raw: unknown): FleetGroup | null {
  const group = object(raw);
  if (!group) return null;
  const axis = group.axis === "acquisition" ? "acquisition" : group.axis === "time" ? "time" : invalid();
  const at = (value: unknown) => axis === "time" ? Date.parse(String(value)) : finite(value);
  const record = object(group.record) ?? invalid();
  const series = (Array.isArray(group.series) ? group.series : invalid()).map((raw: unknown): FleetSeries => {
    const row = object(raw) ?? invalid();
    const trace = Array.isArray(row.trace) ? row.trace : invalid();
    const joins = Array.isArray(row.trace_join) && row.trace_join.length === trace.length ? row.trace_join : invalid();
    return {key: text(row.key) ?? invalid(), label: text(row.label) ?? invalid(), short: text(row.short) ?? invalid(),
      points: trace.map((point: unknown, index: number) => {
        if (!Array.isArray(point) || point.length !== 2) invalid();
        const x = at(point[0]);
        return Number.isFinite(x) ? {x, value: finite(point[1]), join: joins[index] === true} : invalid();
      })};
  });
  const from = at(record.from), to = at(record.to);
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from || !series.length) return null;
  return {label: text(group.label) ?? invalid(), unit: text(group.unit), axis, focus: text(group.focus) ?? invalid(),
    record: {from, to}, bucketMs: typeof group.bucket_seconds === "number" ? group.bucket_seconds * 1000 : null,
    periodSeconds: typeof group.period_seconds === "number" ? group.period_seconds : null, series};
}

/** 재생 위치까지 끝난 점만. 시간 기록의 점은 구간 평균이라 구간이 다 지나야 그 값이 정해진다. */
export function visibleSeries(group: FleetGroup, until: number): FleetSeries[] {
  const span = group.bucketMs ?? 0;
  return group.series.map(row => ({...row, points: row.points.filter(point => point.x + span <= until + span * 0.01)}));
}

/** 재생 위치. 진동은 측정 번호라 정수로 내린다. */
export function positionAt(group: FleetGroup, fraction: number): number {
  const at = group.record.from + (group.record.to - group.record.from) * Math.max(0, Math.min(1, fraction));
  return group.axis === "acquisition" ? Math.max(group.record.from, Math.floor(at)) : at;
}

/** 가장 늦게 시작한 시기의 변화들: 시간이 겹치는 변화를 한 시기로 묶고(설비 시간축과 같은 규칙) 마지막 시기를 고른다. */
export function latestEpisode(changes: FleetChange[]): FleetChange[] {
  return episodes(changes, change => change).at(-1)?.members ?? [];
}

async function json(url: string, signal: AbortSignal): Promise<Record<string, unknown>> {
  const response = await fetch(url, {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("설비 관측을 읽지 못했습니다.");
  }
  return object(await response.json() as unknown) ?? invalid();
}

/** 묶음 신호에서 찾은 변화. `until`이 있으면 그 위치까지의 기록만으로 판정한 결과다. */
export async function readFleetChanges(assetId: string, group: FleetGroup, until: number | null, signal: AbortSignal): Promise<FleetChange[]> {
  const keys = new Set(group.series.map(row => row.key));
  const query = new URLSearchParams({asset_id: assetId});
  if (group.axis === "time") {
    if (until !== null) query.set("record_until", new Date(until).toISOString());
    const body = await json("/api/v1/explore/findings?" + query, signal);
    return (Array.isArray(body.intervals) ? body.intervals : []).flatMap((raw: unknown) => {
      const row = object(raw);
      if (!row || !keys.has(String(row.key))) return [];
      return [{key: String(row.key), label: text(row.label) ?? String(row.channel), up: row.direction !== "down",
        from: Date.parse(String(row.start)), to: Date.parse(String(row.end)),
        before: typeof row.reference_value === "number" ? row.reference_value : null,
        after: typeof row.typical_value === "number" ? row.typical_value : null}];
    }).filter(row => Number.isFinite(row.from) && Number.isFinite(row.to));
  }
  if (until !== null) query.set("acquisition_until", String(Math.floor(until)));
  const body = await json("/api/v1/explore/vibration?" + query, signal);
  return (Array.isArray(body.intervals) ? body.intervals : []).flatMap((raw: unknown) => {
    const row = object(raw);
    if (!row || !keys.has(String(row.feature))) return [];
    return [{key: String(row.feature), label: text(row.label) ?? String(row.feature), up: row.direction !== "down",
      from: finite(row.from), to: finite(row.to),
      before: typeof row.reference_value === "number" ? row.reference_value : null,
      after: typeof row.typical_value === "number" ? row.typical_value : null}];
  });
}

/** 설비 조사 화면 주소. 재생 중이면 그 위치까지의 기록으로 연다. */
export function investigationHref(assetId: string, group: FleetGroup | null, until: number | null): string {
  const url = new URL(routeUrl({page: "monitor", assetId, tab: "summary", method: null, data: null}), "http://local");
  url.searchParams.set("observation_view", "record");
  if (group && until !== null)
    url.searchParams.set(group.axis === "time" ? "record_until" : "acquisition_until",
      group.axis === "time" ? new Date(until).toISOString() : String(Math.floor(until)));
  return url.pathname + url.search;
}

/** 실제로 수신 중인 출처는 최근 1시간 관측(앞선 관측과 비교한 변화 포함), 그 밖에는 저장 기록 전체를 읽는다. */
export async function readFleet(asset: Asset, signal: AbortSignal): Promise<FleetRead> {
  if (recentAsset(asset)) {
    const data = await readAssetData(asset.assetId, signal);
    const stream = [...(data.history?.streams ?? [])].sort((a, b) => Date.parse(b.endAt) - Date.parse(a.endAt))[0];
    if (stream) {
      const channel = data.history?.preferred && stream.channels.includes(data.history.preferred) ? data.history.preferred : stream.channels[0];
      const read = await readObservation(asset.assetId, stream, channel, {range: "1h", window: null, snapshot: null, reference: null, anchor: "now"}, signal);
      const group = groupHistory(read.trend).sort((a, b) => Date.parse(b.buckets.at(-1)?.lastEventAt ?? "") - Date.parse(a.buckets.at(-1)?.lastEventAt ?? ""))[0];
      const reference = read.reference?.groups.find(row => row.interpretationId === group?.interpretationId);
      const step = (read.trend.bucketSeconds ?? 60) * 1000;
      const points = (group?.buckets ?? []).flatMap((bucket, index, all) => bucket.mean === null ? [] : [{x: Date.parse(bucket.bucketStart), value: bucket.mean,
        join: index > 0 && all[index - 1].mean !== null && Date.parse(bucket.bucketStart) - Date.parse(all[index - 1].bucketStart) <= step + 1}]);
      const url = new URL(routeUrl({page: "monitor", assetId: asset.assetId, tab: "summary", method: null, data: null}), "http://local");
      url.searchParams.set("observation_view", "recent");
      url.searchParams.set("monitor_source", stream.sourceId);
      url.searchParams.set("monitor_point", stream.pointId ?? "");
      url.searchParams.set("observation_channel", channel);
      return {live: true, href: url.pathname + url.search,
        group: {label: channel, unit: group?.unit ?? null, axis: "time", focus: channel, bucketMs: step, periodSeconds: null,
          record: {from: Date.parse(read.trend.startAt), to: Date.parse(read.trend.endAt)},
          series: [{key: channel, label: channel, short: channel, points}]},
        changes: (reference?.intervals ?? []).map(row => ({key: channel, label: channel, from: row.from, to: row.to,
          up: row.up, before: reference?.median ?? null, after: row.value}))};
    }
  }
  const body = await json("/api/v1/explore/overview?" + new URLSearchParams({asset_id: asset.assetId}), signal);
  if (body.asset_id !== asset.assetId) invalid();
  const group = parseGroup(body.group);
  const changes = group ? await readFleetChanges(asset.assetId, group, null, signal) : [];
  return {group, changes, live: false, href: investigationHref(asset.assetId, group, null)};
}

/** 묶음 신호의 선 색. 관련 신호 그래프(SignalGroupChart)와 같은 순서이며, 색 옆에 항상 상·축 이름을 함께 적는다. */
export const SERIES_COLORS = ["var(--color-action)", "#bd6017", "#557a47", "#8c5793", "#455e73"];
