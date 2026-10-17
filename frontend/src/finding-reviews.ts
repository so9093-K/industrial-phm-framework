/** Explicitly requested human reviews of one asset's stored analysis and model results.
 * The server owns the subject, its status and its history; a model result names where
 * it is stored so the screen can open exactly that result. */
import {assetTabUrl} from "./routes.ts";
import {
  nextReviewStatus,object,postReviewWrite,reviewNote,OutcomeUnknown,REQUEST_ID,
  type ReviewAction,type ReviewEvent,type ReviewStatus,
} from "./review-writes.ts";

export type ModelLocation={bindingId:string;position:number};
export type FindingReview={
  findingId:string;assetId:string;subject:"analysis"|"model";runId:string;evidenceIds:string[];
  capabilityId:string;pointId:string|null;observedAt:string;status:ReviewStatus;
  model:ModelLocation|null;events:ReviewEvent[];eventsTotal:number;
};
export type FindingReviewPage={items:FindingReview[];total:number;truncated:boolean};

const EVENT_PREFIX="finding-review-event-";
const MEANING="human-review-records-not-maintenance-or-diagnosis";
const ACTION_MEANING="human-review-disposition-not-maintenance-execution";
const STATUSES:readonly ReviewStatus[]=["open","acknowledged","closed"];

function invalid(what:string):never{
  throw new Error("검토 목록의 "+what+" 형식이 올바르지 않습니다.");
}
function id(raw:unknown,what:string):string{
  if(typeof raw!=="string"||!raw||raw.length>512||/[\x00-\x1f]/.test(raw))invalid(what);
  return raw;
}
function instant(raw:unknown,what:string):string{
  const value=id(raw,what);
  if(!/(?:Z|[+-]\d\d:\d\d)$/.test(value)||!Number.isFinite(Date.parse(value)))invalid(what);
  return value;
}
function count(raw:unknown,what:string):number{
  if(typeof raw!=="number"||!Number.isSafeInteger(raw)||raw<0)invalid(what);
  return raw;
}
function event(raw:unknown):ReviewEvent{
  const row=object(raw);
  if(!row||!["note","acknowledge","close"].includes(String(row.action))
    ||typeof row.note!=="string"||row.note.length>1000)invalid("검토 기록");
  const eventId=id(row.event_id,"검토 기록 식별자");
  if(!eventId.startsWith(EVENT_PREFIX)||!REQUEST_ID.test(eventId.slice(EVENT_PREFIX.length)))
    invalid("검토 기록 식별자");
  return {eventId,action:row.action as ReviewAction,note:row.note,recordedAt:instant(row.recorded_at,"검토 시각")};
}
function review(raw:unknown,assetId:string):FindingReview{
  const row=object(raw);
  if(!row||!["analysis","model"].includes(String(row.subject))
    ||!STATUSES.includes(row.status as ReviewStatus)||!Array.isArray(row.evidence_ids)
    ||!row.evidence_ids.length||row.evidence_ids.length>64||!Array.isArray(row.events)
    ||row.events.length>50)invalid("검토 항목");
  const subject=row.subject as FindingReview["subject"];
  const evidenceIds=row.evidence_ids.map((item:unknown)=>id(item,"분석 근거"));
  if(new Set(evidenceIds).size!==evidenceIds.length)invalid("분석 근거");
  let model:ModelLocation|null=null;
  if(row.model!==null){
    const location=object(row.model);
    if(subject!=="model"||!location||typeof location.position!=="number"
      ||!Number.isSafeInteger(location.position)||location.position<1)invalid("모델 결과 위치");
    model={bindingId:id(location.binding_id,"적용 모델"),position:location.position};
  }
  const events=row.events.map(event);
  if(new Set(events.map(item=>item.eventId)).size!==events.length)invalid("검토 기록 식별자");
  const eventsTotal=count(row.events_total,"검토 기록 수");
  const status=row.status as ReviewStatus;
  if(eventsTotal<events.length)invalid("검토 기록 수");
  // A complete history must produce the status it is shown with.
  if(eventsTotal===events.length){
    let replayed:ReviewStatus="open";
    for(const item of events)replayed=nextReviewStatus(replayed,item.action);
    if(replayed!==status)throw new Error("검토 상태와 저장된 검토 기록이 일치하지 않습니다.");
  }
  return {findingId:id(row.finding_id,"검토 항목 식별자"),assetId,subject,
    runId:id(row.analysis_run_id,"분석 실행"),evidenceIds,
    capabilityId:id(row.capability_id,"분석 종류"),
    pointId:row.measurement_point_id===null?null:id(row.measurement_point_id,"측정 위치"),
    observedAt:instant(row.observed_at,"분석 대상 시각"),status,model,events,eventsTotal};
}

export function parseFindingReviews(raw:unknown,assetId:string):FindingReviewPage{
  const root=object(raw);
  const reviews=object(root?.reviews);
  if(!root||root.schema_version!==1||root.asset_id!==assetId||root.meaning!==MEANING
    ||!reviews||!Array.isArray(reviews.items)||reviews.items.length>100
    ||typeof reviews.truncated!=="boolean")
    throw new Error("다른 설비의 검토 목록이 돌아왔거나 형식이 올바르지 않습니다.");
  const items=reviews.items.map((item:unknown)=>review(item,assetId));
  if(new Set(items.map(item=>item.findingId)).size!==items.length)invalid("검토 항목 식별자");
  const total=count(reviews.total,"검토 항목 수");
  if(total<items.length||reviews.truncated!==(total>items.length))invalid("검토 항목 수");
  return {items,total,truncated:reviews.truncated};
}

export async function readFindingReviews(assetId:string,signal:AbortSignal):Promise<FindingReviewPage>{
  const response=await fetch("/api/v1/reviews?"+new URLSearchParams({asset_id:assetId}),
    {signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error("분석 결과 검토 목록을 불러오지 못했습니다. 기록이 없다는 뜻은 아닙니다.");
  }
  return parseFindingReviews(await response.json() as unknown,assetId);
}

/** The caller reuses `eventId` while retrying one uncertain action, so a retry can never
 * append a second note or status change. */
export async function recordFindingAction(
  item:FindingReview,action:ReviewAction,note:string,eventId:string,signal:AbortSignal,
):Promise<ReviewStatus>{
  if(!REQUEST_ID.test(eventId))throw new Error("검토 기록 식별자가 올바르지 않습니다.");
  const result=await postReviewWrite("/api/v1/reviews/action",{
    finding_id:item.findingId,action,note:reviewNote(action,note),event_id:eventId,
  },signal);
  if(result.finding_id!==item.findingId||result.event_id!==EVENT_PREFIX+eventId
    ||result.action!==action||!STATUSES.includes(result.status as ReviewStatus)
    ||result.meaning!==ACTION_MEANING)
    throw new OutcomeUnknown("검토 기록 응답의 대상이 요청과 다릅니다. 검토 기록을 확인하세요.");
  return result.status as ReviewStatus;
}

export function findingUrl(assetId:string,findingId:string):string{
  return "/web/?"+new URLSearchParams({page:"maintenance",monitor_asset:assetId,finding_id:findingId});
}

/** The anomaly tab opens exactly this stored model result. */
export function modelResultUrl(assetId:string,model:ModelLocation):string{
  const url=new URL(assetTabUrl(assetId,"anomaly","model"),"http://local");
  url.searchParams.set("model_binding",model.bindingId);
  url.searchParams.set("model_position",String(model.position));
  return url.pathname+url.search;
}
