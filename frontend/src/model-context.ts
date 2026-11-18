/** 상태 요약에서 고른 변화 구간에 모델이 어떻게 판단했는지 센다. 최근 결과만으로는
 * 그 변화를 모델도 보았는지 알 수 없어서, 같은 구간의 결과를 따로 센다. */
import type {ScoreTrend} from "./model-trend.ts";
import {RARE_IN_REFERENCE, type ModelOperation} from "./model-operation.ts";
import {bandName} from "./record-findings.ts";

export type ModelAtChange = {analyzed: number; exceeded: number};

/** `span`이 ms 시각이면(시계열 모델) 결과 위치는 구간이 끝난 시각(µs)이고, 측정 회차면(진동 모델) 회차다.
 * 구간이 변화 안에서 끝난 결과만 센다. 분석에서 제외된 결과는 세지 않는다. */
export function modelAtChange(trend: ScoreTrend, span: {from: number; to: number}, axis: "time" | "acquisition"): ModelAtChange {
  let analyzed = 0, exceeded = 0;
  for (const point of trend.points) {
    if (point.pointer.state !== "analyzed" || point.score === null) continue;
    const at = axis === "time" ? point.pointer.position / 1000 : point.pointer.position;
    if (at < span.from || at > span.to) continue;
    analyzed++;
    if (point.exceeds) exceeded++;
  }
  return {analyzed, exceeded};
}

/** 변화가 판단된 운전 상태가 모델 학습 기간에 거의 없었다면 그 비율. 그런 상태의 기준 초과는
 * 모델이 그 상태를 배우지 못해서일 수 있어, 변화를 확인한 근거로 읽으면 안 된다. 아니면 null. */
export function rareAtChange(operation: ModelOperation, condition: string): number | null {
  const shares = operation.reference?.shares;
  if (!shares) return null;
  for (let band = 1; band < shares.length; band++) {
    if (bandName(operation.names, band) === condition) return shares[band] < RARE_IN_REFERENCE ? shares[band] : null;
  }
  return null;
}

/** 상태 요약의 모델 근거 한 줄: 이 변화 구간을 분석한 모델마다 몇 회 중 몇 회 기준을 넘었는지.
 * 절반 이상 넘은 모델과 절반 미만인 모델이 함께 있으면 판단이 갈렸다고 먼저 말하고, 변화가 모델이 거의
 * 학습하지 않은 운전 상태에서 났으면 그 초과만으로 확인하기 어렵다고 덧붙인다. 척도가 다른 점수는 견주지 않는다. */
export function modelEvidence(rows: {name: string; analyzed: number; exceeded: number}[],
  unlearned: {condition: string; share: number} | null = null): string | null {
  const read = rows.filter(row => row.analyzed > 0);
  if (!read.length) return null;
  const over = read.filter(row => row.exceeded * 2 >= row.analyzed), under = read.filter(row => row.exceeded * 2 < row.analyzed);
  const count = (value: number) => value.toLocaleString("ko-KR");
  const list = [...over, ...under].map(row => row.name + " " + count(row.analyzed) + "회 중 " + count(row.exceeded) + "회").join(", ");
  const lead = over.length && under.length ? "판단이 갈림 · 기준 초과 " : "기준 초과 ";
  const caution = unlearned && over.length
    ? " · 학습 기간에 " + unlearned.condition + (unlearned.share === 0 ? " 없음" : unlearned.share < 0.01 ? " 1% 미만" : " " + Math.round(unlearned.share * 100) + "%")
    : "";
  return lead + list + caution;
}
