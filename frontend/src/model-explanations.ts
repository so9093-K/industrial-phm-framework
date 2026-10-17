/** AI explanations and review requests of one stored model result. The server keeps the
 * feature comparison the answer was checked against; the screen shows that stored
 * comparison and never recomputes a value or a direction. */
import type {Focus} from "./model-comparison.ts";
import type {ModelBinding,ModelRun} from "./model-evidence.ts";
import {object,postReviewWrite,OutcomeUnknown,type ReviewStatus} from "./review-writes.ts";

export type FeatureChange={
  feature:string;label:string;current:number;previous:number|null;relativePercent:number|null;
};
export type Relation="increased"|"decreased"|"unchanged";
export type AnswerSource="model"|"model-trimmed"|"verified-comparison";
export type ModelAnswer={
  summary:string;observations:{feature:string;relation:Relation}[];nextStep:string;
  source:AnswerSource;modelUnavailable:boolean;
};
export type ModelExplanation={
  id:string;status:"pending"|"complete"|"failed";model:string|null;requestedAt:string;
  question:string;comparePosition:number|null;previousScore:number|null;focus:Focus|null;
  features:FeatureChange[];answer:ModelAnswer|null;
};
export type ModelReview={findingId:string|null;status:ReviewStatus|null};

export const DEFAULT_QUESTION="이전 측정과 비교해 어떤 측정값이 함께 변했는지 설명해 주세요.";
const RELATIONS:readonly Relation[]=["increased","decreased","unchanged"];
const SOURCES:readonly AnswerSource[]=["model","model-trimmed","verified-comparison"];

function invalid(what:string):never{
  throw new Error("모델 결과 해설의 "+what+" 형식이 올바르지 않습니다.");
}
function finite(raw:unknown):number|null{
  return typeof raw==="number"&&Number.isFinite(raw)?raw:null;
}
function text(raw:unknown,what:string,max=4000):string{
  if(typeof raw!=="string"||raw.length>max)invalid(what);
  return raw;
}
function position(raw:unknown):number|null{
  if(raw===null||raw===undefined)return null;
  if(typeof raw!=="number"||!Number.isSafeInteger(raw)||raw<1)invalid("비교 측정");
  return raw;
}
function feature(raw:unknown):FeatureChange{
  const row=object(raw);
  const current=finite(row?.current);
  if(!row||current===null)invalid("측정값 비교");
  return {feature:text(row.feature,"측정값 이름",256),label:text(row.label,"측정값 이름",256),
    current,previous:finite(row.previous),relativePercent:finite(row.relative_change_percent)};
}
function answer(raw:unknown,features:FeatureChange[]):ModelAnswer|null{
  if(raw===null||raw===undefined)return null;
  const row=object(raw);
  const checks=object(row?.checks);
  if(!row||!Array.isArray(row.observations)||row.observations.length>8)invalid("해설");
  const known=new Set(features.map(item=>item.feature));
  const observations=row.observations.map((item:unknown)=>{
    const value=object(item);
    if(!value||!RELATIONS.includes(value.relation as Relation)||!known.has(String(value.feature)))
      invalid("해설이 언급한 측정값");
    return {feature:value.feature as string,relation:value.relation as Relation};
  });
  const source=checks?.summary_source;
  return {summary:text(row.summary,"해설"),observations,nextStep:text(row.next_step??"","다음 확인"),
    source:SOURCES.includes(source as AnswerSource)?source as AnswerSource:"verified-comparison",
    modelUnavailable:checks?.model_unavailable===true};
}

/** Only explanations of exactly this stored run; anything else is not shown. */
export function parseModelExplanations(raw:unknown,binding:ModelBinding,run:ModelRun):ModelExplanation[]{
  const root=object(raw);
  if(!root||root.schema_version!==1||!Array.isArray(root.explanations)||root.explanations.length>10)
    throw new Error("모델 결과 해설 목록의 형식이 올바르지 않습니다.");
  return root.explanations.flatMap((item:unknown):ModelExplanation[]=>{
    const row=object(item);
    if(!row)invalid("기록");
    if(row.binding_id!==binding.bindingId||row.position!==run.position
      ||row.analysis_run_id!==run.runId)return [];
    if(!["pending","complete","failed"].includes(String(row.status)))invalid("상태");
    const context=object(row.context);
    const comparison=object(context?.signal_comparison);
    if(!context||!comparison||!Array.isArray(comparison.features)||comparison.features.length>64)
      invalid("비교 근거");
    const features=comparison.features.map(feature);
    const previousOutput=object(comparison.previous_output);
    const focused=object(context.focus);
    const focus:Focus|null=focused?{position:position(focused.position)??invalid("질문 기준"),series:typeof focused.series==="string"?focused.series:null}:null;
    const requestedAt=text(row.requested_at,"요청 시각",64);
    if(!Number.isFinite(Date.parse(requestedAt)))invalid("요청 시각");
    return [{id:text(row.id,"식별자",128),status:row.status as ModelExplanation["status"],
      model:typeof row.model==="string"?row.model:null,requestedAt,
      question:text(context.question,"질문",600),comparePosition:position(comparison.previous_position),
      previousScore:finite(previousOutput?.score),features,focus,
      answer:row.status==="complete"?answer(row.answer,features):null}];
  });
}

async function read(url:string,signal:AbortSignal,failure:string):Promise<unknown>{
  const response=await fetch(url,{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    // A refused read is finished here; an unread body would keep the request open.
    await response.body?.cancel().catch(()=>{});
    throw new Error(failure);
  }
  return await response.json() as unknown;
}
const query=(binding:ModelBinding,run:ModelRun)=>new URLSearchParams(
  {binding_id:binding.bindingId,position:String(run.position)});

export async function readModelExplanations(
  binding:ModelBinding,run:ModelRun,signal:AbortSignal,
):Promise<ModelExplanation[]>{
  return parseModelExplanations(await read("/api/v1/phm/explanations?"+query(binding,run),signal,
    "해설을 불러오지 못했습니다. 해설이 없다는 뜻은 아닙니다."),binding,run);
}

export async function requestModelExplanation(
  binding:ModelBinding,run:ModelRun,comparePosition:number|null,question:string,
  parentId:string|null,signal:AbortSignal,focus:Focus|null=null,
):Promise<string>{
  const asked=question.trim();
  if(!asked||asked.length>600)throw new Error("질문은 1~600자로 입력하세요.");
  const payload:Record<string,unknown>={binding_id:binding.bindingId,position:run.position,question:asked};
  if(comparePosition!==null)payload.compare_position=comparePosition;
  if(parentId!==null)payload.parent_id=parentId;
  if(focus){
    if(comparePosition===null||focus.position<=comparePosition||focus.position>run.position)throw new Error("질문 기준 지점이 비교 구간 밖입니다.");
    payload.focus_position=focus.position;
    if(focus.series!==null)payload.focus_series=focus.series;
  }
  const result=await postReviewWrite("/api/v1/phm/explanations/request",payload,signal,(status)=>{
    if(status===400)
      throw new Error("해설을 요청하지 못했습니다. 동시에 만들 수 있는 해설 수를 넘었거나 비교 조건이 맞지 않습니다.");
  });
  if(result.binding_id!==binding.bindingId||result.position!==run.position
    ||typeof result.explanation_id!=="string")
    throw new OutcomeUnknown("해설 요청 응답의 대상이 요청과 다릅니다.");
  return result.explanation_id;
}

export function parseModelReview(raw:unknown):ModelReview{
  const root=object(raw);
  if(!root||(root.finding_id!==null&&typeof root.finding_id!=="string"))
    throw new Error("모델 결과의 검토 상태를 확인할 수 없습니다.");
  if(root.finding_id===null)return {findingId:null,status:null};
  if(!["open","acknowledged","closed"].includes(String(root.status)))
    throw new Error("모델 결과의 검토 상태를 확인할 수 없습니다.");
  return {findingId:root.finding_id as string,status:root.status as ReviewStatus};
}

export async function readModelReview(
  binding:ModelBinding,run:ModelRun,signal:AbortSignal,
):Promise<ModelReview>{
  return parseModelReview(await read("/api/v1/phm/review?"+query(binding,run),signal,
    "검토 상태를 불러오지 못했습니다."));
}

/** Asks for a human review of this exact stored result; the same request is idempotent. */
export async function requestModelReview(
  binding:ModelBinding,run:ModelRun,explanationId:string|null,signal:AbortSignal,
):Promise<string>{
  const result=await postReviewWrite("/api/v1/phm/reviews/request",
    {binding_id:binding.bindingId,position:run.position,explanation_id:explanationId},signal);
  if(result.analysis_run_id!==run.runId||typeof result.finding_id!=="string")
    throw new OutcomeUnknown("검토 요청 응답의 대상이 요청과 다릅니다. 정비 검토함에서 확인하세요.");
  return result.finding_id;
}
