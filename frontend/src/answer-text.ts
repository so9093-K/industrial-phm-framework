/** Show bold phrases and measured values without interpreting the rest as markup. */
const EMPHASIS = /\*\*([^*\n]+)\*\*|[+-]?\d[\d,]*(?:\.\d+)?\s?(?:g|V|A|Hz|kW|kVA|kVar|%|배)(?![A-Za-z])/g;

export type AnswerPart = {text: string; emphasis: boolean};

export function answerParts(text: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let at = 0;
  for (const match of text.matchAll(EMPHASIS)) {
    if (match.index > at) parts.push({text: text.slice(at, match.index), emphasis: false});
    parts.push({text: match[1] ?? match[0], emphasis: true});
    at = match.index + match[0].length;
  }
  if (at < text.length) parts.push({text: text.slice(at), emphasis: false});
  return parts;
}

/** Whether an answer's analysis link says something new: the same screen is not offered twice in a row. */
export function freshLink<T extends {analysis?: string | null}>(thread: T[], index: number): boolean {
  const own = thread[index]?.analysis;
  return !!own && thread[index - 1]?.analysis !== own;
}
