import {recordContext,type RecordContext} from "./record-context.ts";
import {focusGroups,focusParams,type SourceFocus} from "./signal-selection.ts";
import {settingsQuery,verifySettings,backtests,type Backtest,type ForecastSettings} from "./forecast-settings.ts";
import {parseForecastFit,type ForecastFit} from "./forecast-fit.ts";
import {yTicks, type Tick} from "./chart-axis.ts";
/** Read-only version-coupled history forecast and conditional outlook. */
export type Horizon = "1h" | "24h" | "7d" | "30d";
export type Direction = "upper" | "lower";
export type Conditions = {
  direction: Direction; management: number | null; end: number | null;
};
export type Options = { assetId: string; channels: string[]; horizons: Record<Horizon, string | null>; recordKey?:string; records?:RecordContext[] };
export type Reach = {state: string; expected: number | null; earliest: number | null; latest: number | null};
export type Scenario = {id: string; management: Reach | null; end: Reach | null};
export type OutlookSettings = {
  changepointPriorScale:number;changepointRange:number;
  trainingPoints:number|null;seasonality:"auto"|"off";
};
export type Projection = {
  assetId: string; channel: string; horizon: Horizon; measurementVersion: string; recordKey?:string; sourcePointRecords?:number;
  dataVersion: string; sourceId: string; pointId: string | null; unit: string | null;
  record: {first: string; last: string; points: number};
  future: Array<{at:string; estimate: number; lower: number | null; upper: number | null}>;
  /** The stored values the forecast was fitted on, for drawing; never edited or filled. */
  history?: Array<{at:string; value:number}>;
  fitted?: Array<{at:string; value:number}>; fit?:ForecastFit|null;
  checks?: Backtest[];
  /** The outlook's own check over its reach search, which is what the reach sentence rests on;
   * `checks` belong to the drawn forecast's shorter horizon. */
  reachChecks?: Backtest[]; scenarios: Scenario[]; conditions: Conditions; outlookSettings?: OutlookSettings | null;
};
export class ProjectionUnavailable extends Error {}
export class MeasurementVersionMismatch extends Error {}

function object(raw: unknown): Record<string, unknown> | null {
  return typeof raw === "object" && raw !== null && !Array.isArray(raw)
    ? raw as Record<string, unknown> : null;
}
function str(raw: unknown): string {
  if (typeof raw !== "string" || !raw) throw new Error("전망 결과의 식별 정보가 올바르지 않습니다.");
  return raw;
}
function numberOrNull(raw: unknown): number | null {
  if (raw === null) return null;
  if (typeof raw !== "number" || !Number.isFinite(raw))
    throw new Error("전망 결과의 수치가 올바르지 않습니다.");
  return raw;
}
function date(raw: unknown): string {
  const value = str(raw);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) || !Number.isFinite(Date.parse(value)))
    throw new Error("전망 결과의 시각이 올바르지 않습니다.");
  return value;
}
function count(raw: unknown): number {
  if (typeof raw !== "number" || !Number.isSafeInteger(raw) || raw < 0)
    throw new Error("전망에 쓴 측정 개수가 올바르지 않습니다.");
  return raw;
}
export function parseOptions(payload: unknown, assetId: string, channel?:string): Options {
  const data = object(payload), history = object(data?.history);
  if (data?.schema_version !== 1 || data.asset_id !== assetId)
    throw new Error("다른 설비의 전망 선택지가 돌아왔습니다.");
  if (data.history === null)
    return {assetId, channels: [], horizons: {"1h":"no-history","24h":"no-history",
      "7d":"no-history","30d":"no-history"}};
  if (!history || !Array.isArray(history.series) || !object(history.horizons))
    throw new Error("전망 선택지의 형식이 올바르지 않습니다.");
  const selection=object(data.selection);
  if(channel && (selection?.kind!=="history"||selection.series!==channel||!object(selection.horizons)))
    throw new Error("선택한 신호의 예측 가능 기간을 확인할 수 없습니다.");
  const support=channel?object(selection?.horizons):object(history.horizons);
  const horizons = {} as Record<Horizon, string | null>;
  for (const key of ["1h","24h","7d","30d"] as const) {
    const value = support?.[key];
    if (value !== null && typeof value !== "string")
      throw new Error("예측 기간을 쓸 수 있는지 확인할 수 없습니다.");
    horizons[key] = value as string | null;
  }
  const channels = history.series.map((item: unknown) => str(object(item)?.key));
  return {assetId, channels:[...new Set(channels)], horizons,
    recordKey:typeof selection?.record_key==="string"?selection.record_key:undefined,
    records:Array.isArray(selection?.records)?selection.records.map(recordContext).filter((r):r is RecordContext=>r!==null):[]};
}

/** Preserve the server's actual calculation settings, which data_version does not hash. */
export function parseOutlookSettings(raw:unknown):OutlookSettings|null{
  if(raw===undefined||raw===null)return null;
  const v=object(raw);
  if(!v||typeof v.changepoint_prior_scale!=="number"||
    !Number.isFinite(v.changepoint_prior_scale)||v.changepoint_prior_scale<=0
    ||typeof v.changepoint_range!=="number"||!Number.isFinite(v.changepoint_range)
    ||v.changepoint_range<=0||v.changepoint_range>=1
    ||!(v.training_points===null||(typeof v.training_points==="number"
      &&Number.isSafeInteger(v.training_points)&&v.training_points>=20))
    ||(v.seasonality!=="auto"&&v.seasonality!=="off"))
    throw new Error("전망 계산 설정을 확인할 수 없습니다.");
  return {
    changepointPriorScale:v.changepoint_prior_scale,
    changepointRange:v.changepoint_range,
    trainingPoints:v.training_points as number|null,
    seasonality:v.seasonality as "auto"|"off",
  };
}

function parseReach(raw: unknown): Reach | null {
  if (raw === null || raw === undefined) return null;
  const obj = object(raw);
  if (!obj) throw new Error("기준 도달 결과의 형식이 올바르지 않습니다.");
  return {state:str(obj.state), expected:numberOrNull(obj.expected),
    earliest:numberOrNull(obj.earliest), latest:numberOrNull(obj.latest)};
}
export function parsePairedProjection(
  forecastValue: unknown, outlookValue: unknown,
  assetId: string, channel: string, horizon: Horizon, conditions: Conditions,
): Projection {
  const forecast = object(forecastValue), outlook = object(outlookValue);
  if (!forecast || !outlook || forecast.schema_version !== 1 || outlook.schema_version !== 1
    || forecast.asset_id !== assetId || outlook.asset_id !== assetId
    || forecast.series !== channel || outlook.series !== channel
    || forecast.kind !== "history" || outlook.kind !== "history"
    || forecast.axis !== "time" || outlook.axis !== "time"
    || forecast.horizon !== horizon
    || forecast.meaning !== "stored-flow-continued-not-failure-time-or-remaining-life"
    || outlook.meaning !== "remaining-margin-to-user-conditions-not-a-diagnosis") {
    throw new Error("받은 결과가 고른 설비·신호와 맞지 않아 표시하지 않았습니다.");
  }
  const fVersion = str(forecast.measurement_version);
  const oVersion = str(outlook.measurement_version);
  const fs = str(forecast.source_id), os = str(outlook.source_id);
  const fp = forecast.measurement_point_id ?? null;
  const op = outlook.measurement_point_id ?? null;
  if (fVersion !== oVersion || fs !== os || fp !== op || forecast.record_key!==outlook.record_key) {
    throw new MeasurementVersionMismatch(
      "예측과 기준 도달 계산에 쓴 데이터가 서로 달라 결과를 합치지 않았습니다. 다시 계산하세요."
    );
  }
  const configured = object(outlook.conditions), record = object(outlook.record);
  if (!configured || !record || configured.direction !== conditions.direction
    || numberOrNull(configured.management) !== conditions.management
    || numberOrNull(configured.end) !== conditions.end)
    throw new Error("입력한 조건과 계산된 조건이 달라 결과를 표시하지 않았습니다.");
  if (!Array.isArray(forecast.forecast) || !Array.isArray(outlook.scenarios))
    throw new Error("예측 결과가 완전하지 않습니다.");
  const future = forecast.forecast.map((row: unknown) => {
    if (!Array.isArray(row) || row.length < 2)
      throw new Error("예측값의 형식이 올바르지 않습니다.");
    const estimate = numberOrNull(row[1]);
    if (estimate === null) throw new Error("예측값이 빠져 있습니다.");
    return {at:date(row[0]), estimate,
      lower:numberOrNull(row[2] ?? null), upper:numberOrNull(row[3] ?? null)};
  });
  const history = (Array.isArray(forecast.history) ? forecast.history : []).flatMap((row: unknown) =>
    Array.isArray(row) && typeof row[1] === "number" && Number.isFinite(row[1])
      ? [{at:date(row[0]), value:row[1]}] : []);
  const fitted = (Array.isArray(forecast.fitted) ? forecast.fitted : []).map((row:unknown) => {
    if(!Array.isArray(row)||row.length!==2)throw new Error("모델 학습값의 형식이 올바르지 않습니다.");
    const value=numberOrNull(row[1]);if(value===null)throw new Error("모델 학습값이 빠져 있습니다.");
    return {at:date(row[0]),value};
  });
  const scenarios = outlook.scenarios.map((raw: unknown) => {
    const item = object(raw), limits = object(item?.limits);
    if (!item || !limits) throw new Error("계산 방식별 결과의 형식이 올바르지 않습니다.");
    return {id:str(item.id), management:parseReach(limits.management),
      end:parseReach(limits.end)};
  });
  return {assetId, channel, horizon, measurementVersion:fVersion, recordKey:typeof forecast.record_key==="string"?forecast.record_key:undefined,sourcePointRecords:typeof forecast.source_point_records==="number"?forecast.source_point_records:undefined,
    dataVersion:str(outlook.data_version), sourceId:fs,
    pointId:fp === null ? null : str(fp), unit:typeof forecast.unit === "string" ? forecast.unit : null,
    record: {first:date(record.first),last:date(record.last),points:count(record.points)},
    future, history, fitted, fit:parseForecastFit(forecast), scenarios, conditions, outlookSettings:parseOutlookSettings(outlook.settings)};
}

export const HORIZON_LABEL: Record<Horizon, string> = {"1h":"1시간","24h":"24시간","7d":"7일","30d":"30일"};
const HORIZON_SECONDS: Record<Horizon, number> = {"1h":3600,"24h":86400,"7d":7*86400,"30d":30*86400};
/** The horizon a forecast opens with: the longest the record supports that reaches no further than
 * a quarter of the record, so a record of months is not forecast one hour ahead; else the
 * shortest it supports. */
export function suggestedHorizon(support: Record<Horizon, string | null>, recordSeconds: number | null): Horizon | null {
  const allowed = (Object.keys(HORIZON_SECONDS) as Horizon[]).filter(key => support[key] === null);
  const fitting = recordSeconds === null ? [] : allowed.filter(key => HORIZON_SECONDS[key] <= recordSeconds / 4);
  return fitting.at(-1) ?? allowed[0] ?? null;
}

export type OutlookChart = {
  width: number; height: number; low: number; high: number;
  start: string; lastRecord: string; end: string; lastX: number;
  history: string; fitted:string; gap:{x:number;observed:number;modeled:number}|null; estimate: string; band: string;
  management: number | null; endLimit: number | null;
  ticks: Tick[];
};

/** Recent stored values, the forecast with its range and the user's limits on one plot.
 * The window shows twice the forecast span of history so the forecast stays readable. */
export function outlookChart(projection: Projection, includeLimits = false): OutlookChart | null {
  const future = projection.future;
  if (!future.length) return null;
  const width = 800, height = 220, top = 8, bottom = 212;
  const futureStart = Date.parse(future[0].at), futureEnd = Date.parse(future[future.length - 1].at);
  const span = Math.max(futureEnd - futureStart, 1);
  const shown = (projection.history ?? []).filter((item) => Date.parse(item.at) >= futureStart - 2 * span);
  const fitted=(projection.fitted??[]).filter(item=>Date.parse(item.at)>=futureStart-2*span);
  const start = Math.min(shown.length ? Date.parse(shown[0].at) : futureStart, futureStart);
  const end = Math.max(futureEnd, start + 1);
  const {management, end: endLimit} = projection.conditions;
  const values = [
    ...shown.map((item) => item.value), ...fitted.map(item=>item.value),
    ...future.flatMap((item) => [item.estimate, item.lower ?? item.estimate, item.upper ?? item.estimate]),
    ...(includeLimits ? [management, endLimit].filter((limit): limit is number => limit !== null) : []),
  ];
  const low = Math.min(...values), high = Math.max(...values);
  const padding = low === high ? Math.max(Math.abs(low) * 0.05, 1) : (high - low) * 0.06;
  const lo = low - padding, hi = high + padding;
  const x = (at: string) => ((Date.parse(at) - start) / (end - start)) * width;
  const y = (value: number) => bottom - ((value - lo) / (hi - lo)) * (bottom - top);
  const line = (points: Array<[string, number]>) =>
    points.map(([at, value], i) => (i ? "L" : "M") + x(at).toFixed(1) + " " + y(value).toFixed(1)).join(" ");
  const ranged = future.filter((item) => item.lower !== null && item.upper !== null);
  const band = ranged.length
    ? line(ranged.map((item) => [item.at, item.upper as number]))
      + " " + ranged.slice().reverse().map((item) => "L" + x(item.at).toFixed(1) + " " + y(item.lower as number).toFixed(1)).join(" ") + " Z"
    : "";
  return {
    width, height, low, high,
    start: new Date(start).toISOString(), lastRecord: projection.record.last, end: future[future.length - 1].at,
    lastX: x(projection.record.last),
    history: line(shown.map((item) => [item.at, item.value])),
    fitted:line(fitted.map(item=>[item.at,item.value])),
    gap:shown.length?{x:x(future[0].at),observed:y(shown.at(-1)!.value),modeled:y(future[0].estimate)}:null,
    estimate: line(future.map((item) => [item.at, item.estimate])),
    band,
    management: management === null || management < lo || management > hi ? null : y(management),
    endLimit: endLimit === null || endLimit < lo || endLimit > hi ? null : y(endLimit),
    ticks: yTicks(lo, hi, top, bottom),
  };
}

/** A few forecast rows spread over the whole horizon, always including its last one. */
export function spreadRows<T>(rows: T[], count = 8): T[] {
  if (rows.length <= count) return rows;
  return Array.from({length: count}, (_, i) => rows[Math.round((i * (rows.length - 1)) / (count - 1))]);
}
async function json(url: string, signal: AbortSignal): Promise<unknown> {
  const response=await fetch(url,{signal,cache:"no-store",credentials:"same-origin"});
  if ([404,422].includes(response.status)){
    const result: unknown = await response.json().catch(()=>null);
    const name=object(result)?.error;
    if (name==="nothing_to_forecast" || name==="nothing_to_outlook"
      || name==="forecast_unavailable" || name==="outlook_unavailable"){
      const reason=object(result)?.reason;
      throw new ProjectionUnavailable(
        "고른 신호나 기간으로는 전망할 수 없습니다."
        + (typeof reason==="string" ? " ("+reason+")" : "")
      );
    }
  }
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("전망을 불러오지 못했습니다. 기록이 없거나 이상이 없다는 뜻은 아닙니다.");
  }
  return await response.json() as unknown;
}
export async function loadOptions(assetId: string, signal: AbortSignal,selection?:{channel:string;trainingPoints:number|null;recordKey?:string;focus?:SourceFocus|null}): Promise<Options> {
  const query={asset_id:assetId,...(selection?{kind:"history",series:selection.channel,...(selection.recordKey?{record_key:selection.recordKey}:{}),...(selection.focus?focusParams(selection.focus):{}),
    ...(selection.trainingPoints===null?{}:{training_points:String(selection.trainingPoints)})}:{})};
  const result=parseOptions(await json(
    "/api/v1/forecast/options?" + new URLSearchParams(query),signal),assetId,selection?.channel);
  if(selection?.recordKey&&result.recordKey!==selection.recordKey)
    throw new MeasurementVersionMismatch("선택한 기록과 예측 가능 기간의 대상이 다릅니다.");
  if(selection?.focus){
    const record=result.records?.find(row=>row.key===result.recordKey);
    if(!record||!focusGroups([record],selection.focus).length)
      throw new MeasurementVersionMismatch("선택한 출처·측정 위치·측정 의미와 다른 기록입니다.");
  }
  return result;
}
export async function loadPaired(
  assetId: string, channel: string, horizon: Horizon,
  conditions: Conditions, signal: AbortSignal, settings?:ForecastSettings, recordKey?:string,
): Promise<Projection> {
  const args={asset_id:assetId,kind:"history",series:channel,...settingsQuery(settings),...(recordKey?{record_key:recordKey}:{})};
  const direction={direction:conditions.direction};
  const limits: Record<string,string> = {};
  if (conditions.management !== null) limits.management_limit=String(conditions.management);
  if (conditions.end !== null) limits.end_limit=String(conditions.end);
  const [forecast,outlook] = await Promise.all([
    json("/api/v1/forecast?" + new URLSearchParams({...args,horizon,...(settings?{backtest:settings.backtest}:{})}),signal),
    json("/api/v1/outlook?" + new URLSearchParams({...args,...direction,...limits}),signal),
  ]);
  verifySettings(forecast,outlook,settings);
  if(recordKey&&(object(forecast)?.record_key!==recordKey||object(outlook)?.record_key!==recordKey))throw new MeasurementVersionMismatch("선택한 출처의 기록과 계산 결과가 다릅니다.");
  return {...parsePairedProjection(forecast,outlook,assetId,channel,horizon,conditions),checks:backtests(forecast),
    reachChecks:backtests({backtest:object(outlook)?.check})};
}
