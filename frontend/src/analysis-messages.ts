/** The message an analysis screen leads with: what changed, how plain that is, and what to look at
 * next. Every sentence is built from numbers the screen already shows; nothing is fitted or
 * guessed, and no sentence names a cause or a fault. */
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
    + (ratio !== null && ratio > 0 && (ratio >= 1.5 || ratio <= 1 / 1.5) ? "로 약 " + times(ratio) + "입니다." : "입니다.");
  const share = facts.outsidePercent;
  const count = facts.outsideCount ?? (share === null ? null : Math.round(share * b.usable / 100));
  let headline: string;
  if (share === null || range === null) headline = "기간 A와 B의 " + medians;
  else if (share >= 99.5) headline = "기간 B의 측정 " + b.usable + "회가 모두 기간 A의 평소 범위(" + range + ")를 벗어났습니다. " + medians;
  else if (share >= 50) headline = "기간 B 측정의 " + Math.round(share) + "%(" + count + "회)가 기간 A의 평소 범위(" + range + ")를 벗어났습니다. " + medians;
  else if (share > 10) headline = "기간 B 측정의 일부(" + Math.round(share) + "%, " + count + "회)만 기간 A의 평소 범위(" + range + ")를 벗어났습니다. " + medians;
  else headline = "기간 B의 값은 대부분 기간 A의 평소 범위(" + range + ") 안에 있습니다. " + medians;
  let certainty: string | null = null;
  if (b.usable < 5 || a.usable < 10)
    certainty = "측정 수가 적어(기간 A " + a.usable + "회 · 기간 B " + b.usable + "회) 이 결과만으로 단정하기 이릅니다.";
  else if (share === null) certainty = null;
  else if (share >= 90) certainty = "값 몇 개가 튄 것이 아니라 거의 모든 측정이 벗어나, 값의 수준 자체가 달라졌습니다.";
  else if (share >= 50) certainty = "절반 넘게 벗어났지만 평소 범위 안의 값도 남아 있습니다. 기간 B 안에서 언제부터 달라졌는지 함께 보세요.";
  else if (share > 10) certainty = "일부만 벗어나 잠깐의 변화일 수 있습니다. 벗어난 측정이 한곳에 몰려 있는지 시간 추이에서 확인하세요.";
  else certainty = "기간 A 안에서도 값의 10%는 이 범위 밖에 있으므로, 이 정도는 뚜렷한 변화로 보기 어렵습니다.";
  const onset = facts.onset && share !== null && share > 10
    ? place(facts.onset.first) + "에서 처음 평소 범위를 벗어났고"
      + (facts.onset.stayed ? " 그 뒤로 계속 벗어나 있습니다." : " 그 뒤로 범위 안팎을 오갔습니다.")
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

/** Whether two Pearson coefficients differ by more than their sample sizes allow (Fisher z). */
export function coefficientGap(a: RelationSide, b: RelationSide): number | null {
  if (a.pearson === null || b.pearson === null || a.pairs < 4 || b.pairs < 4) return null;
  const z = (r: number) => Math.atanh(Math.max(-0.999999, Math.min(0.999999, r)));
  return Math.abs(z(a.pearson) - z(b.pearson)) / Math.sqrt(1 / (a.pairs - 3) + 1 / (b.pairs - 3));
}

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

export function relationMessage(x: string, y: string, a: RelationSide, b: RelationSide,
  crest: {a: number | null; b: number | null} | null, next: NextStep[] = []): AnalysisMessage | null {
  const ta = tie(a), tb = tie(b);
  if (!ta && !tb) return null;
  let headline: string;
  if (!ta || !tb) {
    const [name, side, t] = ta ? ["A", a, ta] as const : ["B", b, tb!] as const;
    headline = "기간 " + name + "에서 두 값은 " + is(t) + " (" + coefficients(side, t) + "). 다른 기간은 짝이 부족해 계산하지 못했습니다.";
  } else {
    const kept = ta.kind === tb.kind && (!("strong" in ta) || !("strong" in tb) || ta.strong === tb.strong)
      && Math.abs(a.pearson! - b.pearson!) < 0.2;
    headline = kept
      ? "두 기간 모두 두 값은 " + is(tb) + " (기간 A " + coefficients(a, ta) + " · 기간 B " + coefficients(b, tb) + "). 관계는 그대로입니다."
      : "두 값의 관계가 달라졌습니다. 기간 A에서는 " + was(ta) + "(" + coefficients(a, ta) + "), 기간 B에서는 " + is(tb)
        + "(" + coefficients(b, tb) + ").";
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
  const gap = ta && tb ? coefficientGap(a, b) : null;
  let certainty: string | null = null;
  if (few.length) certainty = few.join(" · ") + "이라 계수가 크게 흔들릴 수 있습니다.";
  else if (unclear.length)
    certainty = "기간 " + unclear.join("·") + "에서는 피어슨과 스피어먼이 서로 다른 방향을 가리켜, 몇몇 측정이 관계를 좌우하고 있을 수 있습니다. 산점도에서 떨어진 점을 확인하세요.";
  else if (gap !== null)
    certainty = gap >= 2.6 ? "측정 수를 감안해도 두 기간의 관계 차이는 우연으로 보기 어렵습니다."
      : gap >= 1.96 ? "측정 수를 감안하면 두 기간의 관계 차이가 우연일 가능성은 낮습니다."
      : "측정 수를 감안하면 두 기간의 관계 차이는 우연 범위 안입니다.";
  return {headline, meaning, certainty, next};
}

export type SpectrumFacts = {label: string; ratio: number | null; shares: BandShare[]};

/** The band whose share of the energy grew most, if any grew by ten points or more. */
export function shiftedBand(shares: BandShare[]): BandShare | null {
  const best = shares.reduce<BandShare | null>((top, band) => !top || band.b - band.a > top.b - top.a ? band : top, null);
  return best && best.b - best.a >= 0.1 ? best : null;
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
      : "주파수별 에너지 분포는 비슷합니다.");
  const notes: string[] = [];
  for (const other of others) {
    const moved = shiftedBand(other.shares);
    if (!band) continue;
    if (moved && moved.from <= band.to && band.from <= moved.to)
      notes.push(other.label + "에서도 같은 대역 비중이 " + percent(moved.a) + " → " + percent(moved.b) + "로 커져, 두 방향이 같은 변화를 보입니다.");
    else if (moved)
      notes.push(other.label + "에서는 비중이 커진 대역이 달라(" + hz(moved.from) + "~" + hz(moved.to) + " Hz) 한 방향에서만 보이는 변화일 수 있습니다.");
    else notes.push(other.label + "에서는 분포가 비슷해 한 방향에서만 보이는 변화입니다.");
  }
  notes.push(Math.min(used.a, used.b) < 3
    ? "기간마다 측정 " + Math.min(used.a, used.b) + "회만 비교해 우연일 수 있습니다."
    : "각 기간에서 고르게 고른 측정 " + used.a + "회·" + used.b + "회의 평균입니다.");
  return {headline, meaning: null, certainty: notes.join(" "), next};
}

export type ModelRead = {name: string; line: RatioLine};

function modelState(read: ModelRead, place: (position: number) => string): string {
  const {name, line} = read, story = line.story;
  const top = line.points.length ? times(Math.max(...line.points.map((p) => p.ratio))) : null;
  if (story.state === "ongoing" && story.ongoing)
    return name + " 점수는 " + place(story.ongoing.start) + "부터 "
      + (story.lastExceeds === false ? "기준을 넘는 구간이 이어졌고 최근 측정은 기준 아래입니다" : "계속 기준을 넘고 있습니다")
      + "(" + story.ongoing.steps + "회" + (top ? ", 가장 높을 때 기준의 " + top : "") + ")";
  if (story.state === "latest" && story.anchor) return name + " 점수는 마지막 측정(" + place(story.anchor.pointer.position) + ")에서만 기준을 넘었습니다";
  if (story.state === "below" && story.anchor) return name + " 점수는 지금 기준 아래입니다(마지막 기준 초과 " + place(story.anchor.pointer.position) + ")";
  return name + " 점수는 한 번도 기준을 넘지 않았습니다" + (top ? "(가장 높을 때 기준의 " + top + ")" : "");
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
  const over = drawn.filter((read) => read.line.story.state === "ongoing" || read.line.story.state === "latest");
  const lead = drawn.length === 1 ? "" : !over.length ? "어느 모델도 지금 기준을 넘지 않았습니다. "
    : over.length === drawn.length ? "모든 모델이 기준을 넘고 있습니다. " : "모델마다 다르게 말합니다. ";
  const headline = lead + states.join(", ") + ".";
  let certainty: string;
  if (drawn.length === 1) certainty = "모델 하나의 결과이므로 같은 시점에 측정값도 달라졌는지 함께 보세요.";
  else if (over.length && over.length < drawn.length)
    certainty = "일부 모델만 기준을 넘어 이 결과만으로는 어느 쪽이 맞는지 알 수 없습니다. 같은 시점에 측정값도 달라졌는지 확인하세요.";
  else if (over.length) {
    const starts = over.map((read) => read.line.story.ongoing?.start ?? read.line.story.anchor!.pointer.position);
    certainty = Math.max(...starts) - Math.min(...starts) <= 3
      ? "서로 다른 모델이 같은 무렵(" + place(Math.min(...starts)) + ")부터 기준을 넘어, 한 모델만의 반응이 아닙니다."
      : "모델마다 기준을 넘기 시작한 때가 달라, 먼저 반응한 " + place(Math.min(...starts)) + "부터 확인하세요.";
  } else certainty = "모델 기준 아래라도 측정값 자체가 달라졌는지는 따로 확인하세요.";
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
    if (!steps.length) { parts.push(label + "에는 계산한 범위 안에서 닿지 않습니다."); continue; }
    const lo = Math.min(...steps), hi = Math.max(...steps);
    parts.push(label + "까지 " + span(lo, hi, facts) + " 남았습니다"
      + (steps.length < reaches.length ? "(계산 방식 " + reaches.length + "가지 중 " + steps.length + "가지에서만 닿음)." : "."));
    if (lo > 0 && hi / lo >= 2) spread = true;
  }
  if (!parts.length && !already.length) return null;
  const headline = [...already, ...parts.map((part, i) => i ? part : "지금 추세가 이어진다고 가정하면 " + part)].join(" ");
  const check = facts.checks[0];
  let certainty: string;
  if (!check) certainty = "기록이 짧아 과거 자료로 예측을 확인하지 못했습니다. 도달 시점은 대략의 범위로 읽으세요.";
  else {
    const versus = check.error < 0.8 * check.naive ? "마지막 값을 그대로 이어 쓴 것보다 오차가 작았습니다"
      : check.error > 1.2 * check.naive ? "마지막 값을 그대로 이어 쓴 것보다 오차가 컸습니다" : "마지막 값을 그대로 이어 쓴 것과 오차가 비슷했습니다";
    const weak = check.coverage < 0.5 || check.error >= 0.8 * check.naive || spread;
    certainty = "기록의 마지막 " + check.points + "개를 가리고 같은 방법으로 예측해 보니 실제 값이 예측 범위 안에 든 비율은 "
      + Math.round(check.coverage * 100) + "%였고, " + versus + ". "
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

/** Two stored results of one model: how the score moved and whether the features left where this
 * asset usually sits, so a score that jumps on ordinary values is told apart from one that follows them. */
export function comparisonMessage(score: {previous: number | null; current: number | null}, features: FeatureChange[],
  usualUntil: number | null, place: (position: number) => string, next: NextStep[] = []): AnalysisMessage | null {
  const judged = withoutTwins(features).filter((feature) => feature.usual);
  if (score.current === null && !judged.length) return null;
  const ratio = score.previous !== null && score.current !== null && score.previous > 0 && score.current > 0
    ? score.current / score.previous : null;
  const moved = ratio !== null && (ratio >= 2 || ratio <= 0.5);
  let headline = score.previous !== null && score.current !== null
    ? "이상 점수가 " + short(score.previous) + " → " + short(score.current)
      + (ratio !== null && (ratio >= 1.5 || ratio <= 1 / 1.5) ? "로 약 " + times(ratio) + "가 됐습니다." : "입니다.")
    : "";
  // Farthest outside first, measured in the width of the usual range.
  const far = (feature: FeatureChange) => {
    const {low, high} = feature.usual!, width = Math.max(high - low, Math.abs(high) * 1e-6, 1e-12);
    return Math.max(feature.current - high, low - feature.current) / width;
  };
  const outside = judged.filter((feature) => against(feature.current, feature.usual!) !== "inside")
    .sort((a, b) => far(b) - far(a));
  if (!judged.length)
    headline += " 이전 기록이 짧아 특징값이 평소와 다른지는 아직 말할 수 없습니다.";
  else if (outside.length)
    headline += " 특징 " + judged.length + "개 중 " + outside.length + "개가 이 설비의 평소 범위를 벗어났습니다: "
      + outside.slice(0, 3).map((feature) => feature.label + "(" + AGAINST_TEXT[against(feature.current, feature.usual!)] + ")").join(", ")
      + (outside.length > 3 ? " 외 " + (outside.length - 3) + "개." : ".");
  else headline += " 특징값은 " + judged.length + "개 모두 이 설비의 평소 범위 안에 있습니다.";
  const meaning = moved && judged.length && !outside.length
    ? "점수는 크게 바뀌었지만 개별 특징값은 평소 범위 안입니다. 하나의 값보다 여러 값의 조합이 평소와 다를 때 점수가 바뀔 수 있으니, 같은 시각의 운전·측정 조건과 함께 보세요."
    : outside.length
      ? (() => { const top = outside[0], unit = top.unit ? " " + top.unit : "";
        return "가장 멀리 벗어난 값은 " + top.label + " " + short(top.current) + unit + "이고, 평소 범위는 "
          + short(top.usual!.low) + "~" + short(top.usual!.high) + unit + "입니다."; })()
      : null;
  const results = judged[0]?.usual?.results ?? 0;
  const certainty = judged.length && usualUntil !== null
    ? "평소 범위는 " + place(usualUntil) + "까지 이 모델이 분석한 " + results + "개 결과의 5~95% 값입니다."
      + (results < 50 ? " 기록이 짧아 평소 범위가 좁거나 넓게 잡혔을 수 있습니다." : "")
    : null;
  return {headline: headline.trim(), meaning, certainty, next};
}
