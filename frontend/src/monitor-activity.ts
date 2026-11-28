import {measure} from "./chart-axis.ts";
import type {ChangeFollowup} from "./change-evidence.ts";
import type {Pointed} from "./change-investigation.ts";
import {plainLabel} from "./change-story.ts";
import {clockText, spanText} from "./date-format.ts";
import {investigationHref, latestEpisode, type FleetChange, type FleetGroup, type FleetRead} from "./fleet-observation.ts";
import {assetOptionLabel, attentionLabel, type Asset, type Snapshot} from "./monitor.ts";
import type {PlaybackScope} from "./record-playback.ts";
import {DECISION_LABEL} from "./review-writes.ts";
import {investigationOriginUrl, routeUrl, systemUrl} from "./routes.ts";

export type MonitorQuestion = {
  assetId: string; name: string; signal: string; range: string; origin: string; reviewKey: string; scope: PlaybackScope | null;
  followup: ChangeFollowup | null; analyses: Record<string, ChangeFollowup>;
  savedJudgment: {label: string; note: string | null} | null; compareLoad?: boolean;
};
export type MonitorChatPoint = {point: Pointed; clear: () => void};
type Activity = {id: string; name: string; title: string; detail: string; href: string};
export type ChangeActivity = Activity & {kind: "change"; assetId: string; change: FleetChange; question: MonitorQuestion | null};
export type MonitorActivity = ChangeActivity | (Activity & {kind: "alert" | "analysis"});

/** The activity and the graph use the same visible representative change. */
export function monitorLead(group: FleetGroup, changes: FleetChange[], until: number | null): FleetChange | null {
  if (until === null) return null;
  const visible = changes.filter(change => change.from <= until);
  const episode = group.axis === "time" ? latestEpisode(visible) : [];
  const lead = group.axis === "time" ? episode.find(change => change.key === group.focus) ?? episode[0] : visible[0];
  return lead ? {...lead, to: Math.min(lead.to, until)} : null;
}

export function changeRange(change: FleetChange, axis: FleetGroup["axis"]): string {
  if (axis === "time") return change.from === change.to ? clockText(change.from) : spanText(change.from, change.to);
  return (change.from === change.to ? change.from : `${change.from}–${change.to}`) + "번째 측정";
}

export function changeActivity(assetId: string, name: string, read: FleetRead, group: FleetGroup, change: FleetChange,
  scope: PlaybackScope | null, origin: string): ChangeActivity {
  const href = read.live ? change.href ?? read.href : investigationHref(assetId, group, scope?.until ?? null, change);
  const title = plainLabel(change.label, change.channel);
  const range = changeRange(change, group.axis);
  const before = change.current?.reference ?? change.before, after = change.current?.value ?? change.after;
  const value = before !== null && after !== null ? `${measure(before, group.unit, 3)} → ${measure(after, group.unit, 3)}` : "";
  const withOrigin = (link: ChangeFollowup) => ({...link, href: investigationOriginUrl(link.href, new URL(href, origin).href)});
  const judged = change.reviewKey ? read.judgments?.[change.reviewKey] : null;
  return {kind: "change", assetId, name, id: JSON.stringify([assetId, change.ref ?? change.key, change.from, change.to]),
    // 언제부터 언제까지인지만 적는다. 저장·재생·관측 같은 출처 꼬리표는 사람이 판단할 일을 바꾸지 않는다.
    title: value ? `${title} · ${value}` : title, detail: range,
    href, change, question: change.reviewKey && !read.live ? {
      assetId, name, signal: title, range, origin: href, reviewKey: change.reviewKey, scope,
      followup: change.followup ? withOrigin(change.followup) : null,
      analyses: Object.fromEntries(Object.entries(change.analyses ?? {}).map(([key, link]) => [key, withOrigin(link)])),
      savedJudgment: judged ? {label: judged.closed ? "검토 종료" : judged.decision ? DECISION_LABEL[judged.decision] : "확인함", note: judged.note} : null,
      compareLoad: change.compareLoad,
    } : null};
}

const RECEIPT_ALERTS = new Set(["source-connection-lost", "source-no-new-data", "source-delayed", "source-flow-error", "collection-worker-error"]);

export function monitorActivities(snapshot: Pick<Snapshot, "assessedAt" | "operationsAttention" | "analyses">,
  assets: Asset[], changes: ChangeActivity[], replaying: boolean): MonitorActivity[] {
  const active = new Map(assets.map(asset => [asset.assetId, asset]));
  const alerts = new Map<string, MonitorActivity>();
  for (const item of snapshot.operationsAttention?.items ?? []) {
    const asset = item.assetId ? active.get(item.assetId) : null;
    if (!asset || asset.flow === "stored-history" || !item.code || !RECEIPT_ALERTS.has(item.code)) continue;
    // The feed is a view of current issues. Repeated reads don't create new events.
    const id = JSON.stringify([item.assetId, item.sourceId]);
    if (alerts.has(id)) continue;
    alerts.set(id, {id: item.id, kind: "alert", name: assetOptionLabel(assets, asset.assetId), title: attentionLabel(item),
      detail: asset.lastReceivedAt ? "마지막 수신 " + clockText(asset.lastReceivedAt) : "연결 상태 확인",
      href: systemUrl(item.destination === "system" ? "status" : "connections")});
  }
  const completed = new Map<string, MonitorActivity>();
  const assessedAt = Date.parse(snapshot.assessedAt ?? "");
  // Completion time is a wall-clock event. It has no position in stored-record playback.
  if (!replaying && snapshot.analyses.available && Number.isFinite(assessedAt)) {
    for (const item of snapshot.analyses.records) {
      const at = Date.parse(item.completedAt ?? "");
      if (!active.has(item.assetId) || completed.has(item.assetId) || !Number.isFinite(at) || at > assessedAt || assessedAt - at > 86_400_000) continue;
      const href = routeUrl({page: "investigations", assetId: item.assetId, tab: "summary", method: null, data: null})
        + "#" + encodeURIComponent("record-" + item.evidenceId);
      completed.set(item.assetId, {id: JSON.stringify([item.runId, item.evidenceId]), kind: "analysis", name: assetOptionLabel(assets, item.assetId),
        title: item.kind === "phase" ? "3상 분석 결과 저장" : "측정 파일 분석 결과 저장", detail: clockText(at), href});
    }
  }
  return [...alerts.values(), ...changes, ...completed.values()];
}
