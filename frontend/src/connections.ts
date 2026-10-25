/** Data connection writes through the supervisor: check and register a CSV, put a connection
 * in use, read a file once, store its history, run an analysis, request collection. Each
 * step keeps its own result; registration is never shown as receipt or storage. */
import {readSources,type Source} from "./operations-status.ts";
import {object,postWrite,OutcomeUnknown,WriteForbidden,WriteRejected} from "./writes.ts";

export type CsvSetup={
  source_id:string;name:string;asset_id:string;measurement_point_id:string;
  channel_columns:string[];timestamp_column:string;
  /** Optional 3-phase roles; the upload path accepts the same field as a workspace CSV. */
  phase_channels?:PhaseRole[];
  /** Optional names and units people see for the saved columns; IDs stay the column names. */
  channel_labels?:{channel_id:string;label:string;unit:string|null}[];
  /** The offset for timestamps the file wrote without one, such as +09:00. */
  timestamp_utc_offset?:string;
};
export type PreflightIssue={code:string;guidance:string;row:number|null;column:string|null};
export type Preflight={
  status:"ready"|"needs_input"|"blocked";sampleCount:number|null;channels:string[];
  first:string|null;last:string|null;warnings:string[];
  match:"absent"|"matching"|"conflict"|"unchecked"|null;issue:PreflightIssue|null;
};
export type Receipt={accepted:boolean;receivedAt:string|null;failure:string|null};
export type SavedAnalysis={assetId:string;runId:string;evidenceId:string};
export type Action="activate"|"pause"|"receive"|"store"|"analyze"|"phase"|"diagnose"|"collect"|"stop";
export type Step={action:Action|null;text:string};

/** Server refusals, in what the person can do about them. */
export function explainWrite(cause:unknown):string{
  if(cause instanceof WriteForbidden)return cause.message;
  if(cause instanceof OutcomeUnknown)
    return "요청이 처리됐는지 확인하지 못했습니다. 연결 목록을 다시 읽어 상태를 확인한 뒤 진행하세요.";
  if(cause instanceof WriteRejected){
    const known:Record<string,string>={
      workspace_writer_busy:"다른 작업이 작업공간을 쓰는 중입니다. 잠시 후 다시 시도하세요.",
      source_id_exists:"이미 등록된 데이터 연결 ID입니다. 다른 ID를 쓰세요.",
      source_control_conflict:"지금 연결 상태에서는 이 작업을 할 수 없습니다. 연결 목록에서 상태를 확인하세요.",
      source_not_found:"등록되지 않은 연결입니다. 목록을 다시 읽으세요.",
      invalid_source_action:"서버가 입력을 받아들이지 않았습니다. 설비·열·파일 형식을 확인하세요.",
      command_capacity_exceeded:"요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
      source_state_unavailable:"저장소에 쓰지 못했습니다. 시스템 상태를 확인한 뒤 다시 시도하세요.",
      supervisor_required:"보기 전용이라 바꿀 수 없습니다. 운영을 시작하면 바꿀 수 있습니다.",
    };
    return known[cause.code]??"요청이 거부됐습니다. 로컬 서버 상태를 확인한 뒤 다시 시도하세요.";
  }
  return cause instanceof Error?cause.message:"요청에 실패했습니다.";
}

export async function base64(blob:Blob):Promise<string>{
  const bytes=new Uint8Array(await blob.arrayBuffer());
  const parts:string[]=[];
  for(let offset=0;offset<bytes.length;offset+=8192)
    parts.push(String.fromCharCode(...bytes.subarray(offset,offset+8192)));
  return btoa(parts.join(""));
}

function unexpected():never{
  throw new OutcomeUnknown("응답의 대상이나 형식이 요청과 다릅니다. 연결 목록을 다시 읽어 확인하세요.");
}
function text(raw:unknown):string|null{return typeof raw==="string"&&raw?raw:null;}

export function parsePreflight(raw:Record<string,unknown>):Preflight{
  if(raw.meaning!=="csv-preflight-only-not-registered-or-ingested"
    ||!["ready","needs_input","blocked"].includes(String(raw.status)))unexpected();
  const issue=object(raw.issue);
  const match=raw.registration_match;
  return {status:raw.status as Preflight["status"],
    sampleCount:typeof raw.sample_count==="number"?raw.sample_count:null,
    channels:Array.isArray(raw.channel_columns)?raw.channel_columns.filter((x):x is string=>typeof x==="string"):[],
    first:text(raw.first_timestamp),last:text(raw.last_timestamp),
    warnings:Array.isArray(raw.quality_warnings)?raw.quality_warnings.filter((x):x is string=>typeof x==="string"):[],
    match:match==="absent"||match==="matching"||match==="conflict"||match==="unchecked"?match:null,
    issue:issue?{code:String(issue.code??""),guidance:String(issue.guidance??""),
      row:typeof issue.row_number==="number"?issue.row_number:null,column:text(issue.column)}:null};
}

export async function preflightUpload(setup:CsvSetup,file:Blob,signal:AbortSignal):Promise<Preflight>{
  return parsePreflight(await postWrite("/api/v1/sources/file/upload/preflight",
    {setup,csv_base64:await base64(file)},signal));
}

export async function registerUpload(setup:CsvSetup,file:Blob,signal:AbortSignal):Promise<void>{
  const result=await postWrite("/api/v1/sources/file/upload",{setup,csv_base64:await base64(file)},signal);
  if(result.registration_state!=="registered"||result.source_id!==setup.source_id)unexpected();
}

export async function setLifecycle(sourceId:string,target:"active"|"paused",signal:AbortSignal):Promise<void>{
  const result=await postWrite("/api/v1/sources/lifecycle",{source_id:sourceId,target_state:target},signal);
  if(result.source_id!==sourceId||result.lifecycle_state!==target)unexpected();
}

/** Records only the wanted collection state; actual receipt is read from the connection. */
export async function requestCollection(sourceId:string,target:"running"|"stopped",signal:AbortSignal):Promise<void>{
  const result=await postWrite("/api/v1/sources/collection",{source_id:sourceId,target_state:target},signal);
  if(result.source_id!==sourceId||result.desired_state!==target)unexpected();
}

function receipt(result:Record<string,unknown>,sourceId:string,meaning:string):Receipt{
  if(result.source_id!==sourceId||result.meaning!==meaning
    ||!["succeeded","failed","skipped"].includes(String(result.cycle_state)))unexpected();
  const accepted=result.cycle_state==="succeeded"&&result.accepted_new_receipt===true;
  return {accepted,receivedAt:accepted?text(result.accepted_received_at):null,failure:text(result.failure_scope)};
}

export async function receiveFile(sourceId:string,signal:AbortSignal):Promise<Receipt>{
  return receipt(await postWrite("/api/v1/sources/file/receive",{source_id:sourceId},signal),
    sourceId,"file-receipt-only-not-history-backfill");
}

export async function diagnoseOpcua(sourceId:string,signal:AbortSignal):Promise<Receipt>{
  return receipt(await postWrite("/api/v1/sources/opcua/diagnose",{source_id:sourceId},signal),
    sourceId,"one-shot-opcua-read-not-continuous-collection-or-history");
}

/** Starts the supervisor's background history write; a retry reuses a stored batch. */
export async function startHistory(sourceId:string,signal:AbortSignal):Promise<string>{
  const result=await postWrite("/api/v1/sources/file/backfill/start",{source_id:sourceId},signal);
  if(result.source_id!==sourceId||!["running","succeeded"].includes(String(result.state))
    ||typeof result.started_at!=="string")unexpected();
  return result.started_at;
}

export class HistoryFailed extends Error {}

/** Waits for the job that started at `startedAt`. A failed status read is not a failed write. */
export async function waitForHistory(
  sourceId:string,startedAt:string,signal:AbortSignal,onTick:(seconds:number,known:boolean)=>void,
  {interval=1000,limit=15*60*1000}:{interval?:number;limit?:number}={},
):Promise<{eventCount:number;snapshotId:number}>{
  const began=Date.now();
  for(;;){
    await new Promise(resolve=>setTimeout(resolve,interval));
    if(signal.aborted)throw new DOMException("aborted","AbortError");
    let job:Source["job"]=null;
    try{job=(await readSources(signal)).items.find(item=>item.sourceId===sourceId)?.job??null;}catch{/* keep waiting */}
    onTick(Math.round((Date.now()-began)/1000),job!==null);
    if(job&&job.startedAt!==startedAt)throw new OutcomeUnknown("다른 이력 저장 작업이 시작됐습니다. 연결 목록에서 확인하세요.");
    if(job?.state==="succeeded"&&job.eventCount!==null&&job.snapshotId!==null)
      return {eventCount:job.eventCount,snapshotId:job.snapshotId};
    if(job?.state==="failed")throw new HistoryFailed(job.failure==="source_control_conflict"
      ?"이력을 저장할 수 없는 상태입니다. 파일 읽기 확인과 시각 열을 확인하세요."
      :"이력 저장에 실패했습니다. 시간대가 있는 시각과 원본 파일을 확인한 뒤 다시 시도하세요.");
    if(job?.state==="interrupted")throw new HistoryFailed("서비스 재시작으로 이력 저장이 중단됐습니다. 다시 시도하면 이어서 저장합니다.");
    if(Date.now()-began>limit)throw new OutcomeUnknown("이력 저장 결과를 확인하지 못했습니다. 연결 목록에서 저장 상태를 확인하세요.");
  }
}

function saved(result:Record<string,unknown>,sourceId:string,meaning:string):SavedAnalysis{
  if(result.source_id!==sourceId||result.meaning!==meaning||typeof result.asset_id!=="string"
    ||typeof result.analysis_run_id!=="string"||typeof result.evidence_id!=="string")unexpected();
  return {assetId:result.asset_id,runId:result.analysis_run_id,evidenceId:result.evidence_id};
}

export async function analyzeFile(sourceId:string,signal:AbortSignal):Promise<SavedAnalysis>{
  return saved(await postWrite("/api/v1/analysis/file",{source_id:sourceId},signal),
    sourceId,"persisted-file-statistical-features-not-diagnosis-or-history");
}

export async function analyzePhase(sourceId:string,signal:AbortSignal):Promise<SavedAnalysis>{
  return saved(await postWrite("/api/v1/analysis/phase-file",{source_id:sourceId},signal),
    sourceId,"persisted-phase-unbalance-from-bound-file-history-not-fault-diagnosis");
}

/** History of a connection is known as stored only from a finished job or a committed batch. */
export function historyStored(source:Source):boolean{
  return source.job?.state==="succeeded"||source.live?.historyCommittedAt!=null;
}

/** The one next action that moves this connection forward, with why. */
export function nextStep(source:Source,analyzed:boolean):Step{
  if(source.lifecycle!=="active"){
    return source.lifecycle===null?{action:null,text:"관리 상태를 확인하지 못했습니다. 목록을 다시 읽으세요."}
      :{action:"activate",text:"사용 전입니다. 이 연결을 사용하면 데이터를 읽을 수 있습니다."};
  }
  if(source.type==="file"){
    if(analyzed)return {action:null,text:"저장된 분석이 있습니다. 분석 기록에서 볼 수 있습니다."};
    if(source.job?.state==="running")return {action:null,text:"측정 이력을 저장하고 있습니다."};
    if(historyStored(source))return {action:"analyze",text:"측정 이력이 저장됐습니다. 신호 통계를 분석할 수 있습니다."};
    if(source.receiptConfirmed)return {action:"store",text:"파일을 읽었습니다. 측정 이력을 저장하면 신호를 그래프로 봅니다."};
    return {action:"receive",text:"사용 중입니다. 다음은 파일을 한 번 읽어 확인하는 것입니다."};
  }
  if(!source.receiptConfirmed)return {action:"diagnose",text:"OPC UA 서버에서 한 번 읽어 연결을 확인하세요."};
  if(source.live?.desired!=="running")return {action:"collect",text:"연결을 확인했습니다. 연속 수집을 시작할 수 있습니다."};
  return {action:null,text:"수집을 요청했습니다. 실제 수신은 위 상태로 판단합니다."};
}

export const ACTION_LABEL:Record<Action,string>={
  activate:"이 연결 사용하기",pause:"일시정지",receive:"파일 읽기 확인",store:"측정 이력 저장",
  analyze:"신호 통계 분석",phase:"3상 불평형 분석",diagnose:"1회 읽기로 연결 확인",
  collect:"수집 시작 요청",stop:"수집 중지 요청",
};

/** Further actions for this connection besides the next step. */
export function otherActions(source:Source,next:Action|null):Action[]{
  const actions:Action[]=[];
  if(source.lifecycle==="active")actions.push("pause");
  if(source.lifecycle==="active"&&source.type==="file"){
    actions.push("receive");
    if(source.receiptConfirmed)actions.push("store","analyze");
    if(source.receiptConfirmed&&source.phaseBindings>=3)actions.push("phase");
  }
  if(source.lifecycle==="active"&&source.type==="opcua"){
    actions.push("diagnose");
    if(source.receiptConfirmed)actions.push(source.live?.desired==="running"?"stop":"collect");
  }
  return actions.filter(action=>action!==next);
}

/** A declared 3-phase role of one CSV column, with the evidence a person gave for it. */
export type PhaseRole={
  channel_id:string;quantity:"voltage"|"current";phase:"R"|"S"|"T";
  unit_evidence:string;interpretation_evidence:string;
};
export type FileRegistration={
  source_id:string;name:string;asset_id:string;measurement_point_id:string;
  channel_columns:string[];timestamp_column:string;phase_channels:PhaseRole[];
};

export const PHASE_ROLES:readonly {quantity:"voltage"|"current";phase:"R"|"S"|"T";label:string}[]=[
  {quantity:"voltage",phase:"R",label:"전압 R상"},{quantity:"voltage",phase:"S",label:"전압 S상"},
  {quantity:"voltage",phase:"T",label:"전압 T상"},{quantity:"current",phase:"R",label:"전류 R상"},
  {quantity:"current",phase:"S",label:"전류 S상"},{quantity:"current",phase:"T",label:"전류 T상"},
];
/** What a person enters per role: the column, and how the unit and the phase wiring were confirmed. */
export type RoleInput={channel:string;unit:string;meaning:string};
export function emptyRoles():RoleInput[]{return PHASE_ROLES.map(()=>({channel:"",unit:"",meaning:""}));}
export function declaredRoles(inputs:RoleInput[]):PhaseRole[]{
  return inputs.flatMap((role,index):PhaseRole[]=>role.channel?[{channel_id:role.channel,
    quantity:PHASE_ROLES[index].quantity,phase:PHASE_ROLES[index].phase,
    unit_evidence:role.unit.trim(),interpretation_evidence:role.meaning.trim()}]:[]);
}
// The whole name must be a quantity, an optional separator and a phase: vR, iT, voltage_a, Current_L1.
const ROLE_NAME={voltage:/^(?:v|u|volt|voltage)[ _-]?(?:phase[ _-]?)?(r|s|t|a|b|c|l1|l2|l3|1|2|3)$/i,
  current:/^(?:i|amp|amps|curr|current)[ _-]?(?:phase[ _-]?)?(r|s|t|a|b|c|l1|l2|l3|1|2|3)$/i};
const PHASE_TOKEN:Record<string,"R"|"S"|"T">={r:"R",a:"R",l1:"R","1":"R",s:"S",b:"S",l2:"S","2":"S",t:"T",c:"T",l3:"T","3":"T"};
/** Suggests only the column for each empty role, when exactly one column name fits.
 * The unit and wiring evidence stays for a person to write. */
export function suggestRoles(channels:string[],current:RoleInput[]):RoleInput[]{
  return PHASE_ROLES.map((role,index)=>{
    const now=current[index]??{channel:"",unit:"",meaning:""};
    if(now.channel)return now;
    const fits=channels.filter(name=>{
      const match=ROLE_NAME[role.quantity].exec(name);
      return match!==null&&PHASE_TOKEN[match[1].toLowerCase()]===role.phase;
    });
    return {...now,channel:fits.length===1?fits[0]:""};
  });
}

/** Roles are optional; when given, each quantity has all of R, S and T on distinct columns. */
export function phaseRoleProblem(roles:PhaseRole[],channels:string[]):string|null{
  if(!roles.length)return null;
  if(roles.length!==3&&roles.length!==6)return "3상 역할은 전압 또는 전류의 R/S/T 세 개를 한 세트로 지정하세요.";
  const used=new Set<string>(),pairs=new Set<string>();
  for(const role of roles){
    if(!channels.includes(role.channel_id))return role.channel_id+" 열이 측정값 열에 없습니다.";
    if(used.has(role.channel_id))return role.channel_id+" 열을 두 역할에 쓸 수 없습니다.";
    if(!role.unit_evidence.trim()||!role.interpretation_evidence.trim())return "역할마다 단위 근거와 해석 근거를 적으세요.";
    if(role.unit_evidence.length>128||role.interpretation_evidence.length>128)return "근거는 128자 이내로 적으세요.";
    used.add(role.channel_id);pairs.add(role.quantity+":"+role.phase);
  }
  for(const quantity of ["voltage","current"]){
    const count=["R","S","T"].filter(phase=>pairs.has(quantity+":"+phase)).length;
    if(count&&count!==3)return (quantity==="voltage"?"전압":"전류")+"의 R/S/T를 모두 지정하세요.";
  }
  return null;
}

function setupOf(values:FileRegistration):Record<string,unknown>{
  const {phase_channels,...rest}=values;
  return phase_channels.length?{...rest,phase_channels}:rest;
}

/** Checks a CSV already in the workspace (`filePath`) or a chosen file, without saving. */
export async function preflightCsv(values:FileRegistration,file:Blob|null,filePath:string,signal:AbortSignal):Promise<Preflight>{
  return parsePreflight(file
    ?await postWrite("/api/v1/sources/file/upload/preflight",{setup:setupOf(values),csv_base64:await base64(file)},signal)
    :await postWrite("/api/v1/sources/file/preflight",{...setupOf(values),file_path:filePath},signal));
}

export async function registerCsv(values:FileRegistration,file:Blob|null,filePath:string,signal:AbortSignal):Promise<void>{
  const result=file
    ?await postWrite("/api/v1/sources/file/upload",{setup:setupOf(values),csv_base64:await base64(file)},signal)
    :await postWrite("/api/v1/sources/file",{...setupOf(values),file_path:filePath},signal);
  if(result.registration_state!=="registered"||result.source_id!==values.source_id)unexpected();
}

export type OpcuaNode={name:string;nodeId:string};
export type OpcuaBrowse={variables:OpcuaNode[];objects:OpcuaNode[];visited:number|null;truncated:boolean};

/** Address space candidates of a local server; nothing is received or registered. */
export async function browseOpcua(endpoint:string,startNode:string,signal:AbortSignal):Promise<OpcuaBrowse>{
  const result=await postWrite("/api/v1/sources/opcua/browse",{endpoint_url:endpoint,start_node_id:startNode},signal);
  if(result.meaning!=="address-space-candidates-not-received-or-registered"||result.start_node_id!==startNode
    ||!Array.isArray(result.variables)||!Array.isArray(result.objects))unexpected();
  const nodes=(items:unknown[],key:string):OpcuaNode[]=>items.flatMap(raw=>{
    const row=object(raw);
    return row&&typeof row.node_id==="string"?[{name:String(row[key]??row.node_id),nodeId:row.node_id}]:[];
  });
  return {variables:nodes(result.variables,"display_name"),objects:nodes(result.objects,"browse_name"),
    visited:typeof result.visited_node_count==="number"?result.visited_node_count:null,truncated:result.truncated===true};
}

export type OpcuaRegistration={
  source_id:string;name:string;asset_id:string;measurement_point_id:string;endpoint_url:string;
  node_mappings:{channel_id:string;node_id:string}[];
};
export async function registerOpcua(values:OpcuaRegistration,signal:AbortSignal):Promise<void>{
  const result=await postWrite("/api/v1/sources/opcua",values,signal);
  if(result.registration_state!=="registered"||result.source_id!==values.source_id)unexpected();
}

/** A channel ID from an OPC UA display name: letters, digits, '_' and '-' only. */
export function channelIdFrom(name:string,taken:string[]):string{
  const base=name.trim().replace(/[^A-Za-z0-9_-]+/g,"_").replace(/^_+|_+$/g,"").slice(0,60)||"channel";
  let candidate=base,index=2;
  while(taken.includes(candidate))candidate=base+"_"+index++;
  return candidate;
}

export type Sample={state:"running"|"stopped";url:string|null;scenario?:"bearing"|"live"|"xjtu";assetId?:string;xjtuAvailable?:boolean};
const SAMPLE_URL=/^http:\/\/127\.0\.0\.1:(\d{2,5})\/web\/$/;

/** The isolated synthetic sample runs in its own workspace; only its local address is used. */
export function parseSample(raw:Record<string,unknown>):Sample{
  if((raw.synthetic!==true&&!(raw.synthetic===false&&(raw.scenario==="xjtu"||typeof raw.xjtu_available==="boolean")))||(raw.state!=="running"&&raw.state!=="stopped"))unexpected();
  if(raw.state==="stopped")return {state:"stopped",url:null,...(typeof raw.xjtu_available==="boolean"?{xjtuAvailable:raw.xjtu_available}:{})};
  const match=typeof raw.url==="string"?SAMPLE_URL.exec(raw.url):null;
  if(raw.separate_workspace!==true||!match||Number(match[1])>65535)unexpected();
  if(raw.scenario!==undefined&&raw.scenario!=="bearing"&&raw.scenario!=="live"&&raw.scenario!=="xjtu")unexpected();
  if(raw.synthetic===false&&raw.scenario!=="xjtu")unexpected();
  if(raw.scenario==="xjtu"&&(typeof raw.asset_id!=="string"||!raw.asset_id||raw.asset_id.length>256))unexpected();
  return {state:"running",url:raw.url as string,xjtuAvailable:raw.xjtu_available===true,
    ...(typeof raw.asset_id==="string"?{assetId:raw.asset_id}:{}),
    ...(raw.scenario?{scenario:raw.scenario as "bearing"|"live"|"xjtu"}:{})};
}

/** The example opens on this page's own loopback name. Browsers treat localhost and 127.0.0.1
 * as different sites, and the example server refuses cross-site requests. */
export function exampleOpenUrl(sampleUrl:string,pageHostname:string,params:Record<string,string>):string{
  const url=new URL(sampleUrl);
  if(pageHostname==="localhost"||pageHostname==="127.0.0.1")url.hostname=pageHostname;
  url.search=new URLSearchParams(params).toString();
  return url.toString();
}

export async function sampleCommand(action:"status"|"start"|"stop",signal:AbortSignal,scenario:"bearing"|"live"|"xjtu"="live"):Promise<Sample>{
  const sample=parseSample(await postWrite("/api/v1/demo/"+(scenario==="live"?"synthetic":scenario)+"/"+action,{},signal));
  return sample.state==="running"?{...sample,scenario:sample.scenario??scenario}:sample;
}
