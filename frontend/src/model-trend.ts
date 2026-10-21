/** A model's stored scores over its whole input order, its threshold-exceedance intervals and
 * the raw input of one measurement. Nothing is rescored; a skipped step stays a gap. */
import type {ModelBinding,StepPointer} from "./model-evidence.ts";
import {object} from "./writes.ts";
import {sinceStart} from "./time-axis.ts";

export type TrendPoint={pointer:StepPointer;score:number|null;threshold:number|null;exceeds:boolean|null;eventStart:string|null};
export type Interval={start:number;end:number;steps:number;peak:number|null;open:boolean};
export type ScoreTrend={points:TrendPoint[];intervals:Interval[];truncated:boolean};
export type ThresholdExceedance = TrendPoint & {score: number; threshold: number; exceeds: true};

/** The first stored exceedance in the displayed measurements, including isolated ones that
 * do not meet the model's sustained-interval rule. Never interpolate between measurements. */
export function firstExceedance(points: TrendPoint[]): ThresholdExceedance | null {
  return points.find((point): point is ThresholdExceedance =>
    point.score !== null && point.threshold !== null && point.exceeds === true) ?? null;
}

/** What a person reads first about a model's crossings. A run still going on comes first, then
 * a latest crossing that is not part of a run, then "below now" after earlier crossings. Earlier
 * runs and one-off crossings are counted, and the first crossing is kept for reference, so a
 * one-off crossing never reads like a sustained change. */
export type ExceedanceStory = {
  state: "ongoing" | "latest" | "below" | "none";
  /** The measurement the headline names, and where the graph's dotted line goes. */
  anchor: ThresholdExceedance | null;
  ongoing: Interval | null;
  /** Whether the latest analyzed measurement is over the threshold; a run stays open for the
   * model's allowed gap, so it can still be open while the latest one is below. */
  lastExceeds: boolean | null;
  /** Before the anchor: runs that ended, measurements over the threshold outside any run. */
  earlierRuns: number; earlierSingles: number;
  first: ThresholdExceedance | null;
};
export function exceedanceStory(trend: ScoreTrend): ExceedanceStory {
  const over = trend.points.filter((point): point is ThresholdExceedance =>
    point.score !== null && point.threshold !== null && point.threshold > 0 && point.exceeds === true);
  const at = (position: number) => over.find((point) => point.pointer.position === position) ?? null;
  const inRun = (position: number) => trend.intervals.some((run) => run.start <= position && position <= run.end);
  const ongoing = trend.intervals.find((run) => run.open) ?? null;
  const last = trend.points.filter((point) => point.score !== null).at(-1);
  const state = ongoing ? "ongoing" : last && last.exceeds === true ? "latest" : over.length ? "below" : "none";
  const anchor = state === "ongoing" ? at(ongoing!.start) : state === "latest" ? at(last!.pointer.position)
    : over.at(-1) ?? null;
  const before = anchor?.pointer.position ?? Infinity;
  return {state, anchor, ongoing, lastExceeds: last?.exceeds ?? null,
    earlierRuns: trend.intervals.filter((run) => !run.open && run.end < before).length,
    earlierSingles: over.filter((point) => point.pointer.position < before && !inRun(point.pointer.position)).length,
    first: over[0] ?? null};
}
/** The headline and the line under it for a story, in the words of the screen. */
export function exceedanceText(story: ExceedanceStory, place: (position: number) => string):
  {headline: string; earlier: string | null} | null {
  if (story.state === "none" || !story.anchor) return null;
  const at = place(story.anchor.pointer.position);
  const headline = story.state === "ongoing"
    ? story.lastExceeds === false ? at + "부터 기준 초과 구간 · " + story.ongoing!.steps + "회 · 최근 측정은 기준 이하"
      : at + "부터 계속 기준 초과 · " + story.ongoing!.steps + "회"
    : story.state === "latest" ? at + "에서 기준 초과 · 연속 초과는 아님"
    : "지금은 기준 이하 · 마지막 기준 초과 " + at;
  const parts: string[] = [];
  if (story.earlierRuns) parts.push("끝난 기준 초과 구간 " + story.earlierRuns + "개");
  if (story.earlierSingles) parts.push("한 번만 넘은 측정 " + story.earlierSingles + "번");
  if (story.first && story.first.pointer.position < story.anchor.pointer.position)
    parts.push("처음 기준을 넘은 때 " + place(story.first.pointer.position));
  return {headline, earlier: parts.length ? "그 전 · " + parts.join(" · ") : null};
}

export function measurementTime(point: TrendPoint, period: number | null): string | null {
  if (point.eventStart && /(?:Z|[+-]\d{2}:\d{2})$/i.test(point.eventStart)
    && Number.isFinite(Date.parse(point.eventStart)))
    return new Date(point.eventStart).toLocaleString("ko-KR", {timeZone: "Asia/Seoul", hourCycle: "h23",
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"}) + " (KST)";
  return period !== null && Number.isFinite(period) && period > 0
    ? sinceStart(point.pointer.position, period) : null;
}
export type Envelope={channel:string;bands:[number,number][]};
export type Waveform=
  |{available:false;reason:string}
  |{available:true;fileName:string;rateHz:number;samples:number;perBin:number;channels:Envelope[];
    /** Values that are not finite numbers, when the server counted them. */
    nonFinite:number|null};
export type WindowChannel={channel:string;unit:string|null;property?:string|null;scope?:string|null;points:{at:string;value:number|null}[]};
export type WindowInput=
  |{available:false;reason:string}
  |{available:true;start:string;end:string;channels:WindowChannel[];
    quality:{good:number;unusable:number;conflict:number}};

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
  const checks=object(root.checks);
  const nonFinite=checks?.sha256_matches===true&&typeof checks.non_finite_values==="number"
    &&Number.isSafeInteger(checks.non_finite_values)?checks.non_finite_values:null;
  return {available:true,fileName:root.file_name,rateHz:finite(root.sampling_rate_hz)??0,
    samples:whole(root.sample_count,"표본 수"),perBin:whole(root.samples_per_bin,"묶음 크기"),channels,nonFinite};
}

export function parseWindow(raw:unknown,position:number):WindowInput{
  const root=object(raw);
  if(!root)invalid("관측 구간");
  if(root.available===false)return {available:false,reason:typeof root.reason==="string"?root.reason:"관측을 읽을 수 없습니다"};
  if(root.available!==true||root.position!==position||!Array.isArray(root.channels)
    ||typeof root.start!=="string"||typeof root.end!=="string")invalid("관측 구간");
  const quality={good:0,unusable:0,conflict:0};
  return {available:true,start:root.start,end:root.end,quality,channels:root.channels.map((item:unknown):WindowChannel=>{
    const row=object(item);
    if(!row||typeof row.channel_id!=="string"||!Array.isArray(row.points))invalid("관측 구간");
    return {channel:row.channel_id,unit:typeof row.unit==="string"?row.unit:null,
      property:typeof row.observed_property==="string"?row.observed_property:null,scope:typeof row.scope==="string"?row.scope:null,
      points:row.points.map((point:unknown)=>{
        const value=object(point);
        if(!value||typeof value.at!=="string")invalid("관측 구간");
        quality[value.quality==="good"?"good":value.quality==="conflict"?"conflict":"unusable"]++;
        return {at:value.at,value:value.quality==="good"?finite(value.value):null};
      })};
  })};
}

/** One line on what was checked about the raw input before it is drawn. */
export function inputCheck(input:Waveform|WindowInput):string|null{
  if(!input.available)return null;
  if("fileName" in input){
    if(input.nonFinite===null)return null;
    return "원본 확인 · 전달 당시 확인값(SHA-256)과 일치 · 표본 "+input.samples.toLocaleString("ko-KR")+"개 × "
      +input.channels.length+"채널 · "+(input.nonFinite?"숫자가 아닌 값 "+input.nonFinite.toLocaleString("ko-KR")+"개":"결측 없음");
  }
  const {good,unusable,conflict}=input.quality;
  return "원본 확인 · 측정값 "+(good+unusable+conflict).toLocaleString("ko-KR")+"개 · "
    +(unusable||conflict?[unusable?"쓸 수 없는 값 "+unusable+"개":"",conflict?"값 충돌 "+conflict+"개":""].filter(Boolean).join(" · "):"결측·충돌 없음");
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

export type RatioLine={points:{position:number;ratio:number;score:number}[];exceeded:number;analyzed:number;
  latest:{position:number;ratio:number}|null;sustainedFrom:number|null;firstExceedance:ThresholdExceedance|null;
  story:ExceedanceStory};
/** Each score divided by the threshold stored with it, so models with different score scales share
 * one axis where 1 is "this model's own threshold". A step without a positive threshold is left out. */
export function thresholdRatios(trend:ScoreTrend):RatioLine{
  const points=trend.points.flatMap(point=>point.score!==null&&point.threshold!==null&&point.threshold>0
    ?[{position:point.pointer.position,ratio:point.score/point.threshold,score:point.score}]:[]);
  const {analyzed,exceeded}=trendSummary(trend);
  const open=trend.intervals.find(item=>item.open);
  const last=points.at(-1);
  return {points,analyzed,exceeded,latest:last?{position:last.position,ratio:last.ratio}:null,sustainedFrom:open?.start??null,
    firstExceedance:firstExceedance(trend.points.filter(point=>point.threshold!==null&&point.threshold>0)),
    story:exceedanceStory(trend)};
}

/** The models drawn on one graph: the first `limit` in list order, with the chosen model always
 * among them, in the last slot when it is further down the list. */
export function overlayModels<T extends {bindingId:string}>(bindings:T[],selected:string,limit:number):T[]{
  const first=bindings.slice(0,limit);
  const chosen=bindings.find(item=>item.bindingId===selected);
  return !chosen||first.some(item=>item.bindingId===selected)?first:[...first.slice(0,limit-1),chosen];
}

/** The last analyzed measurement before the over-threshold interval that holds `position`,
 * its first measurement included: the natural "before" to compare a flagged measurement against. */
export function beforeInterval(intervals:Interval[],analyzed:number[],position:number):number|null{
  const holding=intervals.find(item=>item.start<=position&&position<=item.end);
  if(!holding)return null;
  return analyzed.filter(at=>at<holding.start).reduce<number|null>((best,at)=>best===null||at>best?at:best,null);
}
