/** One wording for a server-computed limit reach, kept on its own axis: acquisition
 * counts are never turned into durations, and time offsets count from the last record. */
import type {Reach} from "./projections.ts";

export type ReachAxis = "time" | "acquisition";

function offset(value: number, axis: ReachAxis): string {
  if (axis === "acquisition") return "추가 측정 " + value + "회 후";
  const hours = value / 3600;
  // Under an hour reads in minutes; "약 0.0시간" said nothing.
  if (hours < 1) return "마지막 기록 후 약 " + Math.max(1, Math.round(value / 60)) + "분";
  return "마지막 기록 후 약 " + (hours < 48 ? hours.toFixed(1) + "시간" : (hours / 24).toFixed(1) + "일");
}

export function reachText(value: Reach | null | undefined, axis: ReachAxis): string {
  if (!value) return "계산 안 됨";
  if (value.state === "already") return "이미 넘음";
  if (value.state === "expected")
    return value.expected === null ? "닿을 것으로 계산됨" : offset(value.expected, axis) + " 닿음";
  if (value.state === "possible")
    return "예측 범위에서만 닿을 수 있음" + (value.earliest === null ? "" : " · 빠르면 " + offset(value.earliest, axis));
  return "계산 범위 안에서는 닿지 않음";
}
