/** A model's stored scores over its whole input order, its threshold-exceedance intervals and
 * the raw input of one measurement. Nothing is rescored; a skipped step stays a gap. */
import type {ModelBinding,StepPointer} from "./model-evidence.ts";
import {object} from "./writes.ts";

export type TrendPoint={pointer:StepPointer;score:number|null;threshold:number|null;exceeds:boolean|null;eventStart:string|null};
export type Interval={start:number;end:number;steps:number;peak:number|null;open:boolean};
export type ScoreTrend={points:TrendPoint[];intervals:Interval[];truncated:boolean};
export type Envelope={channel:string;bands:[number,number][]};
export type Waveform=
  |{available:false;reason:string}
  |{available:true;fileName:string;rateHz:number;samples:number;perBin:number;channels:Envelope[]};
export type WindowChannel={channel:string;unit:string|null;points:{at:string;value:number|null}[]};
export type WindowInput=
  |{available:false;reason:string}
  |{available:true;start:string;end:string;channels:WindowChannel[]};

const MAX_PAGES=4;

function invalid(what:string):never{throw new Error("모델 "+what+"의 형식이 올바르지 않습니다.");}
function finite(raw:unknown):number|null{return typeof raw==="number"&&Number.isFinite(raw)?raw:null;}
function whole(raw:unknown,what:string):number{
  if(typeof raw!=="number"||!Number.isSafeInteger(raw)||raw<0)invalid(what);
  return raw;
}

function pointer(raw:Record<string,unknown>):StepPointer{
  if(raw.state!=="analyzed"&&raw.state!=="skipped")invalid("결과 상태");
  if(typeof raw.analysis_run_id!=="string"||typeof raw.step_key!=="string")invalid("실행 기록");
  return {position:whole(raw.position,"입력 순서"),runId:raw.analysis_run_id,state:raw.state,stepKey:raw.step_key,
    changeSeq:whole(raw.change_seq,"변경 순번"),reason:typeof raw.reason==="string"?raw.reason:null};
}

/** One page of stored results for this binding, merged by position into what was read before. */
export function mergeSeries(raw:unknown,binding:ModelBinding,known:Map<number,TrendPoint>):{
  intervals:Interval[];cursor:number;more:boolean;
}{
  const root=object(raw);
  const owner=object(root?.binding);
  if(!root||root.schema_version!==1||owner?.binding_id!==binding.bindingId||!Array.isArray(root.steps)
    ||!Array.isArray(root.intervals))invalid("점수 기록");
  for(const item of root.steps){
    const row=object(item);
    if(!row)invalid("점수 기록");
    const output=object(row.output)??{};
    const step=pointer(row);
    known.set(step.position,{pointer:step,score:step.state==="analyzed"?finite(output.score):null,
      threshold:finite(output.threshold),
      exceeds:typeof output.exceeds_threshold==="boolean"?output.exceeds_threshold:null,
      eventStart:typeof row.event_start==="string"?row.event_start:null});
  }
  const intervals=root.intervals.map((item:unknown):Interval=>{
    const row=object(item);
    if(!row)invalid("기준 초과 구간");
    return {start:whole(row.start_position,"구간 시작"),end:whole(row.end_position,"구간 끝"),
      steps:whole(row.step_count,"구간 길이"),peak:finite(row.peak_score),open:row.open===true};
  });
  return {intervals,cursor:whole(root.change_seq,"변경 순번"),more:root.has_more===true};
}

async function read(url:string,signal:AbortSignal,failure:string):Promise<unknown>{
  const response=await fetch(url,{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error(failure);
  }
  return await response.json() as unknown;
}

/** All stored results up to a bounded number of pages, in input order. */
export async function readScoreTrend(binding:ModelBinding,signal:AbortSignal):Promise<ScoreTrend>{
  const known=new Map<number,TrendPoint>();
  let cursor=0,intervals:Interval[]=[],more=true,pages=0;
  while(more&&pages<MAX_PAGES){
    const page=mergeSeries(await read("/api/v1/phm/series?"+new URLSearchParams({binding_id:binding.bindingId,since:String(cursor)}),
      signal,"점수 추이를 불러오지 못했습니다. 기록이 없다는 뜻은 아닙니다."),binding,known);
    cursor=page.cursor;intervals=page.intervals;more=page.more;pages++;
  }
  return {points:[...known.values()].sort((a,b)=>a.pointer.position-b.pointer.position),intervals,truncated:more};
}

export function parseWaveform(raw:unknown,position:number):Waveform{
  const root=object(raw);
  if(!root||root.position!==position)invalid("원본 파형");
  if(root.available===false)return {available:false,reason:typeof root.reason==="string"?root.reason:"원본을 읽을 수 없습니다"};
  if(root.available!==true||!Array.isArray(root.channels)||typeof root.file_name!=="string")invalid("원본 파형");
  const channels=root.channels.map((item:unknown):Envelope=>{
    const row=object(item);
    if(!row||typeof row.channel!=="string"||!Array.isArray(row.envelope))invalid("원본 파형");
    return {channel:row.channel,bands:row.envelope.map((band:unknown):[number,number]=>{
      if(!Array.isArray(band)||band.length!==2||finite(band[0])===null||finite(band[1])===null)invalid("원본 파형");
      return [band[0] as number,band[1] as number];
    })};
  });
  return {available:true,fileName:root.file_name,rateHz:finite(root.sampling_rate_hz)??0,
    samples:whole(root.sample_count,"표본 수"),perBin:whole(root.samples_per_bin,"묶음 크기"),channels};
}

export function parseWindow(raw:unknown,position:number):WindowInput{
  const root=object(raw);
  if(!root)invalid("관측 구간");
  if(root.available===false)return {available:false,reason:typeof root.reason==="string"?root.reason:"관측을 읽을 수 없습니다"};
  if(root.available!==true||root.position!==position||!Array.isArray(root.channels)
    ||typeof root.start!=="string"||typeof root.end!=="string")invalid("관측 구간");
  return {available:true,start:root.start,end:root.end,channels:root.channels.map((item:unknown):WindowChannel=>{
    const row=object(item);
    if(!row||typeof row.channel_id!=="string"||!Array.isArray(row.points))invalid("관측 구간");
    return {channel:row.channel_id,unit:typeof row.unit==="string"?row.unit:null,
      points:row.points.map((point:unknown)=>{
        const value=object(point);
        if(!value||typeof value.at!=="string")invalid("관측 구간");
        return {at:value.at,value:value.quality==="good"?finite(value.value):null};
      })};
  })};
}

export async function readInput(binding:ModelBinding,position:number,signal:AbortSignal):Promise<Waveform|WindowInput>{
  const query=new URLSearchParams({binding_id:binding.bindingId,position:String(position)});
  if(binding.stepKind==="acquisition-snapshot"){
    query.set("bins","400");
    return parseWaveform(await read("/api/v1/phm/snapshot?"+query,signal,"원본 파형을 불러오지 못했습니다."),position);
  }
  return parseWindow(await read("/api/v1/phm/window?"+query,signal,"관측 구간을 불러오지 못했습니다."),position);
}

/** Plain counts that say what the trend shows before anyone reads the graph. */
export function trendSummary(trend:ScoreTrend):{analyzed:number;skipped:number;exceeded:number;open:number}{
  let analyzed=0,skipped=0,exceeded=0;
  for(const point of trend.points){
    if(point.pointer.state==="skipped")skipped++;
    else{analyzed++;if(point.exceeds)exceeded++;}
  }
  return {analyzed,skipped,exceeded,open:trend.intervals.filter(item=>item.open).length};
}
