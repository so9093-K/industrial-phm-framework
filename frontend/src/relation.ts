/** Paired stored measurements from the authoritative history relation endpoint. */
import {validatePeriods, type Periods} from "./comparison.ts";

export type PairedGroup = {
  id: string;
  period: "a" | "b";
  source: string;
  point: string | null;
  meaning: string;
  xUnit: string | null;
  yUnit: string | null;
  xUsable: number;
  yUsable: number;
  pairCount: number;
  pearson: number | null;
  spearman: number | null;
  sampled: boolean;
  points: {at: string; x: number; y: number}[];
};
export type Relation = { asset: string; x: string; y: string; groups: PairedGroup[] };
export class RelationUnavailable extends Error {}
function rec(raw: unknown): Record<string,unknown> | null {
  return raw !== null && typeof raw === "object" && !Array.isArray(raw)
    ? raw as Record<string,unknown> : null;
}
function string(raw: unknown): string {
  if(typeof raw !== "string" || !raw) throw new Error("두 신호 관계의 식별자가 올바르지 않습니다.");
  return raw;
}
function nonnegative(raw: unknown): number {
  if(typeof raw !== "number" || !Number.isSafeInteger(raw) || raw < 0)
    throw new Error("서버 관계 분석의 건수가 올바르지 않습니다.");
  return raw;
}
function coefficient(raw: unknown): number | null {
  if (raw === null) return null;
  if (typeof raw !== "number" || !Number.isFinite(raw) || Math.abs(raw)>1.000001)
    throw new Error("두 측정의 관계 계수가 올바르지 않습니다.");
  return raw;
}
function time(raw: unknown): string {
  const value=string(raw);
  if(!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)||!Number.isFinite(Date.parse(value)))
    throw new Error("측정 짝의 시각이 올바르지 않습니다.");
  return value;
}
function finite(raw: unknown): number {
  if(typeof raw!=="number"||!Number.isFinite(raw))
    throw new Error("측정 짝의 값이 올바르지 않습니다.");
  return raw;
}
export function parseRelation(payload: unknown, asset: string, x: string, y: string): Relation {
  const data=rec(payload);
  if(!data || data.schema_version!==1 || data.asset_id!==asset || data.kind!=="history"
    || data.x!==x || data.y!==y || x===y
    || data.pairing!=="same-source-point-and-timestamp" || !Array.isArray(data.groups))
    throw new Error("선택한 설비·측정 짝 또는 서버의 짝지음 계약이 일치하지 않습니다.");
  const seen=new Set<string>();
  const groups=data.groups.map((raw: unknown):PairedGroup=>{
    const group=rec(raw);
    if(!group||!["a","b"].includes(String(group.period))||!Array.isArray(group.points))
      throw new Error("관계 분석의 구간 또는 짝 데이터가 올바르지 않습니다.");
    const period=group.period as "a"|"b";
    const source=string(group.source_id);
    const point=group.measurement_point_id === null ? null : string(group.measurement_point_id);
    const meaning=string(group.meaning_id);
    const id=JSON.stringify([period,source,point,meaning]);
    if(seen.has(id)) throw new Error("동일 출처의 관계가 중복 반환됐습니다.");
    seen.add(id);
    const points=group.points.map((entry:unknown)=>{
      if(!Array.isArray(entry)||entry.length!==3)
        throw new Error("관측 짝의 구조가 올바르지 않습니다.");
      return {at:time(entry[0]),x:finite(entry[1]),y:finite(entry[2])};
    });
    const pairCount=nonnegative(group.pair_count);
    if(pairCount<points.length) throw new Error("서버의 측정 짝 수가 그래프 자료보다 적습니다.");
    return {
      id,period,source,point,meaning,
      xUnit:typeof group.x_unit==="string"?group.x_unit:null,
      yUnit:typeof group.y_unit==="string"?group.y_unit:null,
      xUsable:nonnegative(group.x_usable_count),
      yUsable:nonnegative(group.y_usable_count),
      pairCount,pearson:coefficient(group.pearson),spearman:coefficient(group.spearman),
      sampled:group.sampled===true,points,
    };
  });
  return {asset,x,y,groups};
}
export async function readRelation(asset:string,x:string,y:string,periods:Periods,signal:AbortSignal):Promise<Relation>{
  if(x===y)throw new Error("서로 다른 두 신호를 선택해야 관계를 비교할 수 있습니다.");
  validatePeriods(periods);
  const params=new URLSearchParams({
    asset_id:asset,kind:"history",x,y,
    a_from:periods.a.from,a_to:periods.a.to,b_from:periods.b.from,b_to:periods.b.to,
  });
  const response=await fetch("/api/v1/explore/relation?"+params,{signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404){
    const detail:unknown=await response.json().catch(()=>null);
    if(rec(detail)?.error==="nothing_to_explore")throw new RelationUnavailable("저장된 측정 짝이 없습니다.");
  }
  if(!response.ok)throw new Error("신호 관계 조회가 실패했습니다. 비교할 짝이 없다는 뜻이 아닙니다.");
  return parseRelation(await response.json() as unknown,asset,x,y);
}
