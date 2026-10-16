/** Exact persisted AnalysisRun/Evidence ↔ Finding review identities from one monitor snapshot. */
export type Evidence = {
  runId: string; evidenceId: string; assetId: string;
  sourceId: string; pointId: string | null; capabilityId: string;
  kind: "phase" | "file";
  completedAt: string | null; quality: string | null;
};
export type Review = {
  findingId: string; assetId: string; runId: string;
  status: "open" | "acknowledged" | "closed";
  evidenceIds: string[];
  linked: Evidence[];
  missing: string[];
};
export type ReviewInbox = {
  available: boolean;
  evidenceComplete: boolean;
  partial: boolean;
  reviews: Review[];
};
function rec(raw:unknown):Record<string,unknown>|null {
  return raw!==null && typeof raw==="object" && !Array.isArray(raw)
    ? raw as Record<string,unknown>:null;
}
function id(raw:unknown):string {
  if(typeof raw!=="string" || !raw || raw.length>512)
    throw new Error("저장 검토 근거의 식별자가 올바르지 않습니다.");
  return raw;
}
function collection(root:Record<string,unknown>,key:string):{items:unknown[];truncated:boolean}|null{
  if(root[key]===undefined)return null;
  const raw=rec(root[key]);
  if(!raw||!Array.isArray(raw.items)||typeof raw.truncated!=="boolean")
    throw new Error("서버의 검토·분석 근거 목록을 확인할 수 없습니다.");
  return {items:raw.items,truncated:raw.truncated};
}
export function parseReviewInbox(payload:unknown):ReviewInbox {
  const root=rec(payload);
  if(!root)throw new Error("검토 정보의 응답이 올바르지 않습니다.");
  const reviews=collection(root,"review_requests");
  const phase=collection(root,"phase_unbalance_analyses");
  const file=collection(root,"file_feature_analyses");
  if(!reviews)return {available:false,evidenceComplete:false,partial:true,reviews:[]};
  const evidenceComplete=phase!==null && file!==null && !phase.truncated && !file.truncated;
  const errorScopes=root.system_error_scopes;
  const scopesOk=Array.isArray(errorScopes)&&errorScopes.length===0;
  const evidence=new Map<string,Evidence>();
  for(const [kind,group] of [["phase",phase],["file",file]] as const){
    for(const raw of group?.items??[]){
      const item=rec(raw);
      if(!item)throw new Error("분석 근거 구조가 올바르지 않습니다.");
      const runId=id(item.analysis_run_id),evidenceId=id(item.evidence_id);
      const assetId=id(item.asset_id), sourceId=id(item.source_id);
      const key=JSON.stringify([runId,evidenceId,assetId]);
      if(evidence.has(key))throw new Error("중복된 분석 근거를 검토 대상에 사용할 수 없습니다.");
      evidence.set(key,{
        runId,evidenceId,assetId,sourceId,
        pointId:item.measurement_point_id===null?null:id(item.measurement_point_id),
        capabilityId:id(item.capability_id),kind,
        completedAt:typeof item.completed_at==="string"?item.completed_at:null,
        quality:typeof rec(item.data_quality)?.state==="string"
          ? rec(item.data_quality)!.state as string:null,
      });
    }
  }
  const unique=new Set<string>();
  const parsed=reviews.items.map((raw:unknown):Review=>{
    const value=rec(raw);
    if(!value||!["open","acknowledged","closed"].includes(String(value.status))
      || !Array.isArray(value.evidence_ids))
      throw new Error("검토 상태 또는 참조 근거를 확인할 수 없습니다.");
    const findingId=id(value.finding_id),assetId=id(value.asset_id);
    const runId=id(value.analysis_run_id);
    if(unique.has(findingId))throw new Error("중복된 검토 식별자가 반환됐습니다.");
    unique.add(findingId);
    const evidenceIds=value.evidence_ids.map(id);
    if(!evidenceIds.length || new Set(evidenceIds).size!==evidenceIds.length)
      throw new Error("검토의 원본 근거 목록이 누락 또는 중복됐습니다.");
    const linked:Evidence[]=[],missing:string[]=[];
    for(const evidenceId of evidenceIds){
      const item=evidence.get(JSON.stringify([runId,evidenceId,assetId]));
      if(item)linked.push(item);else missing.push(evidenceId);
    }
    return {findingId,assetId,runId,
      status:value.status as Review["status"],evidenceIds,linked,missing};
  });
  return {
    available:true,evidenceComplete,
    partial:reviews.truncated || !evidenceComplete || !scopesOk,
    reviews:parsed,
  };
}
