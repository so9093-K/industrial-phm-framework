import {object, OutcomeUnknown, postReviewWrite, reviewNote, type ReviewAction, type ReviewDecision} from "./review-writes.ts";
import {parseReview} from "./outlook-captures.ts";
import {parseRecordFindings, type FoundInterval} from "./record-findings.ts";
export type ChangeCapture = {id: string; capturedAt: string; finding: FoundInterval; review: ReturnType<typeof parseReview>};
export type ChangePage = {captures: ChangeCapture[]; next: string|null};
const ROUTE = "/api/v1/explore/change-reviews";
const ID = /^change-review-[0-9a-f]{64}$/;
export function parseChangePage(raw: unknown, assetId: string): ChangePage {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.asset_id !== assetId || !Array.isArray(root.captures) || root.captures.length > 20)
    throw new Error("저장한 변화 검토 목록을 확인할 수 없습니다.");
  const seen = new Set<string>();
  const captures = root.captures.map((raw:unknown): ChangeCapture => {
    const row = object(raw), snapshot = object(row?.snapshot), change = object(snapshot?.change), finding = object(change?.finding), identity = object(snapshot?.identity);
    if (!row || typeof row.capture_id !== "string" || !ID.test(row.capture_id) || seen.has(row.capture_id)
      || typeof row.captured_at !== "string" || !Number.isFinite(Date.parse(row.captured_at))
      || change?.asset_id !== assetId || !finding || !identity || identity.asset_id !== assetId
      || identity.finding_id !== finding.review_key || typeof finding.review_key !== "string" || !/^[0-9a-f]{64}$/.test(finding.review_key))
      throw new Error("저장한 변화의 대상이 맞지 않습니다.");
    seen.add(row.capture_id);
    const parsed = parseRecordFindings({schema_version:1, asset_id:assetId,
      meaning:"departures-from-the-first-30-percent-not-fault-diagnosis", baseline:null, bucket_seconds:null,
      signals:[{channel:finding.channel,label:finding.label,unit:finding.unit,state:finding.kind === "level-change" ? "level-change":"scored"}],
      judged:1, unchecked:0, intervals:[finding], interval_count:1},assetId).intervals[0];
    return {id:row.capture_id,capturedAt:row.captured_at,finding:parsed,review:parseReview(row.review)};
  });
  if (root.next_before !== null && (typeof root.next_before !== "string" || root.next_before !== captures.at(-1)?.id))
    throw new Error("저장 검토의 다음 목록을 확인할 수 없습니다.");
  return {captures,next:root.next_before as string|null};
}
export async function readChangeReviews(assetId:string, signal:AbortSignal, selection:Record<string,string> = {}):Promise<ChangePage> {
  const response = await fetch(ROUTE + "?" + new URLSearchParams({asset_id:assetId,...selection}), {signal, cache:"no-store", credentials:"same-origin"});
  if (!response.ok) {await response.body?.cancel().catch(()=>{}); throw new Error("저장한 변화 검토를 불러오지 못했습니다.");}
  const page = parseChangePage(await response.json() as unknown,assetId);
  if (selection.finding_id && page.captures.some(row => row.finding.reviewKey !== selection.finding_id)) throw new Error("다른 변화의 검토가 반환됐습니다.");
  if (selection.capture_id && (page.captures.length !== 1 || page.captures[0].id !== selection.capture_id)) throw new Error("저장한 검토를 찾지 못했습니다.");
  return page;
}
export async function captureChange(assetId:string, finding:FoundInterval, signal:AbortSignal):Promise<string> {
  if (!finding.reviewKey) throw new Error("저장할 변화의 분석 맥락을 확인할 수 없습니다.");
  const result = await postReviewWrite(ROUTE+"/confirm", {asset_id:assetId,finding_id:finding.reviewKey},signal,
    (status) => {if(status===409) throw new Error("측정 기록이나 기준 기간이 바뀌었습니다. 화면을 새로고침해 확인하세요.");});
  if (result.asset_id !== assetId || typeof result.capture_id !== "string" || !ID.test(result.capture_id)) throw new OutcomeUnknown("저장한 검토의 응답을 확인할 수 없습니다.");
  return result.capture_id;
}
export async function reviewChange(assetId:string, capture:ChangeCapture, action:ReviewAction, note:string, eventId:string,
  signal:AbortSignal,decision:ReviewDecision|null):Promise<void> {
  const result = await postReviewWrite(ROUTE+"/action", {asset_id:assetId,capture_id:capture.id,action,note:reviewNote(action,note),event_id:eventId,...(decision?{decision}:{})},signal);
  if (result.asset_id !== assetId || result.capture_id !== capture.id || result.event_id !== eventId
    || result.meaning !== "human-review-not-maintenance-or-diagnosis") throw new OutcomeUnknown("검토 저장 결과를 다시 확인하세요.");
}
