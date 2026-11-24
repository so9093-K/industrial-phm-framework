import {scopeParams, type PlaybackScope} from "./record-playback.ts";
import {object,postWrite} from "./writes.ts";
/** 답이 근거로 쓴 사실을 화면이 가리킬 수 있는 것으로: 찾은 변화(그래프의 선·구간), 그래프 밖 신호, 운전 수준 띠, 주파수 대역. */
export type Evidence=
  |{fact:string;kind:"change";review_key:string;label:string;before:number|null;after:number|null;unit:string|null;where:string}
  |{fact:string;kind:"signal";label:string;before:number|null;after:number|null;unit:string|null}
  |{fact:string;kind:"operation";label:string;detail:string;levels?:string[];a?:number[];b?:number[];runs?:{from:string;to:string;level:number}[]}
  |{fact:string;kind:"spectrum";label:string;from_hz:number;to_hz:number;a:number;b:number;ratio:number|null};
/** AI의 답: 짧은 문장과, 그 문장이 쓴 사실 중 그래프가 가리킬 수 있는 것. */
export type ChangeAnswer={summary:string;evidence:Evidence[]};
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
/** 대화를 여는 짧은 질문: 사람이 실제로 묻는 말 그대로 보내고 그대로 보인다. */
export const STARTERS=["문제 있어?","왜 그래?","더 커지고 있어?"];
export type ChangeDiscussion={id:string;question:string;status:"pending"|"complete"|"failed";answer:ChangeAnswer|null};
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
    if(answer&&typeof answer.summary!=="string")throw new Error("답을 읽지 못했습니다.");
    return {id:row.id,question:context.question,status:row.status as ChangeDiscussion["status"],
      answer:answer?{summary:answer.summary as string,evidence:readEvidence(answer.evidence)}:null};
  });
}
/** 질문 하나를 보낸다. opening은 대화창 맨 위에 보인 알림(첫 질문에만): AI가 이미 보인 내용을 되풀이하지 않게 한다. */
export async function askChange(asset:string,key:string,question:string,parent:string|null,signal:AbortSignal,scope:PlaybackScope|null=null,opening:string|null=null):Promise<void> {
  const reply=await postWrite("/api/v1/phm/explanations/request",{asset_id:asset,change_id:key,question,...scopeParams(scope),...(parent?{parent_id:parent}:opening?{opening}:{})},signal);
  if(typeof reply.explanation_id!=="string"||reply.status!=="pending"||reply.change_id!==key)throw new Error("질문 접수 결과를 확인하지 못했습니다. 다시 불러오세요.");
}
