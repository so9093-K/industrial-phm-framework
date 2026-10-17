/** Every browser write goes through the supervisor session's CSRF token. This tells a
 * refused write, a forbidden one and one whose outcome is unknown apart; callers map the
 * refusals that mean something for their own subject. */
import {readWriteSession} from "./session.ts";

/** The supervisor may or may not have committed the write. */
export class OutcomeUnknown extends Error {}
export class WriteForbidden extends Error {}
/** The server refused the write and kept nothing; `code` is the server's reason. */
export class WriteRejected extends Error {
  readonly status:number;
  readonly code:string;
  constructor(status:number,code:string){
    super("요청이 거부됐습니다 ("+status+" "+code+").");
    this.status=status;this.code=code;
  }
}

export function object(raw:unknown):Record<string,unknown>|null{
  return raw!==null&&typeof raw==="object"&&!Array.isArray(raw)?raw as Record<string,unknown>:null;
}

/** Writes answer `{"error":{"code":…}}`; some reads answer `{"error":"…"}`. */
export function errorCode(body:unknown):string{
  const error=object(body)?.error;
  if(typeof error==="string")return error;
  const code=object(error)?.code;
  return typeof code==="string"?code:"";
}

export async function postWrite(url:string,payload:object,signal:AbortSignal):Promise<Record<string,unknown>>{
  const session=await readWriteSession(signal);
  if(!session.csrf)throw new WriteForbidden("보기 전용이라 바꿀 수 없습니다. 운영을 시작하면 바꿀 수 있습니다.");
  let response:Response;
  try{
    response=await fetch(url,{method:"POST",signal,cache:"no-store",credentials:"same-origin",
      headers:{"Content-Type":"application/json","X-CSRF-Token":session.csrf},body:JSON.stringify(payload)});
  }catch(cause:unknown){
    if(signal.aborted)throw cause;
    // The request may have reached the server before the connection failed.
    throw new OutcomeUnknown("요청이 처리됐는지 확인하지 못했습니다.");
  }
  if(!response.ok){
    const code=errorCode(await response.json().catch(()=>null));
    if(response.status===503&&code==="command_outcome_unknown")
      throw new OutcomeUnknown("요청이 처리됐는지 확인하지 못했습니다.");
    if(response.status===403)
      throw new WriteForbidden("기록 권한이 확인되지 않았습니다. 새로고침한 뒤 다시 시도하세요.");
    throw new WriteRejected(response.status,code);
  }
  const result=object(await response.json().catch(()=>null));
  if(!result||result.schema_version!==1)throw new OutcomeUnknown("처리 응답을 해석하지 못했습니다.");
  return result;
}
