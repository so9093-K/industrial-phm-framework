/** 관제 대화창에서 AI 관제가 하는 말: 특이사항을 사람이 읽는 문장으로. 숫자와 시각은 화면 값을 그대로 쓴다. */

type Ending = "none" | "rieul" | "other";
// 한글이 아닌 끝 글자는 읽는 소리로: L(엘)·R(알)·1(일)·7(칠)·8(팔)은 ㄹ, M·N·0·3·6은 받침, 나머지는 받침 없음.
const SPOKEN: Record<string, Ending> = {
  L: "rieul", R: "rieul", "1": "rieul", "7": "rieul", "8": "rieul",
  M: "other", N: "other", "0": "other", "3": "other", "6": "other",
};
function ending(word: string): Ending {
  const last = word.replace(/[^0-9A-Za-z가-힣]+$/, "").at(-1) ?? "";
  const code = last.charCodeAt(0) - 0xac00;
  if (code >= 0 && code < 11172) return code % 28 === 0 ? "none" : code % 28 === 8 ? "rieul" : "other";
  return SPOKEN[last.toUpperCase()] ?? "none";
}
/** 끝소리에 맞는 조사를 붙인다: 이/가, 은/는, 을/를, 으로/로. */
export function withParticle(word: string, particle: "이/가" | "은/는" | "을/를" | "으로/로"): string {
  const sound = ending(word);
  const [after, plain] = particle.split("/");
  if (particle === "으로/로") return word + (sound === "other" ? after : plain);
  return word + (sound === "none" ? plain : after);
}

/** '초기보다 4.26 V(1.9%) 높음'·'초기의 약 3.7배'를 서술어로. */
function predicate(size: string): string {
  if (size.endsWith("높음")) return size.slice(0, -2) + "높습니다";
  if (size.endsWith("낮음")) return size.slice(0, -2) + "낮습니다";
  return size + "입니다";
}

export type NoticeFacts = {
  what: string; size: string; before: string | null; after: string | null;
  when: string; still: boolean; duration: string;
  load: {label: string; before: string; after: string; ratio: number} | null;
};
/** 한 특이사항을 두 문장으로: 무엇이 얼마나, 언제부터 얼마 동안과 같은 때의 부하. */
export function noticeSentences(facts: NoticeFacts): string[] {
  const values = facts.before && facts.after ? facts.before + "에서 " + withParticle(facts.after, "으로/로") + ", " : "";
  const first = withParticle(facts.what, "이/가") + " " + values + predicate(facts.size) + ".";
  const span = facts.when + "부터 " + (facts.still ? "마지막 측정까지" : facts.duration + " 동안");
  if (!facts.load) return [first, span + " 이어졌습니다."];
  const {label, before, after, ratio} = facts.load;
  const change = ratio < .9 ? "줄었습니다" : ratio > 1.1 ? "늘었습니다" : "거의 같았습니다";
  return [first, span + " 이어졌고, 같은 때 " + withParticle(label, "은/는") + " " + before + "에서 "
    + withParticle(after, "으로/로") + (change === "거의 같았습니다" ? ", " : " ") + change + "."];
}
