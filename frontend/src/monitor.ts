import {parseAnalysisRecords,type AnalysisRecords} from "./analysis-records.ts";
import {parseReviewInbox,type ReviewInbox} from "./reviews.ts";
// The server owns observation values and PHM meaning. This preview only renders
// validated fields from the existing read-only monitor API.
export type Asset = {
  assetId: string;
  displayName?: string | null;
  flow: string;
  /** Event time of the newest stored measurement. */
  lastObservedAt: string | null;
  /** When data last arrived (a file read or a live receipt); a different clock. */
  lastReceivedAt: string | null;
  attentionCount: number | null;
  /** Delivery order of the newest waveform, for streams that carry no measurement clock. */
  lastPosition?: number | null;
};

export type OperationAttention={id:string;title:string;code:string|null;status:string;destination:string;assetId:string|null;sourceId:string|null;findingId:string|null;at:string|null};
export type Snapshot = {
  operationsAttention?: {items:OperationAttention[];complete:boolean};
  assessedAt: string | null;
  assets: Asset[];
  truncated: boolean;
  systemReadUncertain: boolean;
  /** Store areas the server could not read this time; never shown as empty. */
  errorScopes: string[];
  reviewInbox: ReviewInbox;
  analyses: AnalysisRecords;
};

/** The same receive-state words as the current /web/ monitor; never a health verdict. */
const FLOW_LABELS: Record<string, string> = {
  running: "수신 중", waiting: "수신 대기", delayed: "수신 지연", stopped: "수집 중지",
  "needs-attention": "수신 확인 필요", error: "수신 오류", unavailable: "수신 상태 미확인",
  "stored-history": "저장된 기록",
};
export function flowLabel(flow: string): string {
  return FLOW_LABELS[flow] ?? "수신 상태 미확인";
}

/** Names are presentation only; links, filters and evidence keep the stable ID. */
export function assetLabel(assets: readonly Asset[], assetId: string): string {
  return assets.find(asset => asset.assetId === assetId)?.displayName || assetId;
}

export function assetOptionLabel(assets: readonly Asset[], assetId: string): string {
  const label = assetLabel(assets, assetId);
  return assets.filter(asset => assetLabel(assets, asset.assetId) === label).length > 1
    ? label + " · " + assetId : label;
}

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

/** A malformed analysis list is reported as unreadable; it never blocks the asset list. */
function analysesOf(response: Record<string, unknown>): AnalysisRecords {
  try {
    return parseAnalysisRecords(response);
  } catch {
    return {available: false, records: [], truncated: true, skipped: [], skippedComplete: false};
  }
}

/** Stable application-projected attention codes, not English display copy. */
const ATTENTION_TEXT: Record<string, string> = {
  "collection-service-heartbeat-unavailable": "데이터 수집 서비스 상태를 확인하지 못함",
  "collection-service-error": "데이터 수집 서비스가 오류로 멈춤",
  "collection-service-stopped": "데이터 수집 서비스 중지됨",
  "collection-service-not-running": "데이터 수집 서비스가 실행되지 않음",
  "source-connection-lost": "데이터 연결 끊김",
  "source-no-new-data": "새 측정이 들어오지 않음",
  "collection-worker-error": "데이터 수집 확인 필요",
  "history-writer-error": "측정 이력 저장 확인 필요",
  "analysis-input-error": "분석 입력 준비 확인 필요",
  "analysis-service-error": "분석 실행기가 오류로 멈춤",
  "analysis-service-delayed": "분석 실행기 응답 지연",
  "source-delayed": "데이터 수신 지연",
  "review-waiting": "검토 대기",
  "review-in-progress": "검토 진행 중",
  "data-quality-review": "데이터 품질 확인 필요",
  "system-unavailable": "시스템 상태를 확인하지 못함",
  "source-flow-error": "데이터 수신 오류",
  "source-waiting": "첫 데이터 대기",
};
const DESTINATION_TEXT: Record<string, string> = {
  system: "운영 서비스 확인 필요", "asset-signals": "데이터 확인 필요", investigations: "분석 결과 확인 필요",
};
export function attentionLabel(item: OperationAttention): string {
  return (item.code ? ATTENTION_TEXT[item.code] : null) ?? DESTINATION_TEXT[item.destination] ?? "확인 필요";
}

function attentionOf(raw:unknown):{items:OperationAttention[];complete:boolean} {
  const list=object(raw);
  if(!list||!Array.isArray(list.items)||list.items.length>100)return {items:[],complete:false};
  try {
    const id=(v:unknown)=>{if(typeof v!=="string"||!v||v.length>512)throw new Error("invalid attention");return v;};
    const optional=(v:unknown)=>v===null?null:id(v);
    const items=list.items.map((value:unknown)=>{const v=object(value);if(!v)throw new Error("invalid attention");
      return {id:id(v.attention_id),title:id(v.title),code:v.code===undefined?null:optional(v.code),
        status:id(v.status),destination:id(v.destination),assetId:optional(v.asset_id),
        sourceId:optional(v.source_id),findingId:optional(v.finding_id),at:optional(v.occurred_at)};});
    if(new Set(items.map(item=>item.id)).size!==items.length)throw new Error("duplicate attention");
    return {items,complete:list.truncated===false};
  }catch{return {items:[],complete:false};}
}

export function parseMonitor(value: unknown): Snapshot {
  const response = object(value);
  const assetGroup = object(response?.assets);
  if (!response || !assetGroup || !Array.isArray(assetGroup.items)) {
    throw new Error("관측 응답의 형식을 확인할 수 없습니다.");
  }
  const assets: Asset[] = [];
  for (const entry of assetGroup.items) {
    const row = object(entry);
    if (!row || typeof row.asset_id !== "string" || !row.asset_id) {
      throw new Error("설비 식별자가 올바르지 않습니다.");
    }
    assets.push({
      assetId: row.asset_id,
      displayName: typeof row.asset_display_name === "string" && row.asset_display_name.trim()
        ? row.asset_display_name : null,
      flow: typeof row.data_flow_status === "string" ? row.data_flow_status : "미확인",
      lastObservedAt: typeof row.last_observed_at === "string" ? row.last_observed_at : null,
      lastReceivedAt: typeof row.last_data_at === "string" ? row.last_data_at : null,
      attentionCount: count(row.attention_count),
      lastPosition: typeof row.last_position === "number" && Number.isSafeInteger(row.last_position) ? row.last_position : null,
    });
  }
  return {
    operationsAttention:attentionOf(response.attention),
    assessedAt: typeof response.assessed_at === "string" ? response.assessed_at : null,
    assets,
    truncated: assetGroup.truncated === true,
    systemReadUncertain: !Array.isArray(response.system_error_scopes) || response.system_error_scopes.length > 0,
    errorScopes: Array.isArray(response.system_error_scopes)
      ? response.system_error_scopes.filter((scope): scope is string => typeof scope === "string") : [],
    reviewInbox: parseReviewInbox(response),
    analyses: analysesOf(response),
  };
}

export async function readMonitor(signal: AbortSignal): Promise<Snapshot> {
  const response = await fetch("/api/v1/monitor", { signal, cache: "no-store" });
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("서버에서 관측 정보를 확인하지 못했습니다.");
  }
  return parseMonitor(await response.json() as unknown);
}
