/** Which signals raised a model score: the model's per-feature parts summed per signal (ADR-0035). */

const STATS = new Set(["mean", "std", "min", "max"]);
const VIBRATION: Record<string, string> = {
  Horizontal_vibration_signals: "수평 진동",
  Vertical_vibration_signals: "수직 진동",
};

/** The signal a model feature summarizes: a window statistic's channel, else the feature itself. */
export function signalOf(feature: string): string {
  if (feature.startsWith("feature.")) {
    const rest = feature.slice("feature.".length);
    const cut = rest.lastIndexOf(".");
    return cut > 0 ? VIBRATION[rest.slice(0, cut)] ?? rest.slice(0, cut) : feature;
  }
  const cut = feature.lastIndexOf(".");
  return cut > 0 && STATS.has(feature.slice(cut + 1)) ? feature.slice(0, cut) : feature;
}

/** A signal, its percent of what raised the score, and its feature that raised it most. */
export type Raiser = {signal: string; share: number; feature: string};

function parts(raw: unknown): [string, number][] {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  return Object.entries(raw).filter((entry): entry is [string, number] =>
    typeof entry[1] === "number" && Number.isFinite(entry[1]) && entry[1] > 0);
}

/** Signals whose features raised the score, largest first. Several results add their parts first. */
export function scoreRaisers(raw: unknown | unknown[], limit = 3): Raiser[] {
  const totals = new Map<string, {sum: number; feature: string; top: number}>();
  for (const output of Array.isArray(raw) ? raw : [raw])
    for (const [feature, value] of parts(output)) {
      const signal = signalOf(feature);
      const held = totals.get(signal) ?? {sum: 0, feature, top: 0};
      held.sum += value;
      if (value > held.top) Object.assign(held, {top: value, feature});
      totals.set(signal, held);
    }
  const whole = [...totals.values()].reduce((sum, item) => sum + item.sum, 0);
  if (!(whole > 0)) return [];
  return [...totals.entries()].sort((a, b) => b[1].sum - a[1].sum).slice(0, limit)
    .map(([signal, item]) => ({signal, share: Math.round(100 * item.sum / whole), feature: item.feature}));
}

/** "R상역률 52% · R상전압 21%", or "" when the model gives no parts. */
export function raisersText(raisers: Raiser[], name: (signal: string) => string = (signal) => signal): string {
  return raisers.map((item) => name(item.signal) + " " + item.share + "%").join(" · ");
}
