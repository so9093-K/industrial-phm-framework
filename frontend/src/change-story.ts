import {dayText, timeLabel} from "./date-format.ts";
/** 주요 변화를 읽는 사람의 말로 옮긴다: 무엇이, 언제부터 얼마 동안, 무엇과 견줘 어땠는지.
 * 판정 이름을 붙이지 않고 관측한 사실만 말한다. */

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
    after: {caption: spanCaption ? "특이사항 구간 · " + spanCaption : "특이사항 구간", value: amount(facts.typical, facts.unit),
      note: versusStart(facts.typical, facts.reference, facts.unit)},
  };
}

const shortTime = (at: string) => dayText(at) + " " + timeLabel(at);
/** 변화가 기록 끝보다 먼저 끝났으면 언제 끝났고 기록은 언제까지인지. 마지막 두 구간 안에서 끝났으면
 * 기록 끝까지 이어진 변화로 보고 null을 돌려준다. 상태 요약과 관측 현황이 같은 규칙을 쓴다. */
export function changeEnded(end: string, recordTo: string | null | undefined, bucketSeconds: number | null | undefined): string | null {
  const last = recordTo ? Date.parse(recordTo) : NaN, until = Date.parse(end);
  if (!Number.isFinite(last) || !Number.isFinite(until) || last - until <= 2 * (bucketSeconds ?? 0) * 1000) return null;
  return "변화 종료 " + shortTime(end) + " · 기록 마지막 " + shortTime(recordTo!);
}

/** 주요 변화로 고른 이유를 꼬리표가 아니라 설명으로 말한다. */
export const CHANGE_WHY = {
  sustained: "선정 기준 · 오래 이어진 변화",
  "record-end": "선정 기준 · 기록 끝까지 이어진 변화",
  largest: "선정 기준 · 변화 폭이 큰 구간",
} as const;
