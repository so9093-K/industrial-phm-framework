import {scopeParams, type PlaybackScope} from "./record-playback.ts";
import {findingLinks, relatedSignalHref} from "./record-findings.ts";
import type {EvidenceFocus} from "./change-evidence.ts";
import {object,postWrite} from "./writes.ts";
import {assetTabUrl} from "./routes.ts";
import {featureCompareHref} from "./measurement-links.ts";
export const CHANGE_ACTIONS=["compare","spectrum","onset","model","signals","electrical"] as const;
export type ChangeAction=typeof CHANGE_ACTIONS[number];
/** 답이 근거로 쓴 사실을 화면이 가리킬 수 있는 것으로: 찾은 변화(그래프의 선·구간), 그래프 밖 신호, 운전 수준 띠, 주파수 대역. */
export type Evidence=
  |{fact:string;kind:"change";review_key:string;label:string;before:number|null;after:number|null;unit:string|null;where:string}
  |{fact:string;kind:"signal";label:string;before:number|null;after:number|null;unit:string|null}
  |{fact:string;kind:"operation";label:string;detail:string;levels?:string[];a?:number[];b?:number[];runs?:{from:string;to:string;level:number}[]}
  |{fact:string;kind:"spectrum";label:string;from_hz:number;to_hz:number;a:number;b:number;ratio:number|null};
export type ChangeAnswer={summary:string;next_step?:string;actions:ChangeAction[];evidence?:Evidence[];source:"model"|"computed"};
const num=(v:unknown)=>typeof v==="number"&&Number.isFinite(v);
const maybe=(v:unknown)=>v===null||num(v);
const runs=(list:unknown,count:number)=>Array.isArray(list)&&list.length<=8&&list.every(item=>{const run=object(item);
  return !!run&&typeof run.from==="string"&&typeof run.to==="string"&&Number.isInteger(run.level)&&(run.level as number)>=0&&(run.level as number)<count&&Date.parse(run.from)<Date.parse(run.to);});
const shares=(levels:unknown,a:unknown,b:unknown)=>Array.isArray(levels)&&levels.every(name=>typeof name==="string")
  &&[a,b].every(list=>Array.isArray(list)&&list.length===levels.length&&list.every(v=>num(v)&&v>=0&&v<=1));
/** 근거 한 줄의 모양을 확인한다. 이전 답(근거 없음)은 빈 목록으로 읽는다. */
export function readEvidence(raw:unknown):Evidence[]{
  if(raw===undefined)return [];
  if(!Array.isArray(raw)||raw.length>3)throw new Error("답의 근거를 확인하지 못했습니다.");
  return raw.map(item=>{
    const row=object(item);
    const ok=row&&typeof row.fact==="string"&&typeof row.label==="string"&&(
      row.kind==="change"?typeof row.review_key==="string"&&maybe(row.before)&&maybe(row.after)&&typeof row.where==="string"
      :row.kind==="signal"?maybe(row.before)&&maybe(row.after)
      :row.kind==="operation"?typeof row.detail==="string"&&(row.levels===undefined||(row.a===undefined?Array.isArray(row.levels):shares(row.levels,row.a,row.b)))
        &&(row.runs===undefined||Array.isArray(row.levels)&&runs(row.runs,row.levels.length))
      :row.kind==="spectrum"?num(row.from_hz)&&num(row.to_hz)&&num(row.a)&&num(row.b)&&maybe(row.ratio):false);
    if(!ok)throw new Error("답의 근거를 확인하지 못했습니다.");
    return {...row,unit:typeof row!.unit==="string"?row!.unit:null} as Evidence;
  });
}
export type ChangeDiscussion={id:string;question:string;status:"pending"|"complete"|"failed";answer:ChangeAnswer|null};
/** An AI suggestion opens an existing analysis of this exact change, never a new default. */
export function changeActionLinks(asset:string, change:{feature:string;from:number;to:number;baseline:{from:number;to:number}}, binding:string|null, actions:readonly ChangeAction[]) {
  const spans={a:change.baseline,b:{from:change.from,to:change.to}};
  return actions.flatMap<{key:ChangeAction;label:string;href:string}>(action=>{
    if(action==="compare")return [{key:action,label:"같은 구간의 특징 비교",href:featureCompareHref(asset,change.feature,spans)}];
    const url=new URL(assetTabUrl(asset,action==="spectrum"?"change":"anomaly",action==="spectrum"?"spectrum":"model"),"http://local");
    if(action==="spectrum")for(const name of ["a","b"] as const)for(const edge of ["from","to"] as const)url.searchParams.set("spectrum_"+name+"_"+edge,String(spans[name][edge]));
    else {
      if(!binding)return [];
      url.searchParams.set("model_binding",binding);url.searchParams.set("model_position",String(change.from));
      if(action==="onset")url.hash="selected-model-input";
    }
    return [{key:action,label:action==="spectrum"?"이 구간의 주파수 비교":action==="onset"?"변화 시작 측정의 원본 확인":"변화 시작 측정의 모델 결과",href:url.pathname+url.search+url.hash}];
  });
}
export async function readChangeDiscussion(asset:string,key:string,signal:AbortSignal,scope:PlaybackScope|null=null):Promise<ChangeDiscussion[]> {
  const response=await fetch("/api/v1/phm/change-explanations?"+new URLSearchParams({asset_id:asset,change_id:key,...scopeParams(scope)}),{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){await response.body?.cancel().catch(()=>{});throw new Error("선택한 변화의 조사 내용을 불러오지 못했습니다.");}
  const root=object(await response.json());
  if(root?.schema_version!==1||root.asset_id!==asset||root.change_id!==key||!Array.isArray(root.explanations)||root.explanations.length>10)
    throw new Error("다른 변화의 조사 내용은 보여 드릴 수 없습니다.");
  return root.explanations.map((raw:unknown)=>{
    const row=object(raw),context=object(row?.context),answer=object(row?.answer);
    if(!row||context?.asset_id!==asset||context.change_id!==key||typeof row.id!=="string"||typeof context.question!=="string"
      ||!["pending","complete","failed"].includes(String(row.status)))throw new Error("조사 내용의 대상을 확인하지 못했습니다.");
    if(answer&&(typeof answer.summary!=="string"||(answer.next_step!==undefined&&(typeof answer.next_step!=="string"||!answer.next_step.trim()||answer.next_step.length>200))||!Array.isArray(answer.actions)||answer.actions.some(a=>!CHANGE_ACTIONS.includes(a as ChangeAction))||!["model","computed"].includes(String(answer.source))))
      throw new Error("조사 설명의 다음 분석을 확인하지 못했습니다.");
    return {id:row.id,question:context.question,status:row.status as ChangeDiscussion["status"],
      answer:answer?{...answer,evidence:readEvidence(answer.evidence)} as ChangeAnswer:null};
  });
}
export async function askChange(asset:string,key:string,question:string,parent:string|null,signal:AbortSignal,scope:PlaybackScope|null=null):Promise<void> {
  const reply=await postWrite("/api/v1/phm/explanations/request",{asset_id:asset,change_id:key,question,...scopeParams(scope),...(parent?{parent_id:parent}:{})},signal);
  if(typeof reply.explanation_id!=="string"||reply.status!=="pending"||reply.change_id!==key)throw new Error("질문 접수 결과를 확인하지 못했습니다. 다시 불러오세요.");
}

export function investigationLinks(asset:string,focus:EvidenceFocus,actions:readonly ChangeAction[]){
  if(focus.kind==="vibration")return changeActionLinks(asset,focus.change,focus.record.bindingId,actions);
  const links=findingLinks(asset,focus.item,focus.record.baseline,focus.record.bucketSeconds,focus.record.record);
  return actions.flatMap<{key:ChangeAction;label:string;href:string}>(action=>{
    if(action==="compare"&&links.compare)return [{key:action,label:"같은 기간의 값 비교",href:links.compare}];
    if(action==="signals"&&links.signal)return [{key:action,label:"같은 시각의 관련 신호",href:relatedSignalHref(links.signal,focus.item,focus.record.signals)}];
    if(action==="electrical"&&links.signal){
      const url=new URL(links.signal,"http://local");
      url.searchParams.set("tab","change");url.searchParams.set("method","electrical");
      const reference=links.compare?new URL(links.compare,"http://local").searchParams.get("compare_a"):null;
      if(reference)url.searchParams.set("compare_a",reference);
      return [{key:action,label:"3상 전압·전류 비교",href:url.pathname+url.search}];
    }
    return [];
  });
}
