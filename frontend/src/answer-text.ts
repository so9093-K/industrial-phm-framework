/** An AI answer split so its measured values stand out: "0.617 g", "226 V", "약 4.4배", "12%". */
const VALUE = /[+-]?\d[\d,]*(?:\.\d+)?\s?(?:g|V|A|Hz|kW|kVA|kVar|%|배)(?![A-Za-z])/g;

export type AnswerPart = {text: string; value: boolean};

export function answerParts(text: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let at = 0;
  for (const match of text.matchAll(VALUE)) {
    if (match.index > at) parts.push({text: text.slice(at, match.index), value: false});
    parts.push({text: match[0], value: true});
    at = match.index + match[0].length;
  }
  if (at < text.length) parts.push({text: text.slice(at), value: false});
  return parts;
}

/** Whether an answer's analysis link says something new: the same screen is not offered twice in a row. */
export function freshLink<T extends {analysis?: string | null}>(thread: T[], index: number): boolean {
  const own = thread[index]?.analysis;
  return !!own && thread[index - 1]?.analysis !== own;
}
