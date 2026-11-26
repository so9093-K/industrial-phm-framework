import {object} from "./writes.ts";
export type SignalEvolution = {
  recentPoints:number;recentFrom:number|string;recentTo:number|string;recentMedian:number;baselineMedian:number|null;
  /** 처음 범위: 처음 구간 중앙값 ± 변동폭×이탈 기준 배수. 이 밖의 값을 처음과 달라진 값으로 본다. */
  baselineRange:{low:number;high:number}|null;
  changeRatio:number|null;rate:number;earlierRate:number|null;rateUnit:"acquisition"|"hour"|"day";
  /** 속도를 잰 측정·구간 수. 진동 측정은 마지막 10회(AI 해설과 같은 '최근'), 그 밖은 최근 구간. */
  ratePoints:number;
  /** The last value itself: the representative value and the rates are robust and can hide it. */
  latest:number|null;
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
  const baseline=object(data.baseline),departure=object(data.departure);
  const range=finite(baseline?.median)&&finite(baseline?.spread)&&finite(departure?.threshold)&&baseline.spread>0
    ?{low:baseline.median-departure.threshold*baseline.spread,high:baseline.median+departure.threshold*baseline.spread}:null;
  return {recentPoints:recent.points,recentFrom:recent.from,recentTo:recent.to,recentMedian:recent.median,baselineMedian:finite(baseline?.median)?baseline.median:null,
    baselineRange:range,
    changeRatio:data.change_ratio as number|null,rate:data.rate,earlierRate:data.earlier_rate as number|null,
    rateUnit:root.rate_unit as SignalEvolution["rateUnit"],latest:finite(data.latest)?data.latest:null,
    ratePoints:finite(data.rate_points)&&Number.isSafeInteger(data.rate_points)&&data.rate_points>0?data.rate_points:recent.points};
}
