/** Read-only version-coupled history forecast and conditional outlook. */
export type Horizon = "1h" | "24h" | "7d" | "30d";
export type Direction = "upper" | "lower";
export type Conditions = {
  direction: Direction; management: number | null; end: number | null;
};
export type Options = { assetId: string; channels: string[]; horizons: Record<Horizon, string | null> };
export type Reach = {state: string; expected: number | null; earliest: number | null; latest: number | null};
export type Scenario = {id: string; management: Reach | null; end: Reach | null};
export type Projection = {
  assetId: string; channel: string; horizon: Horizon; measurementVersion: string;
  dataVersion: string; sourceId: string; pointId: string | null; unit: string | null;
  record: {first: string; last: string; points: number};
  future: Array<{at:string; estimate: number; lower: number | null; upper: number | null}>;
  scenarios: Scenario[]; conditions: Conditions;
};
export class ProjectionUnavailable extends Error {}
export class MeasurementVersionMismatch extends Error {}

function object(raw: unknown): Record<string, unknown> | null {
  return typeof raw === "object" && raw !== null && !Array.isArray(raw)
    ? raw as Record<string, unknown> : null;
}
function str(raw: unknown): string {
  if (typeof raw !== "string" || !raw) throw new Error("예측 근거의 식별자가 올바르지 않습니다.");
  return raw;
}
function numberOrNull(raw: unknown): number | null {
  if (raw === null) return null;
  if (typeof raw !== "number" || !Number.isFinite(raw))
    throw new Error("예측 근거의 수치가 올바르지 않습니다.");
  return raw;
}
function date(raw: unknown): string {
  const value = str(raw);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) || !Number.isFinite(Date.parse(value)))
    throw new Error("예측 근거의 시각이 올바르지 않습니다.");
  return value;
}
function count(raw: unknown): number {
  if (typeof raw !== "number" || !Number.isSafeInteger(raw) || raw < 0)
    throw new Error("예측 근거의 측정 개수가 올바르지 않습니다.");
  return raw;
}
export function parseOptions(payload: unknown, assetId: string): Options {
  const data = object(payload), history = object(data?.history);
  if (data?.schema_version !== 1 || data.asset_id !== assetId)
    throw new Error("다른 설비의 예측 선택지가 응답됐습니다.");
  if (data.history === null)
    return {assetId, channels: [], horizons: {"1h":"no-history","24h":"no-history",
      "7d":"no-history","30d":"no-history"}};
  if (!history || !Array.isArray(history.series) || !object(history.horizons))
    throw new Error("예측 선택지의 자료 형태가 올바르지 않습니다.");
  const horizons = {} as Record<Horizon, string | null>;
  for (const key of ["1h","24h","7d","30d"] as const) {
    const value = object(history.horizons)?.[key];
    if (value !== null && typeof value !== "string")
      throw new Error("예측 기간의 계산 가능 여부가 명확하지 않습니다.");
    horizons[key] = value as string | null;
  }
  const channels = history.series.map((item: unknown) => str(object(item)?.key));
  return {assetId, channels:[...new Set(channels)], horizons};
}

function parseReach(raw: unknown): Reach | null {
  if (raw === null || raw === undefined) return null;
  const obj = object(raw);
  if (!obj) throw new Error("조건 도달 전망의 계산 근거가 올바르지 않습니다.");
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
    throw new Error("예측·상태 전망의 대상 설비·신호·계산 의미가 맞지 않습니다.");
  }
  const fVersion = str(forecast.measurement_version);
  const oVersion = str(outlook.measurement_version);
  const fs = str(forecast.source_id), os = str(outlook.source_id);
  const fp = forecast.measurement_point_id ?? null;
  const op = outlook.measurement_point_id ?? null;
  if (fVersion !== oVersion || fs !== os || fp !== op) {
    throw new MeasurementVersionMismatch(
      "두 계산에 사용된 측정 버전 또는 원본 출처가 서로 다릅니다. 값을 결합하지 않았습니다."
    );
  }
  const configured = object(outlook.conditions), record = object(outlook.record);
  if (!configured || !record || configured.direction !== conditions.direction
    || numberOrNull(configured.management) !== conditions.management
    || numberOrNull(configured.end) !== conditions.end)
    throw new Error("표시한 조건과 서버가 계산한 조건이 다릅니다.");
  if (!Array.isArray(forecast.forecast) || !Array.isArray(outlook.scenarios))
    throw new Error("예측과 시나리오 결과가 완전하지 않습니다.");
  const future = forecast.forecast.map((row: unknown) => {
    if (!Array.isArray(row) || row.length < 2)
      throw new Error("미래 예측값 형식이 올바르지 않습니다.");
    const estimate = numberOrNull(row[1]);
    if (estimate === null) throw new Error("미래 예측값이 누락됐습니다.");
    return {at:date(row[0]), estimate,
      lower:numberOrNull(row[2] ?? null), upper:numberOrNull(row[3] ?? null)};
  });
  const scenarios = outlook.scenarios.map((raw: unknown) => {
    const item = object(raw), limits = object(item?.limits);
    if (!item || !limits) throw new Error("조건부 시나리오 구조가 올바르지 않습니다.");
    return {id:str(item.id), management:parseReach(limits.management),
      end:parseReach(limits.end)};
  });
  return {assetId, channel, horizon, measurementVersion:fVersion,
    dataVersion:str(outlook.data_version), sourceId:fs,
    pointId:fp === null ? null : str(fp), unit:typeof forecast.unit === "string" ? forecast.unit : null,
    record: {first:date(record.first),last:date(record.last),points:count(record.points)},
    future, scenarios, conditions};
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
        "선택한 측정 또는 계산 기간에 예측을 제공할 수 없습니다."
        + (typeof reason==="string" ? " ("+reason+")" : "")
      );
    }
  }
  if (!response.ok) throw new Error("예측 서버의 조회 오류입니다. 측정값 부재나 설비 정상 판정과 다릅니다.");
  return await response.json() as unknown;
}
export async function loadOptions(assetId: string, signal: AbortSignal): Promise<Options> {
  return parseOptions(await json(
    "/api/v1/forecast/options?" + new URLSearchParams({asset_id:assetId}),signal),assetId);
}
export async function loadPaired(
  assetId: string, channel: string, horizon: Horizon,
  conditions: Conditions, signal: AbortSignal,
): Promise<Projection> {
  const args={asset_id:assetId,kind:"history",series:channel};
  const direction={direction:conditions.direction};
  const limits: Record<string,string> = {};
  if (conditions.management !== null) limits.management_limit=String(conditions.management);
  if (conditions.end !== null) limits.end_limit=String(conditions.end);
  const [forecast,outlook] = await Promise.all([
    json("/api/v1/forecast?" + new URLSearchParams({...args,horizon}),signal),
    json("/api/v1/outlook?" + new URLSearchParams({...args,...direction,...limits}),signal),
  ]);
  return parsePairedProjection(forecast,outlook,assetId,channel,horizon,conditions);
}
