/** One wording for a server-computed limit reach, kept on its own axis: acquisition
 * counts are never turned into durations, and time offsets count from the last record. */
import type {Reach} from "./projections.ts";
import {elapsedText} from "./time-axis.ts";

export type ReachAxis = "time" | "acquisition";

function offset(value: number, axis: ReachAxis): string {
  if (axis === "acquisition") return "추가 측정 " + value + "회 후";
  const hours = value / 3600;
  // Under an hour reads in minutes; "약 0.0시간" said nothing.
  if (hours < 1) return "마지막 기록 후 약 " + Math.max(1, Math.round(value / 60)) + "분";
  return "마지막 기록 후 약 " + (hours < 48 ? hours.toFixed(1) + "시간" : (hours / 24).toFixed(1) + "일");
}

/** The same reach as a duration when the measurement interval is recorded or assumed. */
export function reachDuration(value: Reach | null | undefined, period: number | null): string {
  const steps = value?.state === "expected" ? value.expected : value?.state === "possible" ? value.earliest : null;
  if (steps === null || steps === undefined || period === null) return "";
  return offset(steps * period, "time").replace("마지막 기록 후 ", "");
}

/** Calendar context applies only to timestamped records, never to acquisition/receipt order. */
export function recordAgeText(last: string, now: number): string {
  const age = (now - Date.parse(last)) / 1000;
  return Number.isFinite(age) && age >= 60
    ? "기록이 " + elapsedText(age) + " 전에 끝났습니다. 전망은 마지막 기록 시점 기준입니다." : "";
}

export function reachCalendarText(value: Reach | null | undefined, last: string, now: number): string {
  const seconds = value?.state === "expected" ? value.expected : value?.state === "possible" ? value.earliest : null;
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return "";
  const at = Date.parse(last) + seconds * 1000;
  if (!Number.isFinite(at) || !Number.isFinite(now)) return "";
  const clock = new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  if (value?.state === "possible")
    return "예측 범위의 가장 이른 도달 시각 " + clock + " (KST)" + (at <= now ? " · 지난 시점" : "");
  return at <= now
    ? "도달 예상 시점이 지났습니다 (" + clock + " KST). 실제 도달 여부는 이후 측정으로 확인하세요."
    : "도달 예상 시각 " + clock + " (KST)";
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
