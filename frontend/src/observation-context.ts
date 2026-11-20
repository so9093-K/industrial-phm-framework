/** The observation to return to; analysis controls never edit these fields. */
import {pickFrom,type Span} from "./signal-selection.ts";
import type {TrendWindow} from "./history.ts";

export type ObservationOrigin={asset:string;source:string;point:string|null;channel:string;
  window:TrendWindow;selection:Span|null;snapshot:number};

export function observationSnapshot(params:URLSearchParams,asset:string):number|null{
  if(params.get("observation_asset")!==asset||!params.has("observation_snapshot"))return null;
  const raw=params.get("observation_snapshot")!,snapshot=Number(raw);
  if(!/^\d+$/.test(raw)||!Number.isSafeInteger(snapshot))throw Error("선택한 관측을 확인하지 못했습니다. 관측 화면에서 다시 선택하세요.");
  return snapshot;
}
export function observationOrigin(params:URLSearchParams,asset:string):ObservationOrigin|null{
  if(params.get("observation_asset")!==asset||params.get("observation_follow")!=="paused")return null;
  const from=params.get("observation_from"),to=params.get("observation_to"),source=params.get("observation_source"),channel=params.get("observation_channel");
  const snapshot=observationSnapshot(params,asset),a=Date.parse(from??""),b=Date.parse(to??"");
  const selection=pickFrom(params.get("observation_pick"));
  if(!from||!to||!source||!channel||snapshot===null||!Number.isFinite(a)||!Number.isFinite(b)||b-a<1000||b-a>31*86400_000
    ||selection&&(selection.from<a||selection.to>b))throw Error("선택한 관측을 복원하지 못했습니다. 관측 화면에서 다시 선택하세요.");
  return {asset,source,point:params.get("observation_point")||null,channel,window:{from,to},selection,snapshot};
}
export function originParams(asset:string,source:string,point:string|null,channel:string,window:Span,selection:Span):Record<string,string>{
  return {observation_asset:asset,observation_source:source,observation_point:point??"",observation_channel:channel,
    observation_from:new Date(window.from).toISOString(),observation_to:new Date(window.to).toISOString(),
    observation_pick:new Date(selection.from).toISOString()+"~"+new Date(selection.to).toISOString()};
}
export function assertObservationSnapshot(payload:unknown,snapshot:number|null):void{
  if(snapshot!==null&&(!payload||typeof payload!=="object"||!("snapshot_id" in payload)||payload.snapshot_id!==snapshot))
    throw Error("선택한 관측의 분석 결과가 아닙니다. 관측 화면에서 다시 선택하세요.");
}

/** A point or analysis link may edit its own range without losing the observation return path. */
export function withObservation(href:string,currentHref:string,asset:string):string{
  const current=new URL(currentHref),next=new URL(href,current);
  if(next.origin!==current.origin)return next.href;
  if(next.searchParams.get("monitor_asset")!==asset||current.searchParams.get("observation_asset")!==asset)
    return next.pathname+next.search+next.hash;
  for(const [key,value] of current.searchParams)if(key.startsWith("observation_"))next.searchParams.set(key,value);
  return next.pathname+next.search+next.hash;
}
