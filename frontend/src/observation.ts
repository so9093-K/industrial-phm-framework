/** A bounded view of committed measurements, independent of the ingestion protocol. */
import {originParams} from "./observation-context.ts";
import {parseTrend,phaseSiblings, type HistoryTrend, type HistoryStream, type TrendWindow} from "./history.ts";
import {object} from "./writes.ts";
import {assetTabUrl} from "./routes.ts";
import {focusParams,periodParams,periodsBefore,windowParams,type Span} from "./signal-selection.ts";
import type {Asset} from "./monitor.ts";
import type {Source} from "./operations-status.ts";

export type ReferenceResult={interpretationId:string;unit:string|null;state:string;median:number|null;
  intervals:{from:number;to:number;value:number;up:boolean}[]};
export type Observation={trend:HistoryTrend;reference:{period:TrendWindow;groups:ReferenceResult[]}|null};
export const streamKey=(stream:Pick<HistoryStream,"sourceId"|"pointId">)=>JSON.stringify([stream.sourceId,stream.pointId]);
const instant=(value:unknown):string=>{if(typeof value!=="string"||!Number.isFinite(Date.parse(value)))throw Error("관측 기간을 확인하지 못했습니다.");return value;};
const finite=(value:unknown):number=>{if(typeof value!=="number"||!Number.isFinite(value))throw Error("관측 수치를 확인하지 못했습니다.");return value;};
export function readWindow(from:string|null,to:string|null):TrendWindow|null{
  const a=Date.parse(from??""),b=Date.parse(to??"");
  return Number.isFinite(a)&&Number.isFinite(b)&&b-a>=1000&&b-a<=31*86400_000?{from:from!,to:to!}:null;
}
export function parseObservation(raw:unknown,assetId:string,stream:HistoryStream,channel:string):Observation{
  const trend=parseTrend(raw,assetId,channel),root=object(raw);
  if(trend.snapshotId===undefined||trend.buckets.some(b=>b.sourceId!==stream.sourceId||b.pointId!==stream.pointId)
    ||trend.latest.some(p=>p.sourceId!==stream.sourceId||p.pointId!==stream.pointId))throw Error("다른 측정의 관측 결과입니다.");
  const reference=object(root?.reference);
  if(!reference)return {trend,reference:null};
  const period={from:instant(reference.from),to:instant(reference.to)};
  if(!readWindow(period.from,period.to)||!Array.isArray(reference.groups))throw Error("비교 기준을 확인하지 못했습니다.");
  return {trend,reference:{period,groups:reference.groups.map((raw:unknown)=>{
    const row=object(raw);
    if(!row||row.source_id!==stream.sourceId||row.measurement_point_id!==stream.pointId||row.channel_id!==channel
      ||typeof row.interpretation_id!=="string"||typeof row.state!=="string"||!Array.isArray(row.intervals))throw Error("비교 기준의 측정이 일치하지 않습니다.");
    return {interpretationId:row.interpretation_id,unit:typeof row.unit==="string"?row.unit:null,state:row.state,
      median:row.median===null?null:finite(row.median),intervals:row.intervals.map((raw:unknown)=>{
        const interval=object(raw);if(!interval||(interval.direction!=="up"&&interval.direction!=="down"))throw Error("특이사항 구간을 확인하지 못했습니다.");
        const from=Date.parse(instant(interval.from)),to=Date.parse(instant(interval.to));
        if(from>=to||from<Date.parse(period.to)||from<Date.parse(trend.startAt)||to>Date.parse(trend.endAt))throw Error("관측 밖의 특이사항 구간입니다.");
        return {from,to,value:finite(interval.value),up:interval.direction==="up"};
      })};
  })}};
}
export async function readObservation(assetId:string,stream:HistoryStream,channel:string,options:{range:string;
  window:TrendWindow|null;snapshot:number|null;reference:TrendWindow|null;anchor:"now"|"latest"},signal:AbortSignal):Promise<Observation>{
  const duration=options.window?Date.parse(options.window.to)-Date.parse(options.window.from):options.range==="15m"?900_000:options.range==="24h"?86400_000:3600_000;
  const buckets=String(Math.max(1,Math.min(120,Math.ceil(duration/60_000))));
  const query=new URLSearchParams({asset_id:assetId,source_id:stream.sourceId,point_id:stream.pointId??"",channel_id:channel,
    buckets,snapshot:options.snapshot===null?"latest":String(options.snapshot)});
  if(options.window){query.set("from",options.window.from);query.set("to",options.window.to);}
  else{query.set("range",options.range);query.set("anchor",options.anchor);}
  if(options.reference){query.set("reference_from",options.reference.from);query.set("reference_to",options.reference.to);}
  else query.set("auto_reference","1");
  const response=await fetch("/api/v1/history/trend?"+query,{signal,cache:"no-store",credentials:"same-origin"});
  if(!response.ok){await response.body?.cancel().catch(()=>{});throw Error("새로 저장된 측정을 읽지 못했습니다.");}
  const read=parseObservation(await response.json(),assetId,stream,channel);
  if(options.reference&&(!read.reference||Date.parse(read.reference.period.from)!==Date.parse(options.reference.from)||Date.parse(read.reference.period.to)!==Date.parse(options.reference.to)))throw Error("선택한 비교 기준이 아닙니다.");
  if(options.snapshot!==null&&read.trend.snapshotId!==options.snapshot)throw Error("선택한 관측을 읽지 못했습니다.");
  return read;
}
export function receiptStatus(source:Source|undefined,readable:boolean):string{
  if(!readable||source?.readError)return "수집 상태 미확인";
  if(!source)return "저장된 측정";
  if(source.job?.state==="failed")return "새 기록 저장 실패";
  if(source.job?.state==="interrupted")return "새 기록 저장 중단";
  if(source.lifecycle==="paused")return "데이터 연결 일시정지";
  if(source.job?.state==="running")return "측정 기록 저장 중";
  if(!source.live)return "파일에서 저장한 측정";
  if(source.live.desired!=="running")return source.live.desired==="paused"?"수집 일시정지":"수집 실행 미확인";
  if(source.live.session?.toUpperCase()!=="CONNECTED")return "데이터 연결 미확인";
  if(source.live.receivedAt&&(!source.live.historyCommittedAt||Date.parse(source.live.receivedAt)>Date.parse(source.live.historyCommittedAt)))return "새 측정 저장 대기";
  return source.live.fresh?"수신 중":"연결됨 · 최근 새 값 없음";
}

/** A collecting source keeps its gaps against the clock; an old file keeps its recorded dates. */
export function observationAnchor(endAt:string,source:Pick<Source,"live">|undefined,now=Date.now()):"now"|"latest"{
  const end=Date.parse(endAt);
  return source?.live||end<=now&&end>=now-3600_000?"now":"latest";
}
export function observationLink(assetId:string,channel:string,stream:HistoryStream,meaning:string,window:Span,selection:Span,
  reference:TrendWindow|null,method:"signals"|"compare"|"relation",label:string):string{
  const url=new URL(assetTabUrl(assetId,method==="signals"?"signals":"change",method==="signals"?null:method,"history",channel),"http://local");
  const periods=reference?{a:reference,b:{from:new Date(selection.from).toISOString(),to:new Date(selection.to).toISOString()}}:periodsBefore(selection);
  const params={...originParams(assetId,stream.sourceId,stream.pointId,channel,window,selection),...windowParams(window,selection),...focusParams({source:stream.sourceId,point:stream.pointId,interpretation:meaning}),
    ...(periods?periodParams(periods,reference?"observation":"signal"):{}),observation_view:"recent",observation_follow:"paused",
    summary_change:JSON.stringify(["history",streamKey(stream)+":"+channel,new Date(selection.from).toISOString(),new Date(selection.to).toISOString()]),summary_kind:"history",summary_label:label};
  if(method==="relation"){url.searchParams.set("relation_x",channel);const other=phaseSiblings(stream.channels,channel)[0]??stream.channels.find(id=>id!==channel);if(other)url.searchParams.set("relation_y",other);}
  for(const [key,value] of Object.entries(params))url.searchParams.set(key,value);
  return url.pathname+url.search;
}

/** Recent measurements are useful for any ingestion path; collection status is separate. */
export function recentAsset(asset:Asset):boolean{
  return asset.flow!=="stored-history"||!!asset.lastObservedAt&&Date.parse(asset.lastObservedAt)>=Date.now()-3600_000;
}
