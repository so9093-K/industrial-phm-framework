// The server owns observation values and PHM meaning. This preview only renders
// validated fields from the existing read-only monitor API.
export type Asset = {
  assetId: string;
  flow: string;
  lastObservedAt: string | null;
  attentionCount: number;
};

export type Snapshot = {
  assessedAt: string | null;
  assets: Asset[];
  truncated: boolean;
  systemReadUncertain: boolean;
};

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : 0;
}

export function parseMonitor(value: unknown): Snapshot {
  const response = object(value);
  const assetGroup = object(response?.assets);
  if (!response || !assetGroup || !Array.isArray(assetGroup.items)) {
    throw new Error("관측 응답의 형식을 확인할 수 없습니다.");
  }
  const assets: Asset[] = [];
  for (const entry of assetGroup.items) {
    const row = object(entry);
    if (!row || typeof row.asset_id !== "string" || !row.asset_id) {
      throw new Error("설비 식별자가 올바르지 않습니다.");
    }
    assets.push({
      assetId: row.asset_id,
      flow: typeof row.data_flow_status === "string" ? row.data_flow_status : "미확인",
      lastObservedAt: typeof row.last_data_at === "string" ? row.last_data_at : null,
      attentionCount: count(row.attention_count),
    });
  }
  return {
    assessedAt: typeof response.assessed_at === "string" ? response.assessed_at : null,
    assets,
    truncated: assetGroup.truncated === true,
    systemReadUncertain: Array.isArray(response.system_error_scopes) && response.system_error_scopes.length > 0,
  };
}

export async function readMonitor(signal: AbortSignal): Promise<Snapshot> {
  const response = await fetch("/api/v1/monitor", { signal, cache: "no-store" });
  if (!response.ok) throw new Error("서버에서 관측 정보를 확인하지 못했습니다.");
  return parseMonitor(await response.json() as unknown);
}
