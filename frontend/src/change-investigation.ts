import {scopeParams, type PlaybackScope} from "./record-playback.ts";
import {object,postWrite} from "./writes.ts";
/** AI의 답: 사람에게 말하듯 쓴 몇 문장. */
export type ChangeAnswer={summary:string};
/** 대화를 여는 짧은 질문: 사람이 실제로 묻는 말 그대로 보내고 그대로 보인다. */
export const STARTERS=["문제 있어?","이 변화가 왜 생겼을까?","기록 끝까지 이어졌어?"];
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
      answer:answer?{summary:answer.summary as string}:null};
  });
}
/** 질문 하나를 보낸다. parent는 이어 묻는 앞 답: AI는 그 대화를 이어 읽는다. */
export async function askChange(asset:string,key:string,question:string,parent:string|null,signal:AbortSignal,scope:PlaybackScope|null=null):Promise<void> {
  const reply=await postWrite("/api/v1/phm/explanations/request",{asset_id:asset,change_id:key,question,...scopeParams(scope),...(parent?{parent_id:parent}:{})},signal);
  if(typeof reply.explanation_id!=="string"||reply.status!=="pending"||reply.change_id!==key)throw new Error("질문 접수 결과를 확인하지 못했습니다. 다시 불러오세요.");
}
