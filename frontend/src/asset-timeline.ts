/** 설비 시간축: 한 설비에서 찾은 변화, 그때의 운전 상태을 같은 가로축에 모은다.
 * 시간이 겹치는 변화는 한 시기로 묶어, 무엇이 먼저였고 무엇이 함께 변했는지 그래프에서 보이게 한다.
 * 새 계산은 하지 않는다. 서버가 준 변화 구간·운전 수준 시간표를 배치만 한다. */
import type {LevelNames} from "./record-findings.ts";

export type Span = {from: number; to: number};
export type TimelinePoint = {x: number; value: number; join?: boolean};

/** 시간축 한 줄에 그리는 변화 하나. `points`는 기록 전체, `detail`은 변화 앞뒤를 더 촘촘히 읽은 값(있으면). */
export type TimelineLane = {
  matched?:TimelinePoint[];
  key: string; label: string; condition: string | null; unit: string | null;
  points: TimelinePoint[]; detail: TimelinePoint[];
  usual: {low: number; high: number}; interval: Span; numbers: string; focus: boolean; up: boolean;
  /** 이 변화에 마지막으로 남긴 판단(예: '계속 관찰 · 11월 19일'). */
  decision?: string | null;
  values?: {before:number|null;after:number|null;latest:{value:number;at:number}|null};
};
export type TimelineOperation = {names: LevelNames; columns: (Span & {shares: number[]})[]};
/** 시간이 겹치는 변화를 한 시기로 묶는다. 시기는 시작 순서이고, 시기 안의 변화도 시작 순서다. */
export function episodes<T>(items: T[], span: (item: T) => Span): (Span & {members: T[]})[] {
  const sorted = [...items].sort((a, b) => span(a).from - span(b).from || span(a).to - span(b).to);
  const out: (Span & {members: T[]})[] = [];
  for (const item of sorted) {
    const own = span(item), last = out.at(-1);
    if (last && own.from <= last.to) { last.to = Math.max(last.to, own.to); last.members.push(item); }
    else out.push({from: own.from, to: own.to, members: [item]});
  }
  return out;
}

/** 변화 구간을 확대해 볼 범위: 시기 길이의 두 배씩 앞뒤를 더해 전후 맥락을 남긴다(기록 밖으로는 넓히지 않는다). */
export function focusWindow(record: Span, episode: Span): Span {
  const length = Math.max(episode.to - episode.from, (record.to - record.from) / 200);
  return {from: Math.max(record.from, episode.from - 2 * length), to: Math.min(record.to, episode.to + 2 * length)};
}
/** 기록 전체에서 시기가 거의 보이지 않을 만큼(1/60 미만) 짧을 때만 확대해 시작한다. 그 밖에는 기록 전체가
 * 곧 맥락이다: 변화 전의 흐름, 운전 상태가 바뀐 때, 측정값의 변화 양상을 한 화면에 보여 준다. */
export function startsZoomed(record: Span, episode: Span): boolean {
  return episode.to - episode.from < (record.to - record.from) / 60;
}

/** 운전 수준 시간표(칸마다 수준별 측정 수)를 칸마다 비율로. 측정이 없는 칸은 뺀다. */
export function operationColumns(timeline: {at: string; counts: number[]}[], bucketSeconds: number): (Span & {shares: number[]})[] {
  return timeline.flatMap(row => {
    const total = row.counts.reduce((sum, count) => sum + count, 0);
    const from = Date.parse(row.at);
    return total ? [{from, to: from + bucketSeconds * 1000, shares: row.counts.map(count => count / total)}] : [];
  });
}

const KST = 9 * 3600 * 1000;
const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];
/** 시간축의 시각 한 가지 형식: '10월 4일(일) 09:19'. */
export function clockText(ms: number): string {
  const at = new Date(ms + KST);
  const hh = String(at.getUTCHours()).padStart(2, "0"), mm = String(at.getUTCMinutes()).padStart(2, "0");
  return (at.getUTCMonth() + 1) + "월 " + at.getUTCDate() + "일(" + WEEKDAY[at.getUTCDay()] + ") " + hh + ":" + mm;
}
/** 두 시각: 같은 날이면 끝은 시각만 쓴다. */
export function spanText(from: number, to: number): string {
  const start = clockText(from), end = clockText(to);
  return start.slice(0, start.lastIndexOf(" ")) === end.slice(0, end.lastIndexOf(" "))
    ? start + " ~ " + end.slice(end.lastIndexOf(" ") + 1) : start + " ~ " + end;
}

/** 확대했을 때 쓰는 값: 변화 앞뒤를 촘촘히 읽은 값이 있는 범위는 그것으로, 나머지는 기록 전체 값으로. */
export function visiblePoints(lane: Pick<TimelineLane, "points" | "detail">, range: Span, zoomed: boolean): TimelinePoint[] {
  const inside = (point: TimelinePoint) => point.x >= range.from && point.x <= range.to;
  if (!zoomed || lane.detail.length < 2) return lane.points.filter(inside);
  const first = lane.detail[0].x, last = lane.detail.at(-1)!.x;
  return [...lane.points.filter(point => point.x < first || point.x > last), ...lane.detail]
    .filter(inside).sort((a, b) => a.x - b.x);
}

/** 가로 위치에서 가장 가까운 값. 칸 간격의 1.5배보다 멀면 그 자리에는 값이 없다고 본다. */
export function valueAt(points: TimelinePoint[], at: number, reach: number): TimelinePoint | null {
  let best: TimelinePoint | null = null;
  for (const point of points) if (!best || Math.abs(point.x - at) < Math.abs(best.x - at)) best = point;
  return best && Math.abs(best.x - at) <= reach ? best : null;
}
