/** Which analyses one asset's stored data supports, as the server decided them from the stores:
 * ready, one model connection away, waiting for results, or not possible with the reason. It
 * says what the data supports, not whether the asset is healthy; nothing here runs an analysis. */
import {assetTabUrl,systemUrl} from "./routes.ts";
import {object} from "./writes.ts";

export type CapabilityId="measurements"|"period-compare"|"relation"|"spectrum"|"forecast"|"anomaly"|"ai-question";
export type CapabilityStatus="ready"|"needs-connection"|"waiting"|"unavailable";
export type Capability={id:CapabilityId;status:CapabilityStatus;reason:string;facts:Record<string,unknown>};
export type Capabilities={
  assetId:string;
  history:{channels:number;start:string;end:string}|null;
  acquisition:{first:number|null;last:number|null;samplingRate:number|null}|null;
  items:Capability[];
};

const IDS:readonly CapabilityId[]=["measurements","period-compare","relation","spectrum","forecast","anomaly","ai-question"];
const STATUSES:readonly CapabilityStatus[]=["ready","needs-connection","waiting","unavailable"];
export const NAME:Record<CapabilityId,string>={
  measurements:"측정 신호","period-compare":"두 기간 비교",relation:"신호 관계",spectrum:"주파수 분석",
  forecast:"상태 전망",anomaly:"이상 징후","ai-question":"AI 해설",
};
const HORIZON:Record<string,string>={"1h":"1시간","24h":"24시간","7d":"7일","30d":"30일"};

function invalid():never{throw new Error("분석 항목의 형식이 올바르지 않습니다.");}
function count(raw:unknown):number|null{return typeof raw==="number"&&Number.isFinite(raw)?raw:null;}

export function parseCapabilities(raw:unknown,assetId:string):Capabilities{
  const root=object(raw);
  if(!root||root.schema_version!==1||root.asset_id!==assetId||root.meaning!=="what-the-stored-data-supports-not-asset-health"
    ||!Array.isArray(root.capabilities))invalid();
  const data=object(root.data)??{};
  const history=object(data.history),acquisition=object(data.acquisition);
  const items=root.capabilities.map((item:unknown):Capability=>{
    const row=object(item);
    if(!row||!IDS.includes(row.id as CapabilityId)||!STATUSES.includes(row.status as CapabilityStatus)||typeof row.reason!=="string")invalid();
    return {id:row.id as CapabilityId,status:row.status as CapabilityStatus,reason:row.reason,facts:object(row.facts)??{}};
  });
  return {assetId,items,
    history:history&&typeof history.start_at==="string"&&typeof history.end_at==="string"
      ?{channels:count(history.channel_count)??0,start:history.start_at,end:history.end_at}:null,
    acquisition:acquisition?{first:count(acquisition.first),last:count(acquisition.last),samplingRate:count(acquisition.sampling_rate_hz)}:null};
}

/** Nothing stored yet: the server gives these reasons only then, so one line replaces every refusal. */
export function nothingStored(capabilities:Capabilities):"no-data"|"not-received"|null{
  const empty=capabilities.items.find(item=>item.reason==="no-data"||item.reason==="not-received");
  return empty?empty.reason as "no-data"|"not-received":null;
}

const kst=(iso:string)=>new Date(iso).toLocaleString("ko-KR",
  {timeZone:"Asia/Seoul",year:"numeric",month:"numeric",day:"numeric",hour:"numeric",minute:"2-digit"});

/** The fact each analysis rests on, in a few words. */
export function fact(item:Capability,capabilities:Capabilities):string{
  const facts=item.facts,history=capabilities.history,acquisition=capabilities.acquisition;
  const n=(key:string)=>count(facts[key])??0;
  switch(item.reason){
    case "history":
      if(item.id==="measurements"&&history)return "시계열 신호 "+history.channels+"개 · "+kst(history.start)+" ~ "+kst(history.end);
      if(item.id==="relation")return n("channels")>2?"시계열 신호 "+n("channels")+"개 중 2개 선택":"시계열 신호 2개";
      return "두 기간의 분포·데이터 상태";
    case "acquisition":
      if(item.id==="measurements")return "진동 측정 "+n("count")+"회 · 원본 파형";
      if(item.id==="relation")return "같은 진동 측정의 두 특징값";
      if(item.id==="spectrum")return "원본 파형"+(acquisition?.samplingRate?" · "+acquisition.samplingRate/1000+" kHz":"");
      return acquisition?.first!==null&&acquisition?.first!==undefined?acquisition.first+"~"+acquisition.last+"번째 측정":"진동 측정";
    case "explore":return "모델 없이 기준 구간에서 벗어난 값 찾기"+(n("packages")?" · 맞는 모델 "+n("packages")+"개 연결 가능":"");
    case "stored-flow":return "기준까지 남은 여유 · 최대 "+(HORIZON[String(facts.horizon)]??String(facts.horizon))+" 앞까지 예측";
    case "stored-flow-count":return "기준까지 남은 여유 · 측정 횟수 기준";
    case "outlook-only":return "기준까지 남은 여유 · 기록이 짧아 예측 그래프는 없음";
    case "short-history":return "기록이 짧음 (예측 기간의 2배 이상 필요)";
    case "connected":return "모델 결과 "+n("results")+"건"+(facts.recorded_replay===true?" · 기록 재생":"");
    case "model-results":return "모델 결과마다 이전 측정과 비교해 해설";
    case "outlook":return "상태 전망을 근거로 해설";
    case "compatible-model":return "입력이 맞는 모델 "+n("packages")+"개";
    case "waveforms-need-model":return "모델을 연결하면 측정마다 특징값을 계산";
    case "waiting-results":return "첫 모델 결과 대기";
    case "few-acquisitions":return "분석한 진동 측정 "+n("count")+"회";
    case "no-waveform":return "원본 진동 파형 없음";
    case "no-model-input":return "모델에 넣을 진동 측정·관측 구간 없음";
    case "no-model-package":return "설치된 모델 없음";
    case "input-mismatch":{
      const details=Array.isArray(facts.details)?facts.details.filter((detail):detail is string=>typeof detail==="string"):[];
      return "모델 입력 조건이 맞지 않음"+(details.length?" ("+details.join(", ")+")":"");
    }
    case "single-signal":return "시계열 신호 1개";
    case "single-moment":return "측정 시각 1개";
    case "read-only":return "보기 전용 화면에서는 요청할 수 없음 (운영 중인 화면에서 사용)";
    case "needs-results":return "모델 결과나 상태 전망 없음";
    default:return "";
  }
}

/** Where an analysis opens, with the asset kept; null when there is nowhere to go yet. */
export function place(item:Capability,assetId:string):string|null{
  if(item.reason==="no-data"||item.reason==="not-received")return systemUrl("connections");
  if(item.status==="unavailable"||item.status==="waiting")return null;
  if(item.status==="needs-connection")return assetTabUrl(assetId,"anomaly","model");
  const kind=item.reason==="acquisition"?"vibration":item.reason==="history"?"history":null;
  switch(item.id){
    case "measurements":return kind==="history"?assetTabUrl(assetId,"signals"):assetTabUrl(assetId,"anomaly","model");
    case "period-compare":return assetTabUrl(assetId,"change","compare",kind);
    case "relation":return assetTabUrl(assetId,"change","relation",kind);
    case "spectrum":return assetTabUrl(assetId,"change","spectrum");
    case "forecast":return assetTabUrl(assetId,"outlook",null,
      item.reason==="stored-flow-count"?"vibration":item.reason==="outlook-only"?"history":null);
    case "anomaly":return assetTabUrl(assetId,"anomaly",item.reason==="explore"?"baseline":"model");
    case "ai-question":return item.reason==="outlook"?assetTabUrl(assetId,"outlook"):assetTabUrl(assetId,"anomaly","model");
  }
}

/** Model-free analysis is ready, and a model that fits is one connection away as well. */
export function connectPlace(item:Capability,assetId:string):string|null{
  return item.id==="anomaly"&&item.reason==="explore"&&(count(item.facts.packages)??0)>0
    ?assetTabUrl(assetId,"anomaly","model"):null;
}

export async function readCapabilities(assetId:string,signal:AbortSignal):Promise<Capabilities>{
  const response=await fetch("/api/v1/explore/capabilities?"+new URLSearchParams({asset_id:assetId}),
    {signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error("분석 항목을 확인하지 못했습니다.");
  }
  return parseCapabilities(await response.json() as unknown,assetId);
}
