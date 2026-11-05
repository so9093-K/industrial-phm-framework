import {object} from "./writes.ts";
import {focusParams} from "./signal-selection.ts";
/** The stored observations a result belongs to, independent of labels or current data bounds. */
export type RecordContext = {key: string; sourceId: string; pointId: string | null; interpretationId: string; unit?:string|null; meaningLabel?: string | null;
  record: {from: string; to: string}};
export function recordContext(raw: unknown): RecordContext | null {
  const row = object(raw), span = object(row?.record);
  if (!row || row.key === undefined) return null; // older saved results
  if (typeof row.key !== "string" || !row.key || typeof row.source_id !== "string" || !row.source_id
    || !(row.measurement_point_id === null || typeof row.measurement_point_id === "string")
    || typeof row.interpretation_id !== "string" || !row.interpretation_id || !span
    || typeof span.from !== "string" || typeof span.to !== "string"
    || !Number.isFinite(Date.parse(span.from)) || !Number.isFinite(Date.parse(span.to))
    || Date.parse(span.from) >= Date.parse(span.to)) throw new Error("분석 대상 기록을 확인할 수 없습니다.");
  return {key: row.key, sourceId: row.source_id, pointId: row.measurement_point_id,
    interpretationId: row.interpretation_id, unit:typeof row.unit==="string"?row.unit:null, meaningLabel:typeof row.observed_property === "string" ? row.observed_property : null, record: {from: span.from, to: span.to}};
}
export function recordParams(record: RecordContext | null | undefined): Record<string,string> {
  return record ? {record_key:record.key, ...focusParams({source: record.sourceId, point: record.pointId, interpretation: record.interpretationId})} : {};
}
