/** Read-only PHM model run provenance; never manufacture Operational Evidence IDs. */
export type StepKind="acquisition-snapshot"|"observation-window";
export type ModelBinding={
  assetId:string;sourceId:string;pointId:string|null;bindingId:string;packageId:string;
  stepKind:StepKind;recordedReplay:boolean;health:string;
  task:string|null;recipeId:string|null;estimatorKind?:string|null;packageAvailable:boolean;
  lastAnalyzed:number|null;lastProcessed:number|null;
};
const METHOD:Record<string,string>={
  "lstm-autoencoder-v1":"LSTM 오토인코더","isolation-forest-refit-v1":"Isolation Forest","pca-residual-v1":"PCA 잔차",
};
/** A connected model as people name it: its method, else its recipe, else its package without
 * the content hash. The recipe, package and binding identifiers stay under 기술 상세. */
export function modelName(binding:{recipeId:string|null;packageId:string;estimatorKind?:string|null}):string{
  return (binding.estimatorKind?METHOD[binding.estimatorKind]:undefined)
    ?? binding.recipeId ?? binding.packageId.replace(/-[0-9a-f]{12}$/,"");
}
/** Names for a list of models on one screen; two models of the same method keep their recipe. */
export function modelNames(bindings:ModelBinding[]):Map<string,string>{
  const names=new Map(bindings.map(binding=>[binding.bindingId,modelName(binding)]));
  for(const binding of bindings){
    const name=names.get(binding.bindingId)!;
    if(bindings.some(other=>other.bindingId!==binding.bindingId&&modelName(other)===name)&&binding.recipeId&&binding.recipeId!==name)
      names.set(binding.bindingId,name+" · "+binding.recipeId);
  }
  return names;
}
export type StepPointer={
  position:number;runId:string;state:"analyzed"|"skipped";stepKey:string;changeSeq:number;
  reason:string|null;
};
export type ModelTrace={bindingId:string;steps:StepPointer[];limit:number};
export type ModelRun={
  bindingId:string;assetId:string;sourceId:string;pointId:string|null;
  packageId:string;position:number;runId:string;state:"analyzed"|"skipped";
  stepKey:string;changeSeq:number;replay:boolean;eventStart:string|null;
  eventEnd:string|null;processedAt:string;reason:string|null;
  evidenceKind:StepKind;inputReference:Record<string,unknown>;
  output:Record<string,unknown>;features:Record<string,unknown>|null;
};
export class NoModelEvidence extends Error {}
function obj(v:unknown):Record<string,unknown>|null{
  return v!==null&&typeof v==="object"&&!Array.isArray(v)?v as Record<string,unknown>:null;
}
function id(v:unknown):string{
  if(typeof v!=="string"||!v||v.length>512||/[\x00-\x1f]/.test(v))
    throw new Error("모델 분석 식별자가 올바르지 않습니다.");
  return v;
}
function position(v:unknown):number{
  if(typeof v!=="number"||!Number.isSafeInteger(v)||v<1)
    throw new Error("모델 입력의 측정 위치가 올바르지 않습니다.");
  return v;
}
function sequence(v:unknown):number{
  if(typeof v!=="number"||!Number.isSafeInteger(v)||v<0)
    throw new Error("저장 변경 순번이 올바르지 않습니다.");
  return v;
}
function axis(v:unknown):StepKind {
  if(v!=="acquisition-snapshot"&&v!=="observation-window")
    throw new Error("모델 입력 축을 확인할 수 없습니다.");
  return v;
}
function time(v:unknown):string|null{
  if(v===null)return null;
  const value=id(v);
  if(!/(?:Z|[+-]\d\d:\d\d)$/i.test(value)||!Number.isFinite(Date.parse(value)))
    throw new Error("분석 근거의 기록 시각이 올바르지 않습니다.");
  return value;
}
function safeRecord(v:unknown):Record<string,unknown>{
  const record=obj(v);
  if(!record||Object.keys(record).length>256)
    throw new Error("분석 근거의 구조가 올바르지 않습니다.");
  const text=JSON.stringify(record);
  if(!text||text.length>18000)
    throw new Error("분석 근거가 허용된 표시 범위를 초과했습니다.");
  const valid=(x:unknown,depth:number):boolean=>{
    if(depth>9)return false;
    if(x===null||typeof x==="string"||typeof x==="boolean")return true;
    if(typeof x==="number")return Number.isFinite(x);
    if(Array.isArray(x))return x.length<=256&&x.every(k=>valid(k,depth+1));
    const r=obj(x);
    return !!r&&Object.keys(r).length<=256&&Object.values(r).every(k=>valid(k,depth+1));
  };
  if(!valid(record,0))throw new Error("분석 근거에 유효하지 않은 값이 있습니다.");
  return record;
}
/** Bindings of one asset, or of every asset when `assetId` is null. */
export function parseModelBindings(raw:unknown,assetId:string|null):ModelBinding[]{
  const root=obj(raw);
  if(!root||root.schema_version!==1||!Array.isArray(root.bindings)||root.bindings.length>1000)
    throw new Error("적용 모델 목록의 형식이 올바르지 않습니다.");
  const seen=new Set<string>();
  return root.bindings.map((entry:unknown):ModelBinding=>{
    const row=obj(entry);
    if(!row)throw new Error("적용 모델 정보를 확인할 수 없습니다.");
    const bindingId=id(row.binding_id);
    if(seen.has(bindingId))throw new Error("같은 적용 모델이 두 번 돌아왔습니다.");
    seen.add(bindingId);
    const packageSummary=row.package===null?null:obj(row.package);
    if(row.package!==null&&!packageSummary)
      throw new Error("모델 패키지 정보의 형식이 올바르지 않습니다.");
    const last=(key:"latest_analyzed"|"latest_processed"):number|null=>{
      const candidate=row[key];
      if(candidate===null)return null;
      const brief=obj(candidate);
      return position(brief?.position);
    };
    const asset=id(row.asset_id),source=id(row.source_id),pkg=id(row.package_id);
    const point=row.measurement_point_id===null?null:id(row.measurement_point_id);
    const kind=axis(row.step_kind);
    if(typeof row.recorded_replay!=="boolean")throw new Error("재생 자료 여부를 확인할 수 없습니다.");
    const task=obj(packageSummary?.output)?.task;
    if(packageSummary?.package_id!==undefined&&packageSummary?.package_id!==pkg)
      throw new Error("적용 모델과 모델 패키지가 맞지 않습니다.");
    return {assetId:asset,sourceId:source,pointId:point,bindingId,packageId:pkg,
      stepKind:kind,recordedReplay:row.recorded_replay,health:id(row.health),
      packageAvailable:packageSummary!==null,
      task:typeof task==="string"?task:null,
      recipeId:typeof packageSummary?.recipe_id==="string"?packageSummary.recipe_id:null,
      estimatorKind:typeof packageSummary?.estimator_kind==="string"?packageSummary.estimator_kind:null,
      lastAnalyzed:last("latest_analyzed"),lastProcessed:last("latest_processed")};
  }).filter(binding=>assetId===null||binding.assetId===assetId);
}
function pointer(raw:unknown):StepPointer{
  const row=obj(raw);
  if(!row||!["analyzed","skipped"].includes(String(row.state)))
    throw new Error("저장 모델 단계 상태가 올바르지 않습니다.");
  if(row.reason!==null&&typeof row.reason!=="string")
    throw new Error("저장 모델 단계의 제외 사유가 올바르지 않습니다.");
  return {position:position(row.position),runId:id(row.analysis_run_id),
    stepKey:id(row.step_key),state:row.state as "analyzed"|"skipped",
    changeSeq:sequence(row.change_seq),reason:row.reason as string|null};
}
export function parseModelTrace(raw:unknown,binding:ModelBinding):ModelTrace{
  const root=obj(raw);
  if(!root||root.schema_version!==1||root.binding_id!==binding.bindingId
    ||!Array.isArray(root.steps)||root.limit!==64||root.steps.length>64)
    throw new Error("다른 적용 모델의 결과 목록이 돌아왔습니다.");
  const steps=root.steps.map(pointer);
  if(new Set(steps.map(s=>s.position)).size!==steps.length
    ||new Set(steps.map(s=>s.runId)).size!==steps.length)
    throw new Error("같은 모델 결과가 두 번 돌아왔습니다.");
  return {bindingId:binding.bindingId,steps,limit:64};
}
export function parseModelRun(raw:unknown,binding:ModelBinding,expected:StepPointer):ModelRun{
  const root=obj(raw);
  if(!root||root.schema_version!==1||root.binding_id!==binding.bindingId)
    throw new Error("고른 적용 모델과 다른 결과가 돌아왔습니다.");
  const step=pointer(root.step);
  if(step.position!==expected.position||step.runId!==expected.runId
    ||step.stepKey!==expected.stepKey||step.state!==expected.state
    ||step.changeSeq!==expected.changeSeq)
    throw new Error("고른 측정의 모델 실행 기록과 결과가 맞지 않습니다.");
  const row=obj(root.step);
  if(!row||typeof row.replay!=="boolean")throw new Error("모델 실행 기록의 상태가 올바르지 않습니다.");
  const ref=safeRecord(row.input_reference);
  if(ref.kind!==binding.stepKind||ref.source_id!==binding.sourceId
    ||ref.asset_id!==binding.assetId)
    throw new Error("모델 입력이 선택 설비·출처·입력 축과 일치하지 않습니다.");
  const point=binding.pointId;
  if(binding.stepKind==="acquisition-snapshot"){
    if(ref.ordinal!==step.position||typeof ref.sha256!=="string"
      ||!/^[a-f0-9]{64}$/i.test(ref.sha256))
      throw new Error("모델 입력 파일이 고른 측정과 맞지 않아 표시하지 않았습니다.");
  }else{
    if(ref.measurement_point_id!==point||typeof ref.window_id!=="string"
      ||!ref.window_id||typeof ref.input_digest!=="string"
      ||!/^[a-f0-9]{64}$/i.test(ref.input_digest))
      throw new Error("모델 입력 구간이 고른 측정 위치와 맞지 않아 표시하지 않았습니다.");
  }
  if(step.state==="skipped"&&row.features!==null)
    throw new Error("제외된 단계에 계산 특징이 포함됐습니다.");
  const processedAt=time(row.processed_at);
  if(processedAt===null)throw new Error("모델 처리 시각이 기록되지 않았습니다.");
  const output=safeRecord(row.output);
  const features=row.features===null?null:safeRecord(row.features);
  return {bindingId:binding.bindingId,assetId:binding.assetId,sourceId:binding.sourceId,
    pointId:point,packageId:binding.packageId,position:step.position,runId:step.runId,
    state:step.state,stepKey:step.stepKey,changeSeq:step.changeSeq,
    reason:step.reason,replay:row.replay,eventStart:time(row.event_start),
    eventEnd:time(row.event_end),processedAt,
    evidenceKind:binding.stepKind,inputReference:ref,output,features};
}
async function get(url:string,signal:AbortSignal):Promise<unknown>{
  const response=await fetch(url,{signal,cache:"no-store",credentials:"same-origin"});
  if(response.status===404){
    const body:unknown=await response.json().catch(()=>null);
    if(obj(body)?.error==="unknown_binding"||obj(body)?.error==="invalid_phm_query")
      throw new NoModelEvidence("고른 모델 결과를 더 이상 찾을 수 없습니다.");
  }
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("모델 결과를 읽지 못했습니다. 결과가 없다는 뜻은 아닙니다.");
  }
  return await response.json() as unknown;
}
export async function loadModelBindings(assetId:string|null,signal:AbortSignal):Promise<ModelBinding[]>{
  return parseModelBindings(await get("/api/v1/phm/bindings",signal),assetId);
}
export async function loadModelTrace(binding:ModelBinding,signal:AbortSignal):Promise<ModelTrace>{
  const query=new URLSearchParams({binding_id:binding.bindingId});
  return parseModelTrace(await get("/api/v1/phm/trace?"+query,signal),binding);
}
export async function loadModelRun(binding:ModelBinding,step:StepPointer,signal:AbortSignal):Promise<ModelRun>{
  const query=new URLSearchParams({binding_id:binding.bindingId,position:String(step.position)});
  return parseModelRun(await get("/api/v1/phm/result?"+query,signal),binding,step);
}

/** A bookmark can name a stored result older than the recent trace. Its position and
 * full input provenance must still match, and an unavailable one never selects another. */
export async function loadModelPosition(binding:ModelBinding,at:number,signal:AbortSignal):Promise<ModelRun>{
  if(!Number.isSafeInteger(at)||at<1)throw new NoModelEvidence("북마크의 측정 위치가 올바르지 않습니다.");
  const raw=await get("/api/v1/phm/result?"+new URLSearchParams({binding_id:binding.bindingId,position:String(at)}),signal);
  const step=pointer(obj(raw)?.step);
  if(step.position!==at)throw new NoModelEvidence("북마크와 다른 측정이 돌아왔습니다.");
  return parseModelRun(raw,binding,step);
}

/** What the stored output says about the score; nothing is recomputed or inferred. */
export type ScoreSummary={score:number|null;threshold:number|null;exceeds:boolean|null};
export function scoreSummary(output:Record<string,unknown>):ScoreSummary{
  const finite=(v:unknown)=>typeof v==="number"&&Number.isFinite(v)?v:null;
  return {score:finite(output.score),threshold:finite(output.threshold),
    exceeds:typeof output.exceeds_threshold==="boolean"?output.exceeds_threshold:null};
}

export type LatestScore={binding:ModelBinding;run:ModelRun|null};
/** The latest analyzed step of each model bound to the asset (at most three models). */
export async function loadLatestScores(assetId:string,signal:AbortSignal):Promise<LatestScore[]>{
  const bindings=(await loadModelBindings(assetId,signal)).slice(0,3);
  return Promise.all(bindings.map(async(binding):Promise<LatestScore>=>{
    const trace=await loadModelTrace(binding,signal);
    const step=trace.steps.find(item=>item.position===binding.lastAnalyzed&&item.state==="analyzed")
      ??trace.steps.find(item=>item.state==="analyzed");
    return {binding,run:step?await loadModelRun(binding,step,signal):null};
  }));
}
