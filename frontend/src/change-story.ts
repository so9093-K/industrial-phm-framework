/** 주요 변화를 읽는 사람의 말로 옮긴다: 무엇이, 언제부터 얼마 동안, 무엇과 견줘 어땠는지.
 * 판정 이름을 붙이지 않고 관측한 사실만 말한다 (docs/terminology.md, Web 화면 용어 기준). */

const digits = (number: number) => number.toLocaleString("ko-KR", {maximumSignificantDigits: 3});
const amount = (number: number, unit: string | null) => digits(number) + (unit ? " " + unit : "");

// 숫자와 로마자는 읽는 소리의 받침으로 조사를 고른다 (0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔 / L 엘, M 엠, N 엔, R 알).
const CLOSED_DIGITS = "013678", CLOSED_LETTERS = "lmnr";
/** 이름 뒤에 주격 조사 '이/가'를 붙인다. */
export function subject(word: string): string {
  const last = word.trim().replace(/[)\]\s]+$/, "").slice(-1);
  const code = last.charCodeAt(0);
  const closed = code >= 0xac00 && code <= 0xd7a3 ? (code - 0xac00) % 28 !== 0
    : /\d/.test(last) ? CLOSED_DIGITS.includes(last)
    : CLOSED_LETTERS.includes(last.toLowerCase());
  return word + (closed ? "이" : "가");
}

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
        : spread ? "이 기간의 흔들림 약 ±" + amount(spread, facts.unit) : null},
    after: {caption: "이 구간의 중앙값", value: amount(facts.typical, facts.unit),
      note: gap === 0 ? null : "처음보다 " + amount(Math.abs(gap), facts.unit) + (gap > 0 ? " 높음" : " 낮음")
        + (ratio !== null && ratio >= 1.5 ? " · 약 " + digits(ratio) + "배" : "")},
  };
}

/** 주요 변화로 고른 이유를 꼬리표가 아니라 설명으로 말한다. */
export const CHANGE_WHY = {
  sustained: "이 기록에서 오래 이어진 변화라서 먼저 보여 드립니다.",
  "record-end": "기록이 끝날 때까지 이어진 변화라서 먼저 보여 드립니다.",
  largest: "이 기록에서 변화 폭이 큰 구간이라서 먼저 보여 드립니다.",
} as const;
