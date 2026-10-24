/** Actual recorded inputs, independent of forecast readiness or algorithms.
 * GET /api/v1/explore/sources owns input facts, never an asset-health verdict. */
import {methodsOf, type DataKind, type Method, type Tab} from "./routes.ts";
import type {Capabilities, CapabilityId} from "./capabilities.ts";

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
  const vibration = root.acquisition === null ? null : object(root.acquisition);
  if ((root.history !== null && (!history || !Array.isArray(history.channels)))
    || (root.acquisition !== null && (!vibration || !Array.isArray(vibration.features))))
    throw new Error("설비 데이터 목록의 형식이 올바르지 않습니다.");
  const timing = vibration && typeof vibration.source_id === "string" && vibration.source_id.trim()
    && typeof vibration.period_seconds === "number" && Number.isFinite(vibration.period_seconds)
    && vibration.period_seconds > 0
    ? {sourceId: vibration.source_id, periodSeconds: vibration.period_seconds} : null;
  return {
    history: history ? {signals: (history.channels as unknown[]).length} : null,
    vibration: vibration
      ? {measurements: count(vibration.count), first: count(vibration.first), last: count(vibration.last),
        ...(timing ? {timing} : {})}
      : null,
  };
}

/** Unknown data or no stored measurements cannot grant a usable capability. */
export function kindsOf(data: AssetData | null): DataKind[] {
  if (!data) return [];
  const kinds: DataKind[] = [];
  if (data.history) kinds.push("history");
  if (data.vibration) kinds.push("vibration");
  return kinds;
}

/** A mixed asset requires an explicit choice; avoid silently favoring one source. */
export function defaultKind(data: AssetData | null): DataKind | null {
  const kinds = kindsOf(data);
  return kinds.length === 1 ? kinds[0] : null;
}

export async function readAssetData(assetId: string, signal: AbortSignal): Promise<AssetData> {
  const response = await fetch("/api/v1/explore/sources?" + new URLSearchParams({asset_id: assetId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("설비의 데이터 종류를 확인하지 못했습니다.");
  }
  return parseAssetData(await response.json() as unknown, assetId);
}

/** Data kinds are navigation context; execution eligibility is owned by the server.
 * Model and 3-phase electrical methods open inspection/setup, not a ready claim. */
export function methodsFor(
  tab: Tab, data: AssetData | null, capabilities: Capabilities | null, kind: DataKind | null = null,
): Method[] {
  if (!capabilities || !kindsOf(data).length) return [];
  const status = (id: CapabilityId, source: DataKind | null): string => {
    const item = capabilities.items.find(value => value.id === id);
    if (!item) return "unavailable";
    const byKind = item.facts.by_kind;
    if (source && byKind && typeof byKind === "object" && !Array.isArray(byKind)) {
      const state = (byKind as Record<string, unknown>)[source];
      return typeof state === "string" ? state : "unavailable";
    }
    return item.status;
  };
  const kinds = kind ? [kind] : kindsOf(data);
  return methodsOf(tab).filter(method => {
    if (method === "model") return true;
    if (method === "baseline") return data?.history !== null && data?.history !== undefined;
    // Correct R/S/T and units require the existing /api/v1/condition source inspection.
    if (method === "electrical") return kinds.includes("history") && (data?.history?.signals ?? 0) >= 3;
    if (method === "spectrum") return kinds.includes("vibration") && status("spectrum","vibration") === "ready";
    const id = method === "compare" ? "period-compare" : "relation";
    return kinds.some(source => status(id,source) === "ready");
  });
}
