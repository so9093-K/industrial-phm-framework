/** 선택한 변화의 맥락과 두 기간 비교의 범위 이탈 요약. */
import {countShare} from "./analysis-messages.ts";
import {findingLinks, relatedSignalHref, type FoundInterval, type RecordFindings} from "./record-findings.ts";
import {vibrationLinks, type VibrationChange, type VibrationFindings} from "./vibration-findings.ts";

/** 근거를 찾을 변화: 시계열 기록의 한 구간, 또는 진동 기록의 한 변화. */
export type EvidenceFocus =
  | {kind: "history"; item: FoundInterval; record: RecordFindings; condition: string | null}
  | {kind: "vibration"; change: VibrationChange; record: VibrationFindings};

export type ChangeFollowup = {label: string; href: string};

export function changeFollowup(asset: string, focus: EvidenceFocus, replaying = false): ChangeFollowup | null {
  if (focus.kind === "history") {
    const {item, record} = focus;
    const {relation, compare, previous} = findingLinks(asset, item, record.baseline, record.bucketSeconds, record.record);
    if (relation) return relation;
    const href = compare ?? previous;
    return href ? {label: "변화 전후 값 비교", href} : null;
  }
  if (!focus.record.bindingId) return null;
  // 대화가 말한 변화를 그대로 보여 주는 비교로 잇는다. 변화가 시작된 측정의 이상 점수는 '기준 이하'로
  // 나올 수 있어(베어링 1-1의 72번째: 0.568 < 0.754), 대화와 반대로 읽혔다.
  return {label: replaying ? "이 시점까지의 진동 비교" : "초기와 변화 구간의 진동 비교",
    href: vibrationLinks(asset, focus.change).compare};
}

/** AI가 대화에서 고른 분석 화면으로 가는 링크(서버의 분석 이름 → 이 변화의 신호·기간으로 연 화면).
 * 이미 있는 화면의 링크를 그대로 쓴다. 이 변화에서 열 수 없는 화면은 빠진다. */
export function changeAnalyses(asset: string, focus: EvidenceFocus): Record<string, ChangeFollowup> {
  const out: Record<string, ChangeFollowup> = {};
  if (focus.kind === "history") {
    const {item, record} = focus;
    const own = findingLinks(asset, item, record.baseline, record.bucketSeconds, record.record);
    const compare = own.compare ?? own.previous;
    if (compare) out.open_compare = {label: "기간 비교에서 보기", href: compare};
    if (own.relation) out.open_relation = {label: "신호 관계에서 보기", href: own.relation.href};
    if (own.signal) {
      out.open_signals = {label: "실측 신호에서 보기", href: relatedSignalHref(own.signal, item, record.signals)};
      // 3상 전력: 같은 구간을 연 신호 화면 주소에서 분석만 바꾸고, 비교 기준은 기간 비교와 같게.
      const url = new URL(own.signal, "http://local");
      url.searchParams.set("tab", "change");
      url.searchParams.set("method", "electrical");
      const reference = compare ? new URL(compare, "http://local").searchParams.get("compare_a") : null;
      if (reference) url.searchParams.set("compare_a", reference);
      out.open_phase_balance = {label: "3상 전력에서 보기", href: url.pathname + url.search};
    }
    return out;
  }
  const own = vibrationLinks(asset, focus.change);
  out.open_compare = {label: "기간 비교에서 보기", href: own.compare};
  out.open_spectrum = {label: "주파수에서 보기", href: own.spectrum};
  out.open_signals = {label: "실측 신호에서 보기", href: own.signal};
  out.open_outlook = {label: "전망·예상 여유에서 보기", href: own.outlook};
  return out;
}

const count = (value: number) => value.toLocaleString("ko-KR");
/** 문장 안의 값: 유효 숫자 세 자리. */
const value = (raw: number) => raw.toLocaleString("ko-KR", {maximumSignificantDigits: 3});
const withUnit = (raw: number, unit: string | null) => value(raw) + (unit ? " " + unit : "");

/** 범위: 변화 구간의 값이 몇 회 중 몇 회 초기(기록 처음 30%) 값의 90%가 있던 범위 밖이었는지. */
export function rangeEvidence(facts: {usable: number; outside: number | null; low: number | null; high: number | null;
  unit: string | null; percent?: number | null},
  names: {a: string; b: string} = {a: "초기", b: "특이사항 구간"}): string | null {
  const {usable, outside, low, high, unit, percent = null} = facts;
  if (!usable || outside === null || low === null || high === null) return null;
  const range = names.a + " 값의 90% 범위(" + value(low) + "~" + withUnit(high, unit) + ")";
  const lead = names.b + " ";
  if (outside === 0) return lead + count(usable) + "회 모두 " + range + " 안";
  if (outside >= usable) return lead + count(usable) + "회 모두 " + range + " 밖";
  const shown = percent !== null ? percent.toFixed(1) + "%" : countShare(outside, usable);
  return lead + count(usable) + "회 중 " + count(outside) + "회(" + shown + ")가 " + range + " 밖";
}
