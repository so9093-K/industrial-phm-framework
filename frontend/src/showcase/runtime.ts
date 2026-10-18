/** Static showcase only. Production never imports this transport.
 * Exact recorded GETs are replayed. Unknown selections and every write fail closed.
 */
type Recorded = {status:number;body:unknown};
type Snapshot = {schema_version:number;responses:Record<string,Recorded>};

export function requestKey(url:URL):string {
  const pairs=[...url.searchParams.entries()].sort(([ak,av],[bk,bv])=>ak.localeCompare(bk)||av.localeCompare(bv));
  const query=new URLSearchParams(pairs).toString();
  return url.pathname+(query?"?"+query:"");
}

export function snapshotResponse(snapshot:Snapshot,url:URL,method:string):Recorded {
  if(method!=="GET")return {status:403,body:{error:{code:"showcase_read_only"}}};
  return snapshot.responses[requestKey(url)]??{status:404,body:{error:{code:"showcase_selection_not_recorded"}}};
}

export async function installSnapshot():Promise<void>{
  const network=window.fetch.bind(window);
  const result=await network("./scenario/responses.json");
  if(!result.ok)throw new Error("체험 데이터 파일을 불러오지 못했습니다.");
  const snapshot=await result.json() as Snapshot;
  if(snapshot.schema_version!==1||!snapshot.responses)throw new Error("체험 데이터 형식을 확인하세요.");
  window.fetch=async(input,init)=>{
    const url=new URL(input instanceof Request?input.url:String(input),location.href);
    if(url.origin!==location.origin||!url.pathname.startsWith("/api/"))return network(input,init);
    const signal=init?.signal??(input instanceof Request?input.signal:null);
    signal?.throwIfAborted();
    const response=snapshotResponse(snapshot,url,(init?.method??(input instanceof Request?input.method:"GET")).toUpperCase());
    if(response.status===404)window.dispatchEvent(new CustomEvent("showcase-unavailable",{detail:requestKey(url)}));
    return new Response(JSON.stringify(response.body),{status:response.status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
  };
}
