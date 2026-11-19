import {object,postWrite} from "./writes.ts";
export const CHANGE_ACTIONS=["compare","spectrum","onset","model"] as const;
export type ChangeAction=typeof CHANGE_ACTIONS[number];
export type ChangeAnswer={summary:string;actions:ChangeAction[];source:"model"|"computed"};
export type ChangeDiscussion={id:string;question:string;status:"pending"|"complete"|"failed";answer:ChangeAnswer|null};
export async function readChangeDiscussion(asset:string,key:string,signal:AbortSignal):Promise<ChangeDiscussion[]> {
  const response=await fetch("/api/v1/phm/change-explanations?"+new URLSearchParams({asset_id:asset,change_id:key}),{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){await response.body?.cancel().catch(()=>{});throw new Error("선택한 변화의 조사 내용을 불러오지 못했습니다.");}
  const root=object(await response.json());
  if(root?.schema_version!==1||root.asset_id!==asset||root.change_id!==key||!Array.isArray(root.explanations)||root.explanations.length>10)
    throw new Error("다른 변화의 조사 내용은 보여 드릴 수 없습니다.");
  return root.explanations.map((raw:unknown)=>{
    const row=object(raw),context=object(row?.context),answer=object(row?.answer);
    if(!row||context?.asset_id!==asset||context.change_id!==key||typeof row.id!=="string"||typeof context.question!=="string"
      ||!["pending","complete","failed"].includes(String(row.status)))throw new Error("조사 내용의 대상을 확인하지 못했습니다.");
    if(answer&&(typeof answer.summary!=="string"||!Array.isArray(answer.actions)||answer.actions.some(a=>!CHANGE_ACTIONS.includes(a as ChangeAction))||!["model","computed"].includes(String(answer.source))))
      throw new Error("조사 설명의 다음 분석을 확인하지 못했습니다.");
    return {id:row.id,question:context.question,status:row.status as ChangeDiscussion["status"],answer:answer as ChangeAnswer|null};
  });
}
export async function askChange(asset:string,key:string,question:string,parent:string|null,signal:AbortSignal):Promise<void> {
  const reply=await postWrite("/api/v1/phm/explanations/request",{asset_id:asset,change_id:key,question,...(parent?{parent_id:parent}:{})},signal);
  if(typeof reply.explanation_id!=="string"||reply.status!=="pending"||reply.change_id!==key)throw new Error("질문 접수 결과를 확인하지 못했습니다. 다시 불러오세요.");
}
