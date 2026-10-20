/** Stored comparisons and server-computed range shapes; the browser does not fit trends. */
import type {ModelBinding,ModelRun} from "./model-evidence.ts";
import type {FeatureChange} from "./model-explanations.ts";
import {object} from "./writes.ts";

export type Focus={position:number;series:string|null};
export type Comparison={features:FeatureChange[];previousScore:number|null;previousRunId:string|null};
export type Shape={count:number;trend:"insufficient"|"flat"|"increasing"|"decreasing"|"mixed";steady:boolean;
  largest:{from:number;to:number;direction:"increase"|"decrease"}|null;
  shift:{at:number;direction:"increase"|"decrease"}|null};
export type ModelRange={steps:number;points:number;sampled:boolean;primary:Shape;features:{name:string;label:string;shape:Shape}[]};
function invalid():never{throw new Error("측정 비교와 구간 흐름의 대상·근거 형식이 올바르지 않습니다.");}
function finite(v:unknown):number|null{if(v===null)return null;if(typeof v!=="number"||!Number.isFinite(v))invalid();return v;}
function integer(v:unknown,min=0):number{if(typeof v!=="number"||!Number.isSafeInteger(v)||v<min)invalid();return v;}
export function parseComparison(raw:unknown,binding:ModelBinding,run:ModelRun,previous:number|null):Comparison{
  const root=object(raw);
  if(!root||root.schema_version!==1||root.binding_id!==binding.bindingId||root.position!==run.position
    ||root.analysis_run_id!==run.runId||root.compare_position!==previous||(previous!==null&&previous>=run.position)
    ||(previous!==null?typeof root.previous_analysis_run_id!=="string":root.previous_analysis_run_id!==null)||!Array.isArray(root.features)||root.features.length>64)invalid();
  const seen=new Set<string>();
  const features=root.features.map((value:unknown):FeatureChange=>{
    const row=object(value);
    if(!row||typeof row.feature!=="string"||typeof row.label!=="string"||seen.has(row.feature))invalid();
    seen.add(row.feature);
    const current=finite(row.current);
    if(current===null)invalid();
    return {feature:row.feature,label:row.label,current,previous:finite(row.previous),relativePercent:finite(row.relative_change_percent),
      unit:typeof row.unit==="string"&&row.unit.trim()?row.unit:null};
  });
  return {features,previousScore:finite(root.previous_score),previousRunId:root.previous_analysis_run_id as string|null};
}
function shape(raw:unknown,first:number,last:number):Shape{
  const row=object(raw);
  if(!row||!["insufficient","flat","increasing","decreasing","mixed"].includes(String(row.trend)))invalid();
  const within=(v:unknown)=>{const n=integer(v,1);if(n<first||n>last)invalid();return n;};
  const direction=(v:unknown)=>{if(v!=="increase"&&v!=="decrease")invalid();return v;};
  let largest:Shape["largest"]=null,shift:Shape["shift"]=null;
  if(row.largest_step!==null&&row.largest_step!==undefined){
    const value=object(row.largest_step);if(!value)invalid();
    largest={from:within(value.from),to:within(value.to),direction:direction(value.direction)};
    if(largest.from>=largest.to)invalid();
  }
  if(row.level_shift!==null&&row.level_shift!==undefined){
    const value=object(row.level_shift);if(!value)invalid();
    shift={at:within(value.at),direction:direction(value.direction)};
    if(shift.at<=first)invalid();
  }
  return {count:integer(row.count),trend:row.trend as Shape["trend"],steady:row.steady===true,largest,shift};
}
export function parseRange(raw:unknown,binding:ModelBinding,run:ModelRun,previous:number,comparison:Comparison):ModelRange{
  const row=object(raw),features=object(row?.features);
  if(!row||row.schema_version!==1||row.binding_id!==binding.bindingId||row.first!==previous||row.last!==run.position
    ||!features||Object.keys(features).length>8||typeof row.sampled!=="boolean"
    ||row.largest_step_basis!=="adjacent-analyzed-results-in-full-range"
    ||row.flow_basis!==(row.sampled?"sampled-results":"all-results"))invalid();
  const known=new Map(comparison.features.map(feature=>[feature.feature,feature.label]));
  const points=integer(row.points),steps=integer(row.steps);
  if(points>steps||points>513||(!row.sampled&&points!==steps))invalid();
  return {steps,points,sampled:row.sampled,primary:shape(row.primary,previous,run.position),
    features:Object.entries(features).map(([name,value])=>{
      const label=known.get(name);if(!label)invalid();
      return {name,label,shape:shape(value,previous,run.position)};
    })};
}
async function read(path:string,signal:AbortSignal):Promise<unknown>{
  const response=await fetch(path,{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){await response.body?.cancel();throw new Error("측정 비교를 읽지 못했습니다. 기록이 없다는 뜻은 아닙니다.");}
  return await response.json() as unknown;
}
export async function readComparison(binding:ModelBinding,run:ModelRun,previous:number|null,signal:AbortSignal):Promise<Comparison>{
  return parseComparison(await read("/api/v1/phm/comparison?"+new URLSearchParams({binding_id:binding.bindingId,position:String(run.position),...(previous!==null?{compare_position:String(previous)}:{})}),signal),binding,run,previous);
}
export async function readRange(binding:ModelBinding,run:ModelRun,previous:number,comparison:Comparison,signal:AbortSignal):Promise<ModelRange>{
  return parseRange(await read("/api/v1/phm/range?"+new URLSearchParams({binding_id:binding.bindingId,from:String(previous),to:String(run.position)}),signal),binding,run,previous,comparison);
}
export function shapeText(shape:Shape):string{
  return shape.trend==="insufficient"?"흐름을 계산할 기록 부족":shape.trend==="flat"?"거의 일정"
    :shape.trend==="mixed"?"오르내림이 섞임":(shape.steady?"꾸준히 ":"전체적으로 ")+(shape.trend==="increasing"?"증가":"감소");
}
