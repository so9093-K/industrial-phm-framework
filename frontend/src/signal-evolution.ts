import {object} from "./writes.ts";
export type SignalEvolution = {
  recentPoints:number;recentFrom:number|string;recentTo:number|string;recentMedian:number;baselineMedian:number|null;
  changeRatio:number|null;rate:number;earlierRate:number|null;rateUnit:"acquisition"|"hour"|"day";
};
const finite=(v:unknown):v is number=>typeof v==="number"&&Number.isFinite(v);
/** Optional measured change statistics. Old saved results can still show their forecast. */
export function parseSignalEvolution(raw:unknown):SignalEvolution|null {
  const root=object(raw),data=object(root?.degradation),recent=object(data?.recent);
  if(!root||!data||!recent||!finite(recent.points)||!Number.isSafeInteger(recent.points)||recent.points<1
    ||!finite(recent.median)||!finite(data.rate)||!(data.earlier_rate===null||finite(data.earlier_rate))
    ||!(data.change_ratio===null||finite(data.change_ratio))
    ||!["acquisition","hour","day"].includes(String(root.rate_unit)))return null;
  const coordinate=(v:unknown):v is number|string=>root.axis==="acquisition"
    ?finite(v)&&Number.isSafeInteger(v)&&v>=1:typeof v==="string"&&Number.isFinite(Date.parse(v));
  if(!coordinate(recent.from)||!coordinate(recent.to))return null;
  const baseline=object(data.baseline);
  return {recentPoints:recent.points,recentFrom:recent.from,recentTo:recent.to,recentMedian:recent.median,baselineMedian:finite(baseline?.median)?baseline.median:null,
    changeRatio:data.change_ratio as number|null,rate:data.rate,earlierRate:data.earlier_rate as number|null,
    rateUnit:root.rate_unit as SignalEvolution["rateUnit"]};
}
