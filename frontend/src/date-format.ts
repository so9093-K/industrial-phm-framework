/** Display real timestamps in Korean standard time, regardless of the browser's locale or zone. */
export const SEOUL = "Asia/Seoul";
const KST_OFFSET = "+09:00";
export const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

type DateInput = string | number | Date;
type Zone = typeof SEOUL | "UTC";
type Precision = "minute" | "second" | "millisecond";
const clocks = new Map<string, Intl.DateTimeFormat>();

function render(at: DateInput, key: string, options: Intl.DateTimeFormatOptions): string {
  const date = new Date(at);
  if (!Number.isFinite(date.getTime())) return "시각 해석 불가";
  let formatter = clocks.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("ko-KR", options);
    clocks.set(key, formatter);
  }
  return formatter.format(date);
}

/** Numeric calendar dates for full timestamps and graph ticks. */
export function dateLabel(at: DateInput, year = true, zone: Zone = SEOUL): string {
  return render(at, `date:${zone}:${year}`, {
    timeZone: zone, year: year ? "numeric" : undefined, month: "numeric", day: "numeric",
  });
}

export function timeLabel(at: DateInput, precision: Precision = "minute", zone: Zone = SEOUL): string {
  return render(at, `time:${zone}:${precision}`, {
    timeZone: zone, hourCycle: "h23", hour: "2-digit", minute: "2-digit",
    second: precision !== "minute" ? "2-digit" : undefined,
    fractionalSecondDigits: precision === "millisecond" ? 3 : undefined,
  });
}

/** A full timestamp on screen: the same form as every other moment ('10월 22일(목) 23:59:08'), with
 * seconds unless the caller asks for minutes. Graph ticks keep their short numeric dates (timeTicks). */
export function dateTime(at: DateInput | null, precision: Precision = "second"): string {
  return clockText(at, precision);
}

export function dateTimeRange(from: DateInput, to: DateInput, precision: Precision = "second"): string {
  const end = dateLabel(from) === dateLabel(to) ? timeLabel(to, precision) : clockText(to, precision);
  return clockText(from, precision) + " ~ " + end;
}

export function dayText(at: DateInput, weekday = false): string {
  return render(at, `day:${weekday}`, {timeZone: SEOUL, month: "long", day: "numeric",
    weekday: weekday ? "short" : undefined}).replace(" (", "(");
}

/** A moment in a record, written the same way on every screen: '10월 22일(목) 23:59'. */
export function clockText(at: DateInput | null, precision: Precision = "minute"): string {
  if (at === null) return "기록 없음";
  if (!Number.isFinite(new Date(at).getTime())) return "시각 해석 불가";
  return dayText(at, true) + " " + timeLabel(at, precision);
}

/** When the screen last read its list (today's clock): the time alone today, with its day otherwise. */
export function refreshedText(at: DateInput | null, now: DateInput = Date.now()): string {
  if (at === null) return "기록 없음";
  return dateLabel(at) === dateLabel(now) ? timeLabel(at) : clockText(at);
}

export function spanText(from: number, to: number): string {
  return clockText(from) + " ~ " + (dateLabel(from) === dateLabel(to) ? timeLabel(to) : clockText(to));
}

/** Machine-readable local form values are separate from the displayed date. */
export function kstInput(at: string | number, precision: "minute" | "second" = "minute"): string {
  const time = typeof at === "number" ? at : Date.parse(at);
  return Number.isFinite(time) ? new Date(time + KST_OFFSET_MS).toISOString().slice(0, precision === "minute" ? 16 : 19) : "";
}

export function kstInstant(value: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value);
  if (!match) throw new Error("시각 형식을 확인하세요.");
  const local = match[1] + "T" + match[2] + ":" + match[3] + ":" + (match[4] ?? "00");
  const result = local + KST_OFFSET;
  if (kstInput(result, "second") !== local) throw new Error("시각 형식을 확인하세요.");
  return result;
}
