/** Human review writes shared by every review subject: one status policy, one note rule
 * and one way to tell a refused write from one whose outcome is unknown. */
import {postWrite,WriteRejected,OutcomeUnknown,WriteForbidden} from "./writes.ts";
export {object,OutcomeUnknown,WriteForbidden} from "./writes.ts";

export type ReviewStatus="open"|"acknowledged"|"closed";
export type ReviewAction="note"|"acknowledge"|"close";
/** What the person concluded on a confirm or close: a recorded judgement, not a fault verdict. */
export type ReviewDecision="inspect"|"observe"|"no-action";
export const DECISIONS:readonly ReviewDecision[]=["inspect","observe","no-action"];
export const DECISION_LABEL:Record<ReviewDecision,string>={inspect:"추가 점검 필요",observe:"계속 관찰","no-action":"점검 불필요"};
export type ReviewEvent={eventId:string;action:ReviewAction;note:string;recordedAt:string;decision:ReviewDecision|null};
/** A stored decision; an unknown value is refused rather than shown as another one. */
export function readDecision(raw:unknown):ReviewDecision|null{
  if(raw===null||raw===undefined)return null;
  if(!DECISIONS.includes(raw as ReviewDecision))throw new Error("검토 판단의 형식이 올바르지 않습니다.");
  return raw as ReviewDecision;
}
/** The latest decision in a review's history: what it was last judged to need. */
export function latestDecision(events:ReviewEvent[]):ReviewDecision|null{
  return [...events].reverse().find(event=>event.decision!==null)?.decision??null;
}

export class ReviewConflict extends Error {}
export class ReviewNotFound extends Error {}

/** One authoritative OPEN → ACKNOWLEDGED → CLOSED policy, replayed to reject a status
 * that its own append-only events cannot produce. */
export function nextReviewStatus(status:ReviewStatus,action:ReviewAction):ReviewStatus{
  if(status==="closed")throw new Error("완료된 검토에는 기록을 더할 수 없습니다.");
  if(action==="note")return status;
  if(action==="acknowledge"&&status==="open")return "acknowledged";
  if(action==="close"&&status==="acknowledged")return "closed";
  throw new Error("검토 상태 전이가 올바르지 않습니다.");
}

/** A note is required for a note event and optional with a confirm or close, where it
 * records why the person decided so. */
export function reviewNote(action:ReviewAction,raw:string):string{
  const note=raw.trim();
  if(action==="note"&&!note)throw new Error("메모를 입력하세요.");
  if(note.length>1000||new TextEncoder().encode(note).length>2048)
    throw new Error("판단 이유는 1000자(한글은 약 680자) 이내로 입력하세요.");
  if(/[\u0000-\u0008\u000b-\u001f]/.test(note))throw new Error("판단 이유에 제어 문자를 사용할 수 없습니다.");
  return note;
}

export const REQUEST_ID=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** POST through the supervisor session; only its CSRF token makes a write possible.
 * `refuse` maps refusals that mean something for one subject before the shared ones. */
export async function postReviewWrite(
  url:string,payload:object,signal:AbortSignal,refuse:(status:number,code:string)=>void=()=>{},
):Promise<Record<string,unknown>>{
  try{
    return await postWrite(url,payload,signal);
  }catch(cause:unknown){
    if(cause instanceof WriteForbidden&&cause.message.startsWith("보기 전용"))
      throw new WriteForbidden("보기 전용이라 검토를 요청하거나 기록을 남길 수 없습니다.");
    if(!(cause instanceof WriteRejected))throw cause;
    refuse(cause.status,cause.code);
    if(cause.status===409)throw new ReviewConflict("검토 상태가 이미 바뀌었습니다.");
    if(cause.status===404)
      throw new ReviewNotFound("검토 대상을 찾을 수 없습니다. 다른 기록으로 대신하지 않습니다.");
    throw new Error("처리 결과를 확인하지 못했습니다. 같은 작업을 다시 시도해도 기록이 겹치지 않습니다.");
  }
}
