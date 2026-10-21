import {niceTicks} from "./chart-axis.ts";
import {num} from "./format.ts";

/** What the horizontal axis of a measurement chart counts, and its tick labels.
 * Stored records keep their own clock, order and receipt times; only the display converts.
 * A record with timestamps is drawn on the clock. A sequence with a known measurement interval
 * is drawn as time since its first measurement: this only shifts where zero is, never the
 * spacing, so trends, rates and reach times read the same. A sequence with neither is drawn
 * by measurement number. */

export type XScale =
  /** Numeric feature values or frequencies, never measurement addresses. */
  | {kind: "value"}
  /** Values are epoch milliseconds; labels in `zone` (wall times written without an offset
   * are placed on UTC to keep their written clock). */
  | {kind: "clock"; zone?: "Asia/Seoul" | "UTC"}
  /** Values are measurement numbers; #1 is at 0 and each step is `period` seconds. */
  | {kind: "elapsed"; period: number}
  /** Values are measurement numbers. */
  | {kind: "order"};

export type XTick = {value: number; x: number; label: string};

const MINUTE = 60, HOUR = 3600, DAY = 86400;
const ELAPSED_STEPS = [1, 2, 5, 10, 15, 30, MINUTE, 2 * MINUTE, 5 * MINUTE, 10 * MINUTE, 15 * MINUTE,
  20 * MINUTE, 30 * MINUTE, HOUR, 2 * HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, DAY, 2 * DAY, 7 * DAY, 14 * DAY, 30 * DAY];
const CLOCK_STEPS = [1, 5, 10, 15, 30, MINUTE, 2 * MINUTE, 5 * MINUTE, 10 * MINUTE, 15 * MINUTE, 30 * MINUTE,
  HOUR, 2 * HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, DAY, 2 * DAY, 7 * DAY, 14 * DAY];

function step(span: number, count: number, steps: number[]): number {
  const raw = span / count;
  if (raw >= steps[0] && raw <= steps[steps.length - 1])
    return steps.find((candidate) => candidate >= raw)!;
  const power = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map(value => value * power).find(value => value >= raw)!;
}

/** A duration as people say it: "45초", "30분", "1시간 15분", "2일 3시간". */
export function elapsedText(seconds: number): string {
  const s = Math.round(Math.max(0, seconds));
  if (s < MINUTE) return s + "초";
  if (s < HOUR) {
    const m = Math.floor(s / MINUTE), rest = s % MINUTE;
    return m + "분" + (rest && m < 10 ? " " + rest + "초" : "");
  }
  if (s < DAY) {
    const h = Math.floor(s / HOUR), m = Math.round((s % HOUR) / MINUTE);
    return m === 60 ? h + 1 + "시간" : h + "시간" + (m ? " " + m + "분" : "");
  }
  const d = Math.floor(s / DAY), h = Math.round((s % DAY) / HOUR);
  return h === 24 ? d + 1 + "일" : d + "일" + (h ? " " + h + "시간" : "");
}

/** Where a measurement sits in time when only its number and the interval are known. */
export function sinceStart(position: number, period: number): string {
  return "기록 시작 후 " + elapsedText((position - 1) * period);
}

/** Keep the original measurement address beside the interval-derived display time. */
export function measurementLabel(position: number, period?: number | null): string {
  const ordinal = position + "번째 측정";
  return period !== null && period !== undefined && Number.isFinite(period) && period > 0
    ? sinceStart(position, period) + " (" + ordinal + ")" : ordinal;
}

function zeroLabel(unit: number): string {
  return unit < MINUTE ? "0초" : unit < HOUR ? "0분" : unit < DAY ? "0시간" : "0일";
}

function clockParts(at: number, zone: string, unit: number, year: boolean): {day: string; time: string} {
  const date = new Date(at);
  return {
    day: date.toLocaleDateString("ko-KR", {timeZone: zone, year: year ? "numeric" : undefined, month: "numeric", day: "numeric"}),
    time: date.toLocaleTimeString("ko-KR", {timeZone: zone, hour: "2-digit", minute: "2-digit",
      second: unit < MINUTE * 1000 ? "2-digit" : undefined,
      fractionalSecondDigits: unit < 1000 ? 3 : undefined, hourCycle: "h23"}),
  };
}

/** Tick precision follows the spacing even when zoomed into a late part of a long record. */
function elapsedTick(seconds: number, unit: number): string {
  if (seconds === 0) return zeroLabel(unit);
  let rest = Math.round(seconds * 1000) / 1000;
  const parts: string[] = [];
  for (const [size, label] of [[DAY, "일"], [HOUR, "시간"], [MINUTE, "분"]] as const) {
    const amount = Math.floor(rest / size);
    if (amount) parts.push(amount + label);
    rest -= amount * size;
  }
  if (unit < MINUTE && rest) parts.push(Number(rest.toFixed(3)) + "초");
  return parts.join(" ");
}

/** About `count` ticks at round places between `lo` and `hi`, in the scale's own values. */
export function xTicks(lo: number, hi: number, scale: XScale, count = 5): XTick[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi < lo
    || (scale.kind === "elapsed" && (!Number.isFinite(scale.period) || scale.period <= 0))) return [];
  count = Number.isFinite(count) ? Math.max(1, Math.min(12, Math.floor(count))) : 5;
  const at = (value: number) => hi === lo ? 0 : (value - lo) / (hi - lo);
  const ticks: XTick[] = [];
  if (scale.kind === "value") {
    const values = niceTicks(lo, hi, count);
    return (values.length >= 2 ? values : hi === lo ? [lo] : [lo, hi])
      .map(value => ({value, x: at(value), label: num(value)}));
  }
  if (scale.kind === "clock") {
    const zone = scale.zone ?? "Asia/Seoul";
    const shift = zone === "UTC" ? 0 : 9 * HOUR * 1000;
    const unit = Math.max(1, step(Math.max(1, hi - lo) / 1000, count, CLOCK_STEPS) * 1000);
    const year = new Date(lo + shift).getUTCFullYear() !== new Date(hi + shift).getUTCFullYear();
    let previousDay = "";
    for (let value = Math.ceil((lo + shift) / unit) * unit - shift; value <= hi; value += unit) {
      const {day, time} = clockParts(value, zone, unit, year);
      // Midnight names the day alone; the first tick of a new day carries its date.
      const label = unit >= DAY * 1000 || time === "00:00" ? day : day !== previousDay ? day + " " + time : time;
      previousDay = day;
      ticks.push({value, x: at(value), label});
    }
    if (ticks.length < 2) return (hi === lo ? [lo] : [lo, hi]).map(value => {
      const {day, time} = clockParts(value, zone, unit, year);
      return {value, x: at(value), label: day + " " + time};
    });
    return ticks;
  }
  if (scale.kind === "elapsed") {
    const from = (lo - 1) * scale.period, to = (hi - 1) * scale.period;
    const unit = Math.max(0.001, step(Math.max(0.001, to - from), count, ELAPSED_STEPS));
    for (let seconds = Math.ceil(from / unit - 1e-9) * unit; seconds <= to + 1e-9; seconds += unit) {
      const value = seconds / scale.period + 1;
      ticks.push({value, x: Math.max(0, Math.min(1, at(value))), label: elapsedTick(seconds, unit)});
    }
    if (ticks.length < 2) return (hi === lo ? [lo] : [lo, hi]).map(value =>
      ({value, x: at(value), label: elapsedTick((value - 1) * scale.period, unit)}));
    return ticks;
  }
  const raw = (hi - lo) / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(Math.max(raw, 1)));
  const unit = Math.max(1, [1, 2, 5, 10].map((f) => f * power).find((candidate) => candidate >= raw) ?? 10 * power);
  for (let value = Math.ceil(lo / unit) * unit; value <= hi; value += unit) ticks.push({value, x: at(value), label: "#" + value});
  if (ticks.length < 2) return (hi === lo ? [lo] : [lo, hi]).map(value => ({value, x: at(value), label: "#" + value}));
  return ticks;
}

/** The scale for a sequence of measurements: time since the first when the interval is known. */
export function measurementScale(period: number | null | undefined): XScale {
  return period && Number.isFinite(period) && period > 0 ? {kind: "elapsed", period} : {kind: "order"};
}
