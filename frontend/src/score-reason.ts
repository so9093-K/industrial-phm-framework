/** Why one result went over its model's threshold: the signals that raised its score, each with the
 * value that raised it most and where that value sits against the model's reference period. */
import {against} from "./analysis-messages.ts";
import {readSignalNames, type SignalNames} from "./history.ts";
import {readComparison} from "./model-comparison.ts";
import type {ModelBinding, ModelRun} from "./model-evidence.ts";
import {scoreRaisers} from "./score-raisers.ts";

export type ReasonRow = {
  signal: string; name: string; share: number; feature: string; statistic: string;
  value: number | null; unit: string | null; learned: {low: number; high: number} | null;
};
export type ScoreReason = {rows: ReasonRow[]; rest: {signals: number; share: number} | null};
type Measured = {feature: string; label: string; current: number; unit?: string | null; learned?: {low: number; high: number} | null};

const SHOWN = 3;

/** The first three signals that raised the score and one line for the rest, or null without parts. */
export function scoreReason(contributions: unknown, measured: Measured[], names: SignalNames | null): ScoreReason | null {
  const every = scoreRaisers(contributions, Infinity);
  if (!every.length) return null;
  const rows = every.slice(0, SHOWN).map((raiser): ReasonRow => {
    const found = measured.find((item) => item.feature === raiser.feature);
    const named = names?.get(raiser.signal);
    const label = found?.label ?? raiser.feature;
    return {signal: raiser.signal, name: named?.label ?? raiser.signal, share: raiser.share, feature: raiser.feature,
      statistic: label.startsWith(raiser.signal + " ") ? label.slice(raiser.signal.length + 1) : label,
      value: found?.current ?? null, unit: named?.unit ?? found?.unit ?? null, learned: found?.learned ?? null};
  });
  const share = 100 - rows.reduce((sum, row) => sum + row.share, 0);
  return {rows, rest: every.length > rows.length && share > 0 ? {signals: every.length - rows.length, share} : null};
}

/** "표준편차 3.92 A · 기준 기간보다 높음 (0.122–1.22 A)" */
export function reasonValueText(row: ReasonRow, format: (value: number | null) => string): string {
  const unit = row.unit ? " " + row.unit : "";
  const value = row.statistic + " " + format(row.value) + unit;
  if (!row.learned || row.value === null) return value;
  const span = "(" + format(row.learned.low) + "–" + format(row.learned.high) + unit + ")";
  const where = {above: "기준 기간보다 높음", below: "기준 기간보다 낮음", inside: "기준 기간 범위 안"}[against(row.value, row.learned)];
  return value + " · " + where + " " + span;
}

/** Read the selected result's values and the model's reference ranges, then name what raised it. */
export async function readScoreReason(binding: ModelBinding, run: ModelRun, signal: AbortSignal): Promise<ScoreReason | null> {
  if (!scoreRaisers(run.output.feature_contributions).length) return null;
  const [comparison, names] = await Promise.all([readComparison(binding, run, null, signal),
    binding.stepKind === "history-window" ? readSignalNames(binding.assetId) : Promise.resolve(null)]);
  return scoreReason(run.output.feature_contributions, comparison.features, names);
}
