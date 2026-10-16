/** One acquisition feature across two ordinal ranges. No clock or equipment-health inference. */
import {validateSpans, type Spans} from "./spectrum.ts";

export type FeatureOption = {id:string;label:string};
export type FeatureSource = {
  assetId:string;sourceId:string;bindingId:string;
  first:number;last:number;count:number;features:FeatureOption[];
};
export type FeaturePeriod = {
  delivered:number;usable:number;analyzed:number;missingAcquisitions:number;
  unanalyzed:number;sampled:boolean;
  median:number|null;mean:number|null;firstOrdinal:number|null;lastOrdinal:number|null;
};
export type FeatureProfile = {
  assetId:string;sourceId:string;bindingId:string;featureId:string;label:string;
  spans:Spans;a:FeaturePeriod;b:FeaturePeriod;
  medianChange:number|null;outsidePercent:number|null;
};
export class FeatureEvidenceUnavailable extends Error {}

function obj(raw:unknown):Record<string,unknown>|null {
  return raw!==null&&typeof raw==="object"&&!Array.isArray(raw)
    ? raw as Record<string,unknown>:null;
}
function name(raw:unknown):string {
  if(typeof raw!=="string"||!raw||raw.length>512)
    throw new Error("획득 특징의 원본 식별자가 잘못됐습니다.");
  return raw;
}
function count(raw:unknown):number {
  if(typeof raw!=="number"||!Number.isSafeInteger(raw)||raw<0)
    throw new Error("획득 특징의 분석 건수가 잘못됐습니다.");
  return raw;
}
function maybeCount(raw:unknown):number|null {
  return raw===null?null:count(raw);
}
function finiteOrNull(raw:unknown):number|null {
  if(raw===null)return null;
  if(typeof raw!=="number"||!Number.isFinite(raw))
    throw new Error("분석 특징의 수치가 올바르지 않습니다.");
  return raw;
}
function parsePeriod(raw:unknown):FeaturePeriod {
  const p=obj(raw);
  if(!p||typeof p.sampled!=="boolean")
    throw new Error("서버의 획득 회차별 집계가 완전하지 않습니다.");
  let median:number|null=null;
  if(p.quantiles!==null){
    if(!Array.isArray(p.quantiles)||p.quantiles.length!==5)
      throw new Error("특징 분포 분위수가 올바르지 않습니다.");
    const q=p.quantiles.map(finiteOrNull);
    if(q.some(v=>v===null))throw new Error("특징 분위수에 결측 값이 있습니다.");
    median=q[2];
  }
  const delivered=count(p.observation_count),usable=count(p.usable_count);
  const analyzed=count(p.analyzed_count),missingAcquisitions=count(p.missing_count);
  const unanalyzed=count(p.unanalyzed_count);
  if(usable>analyzed||analyzed>delivered)
    throw new Error("서버의 특징 분석·수신 회차 건수가 모순됩니다.");
  if(usable===0&&median!==null)
    throw new Error("유효한 특징이 없는데 중앙값이 반환됐습니다.");
  return {delivered,usable,analyzed,missingAcquisitions,unanalyzed,
    sampled:p.sampled,median,mean:finiteOrNull(p.mean),
    firstOrdinal:maybeCount(p.first_position),lastOrdinal:maybeCount(p.last_position)};
}
export function parseFeatureSource(raw:unknown,assetId:string):FeatureSource|null {
  const root=obj(raw),acq=obj(root?.acquisition);
  if(root?.schema_version!==1||root.asset_id!==assetId)
    throw new Error("선택한 설비와 획득 원본 목록이 일치하지 않습니다.");
  if(root.acquisition===null)return null;
  if(!acq||!Array.isArray(acq.features))
    throw new Error("획득 특징 목록을 조회할 수 없습니다.");
  const first=count(acq.first),last=count(acq.last);
  if(last<first)throw new Error("획득 회차 범위가 올바르지 않습니다.");
  const features=acq.features.map((raw:unknown):FeatureOption=>{
    const item=obj(raw);
    if(!item)throw new Error("원본 특징 목록이 올바르지 않습니다.");
    return {id:name(item.key),label:name(item.label)};
  });
  if(new Set(features.map(f=>f.id)).size!==features.length)
    throw new Error("특징 목록에 중복 식별자가 있습니다.");
  return {assetId,sourceId:name(acq.source_id),bindingId:name(acq.binding_id),
    first,last,count:count(acq.count),features};
}
export function parseFeatureProfile(
  raw:unknown,assetId:string,source:FeatureSource,featureId:string,spans:Spans,
):FeatureProfile {
  validateSpans(spans);
  const root=obj(raw),periods=obj(root?.periods),a0=obj(periods?.a),b0=obj(periods?.b);
  if(!root||root.schema_version!==1||root.asset_id!==assetId||root.kind!=="acquisition"
    ||root.meaning!=="stored-measurements-compared-not-asset-health"
    ||!a0||!b0||!Array.isArray(root.series)||root.series.length!==1)
    throw new Error("선택한 설비·획득 방식과 서버 특징 집계가 일치하지 않습니다.");
  if(count(a0.from)!==spans.a.from||count(a0.to)!==spans.a.to
    ||count(b0.from)!==spans.b.from||count(b0.to)!==spans.b.to)
    throw new Error("요청한 획득 회차와 반환된 계산 기간이 다릅니다.");
  const row=obj(root.series[0]),byPeriod=obj(row?.periods),compare=obj(row?.comparison);
  if(!row||!byPeriod||!compare||row.kind!=="acquisition"
    ||row.key!==featureId||row.source_id!==source.sourceId
    ||row.binding_id!==source.bindingId)
    throw new Error("다른 출처·binding·특징의 결과를 섞을 수 없습니다.");
  const a=parsePeriod(byPeriod.a),b=parsePeriod(byPeriod.b);
  const change=finiteOrNull(compare.median_change);
  if((a.median===null||b.median===null)&&change!==null)
    throw new Error("중앙값 근거가 없는 차이를 표시할 수 없습니다.");
  const outside=compare.b_outside_a_band_percent===undefined?null:
    finiteOrNull(compare.b_outside_a_band_percent);
  if(outside!==null&&(outside<0||outside>100))
    throw new Error("기준 분포 이탈 비율이 유효하지 않습니다.");
  return {assetId,sourceId:source.sourceId,bindingId:source.bindingId,
    featureId,label:typeof row.label==="string"?row.label:featureId,
    spans,a,b,medianChange:change,outsidePercent:outside};
}
async function get(path:string,signal:AbortSignal):Promise<unknown>{
  const response=await fetch(path,{signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404){
    const body:unknown=await response.json().catch(()=>null);
    if(obj(body)?.error==="nothing_to_explore")
      throw new FeatureEvidenceUnavailable("해당 획득 특징의 저장 근거가 없습니다.");
  }
  if(!response.ok)
    throw new Error("획득 특징 데이터 조회 실패입니다. 자료 없음 또는 정상 설비를 의미하지 않습니다.");
  return await response.json() as unknown;
}
export async function loadFeatureSource(assetId:string,signal:AbortSignal):Promise<FeatureSource|null>{
  return parseFeatureSource(await get(
    "/api/v1/explore/sources?"+new URLSearchParams({asset_id:assetId}),signal),assetId);
}
export async function loadFeatureProfile(
  assetId:string,source:FeatureSource,featureId:string,spans:Spans,signal:AbortSignal,
):Promise<FeatureProfile>{
  validateSpans(spans);
  const params=new URLSearchParams({
    asset_id:assetId,kind:"acquisition",series:featureId,
    a_from:String(spans.a.from),a_to:String(spans.a.to),
    b_from:String(spans.b.from),b_to:String(spans.b.to),
  });
  return parseFeatureProfile(await get("/api/v1/explore/profile?"+params,signal),
    assetId,source,featureId,spans);
}
