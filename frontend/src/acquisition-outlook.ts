/** Two server-owned acquisition projections, never an invented observation clock. */
import {parseOutlookSettings,type Conditions,type OutlookSettings,type Reach,type Scenario} from "./projections.ts";

export type TimeBasis="recorded"|"assumed"|"ordinal";
export type AcquisitionFeature={
  id:string;label:string;validPoints:number;countForecast:boolean;
};
export type AcquisitionOptions={
  assetId:string;sourceId:string;bindingId:string;first:number;last:number;count:number;
  recordedPeriod:number|null;features:AcquisitionFeature[];
};
export type AcquisitionProjection={
  assetId:string;sourceId:string;bindingId:string;featureId:string;
  measurementVersion:string;dataVersion:string;timeBasis:TimeBasis;
  recordedPeriod:number|null;assumedPeriod:number|null;effectivePeriod:number;
  horizonCount:number;searchCount:number;searchUntil:number;outlookSettings:OutlookSettings;
  conditions:Conditions;record:{first:number;last:number;points:number};
  forecast:Array<{ordinal:number;estimate:number;lower:number|null;upper:number|null}>;
  scenarios:Scenario[];
};
export class AcquisitionOutlookUnavailable extends Error {}
export class AcquisitionVersionMismatch extends Error {}
function obj(value:unknown):Record<string,unknown>|null{
  return value!==null&&typeof value==="object"&&!Array.isArray(value)
    ? value as Record<string,unknown>:null;
}
function str(value:unknown):string{
  if(typeof value!=="string"||!value||value.length>512)
    throw new Error("획득 전망의 출처 식별자가 유효하지 않습니다.");
  return value;
}
function count(value:unknown):number{
  if(typeof value!=="number"||!Number.isSafeInteger(value)||value<0)
    throw new Error("획득 순번 또는 분석 건수가 올바르지 않습니다.");
  return value;
}
function ordinal(value:unknown):number{
  const n=count(value);
  if(n<1)throw new Error("획득 회차는 1부터 시작합니다.");
  return n;
}
function finite(value:unknown):number{
  if(typeof value!=="number"||!Number.isFinite(value))
    throw new Error("예측 특징값이 올바르지 않습니다.");
  return value;
}
function numberOrNull(value:unknown):number|null{
  return value===null?null:finite(value);
}
function period(value:unknown):number|null{
  if(value===null)return null;
  const n=finite(value);
  if(n<=0)throw new Error("획득의 시간 간격이 올바르지 않습니다.");
  return n;
}
function version(raw:unknown):string{
  if(typeof raw!=="string"||!/^[a-f0-9]{64}$/.test(raw))
    throw new Error("측정·AI 근거 버전이 올바르지 않습니다.");
  return raw;
}
export function validateAcquisitionChoice(
  feature:AcquisitionFeature,horizonCount:number,assumedPeriod:number|null,
):void{
  if(feature.validPoints<20||!feature.countForecast)
    throw new AcquisitionOutlookUnavailable("유효한 저장 획득 특징이 20개 이상 필요합니다.");
  if(!Number.isSafeInteger(horizonCount)||horizonCount<1||horizonCount>2000)
    throw new Error("예측할 추가 획득 횟수는 1~2000의 정수여야 합니다.");
  if(assumedPeriod!==null&&(!Number.isFinite(assumedPeriod)
    ||assumedPeriod<1||assumedPeriod>86400))
    throw new Error("가정한 획득 간격은 1~86400초여야 합니다.");
}
export function parseAcquisitionOptions(raw:unknown,assetId:string):AcquisitionOptions|null{
  const root=obj(raw);
  if(!root||root.schema_version!==1||root.asset_id!==assetId)
    throw new Error("선택한 설비의 획득 전망 목록이 아닙니다.");
  if(root.acquisition===null)return null;
  const acq=obj(root.acquisition);
  if(!acq||!Array.isArray(acq.series)||acq.series.length>256)
    throw new Error("획득 특징 선택지가 올바르지 않습니다.");
  const first=ordinal(acq.first),last=ordinal(acq.last),total=count(acq.count);
  if(last<first||total<1)throw new Error("획득 구간 정보가 올바르지 않습니다.");
  const features=acq.series.map((candidate:unknown):AcquisitionFeature=>{
    const row=obj(candidate);
    if(!row||typeof row.count_forecast!=="boolean")
      throw new Error("획득 특징의 계산 가능 여부가 명확하지 않습니다.");
    const valid=count(row.valid_points);
    if(row.count_forecast!==(valid>=20))
      throw new Error("획득 특징의 계산 가능 여부와 분석 건수가 다릅니다.");
    return {id:str(row.key),label:str(row.label),validPoints:valid,
      countForecast:row.count_forecast};
  });
  if(new Set(features.map(f=>f.id)).size!==features.length)
    throw new Error("획득 특징 식별자가 중복됐습니다.");
  return {assetId,sourceId:str(acq.source_id),bindingId:str(acq.binding_id),
    first,last,count:total,recordedPeriod:period(acq.period_seconds),features};
}
function reach(raw:unknown):Reach|null{
  if(raw===null||raw===undefined)return null;
  const row=obj(raw);
  if(!row||!["already","expected","possible","beyond","not-reached"].includes(String(row.state)))
    throw new Error("기준 도달 상태의 의미가 불명확합니다.");
  return {state:str(row.state),expected:numberOrNull(row.expected),
    earliest:numberOrNull(row.earliest),latest:numberOrNull(row.latest)};
}
function conditionsMatch(raw:unknown,expected:Conditions):boolean{
  const row=obj(raw);
  return !!row&&row.direction===expected.direction
    &&row.management===expected.management&&row.end===expected.end;
}
export function parseAcquisitionPair(
  forecastRaw:unknown,outlookRaw:unknown,options:AcquisitionOptions,
  featureId:string,horizonCount:number,assumedPeriod:number|null,
  conditions:Conditions,
):AcquisitionProjection{
  const feature=options.features.find(f=>f.id===featureId);
  if(!feature)throw new Error("선택한 출처에 해당 획득 특징이 없습니다.");
  validateAcquisitionChoice(feature,horizonCount,assumedPeriod);
  const forecast=obj(forecastRaw),outlook=obj(outlookRaw);
  if(!forecast||!outlook||forecast.schema_version!==1||outlook.schema_version!==1
    ||forecast.kind!=="acquisition"||outlook.kind!=="acquisition"
    ||forecast.axis!=="acquisition"||outlook.axis!=="acquisition"
    ||forecast.asset_id!==options.assetId||outlook.asset_id!==options.assetId
    ||forecast.series!==featureId||outlook.series!==featureId
    ||forecast.horizon!=="count"||forecast.horizon_count!==horizonCount
    ||outlook.offset_unit!=="acquisition"
    ||forecast.meaning!=="stored-flow-continued-not-failure-time-or-remaining-life"
    ||outlook.meaning!=="remaining-margin-to-user-conditions-not-a-diagnosis"
    ||!conditionsMatch(outlook.conditions,conditions))
    throw new Error("획득 전망의 대상·조건·축 또는 계산 의미가 일치하지 않습니다.");
  const keys=["source_id","binding_id","measurement_point_id","measurement_version",
    "time_basis","period_seconds","recorded_period_seconds","assumed_period_seconds"];
  for(const key of keys){
    if(forecast[key]!==outlook[key])
      throw new AcquisitionVersionMismatch("획득 전망의 원본·binding·측정 버전·시간 가정이 불일치합니다.");
  }
  if(forecast.source_id!==options.sourceId||forecast.binding_id!==options.bindingId
    ||forecast.measurement_point_id!==null||forecast.time_basis===undefined
    ||!["recorded","assumed","ordinal"].includes(String(forecast.time_basis)))
    throw new AcquisitionVersionMismatch("선택한 획득 원본과 계산된 전망의 출처·축이 다릅니다.");
  const basis=forecast.time_basis as TimeBasis;
  const expectedBasis=assumedPeriod!==null?"assumed"
    :options.recordedPeriod!==null?"recorded":"ordinal";
  if(basis!==expectedBasis)
    throw new AcquisitionVersionMismatch("서버가 사용한 획득 시간 근거가 선택과 다릅니다.");
  const recorded=period(forecast.recorded_period_seconds);
  const assumed=period(forecast.assumed_period_seconds);
  const effective=period(forecast.period_seconds);
  if(recorded!==options.recordedPeriod||assumed!==assumedPeriod
    ||effective===null||Math.abs(effective-(assumed??recorded??1))>1e-9)
    throw new AcquisitionVersionMismatch("기록된/가정한 획득 간격이 서버 근거와 다릅니다.");
  const fVersion=version(forecast.measurement_version);
  if(fVersion!==version(outlook.measurement_version))
    throw new AcquisitionVersionMismatch("획득 측정 버전이 다릅니다.");
  const record=obj(outlook.record);
  if(!record||!Array.isArray(forecast.forecast)||!Array.isArray(outlook.scenarios))
    throw new Error("획득 전망의 기록 또는 계산 값이 불완전합니다.");
  const first=ordinal(record.first),last=ordinal(record.last),points=count(record.points);
  if(first<options.first||last>options.last||last<first||points<20)
    throw new AcquisitionVersionMismatch("획득 전망이 선택 범위를 벗어났습니다.");
  const outlookSettings=parseOutlookSettings(outlook.settings);
  if(!outlookSettings)throw new Error("획득 전망의 서버 계산 설정을 확인할 수 없습니다.");
  const search=obj(outlook.search);
  if(!search)throw new Error("조건부 도달 탐색 회차의 근거가 없습니다.");
  const searchCount=ordinal(search.acquisitions),searchUntil=ordinal(search.until);
  if(searchUntil!==last+searchCount)
    throw new AcquisitionVersionMismatch("조건부 탐색 끝 획득 회차와 원본 기록이 다릅니다.");
  let previous=last-1;
  const future=forecast.forecast.map((raw:unknown)=>{
    if(!Array.isArray(raw)||raw.length<2||raw.length>4)
      throw new Error("미래 획득 특징값의 형식이 올바르지 않습니다.");
    const position=finite(raw[0]);
    if(position<last||position>last+horizonCount+1e-6||position<previous)
      throw new Error("예측 회차가 마지막 기록·요청 구간과 다릅니다.");
    previous=position;
    return {ordinal:position,estimate:finite(raw[1]),
      lower:numberOrNull(raw[2]??null),upper:numberOrNull(raw[3]??null)};
  });
  if(!future.length)throw new Error("미래 획득 회차 예측값이 없습니다.");
  const seen=new Set<string>();
  const scenarios=outlook.scenarios.map((raw:unknown):Scenario=>{
    const row=obj(raw),limits=obj(row?.limits);
    if(!row||!limits)throw new Error("조건부 획득 시나리오가 잘못됐습니다.");
    const id=str(row.id);
    if(seen.has(id))throw new Error("시나리오 중복이 반환됐습니다.");
    seen.add(id);
    return {id,management:reach(limits.management),end:reach(limits.end)};
  });
  return {assetId:options.assetId,sourceId:options.sourceId,bindingId:options.bindingId,
    featureId,measurementVersion:fVersion,dataVersion:version(outlook.data_version),
    timeBasis:basis,recordedPeriod:recorded,assumedPeriod:assumed,effectivePeriod:effective,
    horizonCount,searchCount,searchUntil,outlookSettings,
    conditions,record:{first,last,points},forecast:future,scenarios};
}
async function json(url:string,signal:AbortSignal):Promise<unknown>{
  const response=await fetch(url,{signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404||response.status===422){
    const payload:unknown=await response.json().catch(()=>null);
    const name=obj(payload)?.error;
    if(["nothing_to_forecast","nothing_to_outlook","forecast_unavailable",
      "outlook_unavailable"].includes(String(name)))
      throw new AcquisitionOutlookUnavailable("선택한 획득 회차에 계산할 특징 근거가 부족합니다.");
  }
  if(!response.ok)throw new Error("획득 전망 저장소·계산 조회 오류입니다.");
  return await response.json() as unknown;
}
export async function loadAcquisitionOptions(
  assetId:string,signal:AbortSignal,
):Promise<AcquisitionOptions|null>{
  const query=new URLSearchParams({asset_id:assetId});
  return parseAcquisitionOptions(await json("/api/v1/forecast/options?"+query,signal),assetId);
}
export async function loadAcquisitionPair(
  options:AcquisitionOptions,featureId:string,horizonCount:number,
  assumedPeriod:number|null,conditions:Conditions,signal:AbortSignal,
):Promise<AcquisitionProjection>{
  const feature=options.features.find(f=>f.id===featureId);
  if(!feature)throw new Error("선택한 특징이 저장 출처에 없습니다.");
  validateAcquisitionChoice(feature,horizonCount,assumedPeriod);
  const base={asset_id:options.assetId,kind:"acquisition",series:featureId};
  const limit:Record<string,string>={direction:conditions.direction};
  if(conditions.management!==null)limit.management_limit=String(conditions.management);
  if(conditions.end!==null)limit.end_limit=String(conditions.end);
  if(assumedPeriod!==null)limit.assumed_period_seconds=String(assumedPeriod);
  const [forecast,outlook]=await Promise.all([
    json("/api/v1/forecast?"+new URLSearchParams({
      ...base,...(assumedPeriod!==null?{assumed_period_seconds:String(assumedPeriod)}:{}),
      horizon:"count",horizon_count:String(horizonCount),
    }),signal),
    json("/api/v1/outlook?"+new URLSearchParams({...base,...limit}),signal),
  ]);
  return parseAcquisitionPair(forecast,outlook,options,featureId,horizonCount,assumedPeriod,conditions);
}
