/** Value-axis ticks for the measurement charts: a few round values inside the drawn range,
 * placed in the chart's own vertical coordinates and labelled with the measurement's unit. */

export type Tick = {value: number; y: number};

/** Round steps (1, 2, 2.5, 5 × 10ⁿ) giving about `count` ticks between lo and hi. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) return [];
  const raw = (hi - lo) / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((f) => f * power).find((candidate) => candidate >= raw) ?? 10 * power;
  const ticks: number[] = [];
  for (let value = Math.ceil(lo / step) * step; value <= hi + step * 1e-9; value += step) {
    ticks.push(Number.parseFloat(value.toPrecision(12)));
  }
  return ticks;
}

/** Ticks for a chart whose value `lo..hi` runs from `bottom` up to `top`; a tick on the very
 * edge is left out so its label never sits half outside the plot. */
export function yTicks(lo: number, hi: number, top: number, bottom: number, count = 4): Tick[] {
  const margin = (bottom - top) * 0.04;
  return niceTicks(lo, hi, count).map((value) => ({value, y: bottom - ((value - lo) / (hi - lo)) * (bottom - top)}))
    .filter((tick) => tick.y >= top + margin && tick.y <= bottom - margin);
}

/** A tick or a measured value as people read it: a few digits and the unit when there is one. */
export function measure(value: number, unit: string | null | undefined, digits = 3): string {
  const text = value !== 0 && Math.abs(value) < 0.0001 ? value.toExponential(digits - 1)
    : Math.abs(value) >= 1000 || Number.isInteger(value)
    ? Math.round(value).toLocaleString("ko-KR")
    : Number.parseFloat(value.toPrecision(digits)).toLocaleString("ko-KR", {maximumFractionDigits: 6});
  return unit ? text + " " + unit : text;
}
