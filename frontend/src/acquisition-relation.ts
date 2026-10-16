/** Server-owned two-feature relationship for identical recorded acquisitions. */
import {validateSpans, type Spans} from "./spectrum.ts";
import type {FeatureSource} from "./acquisition-profile.ts";

export type AcquisitionPair = {ordinal:number;x:number;y:number};
export type AcquisitionPairGroup = {
  period:"a"|"b";sourceId:string;bindingId:string;analyzed:number;
  pairs:number;pearson:number|null;spearman:number|null;sampled:boolean;
  points:AcquisitionPair[];
};
export type AcquisitionRelation = {
  assetId:string;sourceId:string;bindingId:string;x:string;y:string;
  spans:Spans;groups:AcquisitionPairGroup[];
};
export class AcquisitionRelationUnavailable extends Error {}
function rec(raw:unknown):Record<string,unknown>|null {
  return raw!==null&&typeof raw==="object"&&!Array.isArray(raw)
    ? raw as Record<string,unknown>:null;
}
function count(raw:unknown):number {
  if(typeof raw!=="number"||!Number.isSafeInteger(raw)||raw<0)
    throw new Error("획득 관계의 회차·건수가 유효하지 않습니다.");
  return raw;
}
function finite(raw:unknown):number {
  if(typeof raw!=="number"||!Number.isFinite(raw))
    throw new Error("획득 관계 측정값이 유효하지 않습니다.");
  return raw;
}
function coefficient(raw:unknown):number|null {
  if(raw===null)return null;
  const value=finite(raw);
  if(Math.abs(value)>1.000001)throw new Error("획득 특징 관계 계수가 유효하지 않습니다.");
  return value;
}
export function parseAcquisitionRelation(
  payload:unknown,assetId:string,source:FeatureSource,x:string,y:string,spans:Spans,
):AcquisitionRelation {
  validateSpans(spans);
  const root=rec(payload);
  if(!root||root.schema_version!==1||root.asset_id!==assetId
    ||root.kind!=="acquisition"||root.pairing!=="same-acquisition"
    ||root.x!==x||root.y!==y||x===y||!Array.isArray(root.groups)
    ||root.groups.length!==2||source.assetId!==assetId
    ||!source.features.some(f=>f.id===x)||!source.features.some(f=>f.id===y))
    throw new Error("획득 특징·설비 또는 동일 회차 관계 계약이 일치하지 않습니다.");
  const seen=new Set<string>();
  const groups:AcquisitionPairGroup[]=root.groups.map((raw:unknown)=>{
    const group=rec(raw);
    if(!group||(group.period!=="a"&&group.period!=="b")
      ||group.source_id!==source.sourceId||group.binding_id!==source.bindingId
      ||group.measurement_point_id!==null||!Array.isArray(group.points)
      ||typeof group.sampled!=="boolean")
      throw new Error("관계 분석의 출처·binding·측정 축 근거가 일치하지 않습니다.");
    const period=group.period as "a"|"b";
    if(seen.has(period))throw new Error("관계 분석 구간이 중복됐습니다.");
    seen.add(period);
    const {from,to}=spans[period];
    let previous=from-1;
    const points=group.points.map((raw:unknown):AcquisitionPair=>{
      if(!Array.isArray(raw)||raw.length!==3)
        throw new Error("획득 특징 짝의 구조가 올바르지 않습니다.");
      const ordinal=count(raw[0]);
      if(ordinal<from||ordinal>to||ordinal<=previous)
        throw new Error("요청 범위 밖 또는 순서가 잘못된 획득 회차입니다.");
      previous=ordinal;
      return {ordinal,x:finite(raw[1]),y:finite(raw[2])};
    });
    const analyzed=count(group.analyzed_count),pairs=count(group.pair_count);
    if(pairs>analyzed||points.length>pairs
      ||count(group.x_usable_count)!==pairs||count(group.y_usable_count)!==pairs)
      throw new Error("관계 계산 건수와 그래프 근거가 일치하지 않습니다.");
    const pearson=coefficient(group.pearson),spearman=coefficient(group.spearman);
    if(pairs===0&&(pearson!==null||spearman!==null))
      throw new Error("측정 짝이 없는데 관계 계수가 반환됐습니다.");
    return {period,sourceId:source.sourceId,bindingId:source.bindingId,
      analyzed,pairs,pearson,spearman,sampled:group.sampled,points};
  });
  if(!seen.has("a")||!seen.has("b"))throw new Error("비교 구간이 누락됐습니다.");
  return {assetId,sourceId:source.sourceId,bindingId:source.bindingId,x,y,spans,groups};
}
export async function readAcquisitionRelation(
  assetId:string,source:FeatureSource,x:string,y:string,spans:Spans,signal:AbortSignal,
):Promise<AcquisitionRelation> {
  validateSpans(spans);
  if(x===y||!source.features.some(f=>f.id===x)||!source.features.some(f=>f.id===y))
    throw new Error("동일 출처의 서로 다른 두 획득 특징을 선택하세요.");
  for(const name of ["a","b"] as const)
    if(spans[name].from<source.first||spans[name].to>source.last)
      throw new Error("서버에 저장된 획득 회차 범위 안에서 선택하세요.");
  const query=new URLSearchParams({
    asset_id:assetId,kind:"acquisition",x,y,
    a_from:String(spans.a.from),a_to:String(spans.a.to),
    b_from:String(spans.b.from),b_to:String(spans.b.to),
  });
  const response=await fetch("/api/v1/explore/relation?"+query,
    {signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404){
    const body:unknown=await response.json().catch(()=>null);
    if(rec(body)?.error==="nothing_to_explore")
      throw new AcquisitionRelationUnavailable("선택한 설비에 획득 관계 분석 근거가 없습니다.");
  }
  if(!response.ok)
    throw new Error("획득 특징 관계 조회 실패입니다. 저장 근거 없음과는 다릅니다.");
  return parseAcquisitionRelation(await response.json() as unknown,assetId,source,x,y,spans);
}
