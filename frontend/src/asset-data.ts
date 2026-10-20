/** Which stored data an asset has. It picks a sensible default analysis; it says nothing
 * about the asset's condition. Read from the existing GET /api/v1/forecast/options. */
import {methodsOf, type DataKind, type Method, type Tab} from "./routes.ts";

export type AcquisitionTiming = {sourceId: string; periodSeconds: number};
export type AssetData = {
  history: {signals: number} | null;
  vibration: {measurements: number; first: number; last: number; timing?: AcquisitionTiming} | null;
};

function object(raw: unknown): Record<string, unknown> | null {
  return raw !== null && typeof raw === "object" && !Array.isArray(raw)
    ? raw as Record<string, unknown> : null;
}
function count(raw: unknown): number {
  if (typeof raw !== "number" || !Number.isSafeInteger(raw) || raw < 0)
    throw new Error("설비 데이터 개수를 확인할 수 없습니다.");
  return raw;
}

export function parseAssetData(raw: unknown, assetId: string): AssetData {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.asset_id !== assetId)
    throw new Error("선택한 설비의 데이터 목록이 아닙니다.");
  const history = root.history === null ? null : object(root.history);
  const vibration = root.acquisition === null || root.acquisition === undefined
    ? null : object(root.acquisition);
  if ((root.history !== null && (!history || !Array.isArray(history.series)))
    || (root.acquisition !== null && root.acquisition !== undefined && !vibration))
    throw new Error("설비 데이터 목록의 형식이 올바르지 않습니다.");
  const timing = vibration && typeof vibration.source_id === "string" && vibration.source_id.trim()
    && typeof vibration.period_seconds === "number" && Number.isFinite(vibration.period_seconds)
    && vibration.period_seconds > 0
    ? {sourceId: vibration.source_id, periodSeconds: vibration.period_seconds} : null;
  return {
    history: history ? {signals: (history.series as unknown[]).length} : null,
    vibration: vibration
      ? {measurements: count(vibration.count), first: count(vibration.first), last: count(vibration.last),
        ...(timing ? {timing} : {})}
      : null,
  };
}

/** Unknown availability offers both kinds rather than hiding one. */
export function kindsOf(data: AssetData | null): DataKind[] {
  if (!data) return ["history", "vibration"];
  const kinds: DataKind[] = [];
  if (data.history) kinds.push("history");
  if (data.vibration) kinds.push("vibration");
  return kinds.length ? kinds : ["history", "vibration"];
}

export function defaultKind(data: AssetData | null): DataKind {
  return kindsOf(data)[0];
}

export async function readAssetData(assetId: string, signal: AbortSignal): Promise<AssetData> {
  const response = await fetch("/api/v1/forecast/options?" + new URLSearchParams({asset_id: assetId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("설비의 데이터 종류를 확인하지 못했습니다.");
  }
  return parseAssetData(await response.json() as unknown, assetId);
}

/** The analysis methods this asset's data supports: frequency analysis needs waveforms, and the
 * baseline departure and load/unbalance read time series. Unknown data offers them all. */
export function methodsFor(tab: Tab, data: AssetData | null): Method[] {
  const needs: Partial<Record<Method, keyof AssetData>> = {baseline: "history", spectrum: "vibration", electrical: "history"};
  // As with data kinds, knowing of neither kind is not a reason to hide a method.
  const known = data !== null && (data.history !== null || data.vibration !== null);
  return methodsOf(tab).filter((method) => !known || !needs[method] || data![needs[method]!] !== null);
}
