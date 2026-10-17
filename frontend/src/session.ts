/** The server session decides who may write; the browser only forwards its CSRF token. */
/** `example` marks the isolated synthetic sample workspace, which is always read-only. */
export type WriteSession={writable:boolean;csrf:string|null;example:boolean};

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
  return {writable,csrf:writable?session.csrf_token as string:null,example:session.workspace_kind==="synthetic-demo"};
}

export async function readWriteSession(signal:AbortSignal):Promise<WriteSession>{
  const response=await fetch("/api/v1/session",{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok)throw new Error("쓰기 권한 세션을 확인할 수 없습니다.");
  return parseWriteSession(await response.json() as unknown);
}

/** Where the sample workspace returns to: only a page of the same app on a local port. */
export function sampleReturn(search:string):string|null{
  const raw=new URLSearchParams(search).get("return_to");
  if(!raw)return null;
  let url:URL;
  try{url=new URL(raw);}catch{return null;}
  if(url.protocol!=="http:"||url.hostname!=="127.0.0.1"||!/^\d{2,5}$/.test(url.port)
    ||!["/web/","/web-next/"].includes(url.pathname))return null;
  return url.origin+url.pathname+"?page=system";
}
