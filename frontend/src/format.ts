/** Display-only number text: stored values are never rounded, only how they read on screen. */
export function num(value: number | null | undefined, missing = "미산출"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return missing;
  if (Number.isInteger(value)) return String(value);
  return String(Number.parseFloat(value.toPrecision(6)));
}
