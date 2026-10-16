// One display policy for the Korean Web. API instants stay UTC ISO 8601; the screen shows
// KST, a fixed UTC+09:00 offset, so display and date-time input conversion round-trip exactly.
// This changes presentation only: an original measurement time is never relabelled as a
// receipt, commit or analysis time, and the stored instant is never rewritten.
const OFFSET_MS = 9 * 60 * 60 * 1000;
export const ZONE = "KST";
const pad = (value) => String(value).padStart(2, "0");

function shifted(value) {
  const stamp = value instanceof Date ? value.getTime()
    : typeof value === "number" ? value
    : typeof value === "string" && value ? Date.parse(value) : NaN;
  return Number.isFinite(stamp) ? new Date(stamp + OFFSET_MS) : null;
}

export function formatTime(value, {seconds = true, zone = true, missing = "시각 없음"} = {}) {
  const at = shifted(value);
  if (!at) return missing;
  const text = at.getUTCFullYear() + "-" + pad(at.getUTCMonth() + 1) + "-" + pad(at.getUTCDate())
    + " " + pad(at.getUTCHours()) + ":" + pad(at.getUTCMinutes()) + (seconds ? ":" + pad(at.getUTCSeconds()) : "");
  return zone ? text + " " + ZONE : text;
}

// Compact axis label: a clock for short spans, month-day and minute once the span may cross a day.
export function formatAxisTime(value, spanMs = 0) {
  const at = shifted(value);
  if (!at) return "";
  const clock = pad(at.getUTCHours()) + ":" + pad(at.getUTCMinutes());
  return spanMs >= 6 * 60 * 60 * 1000
    ? pad(at.getUTCMonth() + 1) + "-" + pad(at.getUTCDate()) + " " + clock
    : clock + ":" + pad(at.getUTCSeconds());
}

// A datetime-local value has no offset. In this Web it is entered as KST, so send the same
// instant explicitly; never append "Z" and silently move the user's chosen time by nine hours.
export function kstInputToInstant(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/.exec(value || "");
  if (!match) throw new Error("invalid-local-time");
  return match[1] + "-" + match[2] + "-" + match[3] + "T" + match[4] + ":" + match[5] + ":" + (match[6] || "00") + "+09:00";
}

// A measurement burst may contain many waveform samples. Counts are additional measurements,
// positions remain identifiers, and elapsed time needs a recorded or explicitly assumed cadence.
export function measurementPeriod(data) {
  return ["recorded", "assumed"].includes(data.time_basis)
    && typeof data.period_seconds === "number" && Number.isFinite(data.period_seconds) && data.period_seconds > 0
    ? data.period_seconds : null;
}
export function formatDuration(seconds) {
  const one = value => value.toLocaleString("ko-KR", {maximumFractionDigits: 1});
  return seconds >= 86400 ? one(seconds / 86400) + "일" : seconds >= 3600 ? one(seconds / 3600) + "시간"
    : seconds >= 60 ? one(seconds / 60) + "분" : one(seconds) + "초";
}
export function formatMargin(data, offset) {
  if (data.offset_unit !== "acquisition") return formatDuration(offset);
  const period = measurementPeriod(data);
  return period === null ? "추가 측정 " + offset.toLocaleString("ko-KR", {maximumFractionDigits: 3}) + "회"
    : formatDuration(offset * period);
}
export function measurementIntervalNote(data) {
  if (data.axis !== "acquisition") return "";
  const period = measurementPeriod(data);
  return period === null ? "측정 간격 정보 없음 · 시간 환산 불가"
    : (data.time_basis === "recorded" ? "기록된 " : "가정한 ") + formatDuration(period) + " 측정 간격이 유지될 경우";
}
