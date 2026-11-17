/** 변화가 기록 전체의 어디에 있었는지 보여 주는 표시용 계열 (findings의 `overview`). */
import {yTicks, type Tick} from "./chart-axis.ts";

export type OverviewRow = {at: string; mean: number; low: number; high: number; judged: number | null; join: boolean};
/** 판단한 값이 기록 전체와 어떻게 다른지: 같음, 한 운전 수준만, 정지를 뺀 값. */
export type OverviewKind = "all" | "level" | "running";

function invalid(): never { throw new Error("기록 전체 추이의 형식이 올바르지 않습니다."); }
const finite = (raw: unknown): number => typeof raw === "number" && Number.isFinite(raw) ? raw : invalid();

export function parseOverview(raw: unknown): OverviewRow[] {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) invalid();
  return raw.map((row: unknown) => {
    if (!Array.isArray(row) || row.length !== 6 || typeof row[0] !== "string" || Number.isNaN(Date.parse(row[0]))
      || typeof row[5] !== "boolean") invalid();
    const [at, mean, low, high, judged, join] = row;
    const read = {at, mean: finite(mean), low: finite(low), high: finite(high), judged: judged === null ? null : finite(judged), join};
    if (read.low > read.mean || read.mean > read.high) invalid();
    return read;
  });
}
export function overviewKind(raw: unknown): OverviewKind {
  return raw === "level" || raw === "running" ? raw : "all";
}

type Span = {from: string; to: string};
export type OverviewChart = {
  width: number; height: number; start: number; end: number; ticks: Tick[];
  /** 칸마다 최저~최고 (신호 그래프의 옅은 막대와 같은 뜻). */
  ranges: {x: number; low: number; high: number}[];
  /** 모든 운전 상태의 평균. 판단한 값이 같으면 그리지 않는다. */
  all: string | null;
  /** 변화를 판단한 값. 이어진 칸은 선, 홀로 있는 칸은 점으로 그린다. */
  judged: string; dots: {x: number; y: number}[];
  bands: {baseline: {x: number; width: number} | null; change: {x: number; width: number}; window: {x: number; width: number} | null};
};

/** 기록 전체를 그리는 좌표. 기준 구간·변화 구간·확대한 구간은 같은 시간축에 띠로 표시한다. */
export function overviewChart(rows: OverviewRow[], kind: OverviewKind,
  marks: {baseline: Span | null; change: Span; window: Span | null; record: Span | null}, width = 1000, height = 96): OverviewChart | null {
  if (rows.length < 2) return null;
  const times = rows.map((row) => Date.parse(row.at));
  const start = marks.record ? Math.min(Date.parse(marks.record.from), times[0]) : times[0];
  const end = Math.max(marks.record ? Date.parse(marks.record.to) : times.at(-1)!, times.at(-1)!, start + 1);
  const lowest = Math.min(...rows.map((row) => row.low)), highest = Math.max(...rows.map((row) => row.high));
  const pad = highest > lowest ? (highest - lowest) * 0.08 : Math.max(Math.abs(lowest) * 0.05, 1);
  const lo = lowest - pad, hi = highest + pad;
  const x = (at: number) => Math.max(0, Math.min(width, (at - start) / (end - start) * width));
  const y = (value: number) => height - (value - lo) / (hi - lo) * height;
  const line = (value: (row: OverviewRow) => number | null) => {
    let path = "", previous: number | null = null;
    rows.forEach((row, i) => {
      const v = value(row);
      if (v === null) { previous = null; return; }
      path += (previous !== null && row.join ? "L" : "M") + x(times[i]).toFixed(1) + "," + y(v).toFixed(1) + " ";
      previous = i;
    });
    return path.trim();
  };
  const judgedValue = (row: OverviewRow) => kind === "all" ? row.mean : row.judged;
  // 앞뒤 칸과 이어지지 않는 판단 값은 선으로 보이지 않으므로 점으로 남긴다.
  const dots = rows.flatMap((row, i) => {
    const v = judgedValue(row);
    if (v === null) return [];
    const before = i > 0 && row.join && judgedValue(rows[i - 1]) !== null;
    const after = i + 1 < rows.length && rows[i + 1].join && judgedValue(rows[i + 1]) !== null;
    return before || after ? [] : [{x: x(times[i]), y: y(v)}];
  });
  const band = (span: Span | null, least: number) => {
    if (!span) return null;
    const from = x(Date.parse(span.from)), to = x(Date.parse(span.to));
    return {x: Math.min(from, width - least), width: Math.max(least, to - from)};
  };
  return {
    width, height, start, end, ticks: yTicks(lo, hi, 0, height, 3),
    ranges: rows.map((row, i) => ({x: x(times[i]), low: y(row.low), high: y(row.high)})),
    all: kind === "all" ? null : line((row) => row.mean),
    judged: line(judgedValue), dots,
    bands: {baseline: band(marks.baseline, 1), change: band(marks.change, 3)!, window: band(marks.window, 3)},
  };
}
