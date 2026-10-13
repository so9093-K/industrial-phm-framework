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
