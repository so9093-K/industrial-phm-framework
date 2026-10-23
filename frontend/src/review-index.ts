/** Server-owned, paged discovery of assets with stored human-review subjects. */
export type ReviewAssetIndex={assets:string[];totalAssets:number;nextAfter:string|null};

export function parseReviewAssetIndex(raw:unknown):ReviewAssetIndex {
  const row=raw!==null&&typeof raw==="object"&&!Array.isArray(raw)
    ?raw as Record<string,unknown>:null;
  if(!row||row.schema_version!==1
    ||row.meaning!=="stored-human-review-asset-identities-not-health"
    ||!Array.isArray(row.asset_ids)||row.asset_ids.length>20
    ||typeof row.total_assets!=="number"||!Number.isSafeInteger(row.total_assets)
    ||row.total_assets<row.asset_ids.length)throw new Error("검토 대상 목록의 형식이 올바르지 않습니다.");
  const assets=row.asset_ids as unknown[];
  if(assets.some(id=>typeof id!=="string"||!id||id.length>512||/[\x00-\x1f]/.test(id))
    ||new Set(assets).size!==assets.length
    ||assets.some((id,i)=>i>0 && String(assets[i-1])>=String(id)))
    throw new Error("검토 설비의 식별자 또는 정렬이 올바르지 않습니다.");
  const cursor=row.next_after;
  if(cursor!==null&& (typeof cursor!=="string"||cursor!==assets.at(-1)))
    throw new Error("검토 목록의 다음 페이지가 올바르지 않습니다.");
  return {assets:assets as string[],totalAssets:row.total_assets,nextAfter:cursor as string|null};
}

export async function readReviewAssetIndex(signal:AbortSignal,after:string|null=null):Promise<ReviewAssetIndex> {
  const params=after===null?"":("?"+new URLSearchParams({after_asset:after}));
  const response=await fetch("/api/v1/review-inbox/assets"+params,
    {signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error("저장된 검토 설비 목록을 조회하지 못했습니다.");
  }
  return parseReviewAssetIndex(await response.json() as unknown);
}
