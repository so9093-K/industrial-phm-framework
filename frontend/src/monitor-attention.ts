/** What needs a look on each asset right now: a model over its threshold, an input the model
 * refused or has not reached, a model that cannot run, a collection that stopped receiving or
 * a review in progress. Each item opens the exact place to check; none is a fault verdict. */
import {modelResultUrl} from "./finding-reviews.ts";
import type {Source} from "./operations-status.ts";
import {routeUrl,systemUrl} from "./routes.ts";
import {object} from "./writes.ts";

export type ModelState="processed"|"pending"|"warmup"|"rejected"|"waiting"|"unavailable";
export type MonitoredModel={
  bindingId:string;assetId:string;stepKind:"acquisition-snapshot"|"observation-window";recipeId:string|null;
  state:ModelState;reason:string|null;analyzed:{position:number;exceeds:boolean|null}|null;
  processed:number|null;reviewStatus:"open"|"acknowledged"|"closed"|null;
};
export type PhmMonitor={assessedAt:string|null;models:MonitoredModel[];truncated:boolean;reviewsUnknown:boolean};
export type NoteKind="threshold"|"refusal"|"unavailable"|"receipt"|"pending"|"review";
export type Note={kind:NoteKind;label:string;detail:string;href:string;action:string};
export type AssetAttention={assetId:string;notes:Note[]};

const STATES:readonly ModelState[]=["processed","pending","warmup","rejected","waiting","unavailable"];
const PRIORITY:Record<NoteKind,number>={threshold:0,refusal:1,unavailable:1,receipt:2,pending:3,review:4};

function invalid():never{throw new Error("모델 처리 상태의 형식이 올바르지 않습니다.");}
function text(raw:unknown):string|null{return typeof raw==="string"&&raw?raw:null;}
function position(raw:unknown):number|null{
  const value=object(raw)?.position;
  return typeof value==="number"&&Number.isSafeInteger(value)?value:null;
}

export function parsePhmMonitor(raw:unknown):PhmMonitor{
  const root=object(raw);
  if(!root||root.schema_version!==1||!Array.isArray(root.items))invalid();
  const models=root.items.map((item:unknown):MonitoredModel=>{
    const row=object(item);
    const bindingId=text(row?.binding_id),assetId=text(row?.asset_id);
    if(!row||!bindingId||!assetId||!STATES.includes(row.processing_state as ModelState)
      ||(row.step_kind!=="acquisition-snapshot"&&row.step_kind!=="observation-window"))invalid();
    const analyzed=object(row.latest_analyzed),output=object(analyzed?.output);
    const at=position(analyzed);
    const review=row.latest_review_status;
    return {bindingId,assetId,stepKind:row.step_kind,recipeId:text(row.recipe_id),state:row.processing_state as ModelState,
      reason:text(row.processing_reason),
      analyzed:at===null?null:{position:at,exceeds:typeof output?.exceeds_threshold==="boolean"?output.exceeds_threshold:null},
      processed:position(row.latest_processed),
      reviewStatus:review==="open"||review==="acknowledged"||review==="closed"?review:null};
  });
  return {assessedAt:text(root.assessed_at),models,truncated:root.truncated===true,reviewsUnknown:root.review_read_error===true};
}

/** The legacy screen's plain reasons for a refused input. */
export function refusalReason(reason:string|null):string{
  if(/sha.?256|checksum|digest/i.test(reason??""))return "전달 뒤 원본이 바뀜";
  if(/channels differ|sampling rate|sample count|package expects/i.test(reason??""))return "모델이 받는 입력 규격과 다름";
  if(/file|snapshot.*unavailable/i.test(reason??""))return "원본 입력을 읽을 수 없음";
  return "입력 조건이 맞지 않음";
}

function at(model:MonitoredModel,which:number|null):string{
  return which===null?routeUrl({page:"assets",assetId:model.assetId,tab:"anomaly",method:"model",data:null})
    :modelResultUrl(model.assetId,{bindingId:model.bindingId,position:which});
}

/** Notes per asset, most urgent first; assets without notes are left out. */
export function attentionByAsset(models:MonitoredModel[],sources:Source[]|null):AssetAttention[]{
  const groups=new Map<string,Note[]>();
  const add=(assetId:string,note:Note)=>{const list=groups.get(assetId)??[];list.push(note);groups.set(assetId,list);};
  const byAsset=new Map<string,MonitoredModel[]>();
  for(const model of models)byAsset.set(model.assetId,[...(byAsset.get(model.assetId)??[]),model]);
  for(const [assetId,list] of byAsset){
    const vibration=list.some(model=>model.stepKind==="acquisition-snapshot");
    const exceeded=list.filter(model=>model.state==="processed"&&model.analyzed?.exceeds===true);
    if(exceeded.length)add(assetId,{kind:"threshold",label:(vibration?"진동":"전기 신호")+" 변화 확인 필요",
      detail:"모델 기준 초과 "+exceeded.length+"개 · 점수 추이와 원본을 확인하세요",href:at(exceeded[0],exceeded[0].analyzed!.position),action:"점수 추이 보기"});
    const refused=list.filter(model=>model.state==="rejected");
    if(refused.length)add(assetId,{kind:"refusal",label:vibration?"최근 진동 파형을 분석하지 못함":"최근 측정 입력을 분석하지 못함",
      detail:[...new Set(refused.map(model=>refusalReason(model.reason)))].join(" · ")+" · "+refused.length+"개 모델",
      href:at(refused[0],refused[0].processed),action:"입력·모델 확인"});
    const down=list.filter(model=>model.state==="unavailable");
    if(down.length)add(assetId,{kind:"unavailable",label:"모델을 실행할 수 없음",detail:down.length+"개 모델 · 모델 패키지와 분석 실행기 상태를 확인하세요",
      href:at(down[0],null),action:"모델 확인"});
    const waiting=list.filter(model=>model.state==="pending");
    if(waiting.length)add(assetId,{kind:"pending",label:"새 입력 분석 대기",detail:waiting.length+"개 모델이 아직 처리하지 않았습니다",
      href:at(waiting[0],null),action:"분석 진행 보기"});
    if(list.some(model=>model.reviewStatus==="open"||model.reviewStatus==="acknowledged"))
      add(assetId,{kind:"review",label:"검토 진행 중",detail:"모델 결과의 사람 검토가 끝나지 않았습니다",
        href:routeUrl({page:"maintenance",assetId,tab:"summary",method:null,data:null}),action:"정비 검토함 보기"});
  }
  for(const source of sources??[]){
    // A collection someone asked to run that has not received recently; paused or stopped is expected.
    if(source.type==="opcua"&&source.lifecycle==="active"&&source.live?.desired==="running"&&!source.live.fresh)
      add(source.assetId,{kind:"receipt",label:"최근 30초 수신 없음",detail:source.name+" · 연결·수집 상태를 확인하세요",
        href:systemUrl("connections"),action:"데이터 연결 보기"});
  }
  return [...groups].map(([assetId,notes])=>({assetId,notes:notes.sort((a,b)=>PRIORITY[a.kind]-PRIORITY[b.kind])}))
    .sort((a,b)=>PRIORITY[a.notes[0].kind]-PRIORITY[b.notes[0].kind]||a.assetId.localeCompare(b.assetId));
}

export async function readPhmMonitor(signal:AbortSignal):Promise<PhmMonitor>{
  const response=await fetch("/api/v1/phm/monitor",{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error("모델 처리 상태를 읽지 못했습니다.");
  }
  return parsePhmMonitor(await response.json() as unknown);
}
