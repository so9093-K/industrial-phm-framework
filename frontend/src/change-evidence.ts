/** 선택한 변화의 맥락과 두 기간 비교의 범위 이탈 요약. */
import {countShare} from "./analysis-messages.ts";
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

/** 범위: 변화 구간의 값이 몇 회 중 몇 회 초기(기록 처음 30%) 값의 90%가 있던 범위 밖이었는지. */
export function rangeEvidence(facts: {usable: number; outside: number | null; low: number | null; high: number | null;
  unit: string | null; condition: string | null; percent?: number | null},
  names: {a: string; b: string} = {a: "초기", b: "특이사항 구간"}): string | null {
  const {usable, outside, low, high, unit, condition, percent = null} = facts;
  if (!usable || outside === null || low === null || high === null) return null;
  const range = names.a + " 값의 90% 범위(" + value(low) + "~" + withUnit(high, unit) + ")";
  const lead = (condition ? condition + " 중 값끼리 · " : "") + names.b + " ";
  if (outside === 0) return lead + count(usable) + "회 모두 " + range + " 안";
  if (outside >= usable) return lead + count(usable) + "회 모두 " + range + " 밖";
  const shown = percent !== null ? percent.toFixed(1) + "%" : countShare(outside, usable);
  return lead + count(usable) + "회 중 " + count(outside) + "회(" + shown + ")가 " + range + " 밖";
}
