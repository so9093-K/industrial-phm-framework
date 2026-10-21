/** What a person needs in one place to judge a model result under review: since when it has
 * been over the threshold, how much the measurements changed, what the AI said about it and how
 * the other models on the same input read it. Each part is read on its own; one that cannot be
 * read is left out, never filled with another result's facts. */
import {
  loadModelBindings, loadModelPosition, modelNames, scoreSummary,
  type ModelRun, type ScoreSummary,
} from "./model-evidence.ts";
import {beforeInterval, exceedanceStory, exceedanceText, readScoreTrend, type ScoreTrend} from "./model-trend.ts";
import {readComparison} from "./model-comparison.ts";
import {readModelExplanations, type FeatureChange} from "./model-explanations.ts";

export type ReviewEvidence = {
  unread: ("flow" | "changes" | "ai" | "others")[];
  name: string; at: string; eventStart: string | null; score: ScoreSummary;
  /** 언제부터: the run still going on, or the latest crossing, in the score trend's words. */
  flow: {headline: string; earlier: string | null} | null;
  /** 얼마나: the largest stored changes against the measurement compared with. */
  changes: {against: string; rows: FeatureChange[]} | null;
  /** The latest AI explanation of this result, and whether the AI wrote it. */
  ai: {summary: string; byAi: boolean} | null;
  /** 다른 모델: each other model on the same input at the same measurement. */
  others: {name: string; score: ScoreSummary}[];
};

/** Match the complete stored input identity, as the server does for related models. */
export function sameInputReference(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right))
    return left.length === right.length && left.every((value, i) => sameInputReference(value, right[i]));
  if (left && right && typeof left === "object" && typeof right === "object"
    && !Array.isArray(left) && !Array.isArray(right)) {
    const a = left as Record<string, unknown>, b = right as Record<string, unknown>;
    return Object.keys(a).length === Object.keys(b).length
      && Object.keys(a).every(key => Object.hasOwn(b, key) && sameInputReference(a[key], b[key]));
  }
  return false;
}

/** The features that changed most, by size of the relative change; unchanged or unknown last. */
export function largestChanges(features: FeatureChange[], count = 3): FeatureChange[] {
  return features.filter((row) => row.relativePercent !== null && row.previous !== null)
    .sort((a, b) => Math.abs(b.relativePercent!) - Math.abs(a.relativePercent!)).slice(0, count);
}

/** The trend as it stood at one measurement: later points dropped, and a run that held that
 * measurement read as going on then, with the crossings counted up to it. */
export function asOf(trend: ScoreTrend, position: number, minimum = Infinity): ScoreTrend {
  const points = trend.points.filter((point) => point.pointer.position <= position);
  const over = (start: number) => points.filter((point) => point.pointer.position >= start && point.exceeds === true).length;
  return {...trend, points, intervals: trend.intervals.filter((run) => run.start <= position
    && (run.end <= position || over(run.start) >= minimum)).map((run) =>
    run.end >= position ? {...run, end: position, open: true, steps: over(run.start)} : {...run, open: false})};
}

export async function readReviewEvidence(
  assetId: string, location: {bindingId: string; position: number}, signal: AbortSignal,
): Promise<ReviewEvidence | null> {
  const bindings = await loadModelBindings(assetId, signal);
  const binding = bindings.find((item) => item.bindingId === location.bindingId);
  if (!binding) return null;
  const names = modelNames(bindings);
  const place = (position: number) => (binding.stepKind === "observation-window" ? "시간 구간 #" : "측정 순서 #") + position;
  const run = await loadModelPosition(binding, location.position, signal);
  const unread: ReviewEvidence["unread"] = [];
  const quiet = <T,>(part: ReviewEvidence["unread"][number], read: Promise<T>): Promise<T | null> =>
    read.catch(() => { if (!unread.includes(part)) unread.push(part); return null; });
  const [trend, explanations, others] = await Promise.all([
    quiet("flow", readScoreTrend(binding, signal)),
    quiet("ai", readModelExplanations(binding, run, signal)),
    Promise.all(bindings.filter((other) => other.bindingId !== binding.bindingId && other.sourceId === binding.sourceId
      && other.stepKind === binding.stepKind && other.pointId === binding.pointId)
      .map((other) => quiet("others", loadModelPosition(other, location.position, signal)).then((found: ModelRun | null) => {
        if (!found) return [];
        if (!sameInputReference(run.inputReference, found.inputReference)) {
          if (!unread.includes("others")) unread.push("others");
          return [];
        }
        return [{name: names.get(other.bindingId) ?? other.bindingId, score: scoreSummary(found.output)}];
      }))),
  ]);
  const historical = trend ? asOf(trend, location.position, binding.minimumIntervalSteps) : null;
  const story = historical ? exceedanceStory(historical) : null;
  const explained = explanations?.find((item) => item.status === "complete" && item.answer) ?? null;
  // Compare with what the explanation compared, else with the measurement before the run.
  const analyzed = historical?.points.filter((point) => point.score !== null).map((point) => point.pointer.position) ?? [];
  const against = explained?.comparePosition ?? (historical ? beforeInterval(historical.intervals, analyzed, location.position)
    ?? analyzed.filter((at) => at < location.position).at(-1) ?? null : null);
  const features = explained?.comparePosition === against && explained ? explained.features
    : against === null ? null : await quiet("changes", readComparison(binding, run, against, signal)).then((found) => found?.features ?? null);
  return {
    unread,
    name: names.get(binding.bindingId) ?? binding.bindingId, at: place(location.position), eventStart: run.eventStart,
    score: scoreSummary(run.output),
    flow: story ? exceedanceText(story, place) : null,
    changes: against !== null && features?.length ? {against: place(against), rows: largestChanges(features)} : null,
    ai: explained?.answer ? {summary: explained.answer.summary,
      byAi: !explained.answer.modelUnavailable && explained.answer.source !== "verified-comparison"} : null,
    others: others.flat(),
  };
}
