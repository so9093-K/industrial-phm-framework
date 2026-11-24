/** 분석 화면에서 이어 가는 AI 조사: 조사 화면이 넘겨 준 특이사항(주소의 summary_change)을 다시 찾는다. */
import type {EvidenceFocus} from "./change-evidence.ts";
import type {PlaybackScope} from "./record-playback.ts";
import {bandName, readRecordFindings, type RecordFindings} from "./record-findings.ts";
import {readVibrationFindings, type VibrationFindings} from "./vibration-findings.ts";
import type {Tab, Method} from "./routes.ts";

export type ChangeRef =
  | {kind: "history"; key: string; start: string; end: string}
  | {kind: "vibration"; feature: string; from: number; to: number};

/** 주소의 summary_change(["history", 신호, 시작, 끝] 또는 ["vibration", 특징, 처음, 끝]). */
export function changeRef(search: string): ChangeRef | null {
  try {
    const raw: unknown = JSON.parse(new URLSearchParams(search).get("summary_change") ?? "null");
    if (!Array.isArray(raw) || raw.length !== 4 || typeof raw[1] !== "string" || !raw[1]) return null;
    if (raw[0] === "history" && typeof raw[2] === "string" && typeof raw[3] === "string")
      return {kind: "history", key: raw[1], start: raw[2], end: raw[3]};
    if (raw[0] === "vibration" && Number.isSafeInteger(raw[2]) && Number.isSafeInteger(raw[3]))
      return {kind: "vibration", feature: raw[1], from: raw[2], to: raw[3]};
  } catch { /* 직접 연 분석 주소에는 이어 갈 특이사항이 없다. */ }
  return null;
}

/** 읽은 특이사항 목록에서 그 특이사항을 찾는다(조사 화면이 고른 것과 같은 기간·신호). */
export function focusOf(ref: ChangeRef, history: RecordFindings | null, vibration: VibrationFindings | null): EvidenceFocus | null {
  if (ref.kind === "history" && history) {
    const item = history.intervals.find(row => (row.context?.key ?? row.channel) === ref.key && row.start === ref.start && row.end === ref.end);
    if (!item?.reviewKey) return null;
    const own = item.operation ? history.operation.find(entry => entry.key === item.operation?.key) : undefined;
    return {kind: "history", item, record: history, condition: own && item.band != null ? bandName(own, item.band) : null};
  }
  if (ref.kind === "vibration" && vibration) {
    const change = vibration.intervals.find(row => row.feature === ref.feature && row.from === ref.from && row.to === ref.to);
    return change?.reviewKey ? {kind: "vibration", change, record: vibration} : null;
  }
  return null;
}

export async function resolveFocus(assetId: string, search: string, scope: PlaybackScope | null, signal: AbortSignal): Promise<EvidenceFocus | null> {
  const ref = changeRef(search);
  if (!ref) return null;
  return ref.kind === "history"
    ? focusOf(ref, await readRecordFindings(assetId, signal, scope), null)
    : focusOf(ref, null, await readVibrationFindings(assetId, signal, scope));
}

/** 지금 화면이 어떤 분석인지: 서버가 그 화면의 수치를 함께 읽는다. 조사 화면(요약)은 null. */
export function analysisView(tab: Tab, method: Method | null): string | null {
  if (tab === "change") return method ?? "compare";
  if (tab === "signals" || (tab === "anomaly" && method === "model")) return tab;
  return null;
}
