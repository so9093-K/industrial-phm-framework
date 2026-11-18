/** One asset as a row of the comparison overview (GET /api/v1/explore/overview): how it ran,
 * its main signal's latest value and trace, and the first change its summary leads with. */
import {parseVibrationChange, type VibrationChange} from "./vibration-findings.ts";
import {recordContext,type RecordContext} from "./record-context.ts";
import {object} from "./writes.ts";
import type {LevelNames} from "./record-findings.ts";
import {parseFindingInterval, type FoundInterval} from "./record-findings.ts";

export type OverviewRow = {
  assetId: string; kind: "history" | "vibration" | null;
  /** Share of time per band over the record, stopped first, with the band names. */
  operation: {key: string | null; names: LevelNames; label: string; shares: number[] | null} | null;
  main: {context?:RecordContext|null; label: string; unit: string | null; axis: "time" | "acquisition"; periodSeconds: number | null;
    latest: {at: string | null; position: number | null; value: number} | null; trace: {x: number; value: number; join?: boolean}[]} | null;
  finding: {label: string; unit: string | null; band: number | null; direction: "up" | "down"; kind: string;
    reference: number | null; typical: number | null; value: number;
    start: string | null; end: string | null; from: number | null; to: number | null} | null;
  findingCount: number; judged: number; copied: number;
  historyInterval: FoundInterval | null;
  vibrationInterval: {change: VibrationChange; sourceId: string; bindingId: string; periodSeconds: number | null} | null;
};

function invalid(): never { throw new Error("설비 개요의 형식이 올바르지 않습니다."); }
const finite = (raw: unknown): number => typeof raw === "number" && Number.isFinite(raw) ? raw : invalid();
const optional = (raw: unknown): number | null => raw === null || raw === undefined ? null : finite(raw);
const count = (raw: unknown): number => Number.isInteger(raw) && (raw as number) >= 0 ? raw as number : invalid();
const text = (raw: unknown): string | null => typeof raw === "string" && raw ? raw : null;

export function parseOverview(raw: unknown, assetId: string): OverviewRow {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || root.asset_id !== assetId) invalid();
  const kind = root.kind === "history" || root.kind === "vibration" ? root.kind : null;
  const op = object(root.operation);
  const operation = op && Array.isArray(op.levels) ? {
    key: text(op.key),
    label: text(op.label) ?? "",
    names: {stoppedBelow: finite(op.stopped_below), unit: "A",
      levels: op.levels.map((entry: unknown) => {
        const level = object(entry) ?? invalid();
        return {low: finite(level.low), high: optional(level.high), typical: finite(level.typical)};
      })},
    shares: Array.isArray(op.shares) ? op.shares.map(finite) : null,
  } : null;
  if (operation?.shares && operation.shares.length !== operation.names.levels.length + 1) invalid();
  const main = object(root.main);
  if(main?.trace_join !== undefined && (!Array.isArray(main.trace_join) || !Array.isArray(main.trace)
    || main.trace_join.length !== main.trace.length || !main.trace_join.every(value => typeof value === "boolean"))) invalid();
  const joins = Array.isArray(main?.trace_join) ? main.trace_join : [];
  const axis = main?.axis === "acquisition" ? "acquisition" : "time";
  const latest = object(main?.latest);
  const finding = object(root.finding);
  const vibration = object(root.vibration_interval);
  return {
    assetId, kind, operation,
    vibrationInterval: vibration ? {
      change: parseVibrationChange(vibration), sourceId: text(vibration.source_id) ?? invalid(),
      bindingId: text(vibration.binding_id) ?? invalid(), periodSeconds: optional(vibration.period_seconds),
    } : null,
    historyInterval: root.history_interval == null ? null : parseFindingInterval(root.history_interval),
    main: main ? {context:recordContext(main.context),
      label: text(main.label) ?? "", unit: text(main.unit), axis, periodSeconds: optional(main.period_seconds),
      latest: latest ? {at: text(latest.at), position: optional(latest.position), value: finite(latest.value)} : null,
      trace: (Array.isArray(main.trace) ? main.trace : []).map((point: unknown, i: number) => {
        if (!Array.isArray(point) || point.length !== 2) invalid();
        const x = axis === "time" ? Date.parse(String(point[0])) : finite(point[0]);
        return Number.isFinite(x) ? {x, value: finite(point[1]), join: joins[i] as boolean | undefined} : invalid();
      }),
    } : null,
    finding: finding ? {
      label: text(finding.label) ?? invalid(), unit: text(finding.unit),
      band: Number.isInteger(finding.band) && (finding.band as number) > 0 ? finding.band as number : null,
      direction: finding.direction === "down" ? "down" : "up", kind: String(finding.kind ?? "departure"),
      reference: optional(finding.reference), typical: optional(finding.typical), value: finite(finding.value),
      start: text(finding.start), end: text(finding.end), from: optional(finding.from), to: optional(finding.to),
    } : null,
    findingCount: count(root.finding_count), judged: count(root.judged), copied: count(root.copied),
  };
}

export async function readOverview(assetId: string, signal: AbortSignal): Promise<OverviewRow> {
  const response = await fetch("/api/v1/explore/overview?" + new URLSearchParams({asset_id: assetId}),
    {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("설비 개요를 읽지 못했습니다.");
  }
  return parseOverview(await response.json() as unknown, assetId);
}

/** The kind of equipment an asset name says, without its number: "공기압축기 1306" → "공기압축기". */
export function equipmentKind(name: string): string {
  if (/^Bearing\d+_\d+$/.test(name)) return "베어링";
  return name.replace(/[\s_-]*\d[\w.-]*$/, "").trim() || name;
}

/** Shared continuity rule: without explicit support, leave separate measurements separate. */
export function tracePath(points: {x: number; y: number; join?: boolean}[]): string {
  return points.map((point, index) => (index && point.join === true ? "L" : "M")
    + point.x.toFixed(1) + " " + point.y.toFixed(1)).join(" ");
}

export function sparklinePoints(trace: {x: number; value: number; join?: boolean}[], width: number, height: number) {
  const xs = trace.map(point => point.x), values = trace.map(point => point.value);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)], [low, high] = [Math.min(...values), Math.max(...values)];
  return trace.map(point => ({
    x: (point.x - x0) / Math.max(x1 - x0, 1e-9) * width,
    y: height - 2 - (point.value - low) / Math.max(high - low, 1e-9) * (height - 4),
    join: point.join,
  }));
}

/** A path through the trace's points scaled into a width × height box. */
export function sparkline(trace: {x: number; value: number; join?: boolean}[], width: number, height: number): string {
  return trace.length < 2 ? "" : tracePath(sparklinePoints(trace,width,height));
}
