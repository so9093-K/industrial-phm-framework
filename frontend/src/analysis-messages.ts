/** The message an analysis screen leads with: what changed, how plain that is, and what to look at
 * next. Every sentence is built from numbers the screen already shows; nothing is fitted or
 * guessed, and no sentence names a cause or a fault. */
import {worseThanPersistence} from "./forecast-fit.ts";
import type {BandShare} from "./spectrum.ts";
import type {RatioLine} from "./model-trend.ts";
import {elapsedText} from "./time-axis.ts";
import type {FeatureChange} from "./model-explanations.ts";

export type NextStep = {label: string; href: string};
export type AnalysisMessage = {
  /** What changed, in one or two sentences. */
  headline: string;
  /** What the change means when the numbers alone would mislead, such as a formula link. */
  meaning: string | null;
  /** How plain the change is: amount of data, agreement between methods, chance. */
  certainty: string | null;
  next: NextStep[];
};

/** Explain the server's verdict for one selected model result without inventing a verdict
 * from the score, or treating a below-threshold result as evidence of a healthy asset. */
export function selectedScoreMessage(summary: {score: number | null; threshold: number | null; exceeds: boolean | null},
  next: NextStep[] = []): AnalysisMessage {
  const equalDisplay = summary.score !== null && summary.threshold !== null && summary.score !== summary.threshold
    && short(summary.score) === short(summary.threshold);
  const score = summary.score === null ? "" : equalDisplay ? String(summary.score) : short(summary.score);
  const threshold = summary.threshold === null ? "" : equalDisplay ? String(summary.threshold) : short(summary.threshold);
  const numbers = summary.score === null ? "이 측정의 모델 점수가 기록되지 않았습니다."
    : "이 측정의 모델 점수는 " + score
      + (summary.threshold === null ? "이며, 비교 기준값은 기록되지 않았습니다." : ", 모델 기준은 " + threshold + "입니다.");
  const judged = summary.score !== null && summary.threshold !== null && summary.exceeds !== null;
  return {
    headline: judged ? "선택한 측정이 이 모델의 기준을 " + (summary.exceeds ? "넘었습니다." : "넘지 않았습니다.") : "이 측정의 기준 초과 여부를 확인할 수 없습니다.",
    meaning: numbers,
    certainty: judged && summary.exceeds
      ? "같은 측정의 원본 값과 앞선 측정의 차이를 함께 확인하세요."
      : judged ? null : "점수·비교 기준·판정 기록이 부족합니다.",
    next,
  };
}

/** A value as people read it in a sentence: three significant digits. */
export function short(value: number): string {
  return value.toLocaleString("ko-KR", {maximumSignificantDigits: 3});
}
/** A ratio as "3.6배": whole from ten up, two decimals near 1 so 0.97 never reads as 1. */
export function times(ratio: number): string {
  const text = ratio >= 10 ? Math.round(ratio).toLocaleString("ko-KR") : ratio >= 1.1 ? ratio.toFixed(1)
    : ratio >= 0.1 ? String(Number(ratio.toFixed(2))) : ratio.toLocaleString("ko-KR", {maximumSignificantDigits: 2});
  return text + "배";
}
const percent = (share: number) => Math.round(share * 100) + "%";
/** A share of counted measurements as a percentage that is neither inflated nor read as all or
 * none unless it is: 1–99% rounds to a whole percent, otherwise to one decimal, and a share below
 * 0.1% or above 99.9% is said as that bound ("0.1% 미만", "99.9% 초과") instead of rounded to it. */
export function countShare(part: number, whole: number): string {
  if (whole <= 0 || part <= 0) return "0%";
  if (part >= whole) return "100%";
  const share = 100 * part / whole;
  if (share < 0.1) return "0.1% 미만";
  if (share > 99.9) return "99.9% 초과";
  if (share >= 1 && share <= 99) return Math.round(share) + "%";
  return (Math.round(share * 10) / 10).toFixed(1) + "%";
}
const hz = (value: number) => Math.round(value).toLocaleString("ko-KR");

export type PeriodFacts = {
  unit: string | null;
  a: {usable: number; median: number | null; low: number | null; high: number | null};
  b: {usable: number; median: number | null};
  /** B values outside A's 5–95% range, as a count and a percent of B's usable values. */
  outsideCount: number | null; outsidePercent: number | null;
  /** B's median over A's as a percent change, only for a positive magnitude. */
  medianChangePercent: number | null;
  /** From the measurement-by-measurement record, when every value is there. */
  onset: {first: number; stayed: boolean} | null;
};

/** Where period B first leaves A's usual range, read from every stored value of the feature. */
export function periodOnset(points: {ordinal: number; value: number}[], b: {from: number; to: number},
  low: number, high: number): {first: number; stayed: boolean} | null {
  const inside = points.filter((p) => b.from <= p.ordinal && p.ordinal <= b.to);
  const index = inside.findIndex((p) => p.value < low || p.value > high);
  if (index < 0) return null;
  return {first: inside[index].ordinal, stayed: inside.slice(index).every((p) => p.value < low || p.value > high)};
}

export function periodMessage(facts: PeriodFacts, place: (ordinal: number) => string,
  next: NextStep[] = []): AnalysisMessage | null {
  const {a, b} = facts;
  if (a.median === null || b.median === null) return null;
  const unit = facts.unit ? " " + facts.unit : "";
  const range = a.low !== null && a.high !== null ? short(a.low) + "~" + short(a.high) + unit : null;
  const ratio = facts.medianChangePercent !== null ? 1 + facts.medianChangePercent / 100 : null;
  const medians = "중앙값은 " + short(a.median) + " → " + short(b.median) + unit
    + (ratio !== null && ratio >= 0 && ratio <= 1 / 1.5 ? "로 약 " + short(100 * (1 - ratio)) + "% 낮아졌습니다."
      : ratio !== null && ratio >= 1.5 ? "로 약 " + times(ratio) + "입니다." : "입니다.");
  const share = facts.outsidePercent;
  const count = facts.outsideCount ?? (share === null ? null : Math.round(share * b.usable / 100));
  // "모두" only when every usable measurement is outside; otherwise the count itself, and a
  // percentage that never rounds 99.5% up to 100% or 0.4% down to 0%.
  const all = count !== null && b.usable > 0 && count === b.usable;
  const pct = share === null ? "" : count !== null ? countShare(count, b.usable) : Math.round(share) + "%";
  let headline: string;
  if (share === null || range === null) headline = "기간 A와 B의 " + medians;
  else if (all) headline = "기간 B의 측정 " + b.usable + "회가 모두 기간 A의 평소 범위(" + range + ")를 벗어났습니다. " + medians;
  else if (share >= 50) headline = (share === 50 ? "기간 B 측정의 절반(" + count + "회)이"
    : "기간 B 측정 " + b.usable + "회 중 " + count + "회(" + pct + ")가") + " 기간 A의 평소 범위(" + range + ")를 벗어났습니다. " + medians;
  else if (share > 10) headline = "기간 B 측정의 일부(" + pct + ", " + count + "회)만 기간 A의 평소 범위(" + range + ")를 벗어났습니다. " + medians;
  else headline = "기간 B의 값은 대부분 기간 A의 평소 범위(" + range + ") 안에 있습니다. " + medians;
  let certainty: string | null = null;
  if (b.usable < 5 || a.usable < 10)
    certainty = "측정 수가 적어(기간 A " + a.usable + "회 · 기간 B " + b.usable + "회) 이 결과만으로 단정하기 이릅니다.";
  else if (share === null) certainty = null;
  else if (share >= 90) certainty = "값 몇 개가 튄 것이 아니라 거의 모든 측정이 벗어나, 값의 수준 자체가 달라졌습니다.";
  else if (share >= 50) certainty = (share > 50 ? "절반 넘게" : "절반이") + " 벗어났지만 평소 범위 안의 값도 남아 있습니다. 기간 B 안에서 언제부터 달라졌는지 함께 보세요.";
  else if (share > 10) certainty = "기간 B 측정 중 일부만 벗어났습니다. 벗어난 측정이 한 시기에 몰려 있는지 흩어져 있는지 시간 추이에서 확인하세요.";
  else certainty = "기간 A 안에서도 값의 10%는 이 범위 밖에 있으므로, 이 정도는 뚜렷한 변화로 보기 어렵습니다.";
  const onset = facts.onset && share !== null && share > 10
    ? place(facts.onset.first) + "에서 처음 평소 범위를 벗어났고"
      + (facts.onset.stayed ? " 그 뒤 기간 B의 측정도 모두 평소 범위 밖입니다." : " 그 뒤 기간 B의 측정 중 일부는 평소 범위 안으로 돌아왔습니다.")
    : null;
  return {headline, meaning: onset, certainty, next};
}

type Tie = {kind: "same" | "opposite"; strong: boolean} | {kind: "none" | "unclear"};
export type RelationSide = {pearson: number | null; spearman: number | null; pairs: number};

/** What a pair's coefficients say together; disagreeing signs mean a few points decide it. */
export function tie(side: RelationSide): Tie | null {
  const {pearson: p, spearman: s} = side;
  if (p === null || side.pairs < 3) return null;
  if (Math.abs(p) < 0.3 && (s === null || Math.abs(s) < 0.3)) return {kind: "none"};
  if (s !== null && Math.sign(p) !== Math.sign(s) && Math.max(Math.abs(p), Math.abs(s)) >= 0.3) return {kind: "unclear"};
  return {kind: p > 0 ? "same" : "opposite", strong: Math.abs(p) >= 0.7};
}
const way = (t: Tie) => t.kind === "same" || t.kind === "opposite"
  ? (t.kind === "same" ? "같은 방향으로 " : "반대 방향으로 ") + (t.strong ? "강하게" : "어느 정도") + " 함께 움직" : null;
const was = (t: Tie) => way(t) ? way(t) + "였고" : t.kind === "none" ? "뚜렷한 관계가 없었고" : "관계가 분명하지 않았고";
const is = (t: Tie) => way(t) ? way(t) + "입니다" : t.kind === "none" ? "뚜렷한 관계가 없습니다" : "관계가 분명하지 않습니다";
function coefficients(side: RelationSide, t: Tie): string {
  return "피어슨 " + side.pearson!.toFixed(2) + (t.kind === "unclear" && side.spearman !== null ? " · 스피어먼 " + side.spearman.toFixed(2) : "");
}

/** How far apart the two periods' Pearson coefficients are, described and not tested: consecutive
 * measurements are not independent pairs, so no sample-size test is offered as a verdict. */
export function coefficientSpread(a: RelationSide, b: RelationSide): "large" | "moderate" | "small" | null {
  if (a.pearson === null || b.pearson === null) return null;
  const gap = Math.abs(a.pearson - b.pearson);
  return gap >= 0.5 ? "large" : gap >= 0.2 ? "moderate" : "small";
}
const SPREAD_TEXT = {large: "크게", moderate: "어느 정도", small: "조금만"} as const;

/** Pairs of vibration features that move together because one is computed from the other. */
export function formulaLink(x: string, y: string): "crest" | "crest-rms" | "rms-std" | "peaks" | null {
  const part = (id: string) => { const m = /^feature\.(.+)\.([a-z_]+)$/.exec(id); return m ? {channel: m[1], stat: m[2]} : null; };
  const p = part(x), q = part(y);
  if (!p || !q || p.channel !== q.channel) return null;
  const pair = new Set([p.stat, q.stat]);
  const both = (one: string, two: string) => pair.has(one) && pair.has(two);
  if (both("crest_factor", "absolute_peak")) return "crest";
  if (both("crest_factor", "rms")) return "crest-rms";
  if (both("rms", "standard_deviation")) return "rms-std";
  if (both("absolute_peak", "peak_to_peak")) return "peaks";
  return null;
}

export function middle(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((p, q) => p - q), mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** What y did at the same x, as sentences: how many compared ranges moved, and the best supported
 * one with both medians and A's middle 50%. */
export function sameXText(moved: {shown: {low: number; high: number; a: {median: number; q1: number; q3: number}; b: {median: number}};
  outside: number; total: number}, x: {name: string; unit: string | null}, y: {name: string; unit: string | null}): string {
  const unit = (value: string, of: string | null) => value + (of ? " " + of : "");
  const {shown, outside, total} = moved;
  const where = unit(short(shown.low) + "~" + short(shown.high), x.unit);
  const values = short(shown.a.median) + " → " + unit(short(shown.b.median), y.unit);
  const usual = unit(short(shown.a.q1) + "~" + short(shown.a.q3), y.unit);
  if (outside === total && total > 1)
    return "같은 " + x.name + "끼리 견준 범위 " + total + "개 모두에서 기간 B의 " + y.name + " 중앙값이 기간 A의 가운데 50% 밖입니다. "
      + "짝이 가장 많은 " + where + "에서는 " + values + "입니다(기간 A 가운데 50% " + usual + ").";
  return "같은 " + x.name + " " + where + "에서 " + y.name + " 중앙값은 " + values + "로, 기간 A의 가운데 50%(" + usual + ") 밖입니다"
    + (total > 1 ? "(견준 범위 " + total + "개 중 " + outside + "개에서 밖)." : ".");
}

export function relationMessage(x: string, y: string, a: RelationSide, b: RelationSide,
  crest: {a: number | null; b: number | null} | null, next: NextStep[] = [], sameX: string | null = null): AnalysisMessage | null {
  const ta = tie(a), tb = tie(b);
  if (!ta && !tb) return null;
  let headline: string;
  if (!ta || !tb) {
    const [name, side, t] = ta ? ["A", a, ta] as const : ["B", b, tb!] as const;
    headline = "기간 " + name + "에서 두 값은 " + is(t) + " (" + coefficients(side, t) + "). 다른 기간은 짝이 부족해 계산하지 못했습니다.";
  } else {
    // Two coefficients both too small to call a relation are no change of one, however far apart.
    const neither = ta.kind === "none" && tb.kind === "none";
    const kept = neither || ta.kind === tb.kind
      && (!("strong" in ta) || !("strong" in tb) || ta.strong === tb.strong) && Math.abs(a.pearson! - b.pearson!) < 0.2;
    // Moving together as strongly says nothing of where y sits at the same x; a shift there is
    // a change of the relation the coefficients cannot show.
    headline = kept
      ? "두 기간 모두 두 값은 " + is(tb) + " (기간 A " + coefficients(a, ta) + " · 기간 B " + coefficients(b, tb) + ")."
        + (sameX ? " 다만 " + sameX : neither ? "" : " 관계는 그대로입니다.")
      : "두 값의 관계가 달라졌습니다. 기간 A에서는 " + was(ta) + "(" + coefficients(a, ta) + "), 기간 B에서는 " + is(tb)
        + "(" + coefficients(b, tb) + ")." + (sameX ? " " + sameX : "");
  }
  const link = formulaLink(x, y);
  let meaning: string | null = null;
  if (link === "crest" || link === "crest-rms") {
    meaning = link === "crest"
      ? "파고율은 절대 피크를 RMS로 나눈 값이라 두 값은 계산식으로 묶여 있습니다. RMS가 거의 그대로일 때는 피크가 클수록 파고율도 커지고, RMS가 피크보다 더 크게 늘면 파고율은 작아집니다."
      : "파고율은 절대 피크를 RMS로 나눈 값이라, 피크가 그대로일 때 RMS가 커지면 파고율은 작아집니다.";
    if (crest?.a && crest.b && Math.abs(crest.b / crest.a - 1) >= 0.1)
      meaning += " 파고율 중앙값은 " + short(crest.a) + " → " + short(crest.b) + (crest.b < crest.a
        ? "로 낮아졌습니다. 가끔 튀는 진동보다 진동 전체가 커지는 쪽으로 바뀌었다는 뜻입니다."
        : "로 높아졌습니다. 진동 전체보다 순간적으로 튀는 값이 더 커졌다는 뜻입니다.");
  } else if (link === "rms-std") {
    meaning = "진동처럼 평균이 0에 가까운 값에서는 RMS와 표준편차가 거의 같은 값입니다. 함께 움직이는 것은 계산상 당연하므로 서로 다른 근거로 세지 마세요.";
  } else if (link === "peaks") {
    meaning = "피크-피크는 가장 큰 값과 가장 작은 값의 차이라 절대 피크와 대부분 같은 정보를 담습니다. 서로 다른 근거로 세지 마세요.";
  }
  const sides = [{name: "A", side: a, t: ta}, {name: "B", side: b, t: tb}];
  const few = sides.filter(({side}) => side.pairs < 10).map(({name, side}) => "기간 " + name + "는 짝이 " + side.pairs + "개뿐");
  const unclear = sides.filter(({t}) => t?.kind === "unclear").map(({name}) => name);
  const spread = ta && tb ? coefficientSpread(a, b) : null;
  // Consecutive measurements resemble their neighbours, which can make a coefficient look stronger
  // than the pairs alone would; the reader is pointed at the scatter instead of a test.
  const caution = "연속된 측정은 이웃한 값끼리 비슷해 계수가 실제보다 강하게 나올 수 있으니, 시간상 이웃한 측정과 산점도에서 떨어진 점을 함께 확인하세요.";
  let certainty: string | null = null;
  if (few.length) certainty = few.join(" · ") + "이라 계수가 크게 흔들릴 수 있습니다.";
  else if (unclear.length)
    certainty = "기간 " + unclear.join("·") + "에서는 피어슨과 스피어먼이 서로 다른 방향을 가리켜, 몇몇 측정이 관계를 좌우하고 있을 수 있습니다. 산점도에서 떨어진 점을 확인하세요.";
  else if (spread !== null)
    certainty = "두 기간의 피어슨 계수는 " + SPREAD_TEXT[spread] + " 다릅니다(" + a.pearson!.toFixed(2) + " → " + b.pearson!.toFixed(2) + "). " + caution;
  return {headline, meaning, certainty, next};
}

export type SpectrumFacts = {label: string; ratio: number | null; shares: BandShare[]};

/** The band whose share of the energy grew most, if any grew by ten points or more. */
export function shiftedBand(shares: BandShare[]): BandShare | null {
  const best = shares.reduce<BandShare | null>((top, band) => !top || band.b - band.a > top.b - top.a ? band : top, null);
  return best && best.b - best.a >= 0.1 ? best : null;
}

/** How much of the energy moved between bands, all bands together: half the summed share changes.
 * Several bands can each move a little and still move much of the energy between them. */
export function movedShare(shares: BandShare[]): number {
  return shares.reduce((sum, band) => sum + Math.abs(band.b - band.a), 0) / 2;
}

export function spectrumMessage(channels: SpectrumFacts[], used: {a: number; b: number},
  next: NextStep[] = []): AnalysisMessage | null {
  const [main, ...others] = channels;
  if (!main || main.ratio === null) return null;
  const energy = main.ratio >= 1.25 ? "기간 A의 " + times(main.ratio) + "가 됐고"
    : main.ratio <= 0.8 ? "기간 A의 " + times(main.ratio) + "로 줄었고" : "기간 A와 비슷하고(" + times(main.ratio) + ")";
  const band = shiftedBand(main.shares);
  const headline = "기간 B의 " + main.label + " 에너지는 " + energy + ", "
    + (band ? hz(band.from) + "~" + hz(band.to) + " Hz가 전체 에너지에서 차지하는 비중이 " + percent(band.a) + " → " + percent(band.b) + "로 커졌습니다."
      : "비중이 10%p 이상 커진 대역은 없고, 대역 사이에 옮겨 간 에너지 비중은 모두 합쳐 전체의 " + percent(movedShare(main.shares)) + "입니다.");
  const notes: string[] = [];
  for (const other of others) {
    const moved = shiftedBand(other.shares);
    if (!band) continue;
    if (moved && moved.from <= band.to && band.from <= moved.to)
      notes.push(other.label + "에서도 같은 대역 비중이 " + percent(moved.a) + " → " + percent(moved.b) + "로 커져, 두 방향이 같은 변화를 보입니다.");
    else if (moved)
      notes.push(other.label + "에서는 비중이 커진 대역이 달라(" + hz(moved.from) + "~" + hz(moved.to) + " Hz) 한 방향에서만 보이는 변화일 수 있습니다.");
    else notes.push(other.label + "에서는 비중이 10%p 이상 커진 대역이 없어(옮겨 간 비중 전체의 " + percent(movedShare(other.shares))
      + ") 한 방향에서만 보이는 변화일 수 있습니다.");
  }
  notes.push(Math.min(used.a, used.b) < 3
    ? "기간마다 측정 " + Math.min(used.a, used.b) + "회만 비교해 우연일 수 있습니다."
    : "각 기간에서 고르게 고른 측정 " + used.a + "회·" + used.b + "회의 평균입니다.");
  return {headline, meaning: null, certainty: notes.join(" "), next};
}

export type ModelRead = {name: string; line: RatioLine};

/** One model's crossings as observed: where and how many, and how its last analyzed measurement
 * stands. No word for a kind of run ("continuous", "one-off") is used: the run rule tolerates
 * measurements below the threshold, so such words would say more, or other, than was seen. */
function modelState(read: ModelRead, place: (position: number) => string): string {
  const {name, line} = read, story = line.story;
  const top = line.points.length ? times(Math.max(...line.points.map((p) => p.ratio))) : null;
  const latest = line.latest ? place(line.latest.position) : null;
  const before = story.earlierCount
    ? "그 전에도 " + story.earlierCount + "회" + (story.first && story.anchor && story.first.pointer.position < story.anchor.pointer.position
      ? ", 처음 " + place(story.first.pointer.position) : "")
    : "그 전에는 기준을 넘은 측정 없음";
  if (story.state === "ongoing" && story.ongoing)
    return name + " 점수는 " + place(story.ongoing.start) + " 이후 기준을 " + story.ongoing.steps + "회 넘었고, 마지막으로 분석한 "
      + (latest ?? "측정") + "은 기준 " + (story.lastExceeds === false ? "이하" : "초과") + "입니다(" + before
      + (top ? ", 가장 높을 때 기준의 " + top : "") + ")";
  if (story.state === "latest" && story.anchor)
    return name + " 점수는 마지막으로 분석한 " + place(story.anchor.pointer.position) + "에서 기준을 넘었습니다(" + before + ")";
  if (story.state === "below" && story.anchor)
    return name + " 점수는 마지막으로 분석한 " + (latest ?? "측정") + "에서 기준 이하입니다(그 전 기준 초과 " + (story.earlierCount + 1)
      + "회, 마지막 " + place(story.anchor.pointer.position) + ")";
  return name + " 점수는 분석한 " + line.analyzed + "회 중 기준을 넘은 측정이 없습니다" + (top ? "(가장 높을 때 기준의 " + top + ")" : "");
}

/** Where the models' crossings start, so the next look goes to that measurement. */
export function modelOnset(reads: ModelRead[]): number | null {
  const starts = reads.flatMap((read) => read.line.story.state === "ongoing" && read.line.story.ongoing
    ? [read.line.story.ongoing.start] : read.line.story.anchor ? [read.line.story.anchor.pointer.position] : []);
  return starts.length ? Math.min(...starts) : null;
}

export function modelMessage(reads: ModelRead[], place: (position: number) => string,
  next: NextStep[] = []): AnalysisMessage | null {
  const drawn = reads.filter((read) => read.line.points.length);
  if (!drawn.length) return null;
  const states = drawn.map((read) => modelState(read, place));
  // "Now" is the latest analyzed measurement only. A run the model still holds open within its
  // allowed gap can end on a measurement below the threshold; that is told per model, not as now.
  // Each model's trend is read on its own, so their last analyzed measurements can differ; only
  // the same measurement lets "the latest" be compared across models.
  const lasts = drawn.map((read) => read.line.latest?.position ?? null);
  const aligned = lasts.every((position) => position !== null && position === lasts[0]);
  const now = drawn.filter((read) => read.line.story.lastExceeds === true);
  const crossed = drawn.filter((read) => read.line.story.state !== "none");
  const lead = drawn.length === 1 ? ""
    : !aligned ? "모델마다 마지막으로 분석한 측정이 달라("
      + drawn.map((read) => read.name + " " + (read.line.latest ? place(read.line.latest.position) : "분석 없음")).join(", ")
      + ") 같은 최근 측정에서 견줄 수 없습니다. 각 모델의 마지막 분석 기준으로 보면 "
    : !now.length ? "최근 측정에서 기준을 넘은 모델은 없습니다. "
    : now.length === drawn.length ? "모든 모델이 최근 측정에서 기준을 넘고 있습니다. "
    : "같은 최근 측정에서 모델마다 판단이 다릅니다. ";
  const headline = lead + states.join(", ") + ".";
  let certainty: string;
  if (drawn.length === 1) certainty = "모델 하나의 결과이므로 같은 시점에 측정값도 달라졌는지 함께 보세요.";
  else if (!aligned)
    certainty = "뒤쪽 측정을 아직 분석하지 않은 모델이 있을 수 있습니다. 같은 측정에서의 판단은 그래프에서 같은 측정 위치의 점수로 견줘 보세요.";
  else if (now.length && now.length < drawn.length)
    certainty = "최근 측정에서 일부 모델만 기준을 넘어 이 결과만으로는 어느 쪽이 맞는지 알 수 없습니다. 같은 시점에 측정값도 달라졌는지 확인하세요.";
  else if (now.length) {
    const starts = now.map((read) => read.line.story.ongoing?.start ?? read.line.story.anchor!.pointer.position);
    certainty = Math.max(...starts) - Math.min(...starts) <= 3
      ? "서로 다른 모델이 같은 무렵(" + place(Math.min(...starts)) + ")부터 기준을 넘어, 한 모델만의 반응이 아닙니다."
      : "모델마다 기준을 넘기 시작한 때가 달라, 먼저 반응한 " + place(Math.min(...starts)) + "부터 확인하세요.";
  } else if (crossed.length)
    certainty = "최근 측정은 모든 모델에서 기준 아래지만, 그 전에 기준을 넘은 구간이 있습니다. 그 구간의 측정값도 함께 보세요.";
  else certainty = "모델 기준 아래라도 측정값 자체가 달라졌는지는 따로 확인하세요.";
  return {headline, meaning: null, certainty, next};
}

export type OutlookReach = {state: string; expected: number | null; earliest: number | null; latest: number | null};
export type OutlookFacts = {
  /** Reaches count added measurements, or seconds after the last record. */
  axis: "acquisition" | "time";
  /** Seconds per measurement, recorded or assumed, so measurement counts can read as time. */
  period: number | null;
  unit: string | null;
  conditions: {management: number | null; end: number | null};
  scenarios: {id: string; management: OutlookReach | null; end: OutlookReach | null}[];
  /** The latest backtest first: hidden points, mean errors and the share inside the band. */
  checks: {points: number; error: number; naive: number; coverage: number}[];
};

function span(lo: number, hi: number, facts: OutlookFacts): string {
  const time = (steps: number) => elapsedText(facts.axis === "time" ? steps : steps * facts.period!);
  if (facts.axis === "time") return lo === hi ? "약 " + time(lo) : "약 " + time(lo) + "~" + time(hi);
  const count = "추가 측정 " + (lo === hi ? lo : lo + "~" + hi) + "회";
  return facts.period === null ? count : count + "(약 " + (lo === hi ? time(lo) : time(lo) + "~" + time(hi)) + ")";
}

/** How far each limit is across every reading of the trend, and how much past checks allow trusting it. */
export function outlookMessage(facts: OutlookFacts, next: NextStep[] = []): AnalysisMessage | null {
  const unit = facts.unit ? " " + facts.unit : "";
  // What the record already shows comes first and is not an assumption; the first reach carries it.
  const parts: string[] = [], already: string[] = [];
  let spread = false;
  for (const name of ["management", "end"] as const) {
    const limit = facts.conditions[name];
    if (limit === null || !facts.scenarios.length) continue;
    const label = (name === "end" ? "종료 기준 " : "관리 기준 ") + short(limit) + unit;
    const reaches = facts.scenarios.map((scenario) => scenario[name]);
    if (reaches.some((reach) => reach?.state === "already")) { already.push("마지막 측정이 이미 " + label + "에 닿았습니다."); continue; }
    const steps = reaches.flatMap((reach) => reach?.state === "expected" && reach.expected !== null ? [reach.expected] : []);
    // The central forecast missing a limit is not "never": the band alone may still reach it.
    const banded = reaches.filter((reach) => reach?.state === "possible");
    const earliest = banded.flatMap((reach) => reach!.earliest !== null ? [reach!.earliest] : []);
    // Each method has its own earliest band reach and the tiles show one of them, so the
    // sentence gives the spread over methods; the first alone contradicted the tile.
    const first = Math.min(...earliest), last = Math.max(...earliest);
    const bandText = earliest.length
      ? (earliest.length > 1 ? "계산 방식에 따라 " : "") + "빠르면 " + span(first, last, facts) + " 뒤 " : "";
    if (!steps.length) {
      parts.push(banded.length
        ? label + "에는 중심 예측으로는 계산한 범위 안에서 닿지 않지만, 예측 범위로는 " + bandText + "닿을 수 있습니다"
          + (banded.length < reaches.length ? "(계산 방식 " + reaches.length + "가지 중 " + banded.length + "가지)." : ".")
        : label + "에는 계산한 범위 안에서 닿지 않습니다.");
      if (earliest.length && first > 0 && last / first >= 2) spread = true;
      continue;
    }
    const lo = Math.min(...steps), hi = Math.max(...steps);
    const rest = steps.length < reaches.length
      ? "(계산 방식 " + reaches.length + "가지 중 " + steps.length + "가지에서 중심 예측이 닿음"
        + (banded.length ? ", " + banded.length + "가지는 예측 범위로만 닿을 수 있음" : "") + ")."
      : ".";
    parts.push(label + "까지 " + span(lo, hi, facts) + " 남았습니다" + rest);
    if (lo > 0 && hi / lo >= 2) spread = true;
  }
  if (!parts.length && !already.length) return null;
  const headline = [...already, ...parts.map((part, i) => i ? part : "기록 마지막 시점의 추세가 이어진다고 가정하면 " + part)].join(" ");
  const check = facts.checks[0];
  let certainty: string;
  if (!check) certainty = "기록이 짧아 과거 자료로 예측을 확인하지 못했습니다. 도달 시점은 대략의 범위로 읽으세요.";
  else {
    const versus = check.error < 0.8 * check.naive ? "마지막 값을 그대로 이어 쓴 것보다 오차가 작았습니다"
      : check.error > 1.2 * check.naive ? "마지막 값을 그대로 이어 쓴 것보다 오차가 컸습니다" : "마지막 값을 그대로 이어 쓴 것과 오차가 비슷했습니다";
    const weak = check.coverage < 0.5 || check.error >= 0.8 * check.naive || spread;
    const inside = countShare(Math.round(check.coverage * check.points), check.points);
    certainty = "기록의 마지막 " + check.points + "개를 가리고 같은 방법으로 예측해 보니 실제 값이 예측 범위 안에 든 비율은 "
      + inside + (inside.endsWith("미만") ? "이었고, " : "였고, ") + versus + ". "
      + (spread ? "계산 방식에 따라 도달 시점이 두 배 넘게 갈립니다. " : "")
      + (weak ? "도달 시점은 정확한 시각이 아니라 대략의 범위로 읽고, 새 측정이 들어올 때마다 다시 확인하세요."
        : "과거 확인에서는 예측이 실제 값을 대체로 따라갔습니다.");
  }
  return {headline, meaning: null, certainty, next};
}

/** Where a value sits against its usual range: above, below or inside. */
export function against(value: number, usual: {low: number; high: number}): "above" | "below" | "inside" {
  return value > usual.high ? "above" : value < usual.low ? "below" : "inside";
}
export const AGAINST_TEXT = {above: "평소보다 높음", below: "평소보다 낮음", inside: "평소 범위 안"} as const;

/** A vibration's standard deviation that carries its RMS's number at both results (mean about zero):
 * one fact under two names, so it is counted once, as the RMS. */
export function withoutTwins(features: FeatureChange[]): FeatureChange[] {
  const byId = new Map(features.map((feature) => [feature.feature, feature]));
  const same = (a: number | null, b: number | null) => a !== null && b !== null && a > 0 && Math.abs(a - b) <= 0.01 * a;
  return features.filter((feature) => {
    if (!feature.feature.endsWith(".standard_deviation")) return true;
    const rms = byId.get(feature.feature.replace(/\.standard_deviation$/, ".rms"));
    return !rms || !same(rms.current, feature.current) || !same(rms.previous, feature.previous);
  });
}

/** Against the middle 90% of the values the model was fitted on: outside it does not mean the model
 * never saw such a value, and no combination of features is checked. */
export const LEARNED_TEXT = {above: "학습값 5~95% 범위보다 높음", below: "학습값 5~95% 범위보다 낮음", inside: "학습값 5~95% 범위 안"} as const;

/** Two stored results of one model: how the score moved, whether the features left where this asset
 * usually sits, and whether they left the middle of the values the model was fitted on. A score over
 * its threshold on values the asset often shows but rarely in its reference period points first at
 * how that period was made up, before anything about the asset. */
export function comparisonMessage(score: {previous: number | null; current: number | null; exceeds?: boolean | null},
  features: FeatureChange[], usualUntil: number | null, place: (position: number) => string,
  next: NextStep[] = []): AnalysisMessage | null {
  const counted = withoutTwins(features), judged = counted.filter((feature) => feature.usual);
  if (score.current === null && !judged.length) return null;
  const ratio = score.previous !== null && score.current !== null && score.previous > 0 && score.current > 0
    ? score.current / score.previous : null;
  const moved = ratio !== null && (ratio >= 2 || ratio <= 0.5);
  const flagged = moved || score.exceeds === true;
  let headline = score.previous !== null && score.current !== null
    ? "이상 점수가 " + short(score.previous) + " → " + short(score.current)
      + (ratio !== null && (ratio >= 1.5 || ratio <= 1 / 1.5) ? "로 약 " + times(ratio) + "가 됐습니다" : "입니다")
      + (score.exceeds === true ? "(모델 기준 초과)." : ".")
    : "";
  // Farthest outside first, measured in the width of the range.
  const far = (value: number, range: {low: number; high: number}) => {
    const width = Math.max(range.high - range.low, Math.abs(range.high) * 1e-6, 1e-12);
    return Math.max(value - range.high, range.low - value) / width;
  };
  const outside = judged.filter((feature) => against(feature.current, feature.usual!) !== "inside")
    .sort((a, b) => far(b.current, b.usual!) - far(a.current, a.usual!));
  const unlearned = counted.filter((feature) => feature.learned && against(feature.current, feature.learned) !== "inside")
    .sort((a, b) => far(b.current, b.learned!) - far(a.current, a.learned!));
  const named = (list: FeatureChange[], text: (feature: FeatureChange) => string) =>
    list.slice(0, 3).map((feature) => feature.label + "(" + text(feature) + ")").join(", ")
      + (list.length > 3 ? " 외 " + (list.length - 3) + "개." : ".");
  if (!judged.length)
    headline += " 이전 기록이 짧아 특징값이 평소와 다른지는 아직 말할 수 없습니다.";
  else if (outside.length)
    headline += " 특징 " + judged.length + "개 중 " + outside.length + "개가 이 설비의 평소 범위를 벗어났습니다: "
      + named(outside, (feature) => AGAINST_TEXT[against(feature.current, feature.usual!)]);
  else {
    headline += " 특징값은 " + judged.length + "개 모두 이 설비의 평소 범위 안에 있습니다.";
    if (unlearned.length)
      headline += " 다만 " + unlearned.length + "개는 모델이 기준 기간에 학습한 값의 5~95% 범위를 벗어났습니다: "
        + named(unlearned, (feature) => LEARNED_TEXT[against(feature.current, feature.learned!)]);
  }
  let meaning: string | null = null;
  if (judged.length && !outside.length && unlearned.length && flagged)
    meaning = "이 설비에서는 흔한 값이지만, 모델이 기준 기간에 학습한 값의 5~95% 범위를 벗어났습니다. 점수가 오른 데에는 "
      + "기준 기간에 이런 값이 드물었던 점이 영향을 줬을 수 있습니다. 먼저 기준 기간의 운전 상태 구성과 이 측정의 운전 조건을 확인하세요. "
      + "기준 기간에 이 운전 상태가 빠져 있었다고 확인되면, 그때 이 상태를 포함한 기준 기간으로 모델을 다시 만드는 것을 검토할 수 있습니다.";
  else if (outside.length) {
    const top = outside[0], unit = top.unit ? " " + top.unit : "";
    meaning = "가장 멀리 벗어난 값은 " + top.label + " " + short(top.current) + unit + "이고, 평소 범위는 "
      + short(top.usual!.low) + "~" + short(top.usual!.high) + unit + "입니다.";
  } else if (judged.length && flagged)
    meaning = "점수는 크게 바뀌었지만 개별 특징값은 평소 범위 안입니다. 하나의 값보다 여러 값의 조합이 평소와 다를 때 점수가 바뀔 수 있으니, 같은 시각의 운전·측정 조건과 함께 보세요.";
  const results = judged[0]?.usual?.results ?? 0;
  const certainty = judged.length && usualUntil !== null
    ? "평소 범위는 비교 측정 이전에 이 모델이 분석한 " + results + "개 결과의 5~95% 값입니다."
      + (results < 50 ? " 기록이 짧아 평소 범위가 좁거나 넓게 잡혔을 수 있습니다." : "")
      + (counted.some((feature) => feature.learned)
        ? " 학습값 범위는 모델이 기준 기간에 학습한 값의 5~95%입니다. 이 범위 밖이어도 모델이 학습 중에 비슷한 값을 봤을 수 있고, 여러 특징의 조합은 따로 확인하지 않았습니다."
        : "")
    : null;
  return {headline: headline.trim(), meaning, certainty, next};
}

export type HistoryPeriodFacts = PeriodFacts & {
  /** Each period's mean and middle half, to tell a moved median from a moved level. */
  means: {a: number | null; b: number | null};
  aMiddle: {low: number; high: number} | null;
  /** For a declared current in A: measurements below 1 A in each period — a low reading, not a stop. */
  lowCurrent: {a: number; b: number} | null;
};

const portion = (part: number, whole: number) => whole > 0 ? part / whole : 0;

/** A stored time series over two periods. Beyond the shared period message, it says whether the
 * share of measurements with no current differs, and when the median moved but the mean barely did,
 * that values may sit at a few levels whose shares changed. Both are observations, not causes. */
export function historyPeriodMessage(facts: HistoryPeriodFacts, next: NextStep[] = []): AnalysisMessage | null {
  const base = periodMessage({...facts, onset: null}, (at) => String(at), next);
  if (!base) return null;
  const unit = facts.unit ? " " + facts.unit : "";
  const notes: string[] = [];
  let lowDiffers = false;
  if (facts.lowCurrent) {
    const a = portion(facts.lowCurrent.a, facts.a.usable), b = portion(facts.lowCurrent.b, facts.b.usable);
    const shareA = countShare(facts.lowCurrent.a, facts.a.usable), shareB = countShare(facts.lowCurrent.b, facts.b.usable);
    lowDiffers = Math.abs(a - b) >= 0.1;
    // A share of stored measurements, not of time, and a low reading, not a stop: spacing can
    // differ, one phase below 1 A says nothing of the others, and a similar share settles no cause.
    notes.push("유효 측정 중 전류가 1 A 미만인 측정의 비율은 기간 A " + shareA + ", 기간 B " + shareB
      + (lowDiffers ? "로 다릅니다(측정 수 기준이라 시간 비율과는 다를 수 있습니다). 두 기간의 차이에는 이 비율 차이가 섞여 있을 수 있으니, 1 A 이상인 측정끼리도 견줘 보세요."
        : "로 비슷합니다(측정 수 기준이라 시간 비율과는 다를 수 있습니다). 이 비율만으로 차이가 어디서 왔는지 정할 수는 없으니, 전류가 낮았던 구간의 길이와 그 밖의 값 분포를 함께 확인하세요.")
      + " 1 A 미만은 측정된 전류가 낮았다는 뜻이며, 설비가 멈췄는지는 운전 기록이나 다른 상의 값으로 따로 확인해야 합니다.");
  }
  const {a, b} = facts, {a: meanA, b: meanB} = facts.means;
  if (!lowDiffers && a.median !== null && b.median !== null && meanA !== null && meanB !== null && facts.aMiddle) {
    const medianMove = b.median - a.median, meanMove = meanB - meanA;
    const width = facts.aMiddle.high - facts.aMiddle.low;
    const apart = Math.abs(medianMove) >= 0.25 * width && width > 0
      && (Math.sign(medianMove) !== Math.sign(meanMove) || Math.abs(meanMove) < 0.5 * Math.abs(medianMove));
    if (apart)
      notes.push("중앙값은 " + short(a.median) + " → " + short(b.median) + unit + "로 바뀌었지만 평균은 " + short(meanA) + " → " + short(meanB) + unit
        + (Math.sign(medianMove) !== Math.sign(meanMove) && Math.abs(meanMove) >= 0.1 * Math.abs(medianMove) ? "로 반대로 움직였습니다. " : "로 거의 같습니다. ")
        + "값이 몇 개의 수준(예: 운전 상태마다 다른 수준)으로 나뉘어 있으면 수준별 측정 비중만 바뀌어도 중앙값이 크게 움직입니다. 분포 그림에서 값이 어디에 몰려 있는지 확인하세요.");
  }
  return {...base, meaning: notes.length ? notes.join(" ") : base.meaning};
}


/** A forecast still has a numerical result when no operating criterion has been supplied. */
export function forecastMessage(facts: {last:number|null; start?:number; end:{estimate:number;lower:number|null;upper:number|null};
  unit:string|null; horizon:string; checks:{points:number;error:number;naive:number;coverage:number}[]}):AnalysisMessage {
  const value=(v:number)=>short(v)+(facts.unit?" "+facts.unit:"");
  const difference=facts.last===null?null:facts.end.estimate-facts.last;
  const check=facts.checks[0];
  return {
    headline:worseThanPersistence(check) ? "과거 기록에서는 마지막 값이 계속된다고 가정했을 때보다 모델 예측의 오차가 컸습니다." : facts.horizon+"의 예상값은 "+value(facts.end.estimate)+"입니다.",
    meaning:(facts.start===undefined?"":"모델 예측은 "+value(facts.start)+"에서 시작하며, 예측값은 이 기간 동안 "+(facts.end.estimate-facts.start>0?"+":"")+value(facts.end.estimate-facts.start)+"만큼 변합니다. ")
      +(facts.start!==undefined&&facts.last!==null?"마지막 구간 평균 "+value(facts.last)+"과 모델 시작값의 차이는 "+value(facts.start-facts.last)+"입니다. ":facts.last===null?"":"마지막 구간 평균 "+value(facts.last)+" 대비 "+(difference!>0?"+":"")+value(difference!)+"입니다. ")
      +(facts.end.lower!==null&&facts.end.upper!==null?"해당 시점의 예측 범위는 "+value(facts.end.lower)+"~"+value(facts.end.upper)+"입니다.":"해당 시점의 예측 범위는 제공되지 않았습니다."),
    certainty:check?"과거 마지막 "+check.points+"개를 가리고 확인한 평균 오차는 "+value(check.error)+"였습니다. 실제 값이 예측 범위 안에 든 비율은 "+short(check.coverage*100)+"%였습니다."
      :"과거 자료를 가린 예측 검증 결과가 없어, 예상값과 범위를 잠정적으로 확인하세요.",
    next:[],
  };
}
