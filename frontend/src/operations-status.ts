/** Local service readiness and registered data connections, read only. Process heartbeats
 * are not sensor receipt, and registration is not receipt or a live connection. */
import {object} from "./review-writes.ts";

export type Condition="running"|"not-ready"|"stale"|"stopped"|"failed"|"unavailable";
export type Component={kind:"collection"|"analysis"|"ui";condition:Condition;pid:number|null;
  runtimeState:string|null;heartbeatAt:string|null};
export type RuntimeStatus={assessedAt:string|null;ready:boolean;supervisor:{condition:Condition;pid:number|null;
  heartbeatAt:string|null};components:Component[]};
export type HistoryJob={state:string;startedAt:string|null;finishedAt:string|null;
  eventCount:number|null;snapshotId:number|null;failure:string|null};
export type Source={
  sourceId:string;name:string;type:"file"|"opcua";assetId:string;pointId:string|null;
  lifecycle:string|null;receiptConfirmed:boolean;lastAcceptedAt:string|null;lastObservedAt:string|null;
  phaseBindings:number;
  live:{receivedAt:string|null;fresh:boolean;session:string|null;desired:string|null;
    historyCommittedAt:string|null}|null;
  job:HistoryJob|null;readError:boolean;
};
export type Sources={assessedAt:string|null;items:Source[];truncated:boolean;readErrors:string[];liveErrors:string[]};

export const CONDITION:Record<Condition,string>={
  running:"실행 중",
  "not-ready":"실행 중 · 준비 확인 안 됨",
  stale:"응답 신호가 오래됨",
  stopped:"중지됨",
  failed:"실패 · 로그 확인 필요",
  unavailable:"상태 미확인",
};
export const COMPONENT={collection:"데이터 수집기",analysis:"분석 실행기",ui:"Web 화면"};

function invalid(what:string):never{
  throw new Error(what+"의 형식이 올바르지 않습니다.");
}
function text(raw:unknown,what:string):string{
  if(typeof raw!=="string"||!raw||raw.length>512)invalid(what);
  return raw;
}
function optional(raw:unknown):string|null{
  return typeof raw==="string"&&raw?raw:null;
}
function instant(raw:unknown):string|null{
  return typeof raw==="string"&&Number.isFinite(Date.parse(raw))?raw:null;
}
function count(raw:unknown):number|null{
  return typeof raw==="number"&&Number.isSafeInteger(raw)&&raw>=0?raw:null;
}
function pid(raw:unknown):number|null{
  return typeof raw==="number"&&Number.isSafeInteger(raw)&&raw>0?raw:null;
}
function condition(raw:unknown):Condition{
  if(typeof raw!=="string"||!(raw in CONDITION))invalid("실행 상태");
  return raw as Condition;
}

export function parseRuntimeStatus(raw:unknown):RuntimeStatus{
  const root=object(raw);
  const supervisor=object(root?.supervisor);
  if(!root||root.meaning!=="local-process-readiness-not-collection-receipt-or-asset-health"
    ||typeof root.ready!=="boolean"||!supervisor||!Array.isArray(root.components)||root.components.length!==3)
    invalid("실행 상태");
  return {assessedAt:instant(root.assessed_at),ready:root.ready,
    supervisor:{condition:condition(supervisor.condition),pid:pid(supervisor.pid),heartbeatAt:instant(supervisor.heartbeat_at)},
    components:root.components.map((item:unknown):Component=>{
      const row=object(item);
      if(!row||!["collection","analysis","ui"].includes(String(row.kind)))invalid("실행 구성 요소");
      return {kind:row.kind as Component["kind"],condition:condition(row.condition),pid:pid(row.pid),
        runtimeState:optional(row.runtime_state),heartbeatAt:instant(row.heartbeat_at)};
    })};
}

export function parseSources(raw:unknown):Sources{
  const root=object(raw);
  const group=object(root?.sources);
  if(!root||root.meaning!=="registration-does-not-imply-accepted-receipt-or-live-connection"
    ||!group||!Array.isArray(group.items)||typeof group.truncated!=="boolean")
    invalid("데이터 연결 목록");
  const scopes=(value:unknown)=>Array.isArray(value)?value.filter((x):x is string=>typeof x==="string"):[];
  return {assessedAt:instant(root.assessed_at),truncated:group.truncated,
    readErrors:scopes(root.read_error_scopes),liveErrors:scopes(root.live_evidence_error_scopes),
    items:group.items.map((item:unknown):Source=>{
      const row=object(item);
      if(!row||(row.source_type!=="file"&&row.source_type!=="opcua"))invalid("데이터 연결");
      const job=object(row.file_history_job);
      return {sourceId:text(row.source_id,"데이터 연결 ID"),name:text(row.name,"데이터 연결 이름"),
        type:row.source_type,assetId:text(row.asset_id,"설비"),pointId:optional(row.measurement_point_id),
        lifecycle:optional(row.lifecycle_state),receiptConfirmed:row.receipt_confirmed===true,
        lastAcceptedAt:instant(row.last_accepted_received_at),lastObservedAt:instant(row.last_accepted_observed_at),
        live:row.source_type==="opcua"?{receivedAt:instant(row.last_live_received_at),
          fresh:row.last_live_receive_fresh===true,session:optional(row.opcua_session_last_state),
          desired:optional(row.collection_desired_state),
          historyCommittedAt:instant(row.last_live_history_committed_at)}:null,
        phaseBindings:typeof row.phase_binding_count==="number"&&Number.isSafeInteger(row.phase_binding_count)
          ?row.phase_binding_count:0,
        job:job&&typeof job.state==="string"?{state:job.state,startedAt:instant(job.started_at),
          finishedAt:instant(job.finished_at),eventCount:count(job.event_count),
          snapshotId:count(job.history_snapshot_id),failure:optional(job.failure)}:null,
        readError:row.live_telemetry_read_error===true};
    })};
}

/** The same receipt words as the current /web/ connection cards; none claims more. */
export function receiptText(source:Source):string{
  if(source.readError)return "수신 상태 조회 실패";
  if(source.live){
    if(source.live.session&&source.live.session.toUpperCase()!=="CONNECTED")return "현재 연결 미확인";
    if(source.live.fresh)return "수신 확인됨";
    if(source.live.receivedAt)return "최근 수신 미확인";
    return source.receiptConfirmed?"1회 수신 확인 · 연속 수신 미확인":"수신 미확인";
  }
  return source.receiptConfirmed?"파일 읽기 확인됨":"파일 확인 대기";
}

export const LIFECYCLE:Record<string,string>={registered:"등록됨 · 사용 전",active:"사용 중",paused:"일시정지",error:"오류"};
export const JOB:Record<string,string>={running:"측정 이력 저장 중",succeeded:"측정 이력 저장됨",
  failed:"측정 이력 저장 실패",interrupted:"측정 이력 저장 중단"};

async function read(url:string,signal:AbortSignal):Promise<unknown>{
  const response=await fetch(url,{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error("상태를 읽지 못했습니다. 문제가 없다는 뜻도, 멈췄다는 뜻도 아닙니다.");
  }
  return await response.json() as unknown;
}
export async function readRuntimeStatus(signal:AbortSignal):Promise<RuntimeStatus>{
  return parseRuntimeStatus(await read("/api/v1/system/runtime",signal));
}
export async function readSources(signal:AbortSignal):Promise<Sources>{
  return parseSources(await read("/api/v1/sources",signal));
}

const named = {at: 0, names: null as Promise<Map<string, string>> | null};
/** Registered connection names by source ID, shared briefly by the screens that show a source. */
export function readSourceNames(): Promise<Map<string, string>> {
  if (named.names && Date.now() - named.at < 30_000) return named.names;
  named.at = Date.now();
  named.names = readSources(new AbortController().signal)
    .then((sources) => new Map(sources.items.map((item) => [item.sourceId, item.name])))
    .catch(() => new Map<string, string>());
  return named.names;
}
/** A source as people know it: its registered connection name, else its ID. */
export function sourceLabel(names: Map<string, string> | null | undefined, id: string): string {
  return names?.get(id) ?? id;
}
