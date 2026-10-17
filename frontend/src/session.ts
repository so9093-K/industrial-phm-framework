/** The server session decides who may write; the browser only forwards its CSRF token. */
export type WriteSession={writable:boolean;csrf:string|null};

function object(raw:unknown):Record<string,unknown>|null{
  return raw!==null&&typeof raw==="object"&&!Array.isArray(raw)?raw as Record<string,unknown>:null;
}

/** Only the supervisor-owned scope may write. A preview or demo session stays read-only
 * even when it reports a token. */
export function parseWriteSession(raw:unknown):WriteSession{
  const session=object(raw);
  if(!session||session.schema_version!==1)
    throw new Error("쓰기 권한 세션을 확인할 수 없습니다.");
  const writable=session.can_change===true
    &&session.write_scope==="supervisor-owned-source-control"
    &&typeof session.csrf_token==="string"&&session.csrf_token.length>=16;
  return {writable,csrf:writable?session.csrf_token as string:null};
}

export async function readWriteSession(signal:AbortSignal):Promise<WriteSession>{
  const response=await fetch("/api/v1/session",{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok)throw new Error("쓰기 권한 세션을 확인할 수 없습니다.");
  return parseWriteSession(await response.json() as unknown);
}
