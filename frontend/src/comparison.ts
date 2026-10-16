/** Two-period stored history, separated by exact server source/point/meaning identity. */
export type Periods = { a: { from: string; to: string }; b: { from: string; to: string } };
export type PeriodProfile = {
  observations: number;
  usable: number;
  missing: number | null;
  nonGood: number | null;
  conflict: number | null;
  median: number | null;
  mean: number | null;
  quantiles: number[] | null;
};
export type ProfileSeries = {
  key: string;
  channel: string;
  source: string;
  point: string | null;
  interpretation: string;
  unit: string | null;
  periods: { a: PeriodProfile; b: PeriodProfile };
  medianChange: number | null;
  outsidePercent: number | null;
};
export type ProfileResult = { assetId: string; channel: string; periods: Periods; series: ProfileSeries[] };
export type SourceHistory = { assetId: string; channels: string[]; from: string; to: string };
export class NoHistoryError extends Error {}

function rec(raw: unknown): Record<string, unknown> | null {
  return raw && typeof raw === "object" && !Array.isArray(raw)
    ? raw as Record<string, unknown> : null;
}
function string(raw: unknown): string {
  if (typeof raw !== "string" || !raw) throw new Error("저장 이력의 식별자가 올바르지 않습니다.");
  return raw;
}
function instant(raw: unknown): string {
  const s = string(raw);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(s) || !Number.isFinite(Date.parse(s)))
    throw new Error("저장 이력의 시각을 확인할 수 없습니다.");
  return s;
}
function positiveCount(raw: unknown): number {
  if (typeof raw !== "number" || !Number.isSafeInteger(raw) || raw < 0)
    throw new Error("저장 이력의 기록 수가 올바르지 않습니다.");
  return raw;
}
function optionalCount(raw: unknown): number | null {
  return raw === undefined || raw === null ? null : positiveCount(raw);
}
function optionalNumber(raw: unknown): number | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== "number" || !Number.isFinite(raw))
    throw new Error("저장 이력의 통계값이 올바르지 않습니다.");
  return raw;
}

export function validatePeriods(periods: Periods): void {
  for (const name of ["a", "b"] as const) {
    const {from, to} = periods[name];
    const diff = Date.parse(instant(to)) - Date.parse(instant(from));
    if (!(diff > 0 && diff <= 31 * 86400 * 1000))
      throw new Error("각 구간은 0보다 길고 31일 이하여야 합니다.");
  }
}

export function defaultPeriods(from: string, to: string): Periods {
  const last = Date.parse(instant(to));
  const first = Math.max(Date.parse(instant(from)), last - 60 * 86400 * 1000);
  if (last - first < 2000) throw new Error("두 구간으로 나눌 저장 측정 기간이 부족합니다.");
  const mid = Math.floor((first + last + 1000) / 2);
  const periods = {
    a: {from: new Date(first).toISOString(), to: new Date(mid).toISOString()},
    b: {from: new Date(mid).toISOString(), to: new Date(last + 1000).toISOString()},
  };
  validatePeriods(periods);
  return periods;
}

export function parseSources(payload: unknown, assetId: string): SourceHistory {
  const response = rec(payload), history = rec(response?.history);
  if (response?.schema_version === 1 && response.asset_id === assetId
    && response.history === null) {
    throw new NoHistoryError("해당 설비에는 저장된 측정 이력이 없습니다.");
  }
  if (response?.schema_version !== 1 || response.asset_id !== assetId
    || !history || !Array.isArray(history.channels)) {
    throw new Error("선택한 설비의 이력 데이터 계약이 맞지 않습니다.");
  }
  const channels = history.channels.map(string);
  return { assetId, channels: [...new Set(channels)],
    from: instant(history.start_at), to: instant(history.end_at) };
}

function parsePeriod(raw: unknown): PeriodProfile {
  const p = rec(raw);
  if (!p) throw new Error("저장 이력의 구간 통계가 없습니다.");
  const quantiles = p.quantiles === null || p.quantiles === undefined
    ? null : Array.isArray(p.quantiles) && p.quantiles.length === 5
      ? p.quantiles.map(x => {
        const n = optionalNumber(x);
        if (n === null) throw new Error("분위수 통계가 올바르지 않습니다.");
        return n;
      }) : null;
  if (p.quantiles !== null && p.quantiles !== undefined && quantiles === null)
    throw new Error("분위수 통계가 올바르지 않습니다.");
  return { observations: positiveCount(p.observation_count),
    usable: positiveCount(p.usable_count),
    missing: optionalCount(p.missing_count),
    nonGood: optionalCount(p.non_good_count),
    conflict: optionalCount(p.conflict_count),
    median: quantiles?.[2] ?? null, quantiles,
    mean: optionalNumber(p.mean) };
}

export function parseProfile(
  payload: unknown, assetId: string, channel: string, requested: Periods,
): ProfileResult {
  validatePeriods(requested);
  const response = rec(payload), periods = rec(response?.periods);
  const a = rec(periods?.a), b = rec(periods?.b);
  if (response?.schema_version !== 1 || response.asset_id !== assetId
    || response.kind !== "history"
    || response.meaning !== "stored-measurements-compared-not-asset-health"
    || !a || !b || !Array.isArray(response.series)) {
    throw new Error("구간 비교 결과의 계산 의미·설비·자료 종류가 맞지 않습니다.");
  }
  for (const name of ["a", "b"] as const) {
    const actual = rec(periods?.[name]);
    if (Date.parse(instant(actual?.from)) !== Date.parse(requested[name].from)
      || Date.parse(instant(actual?.to)) !== Date.parse(requested[name].to))
      throw new Error("요청한 구간과 다른 통계가 반환됐습니다.");
  }
  const identities = new Set<string>();
  const series = response.series.map((raw: unknown) => {
    const item = rec(raw), stats = rec(item?.periods), comp = rec(item?.comparison);
    if (!item || item.kind !== "history" || item.key !== channel || !stats || !comp)
      throw new Error("다른 신호의 통계가 혼합됐습니다.");
    const source = string(item.source_id), interpretation = string(item.interpretation_id);
    const point = item.measurement_point_id === null ? null : string(item.measurement_point_id);
    const identity = JSON.stringify([channel, source, item.source_type, point, interpretation]);
    if (identities.has(identity)) throw new Error("중복 측정 출처가 반환됐습니다.");
    identities.add(identity);
    const pa = parsePeriod(stats.a), pb = parsePeriod(stats.b);
    const medianChange = optionalNumber(comp.median_change);
    if ((!pa.quantiles || !pb.quantiles) && medianChange !== null)
      throw new Error("두 구간의 계산 근거 없이 변화값을 표시할 수 없습니다.");
    return {
      key: identity, channel, source, point, interpretation,
      unit: typeof item.unit === "string" ? item.unit : null,
      periods: {a: pa, b: pb},
      medianChange, outsidePercent: optionalNumber(comp.b_outside_a_band_percent),
    };
  });
  return {assetId, channel, periods: requested, series};
}

async function body(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, {signal, cache:"no-store", credentials:"same-origin"});
  if (response.status === 404) {
    const error: unknown = await response.json().catch(() => null);
    if (rec(error)?.error === "nothing_to_explore") throw new NoHistoryError("비교할 저장 이력이 없습니다.");
    throw new Error("이력 API 경로를 조회할 수 없습니다.");
  }
  if (!response.ok) throw new Error("이력 통계를 조회하지 못했습니다. 데이터 없음과는 다른 상태입니다.");
  return await response.json() as unknown;
}
export async function readSources(assetId: string, signal: AbortSignal): Promise<SourceHistory> {
  return parseSources(await body(
    "/api/v1/explore/sources?" + new URLSearchParams({asset_id:assetId}), signal), assetId);
}
export async function readProfile(
  assetId: string, channel: string, periods: Periods, signal: AbortSignal,
): Promise<ProfileResult> {
  validatePeriods(periods);
  const query = new URLSearchParams({asset_id:assetId,kind:"history",series:channel,
    a_from:periods.a.from,a_to:periods.a.to,b_from:periods.b.from,b_to:periods.b.to});
  return parseProfile(await body("/api/v1/explore/profile?" + query, signal),
    assetId, channel, periods);
}
