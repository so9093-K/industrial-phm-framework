/** Display-only number text: stored values are never rounded, only how they read on screen. */
export function num(value: number | null | undefined, missing = "미산출"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return missing;
  if (Number.isInteger(value)) return String(value);
  return String(Number.parseFloat(value.toPrecision(6)));
}

const PROPERTY: Record<string, string> = {
  "electric current": "전류", "current": "전류", "phase current": "상 전류",
  "voltage": "전압", "phase voltage": "상 전압", "temperature": "온도", "frequency": "주파수",
  "pressure": "압력", "vibration": "진동", "power": "전력",
};
/** A stored measurement meaning as people read it; an unknown meaning stays as stored. */
export function propertyLabel(value: string): string {
  return PROPERTY[value.trim().toLowerCase()] ?? value;
}
