/** 데이터셋 관제의 한 줄: 설비를 지켜보는 신호 묶음(같은 의미의 R·S·T상, 진동의 수평·수직)과 그 묶음에서 찾은 변화.
 * 전체 설비를 함께 관측하되 각 기록의 시각·측정 번호와 단위는 자기 그래프에서 읽는다.
 * 저장 기록은 재생할 수 있다. 재생 위치까지 끝난 구간만 그리고, 변화는 그 위치까지의 기록으로 서버가 판정한다. */
import {readAssetData} from "./asset-data.ts";
import {readChangeReviews, type ChangeCapture} from "./change-reviews.ts";
import {latestDecision, type ReviewDecision} from "./review-writes.ts";
import {episodes} from "./asset-timeline.ts";
import {groupHistory} from "./history.ts";
import {readObservation, recentAsset} from "./observation.ts";
import type {Asset} from "./monitor.ts";
import type {PublicDatasets} from "./public-datasets.ts";
import {routeUrl} from "./routes.ts";
import {object} from "./writes.ts";

export type FleetPoint = {x: number; value: number; join: boolean};
/** `channel`은 같은 데이터셋의 다른 설비에서 같은 신호를 찾는 이름이다(전력: 채널 이름, 진동: 특징 이름). */
export type FleetSeries = {key: string; channel: string; label: string; short: string; points: FleetPoint[]};
export type FleetGroup = {
  label: string; unit: string | null; axis: "time" | "acquisition"; focus: string;
  /** 기록의 처음과 끝(시각 ms 또는 측정 번호). 재생은 이 범위를 움직인다. */
  record: {from: number; to: number};
  /** 시간 기록의 한 점이 덮는 길이(ms). 점은 이 길이가 다 지난 뒤에만 그린다. */
  bucketMs: number | null; periodSeconds: number | null; series: FleetSeries[];
};
export type FleetChange = {key: string; channel: string; label: string; from: number; to: number; up: boolean;
  before: number | null; after: number | null;
  /** 조사 화면이 같은 변화를 고르는 열쇠(summary_change). 모니터링 중이면 그 판정 위치(record_until)의 기록에서만 맞는다. */
  ref?: string;
  /** 같은 때의 부하(전류): 비교 기준 구간과 변화 구간의 평균. */
  load?: {label: string; unit: string | null; before: number; after: number} | null;
  /** 판단·메모가 이 특이사항을 가리키는 열쇠(기간·기준이 같아야 같다). */
  reviewKey?: string};
/** 사람이 남긴 판단: 가장 최근 판단, 마지막 기록 시각, 가장 최근 메모. */
export type Judgment = {decision: ReviewDecision | null; closed: boolean; at: string; note: string | null};
/** 한 설비 칸이 읽은 것. `live`는 실제로 수신 중인 출처의 최근 관측이다(저장 기록 모니터링이 아니다). */
export type FleetRead = {group: FleetGroup | null; changes: FleetChange[]; live: boolean; href: string;
  /** 보는 신호 묶음 밖에서 찾은 변화(예: 상전류를 보는 동안 상전압의 변화). */
  others: FleetChange[];
  /** 묶음 아래 같은 시간축에 그리는 부하 신호(전류). 전압이 오른 때 부하가 어땠는지 함께 보인다. */
  companion: FleetGroup | null;
  /** 이 설비의 특이사항에 남긴 판단(reviewKey별). 읽지 못하면 비어 있다. */
  judgments?: Record<string, Judgment>};

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
    return {key: text(row.key) ?? invalid(), channel: text(row.channel) ?? text(row.key) ?? invalid(),
      label: text(row.label) ?? invalid(), short: text(row.short) ?? invalid(),
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

/** 일시적으로 읽지 못한 응답(503, 연결 끊김)은 잠시 뒤 다시 읽는다. 스택을 막 띄웠을 때 저장소가 아직 열리지 않은 경우다. */
async function json(url: string, signal: AbortSignal, tries = 5): Promise<Record<string, unknown>> {
  for (let attempt = 1; ; attempt++) {
    let response: Response | null = null;
    try { response = await fetch(url, {signal, cache: "no-store", credentials: "same-origin"}); }
    catch (cause) { if (signal.aborted || attempt >= tries) throw cause; }
    if (response?.ok) return object(await response.json() as unknown) ?? invalid();
    await response?.body?.cancel().catch(() => {});
    if (response && response.status !== 503 || attempt >= tries) throw new Error("설비 관측을 읽지 못했습니다.");
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, 1000 * 2 ** (attempt - 1));
      signal.addEventListener("abort", () => { clearTimeout(timer); reject(signal.reason); }, {once: true});
    });
  }
}

/** 설비에서 찾은 변화(서버가 고른 대표 변화). `until`이 있으면 그 위치까지의 기록만으로 판정한 결과다. */
export async function readFleetChanges(assetId: string, group: FleetGroup, until: number | null, signal: AbortSignal): Promise<FleetChange[]> {
  const query = new URLSearchParams({asset_id: assetId});
  if (group.axis === "time") {
    if (until !== null) query.set("record_until", new Date(until).toISOString());
    const body = await json("/api/v1/explore/findings?" + query, signal);
    return (Array.isArray(body.intervals) ? body.intervals : []).flatMap((raw: unknown) => {
      const row = object(raw);
      if (!row) return [];
      const load = object(row.load);
      return [{key: String(row.key), channel: String(row.channel), label: text(row.label) ?? String(row.channel), up: row.direction !== "down",
        ref: JSON.stringify(["history", String(row.key), row.start, row.end]),
        reviewKey: typeof row.review_key === "string" ? row.review_key : undefined,
        load: load && typeof load.reference === "number" && typeof load.current === "number"
          ? {label: text(load.label) ?? "부하", unit: text(load.unit), before: load.reference, after: load.current} : null,
        from: Date.parse(String(row.start)), to: Date.parse(String(row.end)),
        before: typeof row.reference_value === "number" ? row.reference_value : null,
        after: typeof row.typical_value === "number" ? row.typical_value : null}];
    }).filter(row => Number.isFinite(row.from) && Number.isFinite(row.to));
  }
  if (until !== null) query.set("acquisition_until", String(Math.floor(until)));
  const body = await json("/api/v1/explore/vibration?" + query, signal);
  return (Array.isArray(body.intervals) ? body.intervals : []).flatMap((raw: unknown) => {
    const row = object(raw);
    if (!row) return [];
    return [{key: String(row.feature), channel: String(row.feature), label: text(row.label) ?? String(row.feature), up: row.direction !== "down",
      ref: JSON.stringify(["vibration", String(row.feature), row.from, row.to]),
      reviewKey: typeof row.review_key === "string" ? row.review_key : undefined,
      from: finite(row.from), to: finite(row.to),
      before: typeof row.reference_value === "number" ? row.reference_value : null,
      after: typeof row.typical_value === "number" ? row.typical_value : null}];
  });
}

/** 보는 묶음 안의 변화와 밖의 변화. */
export function splitChanges(group: FleetGroup, found: FleetChange[]): {changes: FleetChange[]; others: FleetChange[]} {
  const keys = new Set(group.series.map(row => row.key));
  return {changes: found.filter(row => keys.has(row.key)), others: found.filter(row => !keys.has(row.key))};
}

/** 설비 조사 화면 주소. 재생 중이면 그 위치까지의 기록으로 연다. */
export function investigationHref(assetId: string, group: FleetGroup | null, until: number | null, change?: FleetChange): string {
  const url = new URL(routeUrl({page: "monitor", assetId, tab: "summary", method: null, data: null}), "http://local");
  url.searchParams.set("observation_view", "record");
  if (change?.ref) url.searchParams.set("summary_change", change.ref);
  if (group && until !== null)
    url.searchParams.set(group.axis === "time" ? "record_until" : "acquisition_until",
      group.axis === "time" ? new Date(until).toISOString() : String(Math.floor(until)));
  return url.pathname + url.search;
}

/** 실제로 수신 중인 출처는 최근 1시간 관측(앞선 관측과 비교한 변화 포함), 그 밖에는 저장 기록 전체를 읽는다. */
export async function readFleet(asset: Asset, signal: AbortSignal, like: string | null = null): Promise<FleetRead> {
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
          series: [{key: channel, channel, label: channel, short: channel, points}]},
        changes: (reference?.intervals ?? []).map(row => ({key: channel, channel, label: channel, from: row.from, to: row.to,
          up: row.up, before: reference?.median ?? null, after: row.value})), others: [], companion: null};
    }
  }
  const query = new URLSearchParams({asset_id: asset.assetId});
  if (like) query.set("like", like);
  const body = await json("/api/v1/explore/overview?" + query, signal);
  if (body.asset_id !== asset.assetId) invalid();
  const group = parseGroup(body.group);
  const split = group ? splitChanges(group, await readFleetChanges(asset.assetId, group, null, signal)) : {changes: [], others: []};
  return {group, ...split, live: false, href: investigationHref(asset.assetId, group, null), companion: parseGroup(body.companion),
    judgments: await readJudgments(asset.assetId, signal)};
}

/** 저장한 검토를 특이사항 열쇠별 판단으로: 가장 최근 판단, 마지막 기록 시각, 가장 최근 메모. */
export function judgmentsOf(captures: ChangeCapture[]): Record<string, Judgment> {
  return Object.fromEntries(captures.filter(capture => capture.finding.reviewKey).map(capture => {
    const events = capture.review.events;
    return [capture.finding.reviewKey!, {decision: latestDecision(events), closed: capture.review.status === "closed",
      at: events.at(-1)?.recordedAt ?? capture.capturedAt, note: [...events].reverse().find(event => event.note.trim())?.note.trim() ?? null}];
  }));
}
/** 설비의 특이사항마다 남긴 판단(최근 20건). 판단을 읽지 못해도 관측은 그대로 보인다. */
export async function readJudgments(assetId: string, signal: AbortSignal): Promise<Record<string, Judgment>> {
  try {
    return judgmentsOf((await readChangeReviews(assetId, signal)).captures);
  } catch (error) {
    if (signal.aborted) throw error;
    return {};
  }
}

/** 묶음 신호의 선 색(디자인 토큰). 색 옆에 항상 상·축 이름을 함께 적는다. */
export const SERIES_COLORS = ["var(--color-series-1)", "var(--color-series-2)", "var(--color-series-3)", "var(--color-series-4)"];

/** 관제 화면의 데이터셋: 같은 출처에서 온 설비들. 공개 데이터는 데이터셋 종류로, 나머지는 '연결한 데이터'로 묶는다. */
export type MonitorDataset = {key: string; title: string; assetIds: string[]; detail: Record<string, string>};
const DATASET_TITLE: Record<string, string> = {"aihub-239": "AI-Hub 239 전력 기록", "xjtu-sy": "XJTU-SY 베어링 진동 기록", connected: "연결한 데이터"};
export function monitorDatasets(assets: Asset[], data: PublicDatasets | null): MonitorDataset[] {
  const imported = new Map(Object.entries(data?.jobs ?? {}).map(([id, job]) => [job.assetId, id]));
  const out = new Map<string, MonitorDataset>();
  for (const asset of assets) {
    const job = imported.get(asset.assetId);
    const item = data?.items.find(row => row.datasetId === job) ?? data?.items.find(row => row.assetId === asset.assetId);
    const key = item?.kind ?? (job?.startsWith("xjtu-sy:") ? "xjtu-sy" : job?.startsWith("aihub239:") ? "aihub-239" : "connected");
    const dataset = out.get(key) ?? {key, title: DATASET_TITLE[key], assetIds: [], detail: {}};
    dataset.assetIds.push(asset.assetId);
    if (item?.kind === "xjtu-sy" && item.speedHz !== null && item.loadKn !== null) dataset.detail[asset.assetId] = item.speedHz + " Hz · " + item.loadKn + " kN";
    else if (item?.equipment) dataset.detail[asset.assetId] = item.equipment;
    out.set(key, dataset);
  }
  return [...out.values()].sort((a, b) => Object.keys(DATASET_TITLE).indexOf(a.key) - Object.keys(DATASET_TITLE).indexOf(b.key));
}

/** 같은 축에서 비교할 수 있는 범위. 측정 번호로 세는 시험 기록은 모두 시작부터 맞춰지므로 길이만 비슷하면 되고
 * (어느 기록도 가장 긴 것의 1/5보다 짧지 않을 것), 시각 기록은 기간이 실제로 겹쳐야 한다(가장 짧은 기록의 절반 이상).
 * 서로 다른 시기의 기록을 한 달력에 놓으면 설비마다 화면 일부에만 그려지고 비교할 것도 없다. */
export function sharedSpan(groups: FleetGroup[]): {from: number; to: number} | null {
  if (groups.length < 2 || groups.some(group => group.axis !== groups[0].axis)) return null;
  const from = Math.min(...groups.map(group => group.record.from)), to = Math.max(...groups.map(group => group.record.to));
  const lengths = groups.map(group => group.record.to - group.record.from);
  if (!(to > from) || lengths.some(length => length < (to - from) * 0.2)) return null;
  const overlap = Math.min(...groups.map(group => group.record.to)) - Math.max(...groups.map(group => group.record.from));
  return groups[0].axis === "acquisition" || overlap >= Math.min(...lengths) * 0.5 ? {from, to} : null;
}

/** 재생 위치: 같은 축이면 하나의 시계(시각 또는 측정 번호), 아니면 기록마다 같은 비율. 기록 시작 전이면 null. */
export function untilAt(group: FleetGroup, fraction: number, shared: {from: number; to: number} | null): number | null {
  if (!shared) return positionAt(group, fraction);
  const clock = shared.from + (shared.to - shared.from) * Math.max(0, Math.min(1, fraction));
  if (clock < group.record.from) return null;
  const at = Math.min(group.record.to, clock);
  return group.axis === "acquisition" ? Math.floor(at) : at;
}

/** 줄 순서: 마지막 측정까지 이어지는 변화 → 끝난 변화(최근 것부터) → 변화 없음 → 읽지 못함. */
export function attention(read: FleetRead | null): [number, number] {
  const group = read?.group;
  if (!group) return [3, 0];
  const lead = latestEpisode(read.changes)[0];
  if (!lead) return [2, 0];
  return [ongoing(group, read.changes) ? 0 : 1, -Math.max(...latestEpisode(read.changes).map(row => row.from))];
}

/** 마지막 시기의 변화가 기록(또는 재생 위치) 끝까지 이어지는지. 한 점 길이만큼은 끝으로 본다. */
export function ongoing(group: FleetGroup, changes: FleetChange[], until = group.record.to): boolean {
  const slack = group.axis === "time" ? (group.bucketMs ?? 60_000) * 1.5 : 1;
  return latestEpisode(changes).some(row => row.to >= until - slack);
}

/** 묶음의 중심 신호 이름(같은 데이터셋의 다른 설비에 같은 묶음을 요청할 때 쓴다). */
export function focusChannel(group: FleetGroup): string {
  return group.series.find(row => row.key === group.focus)?.channel ?? group.series[0].channel;
}
