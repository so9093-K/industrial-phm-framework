/** Which anomaly detection packages can read this asset's own input streams, and connecting
 * one. The server decides fit; a connection only records that the runner should analyze. */
import {object,postWrite,OutcomeUnknown} from "./writes.ts";

export type ModelStream={
  sourceId:string;pointId:string|null;kind:"acquisition-snapshot"|"observation-window";name:string;
  channels:number;rateHz:number|null;stored:boolean;
};
export type ModelCandidate={packageId:string;recipeId:string;stream:ModelStream};
export type BlockedModel={packageId:string;recipeId:string;reason:string};
export type ModelChoices={ready:ModelCandidate[];blocked:BlockedModel[];packages:number;streams:ModelStream[]};

const TASK="anomaly-score";

function invalid():never{throw new Error("연결할 수 있는 모델 목록의 형식이 올바르지 않습니다.");}
function text(raw:unknown):string|null{return typeof raw==="string"&&raw?raw:null;}

/** A plain name for what a package does: the signal it watches and, when known, its method. */
export function modelTitle(recipe:string,kind:ModelStream["kind"]|null):string{
  const method=/lstm|autoencoder/i.test(recipe)?"LSTM":/pca/i.test(recipe)?"PCA":/iforest/i.test(recipe)?"Isolation Forest":"";
  const signal=kind==="observation-window"?"관측 신호":kind==="acquisition-snapshot"?"진동":"신호";
  return signal+" 변화 탐지"+(method?" · "+method+" 기반":"");
}

export function parseModelChoices(raw:unknown,assetId:string):ModelChoices{
  const root=object(raw);
  if(!root||root.schema_version!==1||root.asset_id!==assetId||root.meaning!=="model-packages-and-asset-input-streams"
    ||!Array.isArray(root.packages)||!Array.isArray(root.streams))invalid();
  const streams=root.streams.map((item:unknown):ModelStream=>{
    const row=object(item);
    const sourceId=text(row?.source_id);
    if(!row||!sourceId||(row.kind!=="acquisition-snapshot"&&row.kind!=="observation-window"))invalid();
    return {sourceId,pointId:text(row.measurement_point_id),kind:row.kind,name:text(row.name)??sourceId,
      channels:Array.isArray(row.channels)?row.channels.length:0,
      rateHz:typeof row.sampling_rate_hz==="number"?row.sampling_rate_hz:null,stored:row.input_state==="stored-input"};
  });
  const ready:ModelCandidate[]=[],blocked:BlockedModel[]=[];
  let packages=0;
  for(const item of root.packages){
    const row=object(item);
    if(!row||row.task!==TASK||!Array.isArray(row.candidates))continue;
    packages++;
    const packageId=text(row.package_id);
    if(!packageId)invalid();
    const recipeId=text(row.recipe_id)??packageId;
    const candidates=row.candidates.map(object).filter((c):c is Record<string,unknown>=>c!==null);
    // A package already connected to this asset is shown under 적용 모델, not offered again.
    if(candidates.some(c=>c.connected===true))continue;
    const fits=candidates.filter(c=>c.compatible===true);
    for(const candidate of fits){
      const stream=streams.find(s=>s.sourceId===candidate.source_id&&s.pointId===(text(candidate.measurement_point_id)));
      if(stream)ready.push({packageId,recipeId,stream});
    }
    if(!fits.length&&candidates.length)blocked.push({packageId,recipeId,reason:text(candidates[0].reason)??"입력 형식이 맞지 않습니다"});
  }
  return {ready,blocked,packages,streams};
}

/** Why nothing can be connected, in what the person can do about it. */
export function noModelReason(choices:ModelChoices):string{
  if(!choices.streams.length)return "이 설비에는 모델 입력으로 쓸 진동 파형이나 OPC UA 관측 데이터가 없습니다. CSV로 저장한 측정값은 신호 탭과 기준 구간 이탈에서 볼 수 있습니다.";
  if(!choices.packages)return "작업공간에 이상 탐지 모델이 없습니다. 모델 패키지를 작업공간 models 폴더에 넣으면 여기에서 연결할 수 있습니다.";
  return "이 설비의 데이터와 입력 형식이 맞는 이상 탐지 모델이 없습니다.";
}

export async function readModelChoices(assetId:string,signal:AbortSignal):Promise<ModelChoices>{
  const response=await fetch("/api/v1/phm/models?"+new URLSearchParams({asset_id:assetId}),
    {signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error("연결할 수 있는 모델을 불러오지 못했습니다.");
  }
  return parseModelChoices(await response.json() as unknown,assetId);
}

/** Records that the runner should analyze this stream with this package; returns its binding. */
export async function connectModel(assetId:string,candidate:ModelCandidate,signal:AbortSignal):Promise<string>{
  const payload:Record<string,string>={package_id:candidate.packageId,source_id:candidate.stream.sourceId,asset_id:assetId};
  if(candidate.stream.pointId)payload.measurement_point_id=candidate.stream.pointId;
  const result=await postWrite("/api/v1/phm/bindings/create",payload,signal);
  if(result.asset_id!==assetId||result.package_id!==candidate.packageId||typeof result.binding_id!=="string"
    ||result.meaning!=="model-binding-recorded-results-follow-from-the-runner")
    throw new OutcomeUnknown("연결 응답의 대상이 요청과 다릅니다. 적용 모델 목록을 다시 확인하세요.");
  return result.binding_id;
}
