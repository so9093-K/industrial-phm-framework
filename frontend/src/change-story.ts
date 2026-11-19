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
const ratioText = (ratio: number) => ratio.toLocaleString("ko-KR", {maximumSignificantDigits: 2});
/** 초기(기록 처음 30%의 중앙값)와 비교한 크기 한 마디. 1.5배 이상이면 배수, 2/3 이하면 초기의 몇 %,
 * 그 사이면 차이와 비율. 온도처럼 0이 기준이 아닌 단위는 차이만 쓴다. 두 기간 비교처럼 기준 이름이
 * 다르면 name으로 바꾼다(예: '기간 A의 약 2배'). */
export function versusStart(value: number, reference: number | null, unit: string | null, name = "초기"): string | null {
  if (reference === null) return null;
  const ratio = !TEMPERATURE.test(unit ?? "") && reference > 0 && value > 0 ? value / reference : null;
  if (ratio !== null && ratio >= 1.5) return name + "의 약 " + ratioText(ratio) + "배";
  if (ratio !== null && ratio <= 1 / 1.5) return name + "의 약 " + Math.round(ratio * 100) + "%";
  const gap = value - reference;
  if (gap === 0) return name + "와 같음";
  const part = ratio !== null && unit !== "%" ? "(" + share(Math.abs(gap) / reference) + ")" : "";
  return name + "보다 " + amount(Math.abs(gap), unit) + part + (gap > 0 ? " 높음" : " 낮음");
}

/** 결론 한 문장: 변화의 모양만 쉬운 말로 말한다(언제부터, 지금도 이어지는지, 마지막에 한 번 더 크게 움직였는지).
 * 크기는 옆의 숫자 칸이 '초기의 약 n배'로 말하므로 문장에 숫자를 겹쳐 쓰지 않는다. */
export function changeConclusion(facts: Pick<ChangeFacts, "label" | "direction"> & {feature?: string | null},
  shape: {span: string; now?: boolean; condition?: string | null; jump?: boolean}): string {
  const up = facts.direction === "up";
  const who = (shape.condition ? shape.condition + " 중 " : "") + subject(plainLabel(facts.label, facts.feature));
  if (shape.jump) return who + " " + shape.span + " 초기보다 " + (up ? "높아졌고" : "낮아졌고")
    + ", 마지막 측정에서 한 번 더 크게 " + (up ? "뛰었습니다." : "떨어졌습니다.");
  return who + " " + shape.span + " 초기보다 " + (shape.now ? (up ? "높습니다." : "낮습니다.") : (up ? "높았습니다." : "낮았습니다."));
}

/** 기록 끝까지 이어진 변화에서 마지막 측정이 직전 측정의 1.5배 넘게(낮아지는 변화면 2/3 아래로) 움직였는지.
 * 변화 구간의 수준과 마지막 한 번의 급변은 서로 다른 일이라 따로 말하고 그래프에도 따로 표시한다. */
export function lastJump(trace: {at: number; value: number}[], direction: "up" | "down"): {at: number; value: number; before: number} | null {
  const last = trace.at(-1), before = trace.at(-2);
  if (!last || !before || before.value <= 0 || last.value <= 0) return null;
  const ratio = last.value / before.value;
  return (direction === "up" ? ratio >= 1.5 : ratio <= 1 / 1.5) ? {at: last.at, value: last.value, before: before.value} : null;
}

export type ChangeNumber = {caption: string; value: string; note: string | null};
/** 숫자 칸 두 개: 초기와 변화 구간. 변화 구간 아래에는 초기와 비교한 크기를 적는다. */
export function changeNumbers(facts: ChangeFacts, spanCaption: string | null = null): {before: ChangeNumber; after: ChangeNumber} | null {
  if (facts.reference === null || facts.typical === null) return null;
  return {
    before: {caption: "초기 · 기록 처음 30%", value: amount(facts.reference, facts.unit), note: null},
    after: {caption: spanCaption ? "변화 구간 · " + spanCaption : "변화 구간", value: amount(facts.typical, facts.unit),
      note: versusStart(facts.typical, facts.reference, facts.unit)},
  };
}

/** 변화가 기록 끝까지 이어졌을 때의 세 번째 숫자 칸: 마지막 값과 초기 대비 크기. */
export function latestNumber(caption: string, value: number, reference: number | null, unit: string | null): ChangeNumber {
  return {caption, value: amount(value, unit), note: versusStart(value, reference, unit)};
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
  const where = inside === values.length ? "모두 초기 범위 안" : inside === 0 ? "모두 초기 범위 밖" : inside + "개 초기 범위 안";
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
