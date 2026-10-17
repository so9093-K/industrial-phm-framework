/** Human review writes shared by every review subject: one status policy, one note rule
 * and one way to tell a refused write from one whose outcome is unknown. */
import {readWriteSession} from "./session.ts";

export type ReviewStatus="open"|"acknowledged"|"closed";
export type ReviewAction="note"|"acknowledge"|"close";
export type ReviewEvent={eventId:string;action:ReviewAction;note:string;recordedAt:string};

export class ReviewConflict extends Error {}
export class ReviewNotFound extends Error {}
export class OutcomeUnknown extends Error {}
export class WriteForbidden extends Error {}

/** One authoritative OPEN → ACKNOWLEDGED → CLOSED policy, replayed to reject a status
 * that its own append-only events cannot produce. */
export function nextReviewStatus(status:ReviewStatus,action:ReviewAction):ReviewStatus{
  if(status==="closed")throw new Error("완료된 검토에는 기록을 더할 수 없습니다.");
  if(action==="note")return status;
  if(action==="acknowledge"&&status==="open")return "acknowledged";
  if(action==="close"&&status==="acknowledged")return "closed";
  throw new Error("검토 상태 전이가 올바르지 않습니다.");
}

export function reviewNote(action:ReviewAction,raw:string):string{
  const note=action==="note"?raw.trim():"";
  if(action==="note"&&!note)throw new Error("메모를 입력하세요.");
  if(note.length>1000||new TextEncoder().encode(note).length>2048)
    throw new Error("메모는 1000자(UTF-8 2048바이트) 이내로 입력하세요.");
  if(/[\u0000-\u0008\u000b-\u001f]/.test(note))throw new Error("메모에 제어 문자를 사용할 수 없습니다.");
  return note;
}

export const REQUEST_ID=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function object(raw:unknown):Record<string,unknown>|null{
  return raw!==null&&typeof raw==="object"&&!Array.isArray(raw)?raw as Record<string,unknown>:null;
}

/** Status codes every review write shares. A caller maps its own subject-specific
 * refusals (such as changed evidence) before falling back to this. */
export async function writeFailure(response:Response,body:Record<string,unknown>|null):Promise<never>{
  const code=typeof body?.error==="string"?body.error:"";
  if(response.status===503&&code==="command_outcome_unknown")
    throw new OutcomeUnknown("요청이 처리됐는지 확인하지 못했습니다.");
  if(response.status===403)
    throw new WriteForbidden("기록 권한이 확인되지 않았습니다. 새로고침한 뒤 다시 시도하세요.");
  if(response.status===409)throw new ReviewConflict("검토 상태가 이미 바뀌었습니다.");
  if(response.status===404)
    throw new ReviewNotFound("검토 대상을 찾을 수 없습니다. 다른 기록으로 대신하지 않습니다.");
  throw new Error("처리 결과를 확인하지 못했습니다. 같은 작업을 다시 시도해도 기록이 겹치지 않습니다.");
}

/** POST through the supervisor session; only its CSRF token makes a write possible. */
export async function postReviewWrite(
  url:string,payload:object,signal:AbortSignal,
  refuse:(response:Response,body:Record<string,unknown>|null)=>void=()=>{},
):Promise<Record<string,unknown>>{
  const session=await readWriteSession(signal);
  if(!session.csrf)
    throw new WriteForbidden("보기 전용이라 검토를 요청하거나 기록을 남길 수 없습니다.");
  const response=await fetch(url,{method:"POST",signal,cache:"no-store",credentials:"same-origin",
    headers:{"Content-Type":"application/json","X-CSRF-Token":session.csrf},
    body:JSON.stringify(payload)});
  if(!response.ok){
    const body=object(await response.json().catch(()=>null));
    refuse(response,body);
    await writeFailure(response,body);
  }
  const result=object(await response.json().catch(()=>null));
  if(!result||result.schema_version!==1)
    throw new OutcomeUnknown("처리 응답을 해석하지 못했습니다.");
  return result;
}
