/** Each acquisition's spectrum over the whole record, one row per acquisition, so a reader sees
 * from which acquisition a band's energy changed (GET /api/v1/explore/waterfall). Power is in dB
 * against each channel's strongest bin; it locates energy, it does not name a fault frequency. */
import {object} from "./writes.ts";

export type WaterfallChannel = {id: string; label: string; decibels: number[][]};
export type Waterfall = {frequencies: number[]; acquisitions: number[]; floorDb: number; channels: WaterfallChannel[]};

function invalid(): never { throw new Error("측정별 스펙트럼의 형식이 올바르지 않습니다."); }
const finite = (raw: unknown): number => typeof raw === "number" && Number.isFinite(raw) ? raw : invalid();

export function parseWaterfall(raw: unknown, assetId: string): Waterfall {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.asset_id !== assetId || root.meaning !== "stored-waveform-spectra-not-fault-frequencies"
    || !Array.isArray(root.frequencies) || !Array.isArray(root.acquisitions) || !Array.isArray(root.channels)) invalid();
  const frequencies = root.frequencies.map(finite);
  const acquisitions = root.acquisitions.map(value => Number.isInteger(value) ? value as number : invalid());
  const channels = root.channels.map((entry: unknown): WaterfallChannel => {
    const row = object(entry);
    if (!row || typeof row.channel !== "string" || typeof row.label !== "string" || !Array.isArray(row.decibels)
      || row.decibels.length !== acquisitions.length) invalid();
    return {id: row.channel, label: row.label, decibels: row.decibels.map((line: unknown) => {
      if (!Array.isArray(line) || line.length !== frequencies.length) invalid();
      return line.map(finite);
    })};
  });
  return {frequencies, acquisitions, floorDb: finite(root.floor_db), channels};
}

export async function readWaterfall(assetId: string, signal: AbortSignal): Promise<Waterfall> {
  const response = await fetch("/api/v1/explore/waterfall?" + new URLSearchParams({asset_id: assetId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("측정별 스펙트럼을 읽지 못했습니다.");
  }
  return parseWaterfall(await response.json() as unknown, assetId);
}

// One hue from light (weak) to dark (strong), so a stronger band reads darker.
const STOPS = [[244, 249, 251], [179, 219, 229], [74, 155, 179], [31, 118, 144], [11, 61, 79]];
/** The colour of a power in dB between the floor and 0 dB. */
export function shade(decibels: number, floorDb: number): [number, number, number] {
  const t = Math.min(1, Math.max(0, (decibels - floorDb) / -floorDb)) * (STOPS.length - 1);
  const low = Math.floor(t), high = Math.min(STOPS.length - 1, low + 1), part = t - low;
  return [0, 1, 2].map(i => Math.round(STOPS[low][i] + (STOPS[high][i] - STOPS[low][i]) * part)) as [number, number, number];
}
export const GRADIENT = "linear-gradient(90deg," + STOPS.map(color => "rgb(" + color.join(",") + ")").join(",") + ")";
