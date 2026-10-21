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
  spans:Spans;groups:AcquisitionPairGroup[];xUnit?:string|null;yUnit?:string|null;
};
export class AcquisitionRelationUnavailable extends Error {}
function rec(raw:unknown):Record<string,unknown>|null {
  return raw!==null&&typeof raw==="object"&&!Array.isArray(raw)
    ? raw as Record<string,unknown>:null;
}
function count(raw:unknown):number {
  if(typeof raw!=="number"||!Number.isSafeInteger(raw)||raw<0)
    throw new Error("특징 관계 결과의 측정 순서나 건수가 올바르지 않습니다.");
  return raw;
}
function finite(raw:unknown):number {
  if(typeof raw!=="number"||!Number.isFinite(raw))
    throw new Error("특징 관계 결과의 값이 올바르지 않습니다.");
  return raw;
}
function coefficient(raw:unknown):number|null {
  if(raw===null)return null;
  const value=finite(raw);
  if(Math.abs(value)>1.000001)throw new Error("특징 관계 계수가 올바르지 않습니다.");
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
    throw new Error("받은 결과가 고른 설비·진동 특징과 맞지 않아 표시하지 않았습니다.");
  const seen=new Set<string>();
  const groups:AcquisitionPairGroup[]=root.groups.map((raw:unknown)=>{
    const group=rec(raw);
    if(!group||(group.period!=="a"&&group.period!=="b")
      ||group.source_id!==source.sourceId||group.binding_id!==source.bindingId
      ||group.measurement_point_id!==null||!Array.isArray(group.points)
      ||typeof group.sampled!=="boolean")
      throw new Error("받은 결과의 데이터 출처·적용 모델이 고른 것과 달라 표시하지 않았습니다.");
    const period=group.period as "a"|"b";
    if(seen.has(period))throw new Error("관계 분석 구간이 중복됐습니다.");
    seen.add(period);
    const {from,to}=spans[period];
    let previous=from-1;
    const points=group.points.map((raw:unknown):AcquisitionPair=>{
      if(!Array.isArray(raw)||raw.length!==3)
        throw new Error("특징 짝의 형식이 올바르지 않습니다.");
      const ordinal=count(raw[0]);
      if(ordinal<from||ordinal>to||ordinal<=previous)
        throw new Error("고른 범위 밖이거나 순서가 맞지 않는 측정이 들어 있습니다.");
      previous=ordinal;
      return {ordinal,x:finite(raw[1]),y:finite(raw[2])};
    });
    const analyzed=count(group.analyzed_count),pairs=count(group.pair_count);
    if(pairs>analyzed||points.length>pairs
      ||count(group.x_usable_count)!==pairs||count(group.y_usable_count)!==pairs)
      throw new Error("계산에 쓴 짝 수와 그래프 자료가 맞지 않습니다.");
    const pearson=coefficient(group.pearson),spearman=coefficient(group.spearman);
    if(pairs===0&&(pearson!==null||spearman!==null))
      throw new Error("측정 짝이 없는데 관계 계수가 반환됐습니다.");
    return {period,sourceId:source.sourceId,bindingId:source.bindingId,
      analyzed,pairs,pearson,spearman,sampled:group.sampled,points};
  });
  if(!seen.has("a")||!seen.has("b"))throw new Error("비교 구간이 누락됐습니다.");
  return {assetId,sourceId:source.sourceId,bindingId:source.bindingId,x,y,spans,groups,
    xUnit:typeof root.x_unit==="string"?root.x_unit:null,yUnit:typeof root.y_unit==="string"?root.y_unit:null};
}
export async function readAcquisitionRelation(
  assetId:string,source:FeatureSource,x:string,y:string,spans:Spans,signal:AbortSignal,
):Promise<AcquisitionRelation> {
  validateSpans(spans);
  if(x===y||!source.features.some(f=>f.id===x)||!source.features.some(f=>f.id===y))
    throw new Error("같은 출처에서 서로 다른 두 특징을 고르세요.");
  for(const name of ["a","b"] as const)
    if(spans[name].from<source.first||spans[name].to>source.last)
      throw new Error("저장된 측정 순서 범위 안에서 고르세요.");
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
      throw new AcquisitionRelationUnavailable("이 설비에는 특징 관계를 계산할 진동 측정이 없습니다.");
  }
  if(!response.ok)
    throw new Error("특징 관계를 불러오지 못했습니다. 기록이 없다는 뜻은 아닙니다.");
  return parseAcquisitionRelation(await response.json() as unknown,assetId,source,x,y,spans);
}
