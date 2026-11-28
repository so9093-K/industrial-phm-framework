import {scopeParams, type PlaybackScope} from "./record-playback.ts";
import type {AnalysisReadout} from "./analysis-readout.svelte.ts";
import {object,postWrite} from "./writes.ts";
import {parseProfile,type Periods,type ProfileSeries} from "./comparison.ts";
import {bandName} from "./record-findings.ts";
/** AI의 답: 사람에게 말하듯 쓴 몇 문장. */
export type ChangeAnswer={summary:string};
/** 대화를 여는 짧은 질문: 사람이 실제로 묻는 말 그대로 보내고 그대로 보인다. */
export const STARTERS=["문제 있어?","무엇이 함께 달라졌어?","뭘 점검해야 해?"];
export const LOAD_QUESTION="같은 부하에서도 전압이 달라졌어?";
export type LoadComparison={status:"unavailable"|"failed"}|{
  /** 견준 운전 수준을 기간 비교 화면·관제 카드와 같은 말로('약 11 A 운전'). */
  status:"ready"; series:ProfileSeries; periods:Periods; condition:string;
  level:number; snapshot:number; until:string|null;
};
/** 한 문답: 물은 말, 그래프에서 짚고 물은 곳(pointed), 답, 대화 안에서 실행한 비교, AI가 함께 연 분석 화면(analysis). */
export type ChangeDiscussion={id:string;question:string;pointed:string|null;status:"pending"|"complete"|"failed";answer:ChangeAnswer|null;
  comparison:LoadComparison|null;analysis:string|null;answerView:string|null;answerScope:string|null};

function loadComparison(raw:unknown,asset:string):LoadComparison|null {
  if(raw==null)return null;
  const row=object(raw);
  if(row?.status==="unavailable"||row?.status==="failed")return {status:row.status};
  const profile=object(row?.profile), spans=object(profile?.periods);
  const a=object(spans?.a), b=object(spans?.b), snapshot=profile?.snapshot_id;
  if(row?.status!=="ready"||typeof row.channel!=="string"||typeof snapshot!=="number"||!Number.isSafeInteger(snapshot)
    ||typeof a?.from!=="string"||typeof a.to!=="string"||typeof b?.from!=="string"||typeof b.to!=="string"
    ||!(row.until===null||typeof row.until==="string"))throw new Error("전압 비교 결과를 읽지 못했습니다.");
  const result=parseProfile(profile,asset,row.channel,{a:{from:a.from,to:a.to},b:{from:b.from,to:b.to}});
  const series=result.series[0], level=result.level;
  const names=result.operation?.names;
  if(!names||level===null||level<1||level>names.levels.length||result.series.length!==1||!series.periods.a.quantiles||!series.periods.b.quantiles)
    throw new Error("같은 전류 범위의 비교 결과를 읽지 못했습니다.");
  return {status:"ready",series,periods:result.periods,condition:bandName(names,level),level,snapshot,until:row.until};
}
export function newChangeConversation():string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2,"0")).join("");
}
export async function readChangeDiscussion(asset:string,key:string,conversation:string,signal:AbortSignal,scope:PlaybackScope|null=null):Promise<ChangeDiscussion[]> {
  const response=await fetch("/api/v1/phm/change-explanations?"+new URLSearchParams({asset_id:asset,change_id:key,conversation_id:conversation,...scopeParams(scope)}),{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){await response.body?.cancel().catch(()=>{});throw new Error("선택한 변화의 조사 내용을 불러오지 못했습니다.");}
  const root=object(await response.json());
  if(root?.schema_version!==1||root.asset_id!==asset||root.change_id!==key||root.conversation_id!==conversation||!Array.isArray(root.explanations)||root.explanations.length>10)
    throw new Error("다른 변화의 조사 내용은 보여 드릴 수 없습니다.");
  return root.explanations.map((raw:unknown)=>{
    const row=object(raw),context=object(row?.context),answer=object(row?.answer);
    if(!row||context?.asset_id!==asset||context.change_id!==key||context.conversation_id!==conversation||typeof row.id!=="string"||typeof context.question!=="string"
      ||!["pending","complete","failed"].includes(String(row.status)))throw new Error("조사 내용의 대상을 확인하지 못했습니다.");
    if(row.status==="complete"&&typeof answer?.summary!=="string")throw new Error("답을 읽지 못했습니다.");
    return {id:row.id,question:context.question,pointed:typeof context.pointed==="string"?context.pointed:null,status:row.status as ChangeDiscussion["status"],
      answer:typeof answer?.summary==="string"?{summary:answer.summary}:null,comparison:loadComparison(answer?.load_comparison,asset),
      analysis:typeof answer?.analysis==="string"?answer.analysis:null,
      answerView:typeof context.answer_view==="string"?context.answer_view:null,
      answerScope:typeof context.analysis_scope==="string"?context.analysis_scope:null};
  });
}
/** 질문 하나를 보낸다. parent는 이어 묻는 앞 답: AI는 그 대화를 이어 읽는다. */
/** 그래프에서 짚은 곳: 전력은 시각(ms), 진동은 측정 번호. 서버에는 시각을 ISO로, 측정 번호를 정수로 보낸다. */
export type Pointed={at:number;axis:"time"|"acquisition";label:string};
/** 대화가 이어지는 분석 화면 링크: 그 화면에서도 같은 대화를 잇는다(주소의 chat). */
export function withConversation(href:string,conversation:string):string{
  const url=new URL(href,"http://local");url.searchParams.set("chat",conversation);
  return url.pathname+url.search+url.hash;
}
/** 주소에 실린 대화(분석 화면으로 이어 온 것). 없으면 새 대화를 연다. */
export function carriedConversation(search:string):string|null{
  const value=new URLSearchParams(search).get("chat");
  return value&&/^[0-9a-f]{32}$/.test(value)?value:null;
}
function compactReadout(readout:AnalysisReadout):string {
  const bounded:AnalysisReadout={};
  const encoder=new TextEncoder();
  for(const [label,value] of Object.entries(readout).slice(0,8)){
    const key=label.slice(0,100);
    bounded[key]=value.slice(0,180);
    if(encoder.encode(JSON.stringify(bounded)).length>1550){delete bounded[key];break;}
  }
  return JSON.stringify(bounded);
}
export async function askChange(asset:string,key:string,conversation:string,question:string,parent:string|null,signal:AbortSignal,scope:PlaybackScope|null=null,compareLoad=false,pointed:Pointed|null=null,view:string|null=null,readout:AnalysisReadout|null=null):Promise<void> {
  const at=pointed?(pointed.axis==="time"?new Date(pointed.at).toISOString():String(Math.round(pointed.at))):null;
  const reply=await postWrite("/api/v1/phm/explanations/request",{asset_id:asset,change_id:key,conversation_id:conversation,question,...scopeParams(scope),...(parent?{parent_id:parent}:{}),...(compareLoad?{analysis:"same_load"}:{}),...(at?{at}:{}),...(view?{view}:{}),...(view&&readout?{view_snapshot:compactReadout(readout)}:{})},signal);
  if(typeof reply.explanation_id!=="string"||reply.status!=="pending"||reply.change_id!==key)throw new Error("질문 접수 결과를 확인하지 못했습니다. 다시 불러오세요.");
}
