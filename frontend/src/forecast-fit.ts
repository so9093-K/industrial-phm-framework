import {object} from "./writes.ts";
export type ForecastFit={observed:number;modeled:number;gap:number;points:number|null;bucketSeconds:number|null;intervalWidth:number|null;recentLow:number|null;recentHigh:number|null};
/** Values come from one forecast response; no offset is applied to the forecast or its interval. */
export function parseForecastFit(raw:unknown):ForecastFit|null {
  const root=object(raw),model=object(root?.model);
  if(!root||!Array.isArray(root.history)||!Array.isArray(root.forecast)||!root.history.length||!root.forecast.length)return null;
  const observed=root.history.filter((row:unknown)=>Array.isArray(row)&&typeof row[1]==="number"&&Number.isFinite(row[1])).at(-1)?.[1],modeled=root.forecast[0]?.[1];
  if(observed===undefined)return null;
  if(typeof observed!=="number"||!Number.isFinite(observed)||typeof modeled!=="number"||!Number.isFinite(modeled))throw new Error("예측 시작값과 마지막 구간 평균을 확인할 수 없습니다.");
  const history=root.history.filter((row:unknown)=>Array.isArray(row)&&typeof row[1]==="number"&&Number.isFinite(row[1]));
  const coordinate=(value:unknown)=>typeof value==="string"?Date.parse(value):typeof value==="number"?value:NaN;
  const from=coordinate(root.forecast[0]?.[0]),to=coordinate(root.forecast.at(-1)?.[0]);
  const window=history.filter((row:unknown[])=>coordinate(row[0])>=from-2*(to-from)&&coordinate(row[0])<=from).map((row:unknown[])=>row[1] as number);
  return {recentLow:window.length?Math.min(...window):null,recentHigh:window.length?Math.max(...window):null,observed,modeled,gap:modeled-observed,points:typeof model?.points==="number"?model.points:null,
    bucketSeconds:typeof root.bucket_seconds==="number"?root.bucket_seconds:null,
    intervalWidth:typeof model?.interval_width==="number"?model.interval_width:null};
}

/** Compare errors with a numerical tolerance; a round-off residual does not defeat a zero-error baseline. */
export function worseThanPersistence(check:{error:number;naive:number}|undefined):boolean {
  return !!check && check.error-check.naive > 1e-9*Math.max(1,check.error,check.naive);
}

/** This is a visible-range comparison, not a claim about future prediction error. */
export function outsideRecentRange(fit:ForecastFit):boolean {
  const tolerance=1e-9*Math.max(1,Math.abs(fit.observed),Math.abs(fit.modeled));
  return fit.recentLow!==null&&fit.recentHigh!==null&&(fit.modeled<fit.recentLow-tolerance||fit.modeled>fit.recentHigh+tolerance);
}
