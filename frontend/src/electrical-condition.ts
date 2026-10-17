/** Load, voltage/current unbalance and the reference-pattern score of a 3-phase asset, for a
 * recent period against an earlier one, as the server measured them. Changed operating
 * conditions are not a fault, and the reference period is not assumed to be normal. */
import {object} from "./writes.ts";

export type ConditionPeriod="1h"|"6h"|"24h";
export type ConditionSource={sourceId:string;pointId:string|null};
export type PeriodSummary={
  currentMean:number|null;currentAboveFloorHours:number|null;currentAboveFloorFraction:number|null;currentFloor:number|null;
  currentPeak:number|null;currentPeakAt:string|null;voltageUnbalanceMax:number|null;voltageUnbalanceMaxAt:string|null;
  currentUnbalanceP95:number|null;samples:number|null;currentObservedHours:number|null;lowCurrentSamples:number|null;
};
export type TimelinePoint={
  at:string;currentMean:number|null;voltageUnbalance:number|null;currentUnbalance:number|null;patternScore:number|null;
  voltage:number[]|null;current:number[]|null;
};
export type NotablePoint={at:string;score:number|null;channel:string;value:number|null;low:number|null;high:number|null;unit:string};
export type Pattern=
  |{scored:false}
  |{scored:true;threshold:number|null;above:number;scoredSamples:number;percent:number|null;notable:NotablePoint[];
    model:string|null;fitSamples:number|null};
/** Identifiers and data-quality facts shown only under 기술 상세. */
export type ConditionDetails={timeEvidence:string[];snapshotId:string|null;fileQuality:boolean;
  excluded:{reference:Record<string,number>;target:Record<string,number>}};
export type Condition=
  |{analyzed:false;state:string;sources:ConditionSource[]}
  |{analyzed:true;sources:ConditionSource[];sourceId:string;pointId:string|null;targetStart:string;targetEnd:string;
    referenceStart:string;referenceEnd:string;lastObservedAt:string|null;reference:PeriodSummary;target:PeriodSummary;
    pattern:Pattern;timeline:TimelinePoint[];details:ConditionDetails};

export const STATE_TEXT:Record<string,string>={
  "no-history":"저장된 측정값이 없습니다. 데이터를 연결하고 측정 이력을 저장하세요.",
  "select-source":"데이터 출처가 여러 개입니다. 분석할 출처와 측정 위치를 고르세요.",
  "unsupported-signals":"전압·전류의 R/S/T 역할과 단위가 확인되지 않아 분석할 수 없습니다. 데이터 연결에서 3상 역할을 지정해 등록하세요.",
  "ambiguous-phase-roles":"한 측정 위치에 같은 상 역할의 신호가 여러 개 있습니다. 역할 지정을 확인하세요.",
  "changed-measurement-meaning":"기준 기간과 분석 기간 사이에 측정 의미가 바뀌었습니다. 같은 의미의 기간을 고르세요.",
  "no-usable-target":"빠진 값·충돌·품질 문제로 분석할 수 있는 관측이 없습니다. 원본 신호와 수집 상태를 확인하세요.",
  "no-target-observations":"고른 기간에 관측이 없습니다. 분석 끝 시각을 확인하세요.",
  "too-many-sources":"데이터 출처가 너무 많습니다. 분석할 출처를 좁혀 주세요.",
  "unknown-event-time":"관측 시각을 확인할 수 없습니다.",
  unavailable:"분석할 데이터를 읽지 못했습니다.",
};

function invalid():never{throw new Error("부하·불평형 분석 결과의 형식이 올바르지 않습니다.");}
function finite(raw:unknown):number|null{return typeof raw==="number"&&Number.isFinite(raw)?raw:null;}
function text(raw:unknown):string|null{return typeof raw==="string"&&raw?raw:null;}
function phases(raw:unknown):number[]|null{
  return Array.isArray(raw)&&raw.length===3&&raw.every(v=>finite(v)!==null)?raw as number[]:null;
}
function summary(raw:unknown):PeriodSummary{
  const row=object(raw)??{};
  return {currentMean:finite(row.current_mean_a),currentAboveFloorHours:finite(row.current_above_floor_hours),
    currentAboveFloorFraction:finite(row.current_above_floor_fraction),currentFloor:finite(row.current_floor_a),
    currentPeak:finite(row.current_peak_a),currentPeakAt:text(row.current_peak_at),
    voltageUnbalanceMax:finite(row.voltage_unbalance_max_percent),voltageUnbalanceMaxAt:text(row.voltage_unbalance_max_at),
    currentUnbalanceP95:finite(row.current_unbalance_p95_percent),samples:finite(row.sample_count),
    currentObservedHours:finite(row.current_observed_hours),lowCurrentSamples:finite(row.current_low_signal_count)};
}
function counts(raw:unknown):Record<string,number>{
  return Object.fromEntries(Object.entries(object(raw)??{}).flatMap(([key,value])=>finite(value)===null?[]:[[key,value as number]]));
}

/** A KST wall-clock input (YYYY-MM-DDTHH:MM[:SS]) as the same instant with its offset. */
export function kstInstant(value:string):string{
  const match=/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value);
  if(!match)throw new Error("시각 형식을 확인하세요.");
  const iso=match[1]+"T"+match[2]+":"+match[3]+":"+(match[4]??"00")+"+09:00";
  if(!Number.isFinite(Date.parse(iso)))throw new Error("시각 형식을 확인하세요.");
  return iso;
}

export function parseCondition(raw:unknown,assetId:string,expected:ConditionSource|null):Condition{
  const root=object(raw);
  if(!root||root.schema_version!==1||root.asset_id!==assetId
    ||root.meaning!=="measured-operating-change-and-reference-pattern-not-fault-diagnosis")invalid();
  const sources=(Array.isArray(root.sources)?root.sources:[]).flatMap((item:unknown):ConditionSource[]=>{
    const row=object(item);const sourceId=text(row?.source_id);
    return sourceId?[{sourceId,pointId:text(row?.point_id)}]:[];
  });
  if(root.state!=="analyzed")return {analyzed:false,state:String(root.state),sources};
  const sourceId=text(root.source_id);
  if(!sourceId)invalid();
  // The answer must be about the chosen source and point, never another one.
  if(expected&&(expected.sourceId!==sourceId||expected.pointId!==text(root.point_id)))
    throw new Error("고른 데이터 출처와 다른 분석 결과가 돌아왔습니다. 다시 분석하세요.");
  const pattern=object(root.pattern)??{};
  const timeline=(Array.isArray(root.timeline)?root.timeline:[]).map((item:unknown):TimelinePoint=>{
    const row=object(item);const at=text(row?.at);
    if(!row||!at)invalid();
    return {at,currentMean:finite(row.current_mean_a),voltageUnbalance:finite(row.voltage_unbalance_percent),
      currentUnbalance:finite(row.current_unbalance_percent),patternScore:finite(row.pattern_score),
      voltage:phases(row.voltage_phase_v),current:phases(row.current_phase_a)};
  });
  const notable=(Array.isArray(pattern.notable)?pattern.notable:[]).flatMap((item:unknown):NotablePoint[]=>{
    const row=object(item);const at=text(row?.at);
    return row&&at&&row.above_reference===true?[{at,score:finite(row.score),channel:String(row.channel_id??""),
      value:finite(row.value),low:finite(row.reference_p05),high:finite(row.reference_p95),unit:String(row.unit??"")}]:[];
  });
  const range=(key:string)=>{const value=text(root[key]);if(!value)invalid();return value;};
  return {analyzed:true,sources,sourceId,pointId:text(root.point_id),targetStart:range("target_start"),targetEnd:range("target_end"),
    referenceStart:range("reference_start"),referenceEnd:range("reference_end"),lastObservedAt:text(root.last_observed_at),
    reference:summary(root.reference),target:summary(root.target),timeline,
    details:{timeEvidence:Array.isArray(root.time_evidence)?root.time_evidence.filter((item:unknown)=>typeof item==="string"):[],
      snapshotId:root.snapshot_id===null||root.snapshot_id===undefined?null:String(root.snapshot_id),
      fileQuality:root.source_quality==="unknown",
      excluded:{reference:counts(object(root.excluded)?.reference),target:counts(object(root.excluded)?.target)}},
    pattern:pattern.state==="scored"?{scored:true,threshold:finite(pattern.threshold),above:finite(pattern.above_reference_count)??0,
      scoredSamples:finite(pattern.scored_samples)??0,percent:finite(pattern.above_reference_percent),notable,model:text(pattern.model),
      fitSamples:finite(pattern.fit_samples)}
      :{scored:false}};
}

export async function readCondition(
  assetId:string,period:ConditionPeriod,source:ConditionSource|null,
  custom:{end:string;referenceStart:string;referenceEnd:string},signal:AbortSignal,
):Promise<Condition>{
  const query=new URLSearchParams({asset_id:assetId,period});
  if(source){query.set("source_id",source.sourceId);query.set("point_id",source.pointId??"");}
  if(custom.end)query.set("end_at",kstInstant(custom.end));
  if(Boolean(custom.referenceStart)!==Boolean(custom.referenceEnd))throw new Error("기준 기간의 시작과 끝을 모두 입력하세요.");
  if(custom.referenceStart){query.set("reference_start",kstInstant(custom.referenceStart));query.set("reference_end",kstInstant(custom.referenceEnd));}
  const unread="분석할 데이터를 읽지 못했습니다. 이전 결과는 보여 주지 않습니다. 고주파 데이터는 기간을 줄이세요.";
  let response:Response;
  try{response=await fetch("/api/v1/condition?"+query,{signal,cache:"no-store",credentials:"same-origin"});}
  catch(error){if(signal.aborted)throw error;throw new Error(unread);}
  if(!response.ok){
    await response.body?.cancel().catch(()=>{});
    throw new Error(response.status===400?"분석 기간과 그보다 앞선 기준 기간을 확인하세요. 시각은 한국 시각입니다.":unread);
  }
  return parseCondition(await response.json().catch(()=>null) as unknown,assetId,source);
}

export type Metric="currentMean"|"voltageUnbalance"|"currentUnbalance"|"patternScore";
export const METRICS:Record<Metric,{label:string;unit:string}>={
  currentMean:{label:"3상 평균 전류",unit:" A"},voltageUnbalance:{label:"전압 불평형",unit:"%"},
  currentUnbalance:{label:"전류 불평형",unit:"%"},patternScore:{label:"기준 패턴과의 차이",unit:""},
};
export const EXCLUDED_TEXT:Record<string,string>={
  "missing-or-duplicate-phase":"상 값이 빠지거나 겹침","conflict-or-bad-quality":"값 충돌·품질 불량","missing-value":"빠진 값",
};

export function kstTime(iso:string|null):string{
  return iso?new Date(iso).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):"기록 없음";
}
export function measured(value:number|null,unit=""):string{
  return value===null?"분석값 없음":value.toLocaleString("ko-KR",{maximumFractionDigits:2})+unit;
}

/** Runs of consecutive values to draw as one line; a missing value or a time gap longer than
 * 1.5 times the usual interval starts a new run, so nothing is drawn across missing data. */
export function segments(timeline:TimelinePoint[],metric:Metric):TimelinePoint[][]{
  const gaps=timeline.slice(1).map((point,index)=>Date.parse(point.at)-Date.parse(timeline[index].at)).sort((a,b)=>a-b);
  const limit=(gaps[Math.floor(gaps.length/2)]||60_000)*1.5;
  const runs:TimelinePoint[][]=[];let previous:TimelinePoint|null=null;
  for(const point of timeline){
    if(point[metric]===null){previous=null;continue;}
    if(previous&&Date.parse(point.at)-Date.parse(previous.at)<=limit)runs[runs.length-1].push(point);
    else runs.push([point]);
    previous=point;
  }
  return runs;
}

/** What differs from the reference period, in the order an operator checks it. */
export function insights(condition:Extract<Condition,{analyzed:true}>):string[]{
  const {reference,target,pattern}=condition;const lines:string[]=[];
  if(target.currentAboveFloorHours!==null&&reference.currentAboveFloorHours!==null){
    const span=(from:string,until:string)=>Date.parse(until)-Date.parse(from);
    if(span(condition.targetStart,condition.targetEnd)===span(condition.referenceStart,condition.referenceEnd)){
      const difference=target.currentAboveFloorHours-reference.currentAboveFloorHours;
      const floor="전류 "+measured(target.currentFloor," A")+" 이상이 관측된 시간";
      // Below the displayed precision there is no change to report.
      if(Math.abs(difference)<0.005)lines.push(floor+"은 기준 기간과 같습니다.");
      else lines.push(floor+"이 기준 기간보다 "+measured(Math.abs(difference)," h")
        +(difference>0?" 늘었습니다.":" 줄었습니다.")+" 운전 시간이나 부하 일정이 달라졌는지 확인하세요.");
    }else{
      const percent=(value:number|null)=>value===null?null:value*100;
      lines.push("전류가 흐른 관측 비율: 기준 기간 "+measured(percent(reference.currentAboveFloorFraction),"%")+" → 분석 기간 "
        +measured(percent(target.currentAboveFloorFraction),"%")+". 두 기간의 길이가 달라 비율로 비교합니다.");
    }
    lines.push("가장 큰 3상 평균 전류는 "+measured(target.currentPeak," A")+" ("+kstTime(target.currentPeakAt)+")입니다.");
  }
  if(pattern.scored){
    lines.push("기준 패턴의 99% 점수 범위를 넘은 관측 "+pattern.above+"개 / "+pattern.scoredSamples+"개 ("+measured(pattern.percent,"%")+").");
    if(!pattern.above)lines.push("이번 기간에는 기준 점수 범위를 넘은 관측이 없습니다.");
  }else lines.push("기준 기간의 데이터가 부족하거나 거의 일정해 패턴을 비교하지 않았습니다. 기준 기간을 바꿔 보세요.");
  return lines;
}

/** Times to look at first: the observations over the reference pattern, or else the largest values. */
export function firstChecks(condition:Extract<Condition,{analyzed:true}>):{at:string;label:string;detail:string;metric:Metric}[]{
  const notable=condition.pattern.scored?condition.pattern.notable:[];
  if(notable.length)return notable.map(item=>({at:item.at,label:kstTime(item.at),metric:item.unit==="V"?"voltageUnbalance":"currentMean",
    detail:item.channel+" "+measured(item.value," "+item.unit)+" · 기준 5–95% 범위 "+measured(item.low)+"–"+measured(item.high," "+item.unit)}));
  return ([["최대 전류",condition.target.currentPeakAt,"currentMean"],["최대 전압 불평형",condition.target.voltageUnbalanceMaxAt,"voltageUnbalance"]] as const)
    .flatMap(([label,at,metric])=>at?[{at,label:label+" · "+kstTime(at),detail:"",metric}]:[]);
}
