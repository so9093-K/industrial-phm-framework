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

export type ChangeFacts = {
  label: string; unit: string | null; direction: "up" | "down"; kind?: "departure" | "level-change";
  reference: number | null; typical: number | null; referenceSpread?: number | null;
};

/** 한 문장 결론. `span`은 "2. 2. 08:18부터 약 1시간 21분 동안"처럼 언제부터 얼마 동안인지,
 * `condition`은 같은 운전 수준끼리 견줬을 때 그 수준의 이름이다. */
export function changeSentence(facts: ChangeFacts, span: string, condition: string | null = null): string {
  const basis = facts.kind === "level-change" ? "기록 처음 30%에 일정하던 값"
    : condition ? "같은 운전 수준(" + condition + ")의 기록 처음 30%" : "기록 처음 30%";
  return subject(facts.label) + " " + span + " " + basis + "보다 " + (facts.direction === "up" ? "높았습니다." : "낮았습니다.");
}

const PLAIN_FEATURES: [suffix: string, term: RegExp, plain: string][] = [
  [".rms", / RMS$/, " 크기 (RMS)"], [".excess_kurtosis", / 초과 첨도$/, " 충격성 (첨도)"],
  [".skewness", / 왜도$/, " 치우침 (왜도)"], [".crest_factor", / 파고율$/, " 피크 배율 (파고율)"],
];
/** 진동 특징 이름은 쉬운 말을 앞에, 계산 이름을 괄호에 둔다: "수직 진동 초과 첨도" → "수직 진동 충격성 (첨도)". */
export function plainLabel(label: string, feature?: string | null): string {
  const found = feature ? PLAIN_FEATURES.find(([suffix]) => feature.endsWith(suffix)) : undefined;
  return found ? label.replace(found[1], found[2]) : label;
}

/** First-screen headline: keep timing and comparison conditions in the adjacent context. */
export function changeHeadline(facts: Pick<ChangeFacts, "label" | "direction" | "kind"> & {feature?:string}): string {
  const basis = facts.kind === "level-change" ? "일정하던 기준값" : "비교 기준";
  return subject(plainLabel(facts.label, facts.feature)) + " " + basis + "보다 " + (facts.direction === "up" ? "높았습니다." : "낮았습니다.");
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

/** 주요 변화로 고른 이유를 꼬리표가 아니라 설명으로 말한다. */
export const CHANGE_WHY = {
  sustained: "선정 기준 · 오래 이어진 변화",
  "record-end": "선정 기준 · 기록 끝까지 이어진 변화",
  largest: "선정 기준 · 변화 폭이 큰 구간",
} as const;
