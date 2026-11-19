/** 주요 변화를 읽는 사람의 말로 옮긴다: 무엇이, 언제부터 얼마 동안, 무엇과 견줘 어땠는지.
 * 판정 이름을 붙이지 않고 관측한 사실만 말한다 (docs/terminology.md, Web 화면 용어 기준). */

const digits = (number: number) => number.toLocaleString("ko-KR", {maximumSignificantDigits: 3});
const amount = (number: number, unit: string | null) => digits(number) + (unit ? " " + unit : "");

// 숫자와 로마자는 읽는 소리의 받침으로 조사를 고른다 (0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔 / L 엘, M 엠, N 엔, R 알).
const CLOSED_DIGITS = "013678", CLOSED_LETTERS = "lmnr";
function closed(word: string): boolean {
  const last = word.trim().replace(/[)\]\s]+$/, "").slice(-1);
  const code = last.charCodeAt(0);
  return code >= 0xac00 && code <= 0xd7a3 ? (code - 0xac00) % 28 !== 0
    : /\d/.test(last) ? CLOSED_DIGITS.includes(last)
    : CLOSED_LETTERS.includes(last.toLowerCase());
}
/** 이름 뒤에 주격 조사 '이/가'를 붙인다. */
export function subject(word: string): string { return word + (closed(word) ? "이" : "가"); }
/** 이름 뒤에 접속 조사 '과/와'를 붙인다. */
export function withAnd(word: string): string { return word + (closed(word) ? "과" : "와"); }
/** 이름 뒤에 목적격 조사 '을/를'을 붙인다. */
export function object(word: string): string { return word + (closed(word) ? "을" : "를"); }
/** 이름 뒤에 보조사 '은/는'을 붙인다. */
export function topic(word: string): string { return word + (closed(word) ? "은" : "는"); }

export type ChangeFacts = {
  label: string; unit: string | null; direction: "up" | "down"; kind?: "departure" | "level-change";
  reference: number | null; typical: number | null; referenceSpread?: number | null;
};

const PLAIN_FEATURES: [suffix: string, term: RegExp, plain: string][] = [
  [".rms", / RMS$/, " 크기 (RMS)"], [".excess_kurtosis", / 초과 첨도$/, " 충격성 (첨도)"],
  [".skewness", / 왜도$/, " 치우침 (왜도)"], [".crest_factor", / 파고율$/, " 피크 배율 (파고율)"],
];
/** 진동 특징 이름은 쉬운 말을 앞에, 계산 이름을 괄호에 둔다: "수직 진동 초과 첨도" → "수직 진동 충격성 (첨도)". */
export function plainLabel(label: string, feature?: string | null): string {
  const found = feature ? PLAIN_FEATURES.find(([suffix]) => feature.endsWith(suffix)) : undefined;
  return found ? label.replace(found[1], found[2]) : label;
}

const TEMPERATURE = /°|℃|℉/;
const share = (fraction: number) => (fraction * 100).toLocaleString("ko-KR", {maximumFractionDigits: 1}) + "%";
/** 처음 값과 비교한 크기. 1.5배 이상이면 배수, 2/3 이하면 처음의 몇 %, 그 사이면 차이와 비율로 말한다.
 * 온도처럼 0이 기준이 아닌 단위는 배수·비율이 뜻을 갖지 않으므로 차이만 말한다. */
function compared(value: number, reference: number, unit: string | null, basis: string, now: boolean): string {
  const ratio = !TEMPERATURE.test(unit ?? "") && reference > 0 && value > 0 ? value / reference : null;
  const be = now ? "입니다" : "였습니다";
  if (ratio !== null && ratio >= 1.5) return basis + "의 약 " + digits(ratio) + "배" + be;
  if (ratio !== null && ratio <= 1 / 1.5) return basis + "의 약 " + share(ratio) + be;
  const gap = value - reference;
  const part = ratio !== null && unit !== "%" ? "(" + share(Math.abs(gap) / reference) + ")" : "";
  return basis + "보다 " + amount(Math.abs(gap), unit) + part + " "
    + (gap >= 0 ? (now ? "높습니다" : "높았습니다") : (now ? "낮습니다" : "낮았습니다"));
}

/** 변화가 지금 어떤지: 기록 끝까지 이어졌으면 마지막 값, 먼저 끝났으면 언제부터 얼마 동안이었는지. */
export type ChangeNow = {latest: {caption: string; value: number} | null} | {span: string};
/** 결론 한 문장. 신호 이름과 방향만으로는 설비끼리 구별되지 않으므로, 마지막 측정까지 이어졌는지와
 * 처음과 비교한 크기를 함께 말한다. 판정 꼬리표는 붙이지 않는다 (docs/terminology.md). */
export function changeConclusion(facts: ChangeFacts & {feature?: string | null}, now: ChangeNow): string {
  const name = subject(plainLabel(facts.label, facts.feature));
  const basis = facts.kind === "level-change" ? "처음 일정하던 값" : "처음";
  const up = facts.direction === "up";
  if ("span" in now) return name + " " + now.span + " " + (facts.reference === null || facts.typical === null
    ? basis + "보다 " + (up ? "높았습니다" : "낮았습니다")
    : compared(facts.typical, facts.reference, facts.unit, basis, false)) + ".";
  const head = name + " 마지막 측정까지 " + basis + "보다 " + (up ? "높았" : "낮았");
  if (!now.latest || facts.reference === null) return head + "습니다.";
  return head + "고, " + topic(now.latest.caption) + " " + compared(now.latest.value, facts.reference, facts.unit, basis, true) + ".";
}

export type ChangeNumber = {caption: string; value: string; note: string | null};
/** 변화 전후의 두 숫자와 각각이 무엇인지. 숫자만 놓지 않고, 평소 얼마나 흔들리던 값인지와 차이를 함께 말한다. */
export function changeNumbers(facts: ChangeFacts): {before: ChangeNumber; after: ChangeNumber} | null {
  if (facts.reference === null || facts.typical === null) return null;
  const gap = facts.typical - facts.reference;
  const ratio = facts.reference > 0 && facts.typical > 0 ? facts.typical / facts.reference : null;
  const spread = facts.referenceSpread ?? null;
  return {
    before: {caption: "기록 처음 30%의 중앙값", value: amount(facts.reference, facts.unit),
      note: facts.kind === "level-change" || spread === 0 ? "이 값이 그대로 유지됨"
        : spread ? "이 기간의 변동 약 ±" + amount(spread, facts.unit) : null},
    after: {caption: "이 구간의 중앙값", value: amount(facts.typical, facts.unit),
      note: gap === 0 ? null : "처음보다 " + amount(Math.abs(gap), facts.unit) + (gap > 0 ? " 높음" : " 낮음")
        + (ratio !== null && ratio >= 1.5 ? " · 약 " + digits(ratio) + "배" : "")},
  };
}

/** 변화가 기록 끝까지 이어졌을 때의 세 번째 숫자: 마지막 값과, 그 값이 이 구간 중앙값과 얼마나 다른지. */
export function latestNumber(caption: string, value: number, typical: number | null, unit: string | null): ChangeNumber {
  if (typical === null || value === typical) return {caption, value: amount(value, unit), note: null};
  const ratio = typical > 0 && value > 0 ? value / typical : null;
  const note = ratio !== null && (ratio >= 1.5 || ratio <= 1 / 1.5)
    ? "이 구간 중앙값의 약 " + digits(ratio) + "배"
    : "이 구간 중앙값보다 " + amount(Math.abs(value - typical), unit) + (value > typical ? " 높음" : " 낮음");
  return {caption, value: amount(value, unit), note};
}

const shortTime = (at: string) => new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul", month: "long", day: "numeric",
  hour: "2-digit", minute: "2-digit", hour12: false});
/** 변화가 기록 끝보다 먼저 끝났으면 언제 끝났고 기록은 언제까지인지. 마지막 두 구간 안에서 끝났으면
 * 기록 끝까지 이어진 변화로 보고 null을 돌려준다. 상태 요약과 관측 현황이 같은 규칙을 쓴다. */
export function changeEnded(end: string, recordTo: string | null | undefined, bucketSeconds: number | null | undefined): string | null {
  const last = recordTo ? Date.parse(recordTo) : NaN, until = Date.parse(end);
  if (!Number.isFinite(last) || !Number.isFinite(until) || last - until <= 2 * (bucketSeconds ?? 0) * 1000) return null;
  return "변화 종료 " + shortTime(end) + " · 기록 마지막 " + shortTime(recordTo!);
}

/** 기록 끝 전에 끝난 변화 뒤의 사실 한 줄: 이후 구간 가운데 비교한 값(같은 운전 수준끼리 비교했으면 그 수준의 값)이
 * 있는 구간 수와, 그중 처음 범위 안의 수. 이후 같은 조건이 드물면 '돌아왔다'고 볼 근거도 적다는 것을 숫자로 보여 준다. */
export function afterChange(end: string, usual: {low: number; high: number}, rows: {at: string; mean: number; judged: number | null}[],
  kind: "all" | "level" | "running", condition: string | null): string | null {
  const after = rows.filter(row => Date.parse(row.at) > Date.parse(end));
  if (!after.length) return null;
  const values = after.flatMap(row => {const value = kind === "all" ? row.mean : row.judged; return value === null ? [] : [value];});
  const inside = values.filter(value => value >= usual.low && value <= usual.high).length;
  const where = inside === values.length ? "모두 처음 범위 안" : inside === 0 ? "모두 처음 범위 밖" : inside + "개 처음 범위 안";
  const head = "변화 구간 끝 " + shortTime(end) + " · 이후 구간 " + after.length + "개";
  const who = kind === "level" && condition ? condition : kind === "running" ? "운전 중" : null;
  if (!who) return head + ", " + where;
  return head + " 중 " + who + " " + (values.length ? values.length + "개, " + where : "없음");
}

/** 주요 변화로 고른 이유를 꼬리표가 아니라 설명으로 말한다. */
export const CHANGE_WHY = {
  sustained: "선정 기준 · 오래 이어진 변화",
  "record-end": "선정 기준 · 기록 끝까지 이어진 변화",
  largest: "선정 기준 · 변화 폭이 큰 구간",
} as const;
