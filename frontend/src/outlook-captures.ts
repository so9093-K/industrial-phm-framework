/** Explicitly captured outlooks and their exact human-review subject (ADR-0029).
 * The supervisor recomputes and stores every number. The browser only names the
 * selection it showed, so a saved record is never a copy of rendered values. */
import {assertCurrentVersion,type BriefingProjection} from "./outlook-briefings.ts";
import {parseOutlookSettings,type Conditions,type OutlookSettings,type Reach,type Scenario} from "./projections.ts";
import type {AcquisitionProjection,TimeBasis} from "./acquisition-outlook.ts";
import {
  nextReviewStatus,object,postReviewWrite,reviewNote,OutcomeUnknown,ReviewNotFound,
  REQUEST_ID,readDecision,type ReviewAction,type ReviewDecision,type ReviewEvent,type ReviewStatus,
} from "./review-writes.ts";

export type SourceRecheck="same_measurement_projection"|"changed"|"different_source"|"unavailable";
export type Position=string|number;
export type OutlookFacts=Omit<CapturedOutlook,"settings">&{settings:OutlookSettings|null};
export type CapturedOutlook={
  assetId:string;kind:"history"|"acquisition";series:string;sourceId:string;
  pointId:string|null;bindingId:string|null;timeBasis:TimeBasis|null;
  period:number|null;assumedPeriod:number|null;
  record:{first:Position;last:Position;points:number};
  conditions:Conditions;settings:OutlookSettings;scenarios:Scenario[];
  measurementVersion:string;dataVersion:string;sentences:string[];
};
export type Capture={
  id:string;capturedAt:string;outlook:CapturedOutlook;sourceRecheck:SourceRecheck;
  review:{status:ReviewStatus;events:ReviewEvent[]};
};
export type CapturePage={captures:Capture[];nextBefore:string|null};
export type LimitChange={name:"management"|"end";before:Reach|null;after:Reach|null};
export type Reobservation=
  |{kind:"different-subject"}
  |{kind:"changed-assumptions";changes:string[]}
  |{kind:"same-measurement";anomalyEvidenceChanged:boolean;bindingRecorded:boolean}
  |{kind:"new-observation";moved:boolean;before:Position;after:Position;
    limits:LimitChange[];bindingRecorded:boolean};

/** Nothing was saved: the supervisor's recomputation differed or could not run. */
export class CaptureRejected extends Error {}
export class CaptureNotFound extends ReviewNotFound {}

const CAPTURE_ID=/^outlook-capture-[0-9a-f]{64}$/;
const VERSION=/^[0-9a-f]{64}$/;
const RECHECKS:readonly SourceRecheck[]=["same_measurement_projection","changed","different_source","unavailable"];
const STATES=["already","expected","possible","beyond","not-reached"];
const isAcquisition=(p:BriefingProjection):p is AcquisitionProjection=>"featureId" in p;

function invalid(what:string):never{
  throw new Error("검토 요청한 전망의 "+what+" 형식이 올바르지 않습니다.");
}
function text(raw:unknown,what:string,max=512):string{
  if(typeof raw!=="string"||!raw||raw.length>max)invalid(what);
  return raw;
}
function instant(raw:unknown,what:string):string{
  const value=text(raw,what,64);
  if(!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)||!Number.isFinite(Date.parse(value)))invalid(what);
  return value;
}
function finiteOrNull(raw:unknown,what:string):number|null{
  if(raw===null||raw===undefined)return null;
  if(typeof raw!=="number"||!Number.isFinite(raw))invalid(what);
  return raw;
}
function position(raw:unknown,acquisition:boolean):Position{
  if(!acquisition)return instant(raw,"관측 시각");
  if(typeof raw!=="number"||!Number.isSafeInteger(raw)||raw<1)invalid("측정 순서");
  return raw;
}
function reach(raw:unknown):Reach|null{
  if(raw===null||raw===undefined)return null;
  const row=object(raw);
  if(!row||!STATES.includes(String(row.state)))invalid("기준 도달 상태");
  return {state:String(row.state),expected:finiteOrNull(row.expected,"도달 위치"),
    earliest:finiteOrNull(row.earliest,"도달 위치"),latest:finiteOrNull(row.latest,"도달 위치")};
}

/** The capture ID hashes `identity`; the displayed `outlook` must be that same computation. */
function outlookBody(outlook:Record<string,unknown>|null,assetId:string):Record<string,unknown>{
  if(!outlook||outlook.schema_version!==1
    ||outlook.meaning!=="remaining-margin-to-user-conditions-not-a-diagnosis")invalid("계산 결과");
  if(outlook.asset_id!==assetId)throw new Error("다른 설비의 전망이 돌아왔습니다.");
  if(outlook.kind!=="history"&&outlook.kind!=="acquisition")invalid("전망 종류");
  if(outlook.axis!==(outlook.kind==="acquisition"?"acquisition":"time"))invalid("관측 축");
  return outlook;
}

function outlookFacts(outlook:Record<string,unknown>,assetId:string,assumedPeriod:number|null):CapturedOutlook{
  const acquisition=outlook.kind==="acquisition";
  const record=object(outlook.record),conditions=object(outlook.conditions);
  const settings=parseOutlookSettings(outlook.settings);
  if(!record||!conditions||!settings)invalid("계산 조건");
  const direction=conditions.direction;
  if(direction!=="upper"&&direction!=="lower")invalid("기준 방향");
  const timeBasis=outlook.time_basis??null;
  if(acquisition?!["recorded","assumed","ordinal"].includes(String(timeBasis)):timeBasis!==null
    &&typeof timeBasis!=="string")invalid("시간 근거");
  if((timeBasis==="assumed")!==(assumedPeriod!==null))invalid("가정 간격");
  const points=record.points;
  if(typeof points!=="number"||!Number.isSafeInteger(points)||points<1)invalid("관측 개수");
  const measurementVersion=text(outlook.measurement_version,"측정 버전",64);
  const dataVersion=text(outlook.data_version,"분석 근거 버전",64);
  if(!VERSION.test(measurementVersion)||!VERSION.test(dataVersion))invalid("근거 버전");
  if(!Array.isArray(outlook.scenarios)||outlook.scenarios.length>8)invalid("시나리오");
  const seen=new Set<string>();
  const scenarios=outlook.scenarios.map((item:unknown):Scenario=>{
    const row=object(item),limits=object(row?.limits);
    if(!row||!limits)invalid("시나리오");
    const id=text(row.id,"시나리오 식별자",64);
    if(seen.has(id))invalid("시나리오 식별자");
    seen.add(id);
    return {id,management:reach(limits.management),end:reach(limits.end)};
  });
  const rawSentences=outlook.sentences??[];
  if(!Array.isArray(rawSentences)||rawSentences.length>16)invalid("서버 설명");
  return {
    assetId,kind:outlook.kind as "history"|"acquisition",series:text(outlook.series,"신호"),
    sourceId:text(outlook.source_id,"출처"),
    pointId:outlook.measurement_point_id==null?null:text(outlook.measurement_point_id,"측정점"),
    // Captures made before the server echoed a binding keep it unknown, never guessed.
    bindingId:acquisition&&outlook.binding_id!=null?text(outlook.binding_id,"binding"):null,
    timeBasis:acquisition?timeBasis as TimeBasis:null,
    period:finiteOrNull(outlook.period_seconds,"측정 간격"),assumedPeriod,
    record:{first:position(record.first,acquisition),last:position(record.last,acquisition),points},
    conditions:{direction,management:finiteOrNull(conditions.management,"관리 기준"),
      end:finiteOrNull(conditions.end,"종료 기준")},
    settings,scenarios,measurementVersion,dataVersion,
    sentences:rawSentences.map((sentence:unknown)=>text(sentence,"서버 설명",600)),
  };
}

/** The capture ID hashes `identity`; the displayed `outlook` must be that same computation. */
function parseCapturedOutlook(raw:unknown,assetId:string):CapturedOutlook{
  const snapshot=object(raw),identity=object(snapshot?.identity);
  if(!snapshot||snapshot.schema_version!==1||!identity
    ||snapshot.meaning!=="captured-condition-outlook-not-actual-failure-or-maintenance")
    invalid("계산 근거");
  const outlook=outlookBody(object(snapshot.outlook),assetId);
  const record=object(outlook.record),saved=object(identity.record);
  const conditions=object(outlook.conditions),savedConditions=object(identity.conditions);
  const settings=parseOutlookSettings(outlook.settings);
  const savedSettings=parseOutlookSettings(identity.settings);
  if(!record||!saved||!conditions||!savedConditions||!settings||!savedSettings)invalid("계산 조건");
  const same=(left:Record<string,unknown>,right:Record<string,unknown>,keys:string[])=>
    keys.every(key=>(left[key]??null)===(right[key]??null));
  if(!same(identity,outlook,["asset_id","kind","series","source_id","measurement_point_id",
    "axis","time_basis","measurement_version","data_version"])
    ||!same(saved,record,["first","last","points"])
    ||!same(savedConditions,conditions,["direction","management","end"])
    ||JSON.stringify(savedSettings)!==JSON.stringify(settings))
    throw new Error("검토 요청의 식별 정보와 보존된 결과가 맞지 않아 표시하지 않았습니다.");
  return outlookFacts(outlook,assetId,finiteOrNull(identity.assumed_period_seconds,"가정 간격"));
}

/** Today's recomputation under the saved conditions, parsed like the archived facts. */
export function parseCurrentOutlook(raw:unknown,saved:CapturedOutlook):OutlookFacts{
  const outlook=outlookBody(object(raw),saved.assetId);
  const assumed=outlook.time_basis==="assumed"
    ?finiteOrNull(outlook.assumed_period_seconds??outlook.period_seconds,"가정 간격"):null;
  return outlookFacts(outlook,saved.assetId,assumed);
}
export class CompareUnavailable extends Error {}
export async function recomputeForComparison(saved:CapturedOutlook,signal:AbortSignal):Promise<OutlookFacts>{
  const query=new URLSearchParams({asset_id:saved.assetId,kind:saved.kind,series:saved.series,
    direction:saved.conditions.direction,
    changepoint_prior_scale:String(saved.settings.changepointPriorScale),
    changepoint_range:String(saved.settings.changepointRange),seasonality:saved.settings.seasonality});
  if(saved.conditions.management!==null)query.set("management_limit",String(saved.conditions.management));
  if(saved.conditions.end!==null)query.set("end_limit",String(saved.conditions.end));
  if(saved.settings.trainingPoints!==null)query.set("training_points",String(saved.settings.trainingPoints));
  if(saved.assumedPeriod!==null)query.set("assumed_period_seconds",String(saved.assumedPeriod));
  const response=await fetch("/api/v1/outlook?"+query,{signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404||response.status===422)
    throw new CompareUnavailable("지금 데이터로는 같은 조건의 전망을 계산할 수 없습니다.");
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("지금 데이터로 다시 계산하지 못했습니다. 같은 조건으로 다시 시도할 수 있습니다.");
  }
  return parseCurrentOutlook(await response.json() as unknown,saved);
}
/** A projection the user is looking at, in the same comparable shape. */
export function factsOf(projection:BriefingProjection):OutlookFacts{
  const acquisition=isAcquisition(projection);
  return {assetId:projection.assetId,kind:acquisition?"acquisition":"history",
    series:acquisition?projection.featureId:projection.channel,sourceId:projection.sourceId,
    pointId:acquisition?null:projection.pointId,bindingId:acquisition?projection.bindingId:null,
    timeBasis:acquisition?projection.timeBasis:null,period:acquisition?projection.effectivePeriod:null,
    assumedPeriod:acquisition?projection.assumedPeriod:null,
    record:{first:projection.record.first,last:projection.record.last,points:projection.record.points},
    conditions:projection.conditions,settings:projection.outlookSettings??null,
    scenarios:projection.scenarios,measurementVersion:projection.measurementVersion,
    dataVersion:projection.dataVersion,sentences:[]};
}

function parseReview(raw:unknown):Capture["review"]{
  const review=object(raw);
  if(!review||!Array.isArray(review.events)||review.events.length>500)invalid("검토 기록");
  const seen=new Set<string>();
  let replayed:ReviewStatus="open";
  const events=review.events.map((item:unknown):ReviewEvent=>{
    const row=object(item);
    if(!row||!["note","acknowledge","close"].includes(String(row.action))
      ||typeof row.note!=="string"||row.note.length>1000)invalid("검토 기록");
    const eventId=text(row.event_id,"검토 기록 식별자",64);
    if(!REQUEST_ID.test(eventId)||seen.has(eventId))invalid("검토 기록 식별자");
    seen.add(eventId);
    const action=row.action as ReviewAction;
    replayed=nextReviewStatus(replayed,action);
    return {eventId,action,note:row.note,recordedAt:instant(row.recorded_at,"검토 시각"),decision:readDecision(row.decision)};
  });
  if(review.status!==replayed)throw new Error("검토 상태와 저장된 검토 기록이 일치하지 않습니다.");
  return {status:replayed,events};
}

export function parseCapturePage(raw:unknown,assetId:string,captureId:string|null=null):CapturePage{
  const root=object(raw);
  if(!root||root.schema_version!==1||!Array.isArray(root.captures)||root.captures.length>20)
    invalid("목록");
  const seen=new Set<string>();
  const captures=root.captures.map((item:unknown):Capture=>{
    const row=object(item);
    if(!row)invalid("목록");
    const id=text(row.capture_id,"식별자",96);
    if(!CAPTURE_ID.test(id)||seen.has(id))invalid("식별자");
    seen.add(id);
    if(!RECHECKS.includes(row.source_recheck as SourceRecheck))invalid("원본 재검증 상태");
    return {id,capturedAt:instant(row.captured_at,"저장 시각"),
      outlook:parseCapturedOutlook(row.snapshot,assetId),
      sourceRecheck:row.source_recheck as SourceRecheck,review:parseReview(row.review)};
  });
  const next=root.next_before??null;
  if(next!==null&&(next!==captures[captures.length-1]?.id||captureId!==null))invalid("다음 쪽 기준");
  if(captureId!==null&&(captures.length!==1||captures[0].id!==captureId))
    throw new CaptureNotFound("요청한 검토 대상이 아닌 기록이 돌아왔습니다.");
  return {captures,nextBefore:next as string|null};
}

/** Names exactly the projection the user saw; the server echoes nothing numerical back. */
export function capturePayload(projection:BriefingProjection):Record<string,string>{
  const settings=projection.outlookSettings;
  if(!VERSION.test(projection.measurementVersion)||!VERSION.test(projection.dataVersion)||!settings)
    throw new CaptureRejected("검토를 요청할 결과의 데이터 버전이나 계산 설정을 확인할 수 없습니다.");
  const acquisition=isAcquisition(projection);
  const payload:Record<string,string>={
    asset_id:projection.assetId,kind:acquisition?"acquisition":"history",
    series:acquisition?projection.featureId:projection.channel,
    direction:projection.conditions.direction,source_id:projection.sourceId,
    measurement_version:projection.measurementVersion,data_version:projection.dataVersion,
    changepoint_prior_scale:String(settings.changepointPriorScale),
    changepoint_range:String(settings.changepointRange),seasonality:settings.seasonality,
  };
  if(settings.trainingPoints!==null)payload.training_points=String(settings.trainingPoints);
  if(projection.conditions.management!==null)
    payload.management_limit=String(projection.conditions.management);
  if(projection.conditions.end!==null)payload.end_limit=String(projection.conditions.end);
  if(acquisition){
    payload.binding_id=projection.bindingId;
    payload.time_basis=projection.timeBasis;
    if(projection.recordedPeriod!==null)
      payload.recorded_period_seconds=String(projection.recordedPeriod);
    if(projection.timeBasis==="assumed"&&projection.assumedPeriod!==null)
      payload.assumed_period_seconds=String(projection.assumedPeriod);
  }
  return payload;
}

const NOT_FOUND="이 설비에서 해당 검토 요청을 찾을 수 없습니다. 다른 설비의 기록으로 대신하지 않습니다.";
function refuseCapture(status:number):void{
  if(status===400)
    throw new CaptureRejected("요청하는 사이 데이터나 계산 결과가 바뀌어 남기지 않았습니다. 다시 계산하세요.");
  if(status===404)throw new CaptureNotFound(NOT_FOUND);
  // A capture has no review status yet; a conflict here is not someone else's review.
  if(status===409)
    throw new Error("처리 결과를 확인하지 못했습니다. 같은 작업을 다시 시도해도 기록이 겹치지 않습니다.");
}
function refuseReview(status:number):void{
  if(status===404)throw new CaptureNotFound(NOT_FOUND);
}

export async function readCaptures(
  assetId:string,{captureId=null,before=null}:{captureId?:string|null;before?:string|null},
  signal:AbortSignal,
):Promise<CapturePage>{
  if(captureId!==null&&!CAPTURE_ID.test(captureId))
    throw new CaptureNotFound("검토 요청 식별자 형식이 올바르지 않습니다.");
  const query=new URLSearchParams({asset_id:assetId});
  if(captureId!==null)query.set("capture_id",captureId);
  if(before!==null)query.set("before_id",before);
  const response=await fetch("/api/v1/outlook/captures?"+query,
    {signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404)throw new CaptureNotFound(NOT_FOUND);
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("검토 요청 목록을 불러오지 못했습니다. 기록이 없다는 뜻은 아닙니다.");
  }
  return parseCapturePage(await response.json() as unknown,assetId,captureId);
}

/** Re-verify, then ask the supervisor to recompute and persist. Returns the capture ID. */
export async function confirmCapture(projection:BriefingProjection,signal:AbortSignal):Promise<string>{
  const payload=capturePayload(projection);
  await assertCurrentVersion(projection,signal);
  const result=await postReviewWrite("/api/v1/outlook/captures/confirm",payload,signal,refuseCapture);
  if(result.asset_id!==projection.assetId||typeof result.capture_id!=="string"
    ||!CAPTURE_ID.test(result.capture_id))
    throw new OutcomeUnknown("처리 응답의 대상이 요청과 다릅니다. 정비 검토함에서 확인하세요.");
  return result.capture_id;
}

/** The caller reuses `eventId` while retrying one uncertain action, so a retry can never
 * append a second note or status change. */
export async function recordReview(
  capture:Capture,action:ReviewAction,note:string,eventId:string,signal:AbortSignal,
  decision:ReviewDecision|null=null,
):Promise<ReviewStatus>{
  if(!REQUEST_ID.test(eventId))throw new Error("검토 기록 식별자가 올바르지 않습니다.");
  const result=await postReviewWrite("/api/v1/outlook/captures/review/action",{
    asset_id:capture.outlook.assetId,capture_id:capture.id,event_id:eventId,
    action,note:reviewNote(action,note),...(decision?{decision}:{}),
  },signal,refuseReview);
  if(result.capture_id!==capture.id||result.asset_id!==capture.outlook.assetId
    ||result.event_id!==eventId||!["open","acknowledged","closed"].includes(String(result.status))
    ||result.meaning!=="human-review-not-maintenance-or-diagnosis")
    throw new OutcomeUnknown("검토 기록 응답의 대상이 요청과 다릅니다. 검토 기록을 확인하세요.");
  return result.status as ReviewStatus;
}

function samePosition(left:Position,right:Position):boolean{
  return typeof left==="number"||typeof right==="number"
    ?left===right:Date.parse(left)===Date.parse(right);
}

/** A later observation is only comparable under identical subject, axis and assumptions;
 * a setting change is reported as such, never as observed deterioration. */
export function compareReobservation(saved:CapturedOutlook,current:OutlookFacts):Reobservation{
  const acquisition=current.kind==="acquisition";
  const subject=saved.assetId===current.assetId&&saved.kind===current.kind
    &&saved.series===current.series&&saved.sourceId===current.sourceId
    &&(acquisition
      ?saved.timeBasis===current.timeBasis
        &&(saved.bindingId===null||saved.bindingId===current.bindingId)
      :saved.pointId===current.pointId);
  if(!subject)return {kind:"different-subject"};
  const changes:string[]=[];
  if(saved.conditions.direction!==current.conditions.direction)changes.push("기준 방향");
  if(saved.conditions.management!==current.conditions.management)changes.push("관리 기준");
  if(saved.conditions.end!==current.conditions.end)changes.push("종료 기준");
  if(!current.settings||JSON.stringify(current.settings)!==JSON.stringify(saved.settings))
    changes.push("예측 계산 설정");
  if(acquisition&&saved.assumedPeriod!==current.assumedPeriod)changes.push("가정한 측정 간격");
  if(changes.length)return {kind:"changed-assumptions",changes};
  const bindingRecorded=!acquisition||saved.bindingId!==null;
  if(saved.measurementVersion===current.measurementVersion)
    return {kind:"same-measurement",bindingRecorded,
      anomalyEvidenceChanged:saved.dataVersion!==current.dataVersion};
  const before=saved.scenarios.find(item=>item.id==="current");
  const after=current.scenarios.find(item=>item.id==="current");
  const limits=(["management","end"] as const).filter(name=>current.conditions[name]!==null)
    .map(name=>({name,before:before?.[name]??null,after:after?.[name]??null}));
  return {kind:"new-observation",moved:!samePosition(saved.record.last,current.record.last),
    before:saved.record.last,after:current.record.last,limits,bindingRecorded};
}

export function positionText(value:Position):string{
  return typeof value==="number"?"측정 순서 #"+value
    :new Date(value).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"});
}

/** The exact review subject inside the maintenance task. */
export function captureUrl(assetId:string,captureId:string):string{
  return "/web/?"+new URLSearchParams({page:"maintenance",monitor_asset:assetId,capture_id:captureId});
}
/** Reopen the archived subject's conditions for a new recomputation. Server settings
 * that the page cannot choose are compared afterwards rather than silently assumed. */
export function reobservationUrl(saved:CapturedOutlook):string{
  const history=saved.kind==="history";
  const params=new URLSearchParams({page:"assets",tab:"outlook",data:history?"history":"vibration",
    monitor_asset:saved.assetId});
  const prefix=history?"projection_":"acq_";
  params.set(history?"monitor_channel":"acq_forecast_feature",saved.series);
  params.set(prefix+"direction",saved.conditions.direction);
  if(saved.conditions.management!==null)params.set(prefix+"management",String(saved.conditions.management));
  if(saved.conditions.end!==null)params.set(prefix+"end",String(saved.conditions.end));
  if(!history&&saved.assumedPeriod!==null)params.set("acq_assumed_period",String(saved.assumedPeriod));
  return "/web/?"+params;
}
