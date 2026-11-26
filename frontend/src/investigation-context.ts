import {clockText} from "./date-format.ts";

/** The observation that opened an investigation, not the analysis's editable A/B periods. */
export function investigationContext(search: string): {label: string; span: string} | null {
  const params = new URLSearchParams(search);
  try {
    const key: unknown = JSON.parse(params.get("summary_change") ?? "null");
    if (!Array.isArray(key) || key.length !== 4 || typeof key[1] !== "string" || !key[1]) return null;
    const label = ((params.get("summary_label") ?? "").trim() || "선택한 변화").slice(0, 160);
    if (key[0] === "vibration" && Number.isSafeInteger(key[2]) && Number.isSafeInteger(key[3])
      && key[2] >= 1 && key[3] >= key[2]) return {label, span: key[2] + "–" + key[3] + "번째 측정"};
    if (key[0] === "history" && typeof key[2] === "string" && typeof key[3] === "string") {
      const from = Date.parse(key[2]), to = Date.parse(key[3]);
      if (Number.isFinite(from) && Number.isFinite(to) && from <= to)
        return {label, span: clockText(from) + " ~ " + clockText(to)};
    }
  } catch { /* Direct analysis addresses need no invented observation. */ }
  return null;
}
