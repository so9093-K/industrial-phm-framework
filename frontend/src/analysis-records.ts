/** Stored 3-phase unbalance and file feature analyses, and the analyses that did not run,
 * exactly as one monitor snapshot reports them. Nothing is recomputed or interpreted. */
import {postReviewWrite,object,OutcomeUnknown} from "./review-writes.ts";

export type QualityState="pass"|"warning"|"error";
export type PhaseQuantity={
  quantity:"current"|"voltage";median:number|null;p95:number|null;max:number|null;maxAt:string|null;
  evaluated:number;excluded:Record<string,number>;
};
export type AnalysisRecord={
  kind:"phase"|"file";runId:string;evidenceId:string;assetId:string;sourceId:string;pointId:string|null;
  capabilityId:string;version:string|null;observedStart:string|null;observedEnd:string|null;
  completedAt:string|null;quality:QualityState|null;issues:string[];
  quantities:PhaseQuantity[];features:{name:string;value:number|null}[];sha256:string|null;
};
export type SkippedAnalysis={
  assetId:string;sourceId:string;pointId:string|null;capabilityId:string;reason:string;
  observedStart:string|null;observedEnd:string|null;recordedAt:string|null;
};
/** `truncated` is about the results; a missing or cut skipped list is reported apart. */
export type AnalysisRecords={
  available:boolean;records:AnalysisRecord[];truncated:boolean;
  skipped:SkippedAnalysis[];skippedComplete:boolean;
};

function invalid(what:string):never{
  throw new Error("분석 기록의 "+what+" 형식이 올바르지 않습니다.");
}
function id(raw:unknown,what:string):string{
  if(typeof raw!=="string"||!raw||raw.length>512||/[\x00-\x1f]/.test(raw))invalid(what);
  return raw;
}
function optionalId(raw:unknown,what:string):string|null{
  return raw===null||raw===undefined?null:id(raw,what);
}
function instant(raw:unknown):string|null{
  if(raw===null||raw===undefined)return null;
  if(typeof raw!=="string"||!Number.isFinite(Date.parse(raw)))invalid("시각");
  return raw;
}
function finite(raw:unknown):number|null{
  return typeof raw==="number"&&Number.isFinite(raw)?raw:null;
}
function group(root:Record<string,unknown>,key:string):{items:unknown[];truncated:boolean}|null{
  if(root[key]===undefined)return null;
  const raw=object(root[key]);
  if(!raw||!Array.isArray(raw.items)||typeof raw.truncated!=="boolean")invalid("목록");
  return {items:raw.items,truncated:raw.truncated};
}
function quantity(raw:unknown):PhaseQuantity{
  const row=object(raw);
  const excluded=object(row?.excluded_samples);
  if(!row||(row.quantity!=="current"&&row.quantity!=="voltage")||!excluded
    ||typeof row.evaluated_samples!=="number"||!Number.isSafeInteger(row.evaluated_samples))
    invalid("3상 불평형 결과");
  const counts:Record<string,number>={};
  for(const [reason,count] of Object.entries(excluded)){
    if(typeof count!=="number"||!Number.isSafeInteger(count)||count<0)invalid("제외 표본");
    counts[reason]=count;
  }
  return {quantity:row.quantity,median:finite(row.median_percent),p95:finite(row.p95_percent),
    max:finite(row.max_percent),maxAt:instant(row.max_at),evaluated:row.evaluated_samples,excluded:counts};
}
function record(raw:unknown,kind:"phase"|"file"):AnalysisRecord{
  const row=object(raw);
  if(!row)invalid("분석 결과");
  const quality=object(row.data_quality);
  const state=quality?.state;
  const quantities=kind==="phase"?row.quantities:[];
  const features=kind==="file"?row.features:[];
  if(!Array.isArray(quantities)||quantities.length>8||!Array.isArray(features)||features.length>256)
    invalid("분석 결과 값");
  return {kind,runId:id(row.analysis_run_id,"분석 실행"),evidenceId:id(row.evidence_id,"분석 근거"),
    assetId:id(row.asset_id,"설비"),sourceId:id(row.source_id,"데이터 출처"),
    pointId:optionalId(row.measurement_point_id,"측정 위치"),capabilityId:id(row.capability_id,"분석 종류"),
    version:optionalId(kind==="phase"?row.algorithm_version:row.feature_set_id,"계산 버전"),
    observedStart:instant(row.observed_start_at),observedEnd:instant(row.observed_end_at),
    completedAt:instant(row.completed_at),
    quality:state==="pass"||state==="warning"||state==="error"?state:null,
    issues:Array.isArray(quality?.issue_codes)?quality.issue_codes.filter((x):x is string=>typeof x==="string"):[],
    quantities:quantities.map(quantity),
    features:features.map((item:unknown)=>{
      const value=object(item);
      return {name:id(value?.name,"특징 이름"),value:finite(value?.value)};
    }),
    sha256:kind==="file"?optionalId(row.source_snapshot_sha256,"원본 확인값"):null};
}

export function parseAnalysisRecords(payload:unknown):AnalysisRecords{
  const root=object(payload);
  if(!root)throw new Error("분석 기록 응답이 올바르지 않습니다.");
  const phase=group(root,"phase_unbalance_analyses");
  const file=group(root,"file_feature_analyses");
  const skipped=group(root,"skipped_analysis_attempts");
  if(!phase||!file)return {available:false,records:[],truncated:true,skipped:[],skippedComplete:false};
  const records=[...phase.items.map(item=>record(item,"phase")),...file.items.map(item=>record(item,"file"))]
    .sort((a,b)=>Date.parse(b.completedAt??"")-Date.parse(a.completedAt??"")||0);
  const keys=new Set(records.map(item=>item.runId+"\n"+item.evidenceId));
  if(keys.size!==records.length)throw new Error("같은 분석 결과가 두 번 돌아왔습니다.");
  return {available:true,records,
    skipped:(skipped?.items??[]).map((raw:unknown):SkippedAnalysis=>{
      const row=object(raw);
      if(!row)invalid("실행되지 않은 분석");
      return {assetId:id(row.asset_id,"설비"),sourceId:id(row.source_id,"데이터 출처"),
        pointId:optionalId(row.measurement_point_id,"측정 위치"),
        capabilityId:id(row.capability_id,"분석 종류"),reason:typeof row.reason==="string"?row.reason:"사유 기록 없음",
        observedStart:instant(row.observed_start_at),observedEnd:instant(row.observed_end_at),
        recordedAt:instant(row.recorded_at)};
    }),
    truncated:phase.truncated||file.truncated,skippedComplete:skipped!==null&&!skipped.truncated};
}

/** Asks for a human review of exactly this stored analysis result; asking again names
 * the same review item. */
export async function requestAnalysisReview(item:AnalysisRecord,signal:AbortSignal):Promise<string>{
  const result=await postReviewWrite("/api/v1/reviews/request",
    {analysis_run_id:item.runId,evidence_id:item.evidenceId},signal);
  if(result.analysis_run_id!==item.runId||result.asset_id!==item.assetId
    ||!Array.isArray(result.evidence_ids)||!result.evidence_ids.includes(item.evidenceId)
    ||typeof result.finding_id!=="string")
    throw new OutcomeUnknown("검토 요청 응답의 대상이 요청과 다릅니다. 정비 검토함에서 확인하세요.");
  return result.finding_id;
}
