/** What needs a look on each asset right now: a model over its threshold, a stored signal that
 * ends far from its own baseline, an input the model refused or has not reached, a model that
 * cannot run, a collection that stopped receiving or a review in progress. Each item opens the
 * exact place to check; none is a fault verdict. */
import {modelResultUrl} from "./finding-reviews.ts";
import {modelName} from "./model-evidence.ts";
import {readSources,type Source} from "./operations-status.ts";
import {assetTabUrl,routeUrl,systemUrl} from "./routes.ts";
import {object} from "./writes.ts";

export type ModelState="processed"|"pending"|"warmup"|"rejected"|"waiting"|"unavailable";
export type MonitoredModel={
  bindingId:string;assetId:string;stepKind:"acquisition-snapshot"|"observation-window";recipeId:string|null;
  packageId:string;estimatorKind:string|null;
  state:ModelState;reason:string|null;analyzed:{position:number;exceeds:boolean|null}|null;
  /** The run of consecutive crossings still going on, if any. */
  ongoing:{start:number;steps:number;startAt:string|null}|null;
  processed:number|null;reviewStatus:"open"|"acknowledged"|"closed"|null;
};
export type PhmMonitor={assessedAt:string|null;models:MonitoredModel[];truncated:boolean;reviewsUnknown:boolean};
export type NoteKind="threshold"|"crossing"|"departure"|"refusal"|"unavailable"|"receipt"|"pending"|"review"|"warmup";
/** A stored signal whose latest values are still far from the first 30% of its own record. */
export type Departure={assetId:string;channel:string;label:string|null;unit:string|null;
  distance:number;direction:"up"|"down"|null;since:string};
/** `id` is unique within one asset: two connections or two signals of one asset each keep their own note. */
export type Note={id:string;kind:NoteKind;label:string;detail:string;href:string;action:string};
export type AssetAttention={assetId:string;notes:Note[]};
export type AttentionState = "loading" | "ready" | "partial" | "failed";
export function attentionText(count: number | null, state: AttentionState): string {
  if (state === "loading") return count ? count + "건 · 확인 중" : "확인 중";
  if (state !== "ready") return count ? "최소 " + count + "건 · 일부 미확인" : "일부 미확인";
  return count === null ? "미확인" : count ? count + "건" : "없음";
}
export function attentionComplete(phm: PhmMonitor, sources: Awaited<ReturnType<typeof readSources>> | null,
  departuresComplete: boolean): boolean {
  return !phm.truncated && !phm.reviewsUnknown && sources !== null && !sources.truncated
    && !sources.readErrors.length && !sources.liveErrors.length && !sources.items.some(item=>item.readError)
    && departuresComplete;
}

const STATES:readonly ModelState[]=["processed","pending","warmup","rejected","waiting","unavailable"];
const PRIORITY:Record<NoteKind,number>={threshold:0,departure:0,refusal:1,unavailable:1,crossing:2,receipt:2,pending:3,review:4,warmup:3};

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
    const run=object(row.open_interval);
    const start=run?.start_position,steps=run?.step_count;
    return {bindingId,assetId,stepKind:row.step_kind,recipeId:text(row.recipe_id),
      packageId:text(row.package_id)??"",estimatorKind:text(row.estimator_kind),
      ongoing:typeof start==="number"&&Number.isSafeInteger(start)&&typeof steps==="number"&&Number.isSafeInteger(steps)
        ?{start,steps,startAt:text(run?.start_event_at)}:null,
      state:row.processing_state as ModelState,
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

/** Where a run started, as the model's input is counted: an acquisition number or a window's time. */
function since(model:MonitoredModel):string{
  const run=model.ongoing!;
  if(model.stepKind==="observation-window"&&run.startAt)
    return new Date(run.startAt).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",month:"numeric",day:"numeric",hour:"numeric",minute:"2-digit"});
  return (model.stepKind==="acquisition-snapshot"?"측정 순서 #":"시간 구간 #")+run.start;
}

function at(model:MonitoredModel,which:number|null):string{
  return which===null?routeUrl({page:"assets",assetId:model.assetId,tab:"anomaly",method:"model",data:null})
    :modelResultUrl(model.assetId,{bindingId:model.bindingId,position:which});
}

/** Notes per asset, most urgent first; assets without notes are left out. */
export function attentionByAsset(models:MonitoredModel[],sources:Source[]|null,departures:Departure[]=[]):AssetAttention[]{
  const groups=new Map<string,Note[]>();
  const add=(assetId:string,note:Note)=>{const list=groups.get(assetId)??[];list.push(note);groups.set(assetId,list);};
  const byAsset=new Map<string,MonitoredModel[]>();
  for(const model of models)byAsset.set(model.assetId,[...(byAsset.get(model.assetId)??[]),model]);
  for(const [assetId,list] of byAsset){
    const vibration=list.some(model=>model.stepKind==="acquisition-snapshot");
    // A run of crossings still going on is a change to look at; a latest crossing on its own is
    // said as such, lower down, so the two never read alike.
    const processed=list.filter(model=>model.state==="processed"&&model.analyzed);
    const sustained=processed.filter(model=>model.ongoing),lone=processed.filter(model=>!model.ongoing&&model.analyzed?.exceeds===true);
    if(sustained.length)add(assetId,{id:"threshold",kind:"threshold",label:(vibration?"진동":"전기 신호")+" 변화 확인 필요",
      detail:sustained.map(model=>modelName(model)+" "+since(model)
        +(model.analyzed?.exceeds===false?"부터 기준 초과 구간 · ":"부터 계속 기준 초과 · ")+model.ongoing!.steps+"회"
        +(model.analyzed?.exceeds===false?" · 최근 측정은 기준 이하":"")).join(" · ")
        +(lone.length?" · "+lone.map(model=>modelName(model)).join("·")+"는 최근 측정만 기준 초과":""),
      href:at(sustained[0],sustained[0].analyzed!.position),action:"점수 추이 보기"});
    else if(lone.length)add(assetId,{id:"crossing",kind:"crossing",label:"최근 측정에서 모델 기준 초과",
      detail:lone.map(model=>modelName(model)).join("·")+" · 연속 초과는 아님",
      href:at(lone[0],lone[0].analyzed!.position),action:"점수 추이 보기"});
    const refused=list.filter(model=>model.state==="rejected");
    if(refused.length)add(assetId,{id:"refusal",kind:"refusal",label:vibration?"최근 진동 파형을 분석하지 못함":"최근 측정 입력을 분석하지 못함",
      detail:[...new Set(refused.map(model=>refusalReason(model.reason)))].join(" · ")+" · "+refused.length+"개 모델",
      href:at(refused[0],refused[0].processed),action:"입력·모델 확인"});
    const down=list.filter(model=>model.state==="unavailable");
    if(down.length)add(assetId,{id:"unavailable",kind:"unavailable",label:"모델을 실행할 수 없음",detail:down.length+"개 모델 · 모델 패키지와 분석 실행기 상태를 확인하세요",
      href:at(down[0],null),action:"모델 확인"});
    const warmups=list.filter(model=>model.state==="warmup");
    if(warmups.length)add(assetId,{id:"warmup",kind:"warmup",label:"모델 입력을 모으는 중",detail:warmups.length+"개 모델 · "+(warmups[0].reason??"준비할 입력이 더 필요합니다"),href:at(warmups[0],warmups[0].processed),action:"입력 준비 상태 보기"});
    const waiting=list.filter(model=>model.state==="pending");
    if(waiting.length)add(assetId,{id:"pending",kind:"pending",label:"새 입력 분석 대기",detail:waiting.length+"개 모델이 아직 처리하지 않았습니다",
      href:at(waiting[0],null),action:"분석 진행 보기"});
    if(list.some(model=>model.reviewStatus==="open"||model.reviewStatus==="acknowledged"))
      add(assetId,{id:"review",kind:"review",label:"검토 진행 중",detail:"모델 결과의 사람 검토가 끝나지 않았습니다",
        href:routeUrl({page:"maintenance",assetId,tab:"summary",method:null,data:null}),action:"정비 검토함 보기"});
  }
  for(const item of departures){
    const name=item.label?item.label+(item.unit?" ("+item.unit+")":""):item.channel;
    const since=new Date(item.since).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",month:"numeric",day:"numeric",hour:"numeric",minute:"2-digit"});
    add(item.assetId,{id:"departure:"+item.channel,kind:"departure",label:"기준 구간에서 크게 벗어남",
      detail:name+" · 기준 변동 폭의 "+Math.round(item.distance)+"배 "+(item.direction==="down"?"낮음":"높음")+" · "+since+"부터 계속",
      href:assetTabUrl(item.assetId,"anomaly","baseline",null,item.channel),action:"기준 구간 이탈 보기"});
  }
  for(const source of sources??[]){
    // A collection someone asked to run that has not received recently; paused or stopped is expected.
    if(source.type==="opcua"&&source.lifecycle==="active"&&source.live?.desired==="running"&&!source.live.fresh)
      add(source.assetId,{id:"receipt:"+source.sourceId,kind:"receipt",label:"최근 30초 수신 없음",detail:source.name+" · 연결·수집 상태를 확인하세요",
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

export function parseDepartures(raw:unknown):Departure[]{
  const root=object(raw);
  if(!root||root.schema_version!==1||!Array.isArray(root.items))throw new Error("기준 구간 이탈 확인 결과의 형식이 올바르지 않습니다.");
  return root.items.flatMap((value:unknown):Departure[]=>{
    const row=object(value);
    const assetId=text(row?.asset_id),channel=text(row?.channel),since=text(row?.since);
    if(!row||!assetId||!channel||!since||typeof row.distance!=="number"||!Number.isFinite(row.distance))return [];
    return [{assetId,channel,label:text(row.label),unit:text(row.unit),distance:row.distance,
      direction:row.direction==="up"||row.direction==="down"?row.direction:null,since}];
  });
}

export async function readDepartureStatus(signal:AbortSignal,assetId?:string):Promise<{items:Departure[];complete:boolean}>{
  const query=assetId?"?"+new URLSearchParams({asset_id:assetId}):"";
  const response=await fetch("/api/v1/explore/attention"+query,{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error("기준 구간 이탈을 확인하지 못했습니다.");
  }
  const raw = await response.json() as unknown;
  const items = parseDepartures(raw), root = object(raw)!;
  return {items, complete: root.truncated !== true && items.length === (root.items as unknown[]).length};
}
export async function readDepartures(signal:AbortSignal,assetId?:string):Promise<Departure[]>{
  return (await readDepartureStatus(signal,assetId)).items;
}

/** Every asset's notes, read once from what 관측 현황 polls, so the asset list and an asset's
 * summary count the same items. A part that cannot be read is left out, not guessed. */
export async function readAttention(signal:AbortSignal):Promise<{
  groups:AssetAttention[];counts:Record<string,number>;state:"ready"|"partial";
}>{
  const [phm,sources,departures]=await Promise.all([readPhmMonitor(signal),
    readSources(signal).catch(()=>null),readDepartureStatus(signal).catch(()=>null)]);
  const groups = attentionByAsset(phm.models,sources?.items??null,departures?.items??[]);
  return {groups, counts:Object.fromEntries([...phm.models.map(item=>[item.assetId,0]),
    ...groups.map(group=>[group.assetId,group.notes.length])]),
    state:attentionComplete(phm,sources,departures?.complete??false)?"ready":"partial"};
}

/** The signal a screen opens on when none is chosen: the one this asset's baseline check flagged,
 * else the first. The screen waits for the check only briefly; a slow or failed check only means
 * the first signal is shown. */
export async function defaultChannel(assetId:string,ids:string[],signal:AbortSignal,waitMs=1200):Promise<string>{
  if(ids.length<2)return ids[0];
  const flagged=await readDepartures(AbortSignal.any([signal,AbortSignal.timeout(waitMs)]),assetId)
    .then(found=>found.find(item=>item.assetId===assetId)?.channel).catch(()=>undefined);
  return flagged&&ids.includes(flagged)?flagged:ids[0];
}
