/** How a model's reference period and analysed windows ran, by the operating levels of the
 * current its source records (GET /api/v1/phm/operation). A model learns its reference period's
 * patterns, so windows at a level that period hardly held are said apart. */
import {bandName, percent, type LevelNames} from "./record-findings.ts";
import {object} from "./writes.ts";

export type ModelOperation = {
  label: string; names: LevelNames;
  /** The period the model learned from, and its share of time per band (stopped first). */
  reference: {from: string; to: string; shares: number[] | null} | null;
  /** Per band: windows that ran mostly at it, and how many went over the model threshold. */
  windows: {band: number; count: number; exceeded: number}[];
  unplaced: number;
};

function invalid(): never { throw new Error("모델의 운전 상태 정보 형식이 올바르지 않습니다."); }
const count = (raw: unknown): number => typeof raw === "number" && Number.isInteger(raw) && raw >= 0 ? raw : invalid();
const finite = (raw: unknown): number => typeof raw === "number" && Number.isFinite(raw) ? raw : invalid();

export function parseModelOperation(raw: unknown, bindingId: string): ModelOperation | null {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.binding_id !== bindingId) invalid();
  if (root.operation === null || root.operation === undefined) return null;
  const row = object(root.operation);
  if (!row || !Array.isArray(row.levels) || !Array.isArray(row.windows) || typeof row.label !== "string") invalid();
  const levels = row.levels.map((entry: unknown) => {
    const level = object(entry);
    if (!level) invalid();
    return {low: finite(level.low), high: level.high === null ? null : finite(level.high), typical: finite(level.typical)};
  });
  const bands = levels.length + 1;
  const reference = object(row.reference);
  const shares = reference?.shares;
  if (Array.isArray(shares) && (shares.length !== bands || !shares.every(value => typeof value === "number" && value >= 0 && value <= 1))) invalid();
  return {
    label: row.label, unplaced: count(row.unplaced),
    names: {levels, stoppedBelow: finite(row.stopped_below), unit: typeof row.unit === "string" ? row.unit : null},
    reference: reference && typeof reference.from === "string" && typeof reference.to === "string"
      ? {from: reference.from, to: reference.to, shares: Array.isArray(shares) ? shares as number[] : null} : null,
    windows: row.windows.map((entry: unknown) => {
      const item = object(entry);
      if (!item) invalid();
      const band = count(item.band), total = count(item.count), over = count(item.exceeded);
      if (band >= bands || over > total) invalid();
      return {band, count: total, exceeded: over};
    }),
  };
}

export async function readModelOperation(bindingId: string, signal: AbortSignal): Promise<ModelOperation | null> {
  const response = await fetch("/api/v1/phm/operation?" + new URLSearchParams({binding_id: bindingId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("모델의 운전 상태 정보를 읽지 못했습니다.");
  }
  return parseModelOperation(await response.json() as unknown, bindingId);
}

/** A level the reference period held for under this share is one it hardly learned. */
export const RARE_IN_REFERENCE = 0.05;

/** The excesses that came from levels the reference period hardly held, said as observed. */
export function unlearnedText(operation: ModelOperation): string | null {
  const shares = operation.reference?.shares;
  if (!shares) return null;
  const rare = operation.windows.filter(row => shares[row.band] < RARE_IN_REFERENCE && row.count);
  const learned = operation.windows.filter(row => shares[row.band] >= RARE_IN_REFERENCE && row.count);
  const over = operation.windows.reduce((sum, row) => sum + row.exceeded, 0);
  const rareOver = rare.reduce((sum, row) => sum + row.exceeded, 0);
  if (!rare.length || !rareOver) return null;
  const names = rare.map(row => bandName(operation.names, row.band)).join("·");
  const known = learned.map(row => bandName(operation.names, row.band) + "에서는 " + row.count.toLocaleString("ko-KR") + "개 중 "
    + row.exceeded.toLocaleString("ko-KR") + "개(" + percent(row.exceeded / row.count) + ")").join(", ");
  return "기준 초과 " + over.toLocaleString("ko-KR") + "회 중 " + rareOver.toLocaleString("ko-KR") + "회는 모델 기준 기간에 거의 없던 운전 상태("
    + names + ")의 창입니다." + (known ? " 기준 기간에 있던 " + known + "가 기준을 넘었습니다." : "");
}
