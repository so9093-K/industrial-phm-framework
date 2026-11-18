/** 상태 요약의 "이 변화를 확인한 근거" 한 줄씩. 각 줄은 '자세히'로 여는 분석 화면과 같은 계산의 숫자로
 * 확인한 사실만 말하고, 판정 꼬리표(지속적·일시적·이상)를 붙이지 않는다. */
import {countShare, shiftedBand, times} from "./analysis-messages.ts";
import type {BandShare} from "./spectrum.ts";
import type {FoundInterval, RecordFindings} from "./record-findings.ts";
import type {VibrationChange, VibrationFindings} from "./vibration-findings.ts";

/** 근거를 찾을 변화: 시계열 기록의 한 구간, 또는 진동 기록의 한 변화. */
export type EvidenceFocus =
  | {kind: "history"; item: FoundInterval; record: RecordFindings; condition: string | null}
  | {kind: "vibration"; change: VibrationChange; record: VibrationFindings};

const count = (value: number) => value.toLocaleString("ko-KR");
/** 문장 안의 값: 유효 숫자 세 자리. */
const value = (raw: number) => raw.toLocaleString("ko-KR", {maximumSignificantDigits: 3});
const withUnit = (raw: number, unit: string | null) => value(raw) + (unit ? " " + unit : "");
const hz = (raw: number) => Math.round(raw).toLocaleString("ko-KR");
const share = (raw: number) => Math.round(raw * 100) + "%";

/** 범위: 변화 구간의 값이 몇 회 중 몇 회 기록 처음 30% 값의 90%가 있던 범위 밖이었는지. */
export function rangeEvidence(facts: {usable: number; outside: number | null; low: number | null; high: number | null;
  unit: string | null; condition: string | null; percent?: number | null}): string | null {
  const {usable, outside, low, high, unit, condition, percent = null} = facts;
  if (!usable || outside === null || low === null || high === null) return null;
  const range = "기록 처음 30% 값의 90%가 있던 범위(" + value(low) + "~" + withUnit(high, unit) + ")";
  const lead = (condition ? "같은 운전 수준(" + condition + ")끼리 견주면 " : "") + "변화 구간 ";
  if (outside === 0) return lead + count(usable) + "회 모두 " + range + " 안이었습니다.";
  if (outside >= usable) return lead + count(usable) + "회 모두 " + range + " 밖이었습니다.";
  const shown = percent !== null ? percent.toFixed(1) + "%" : countShare(outside, usable);
  return lead + count(usable) + "회 중 " + count(outside) + "회(" + shown + ")가 " + range + " 밖이었습니다.";
}

/** 함께 달라진 것: 같은 구간(시계열)·같은 측정(진동)에서 함께 달라진 신호 한두 개. */
export function relatedEvidence(rows: {label: string; reference: number; current: number; unit: string | null}[],
  where: "구간" | "측정"): string | null {
  if (!rows.length) return null;
  return "같은 " + where + "에서 "
    + rows.slice(0, 2).map(row => row.label + " " + value(row.reference) + " → " + withUnit(row.current, row.unit)).join(", ")
    + "도 함께 달라졌습니다.";
}

/** 주파수: 비중이 가장 크게 늘어난 대역. 그런 대역이 없으면 전체 에너지가 몇 배가 됐는지. */
export function spectrumEvidence(channels: {label: string; ratio: number | null; shares: BandShare[]}[]): string | null {
  const moved = channels.flatMap(channel => {
    const band = shiftedBand(channel.shares);
    return band ? [{channel, band}] : [];
  }).sort((x, y) => (y.band.b - y.band.a) - (x.band.b - x.band.a))[0];
  if (moved) return moved.channel.label + "에서 " + hz(moved.band.from) + "~" + hz(moved.band.to)
    + " Hz 대역이 전체 에너지에서 차지하는 비중이 " + share(moved.band.a) + " → " + share(moved.band.b) + "로 커졌습니다.";
  const strongest = channels.filter(channel => channel.ratio !== null)
    .sort((x, y) => Math.abs(Math.log(y.ratio!)) - Math.abs(Math.log(x.ratio!)))[0];
  return strongest ? strongest.label + " 전체 에너지가 기록 처음의 " + times(strongest.ratio!) + "가 됐고, 비중이 10%p 이상 커진 대역은 없습니다." : null;
}
