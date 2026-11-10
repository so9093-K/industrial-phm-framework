/** One asset as a row of the comparison overview (GET /api/v1/explore/overview): how it ran,
 * its main signal's latest value and trace, and the first change its summary leads with. */
import {object} from "./writes.ts";
import type {LevelNames} from "./record-findings.ts";

export type OverviewRow = {
  assetId: string; kind: "history" | "vibration" | null;
  /** Share of time per band over the record, stopped first, with the band names. */
  operation: {names: LevelNames; label: string; shares: number[] | null} | null;
  main: {label: string; unit: string | null; axis: "time" | "acquisition"; periodSeconds: number | null;
    latest: {at: string | null; position: number | null; value: number} | null; trace: {x: number; value: number}[]} | null;
  finding: {label: string; unit: string | null; band: number | null; direction: "up" | "down"; kind: string;
    reference: number | null; typical: number | null; value: number;
    start: string | null; end: string | null; from: number | null; to: number | null} | null;
  findingCount: number; judged: number; copied: number;
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
  const axis = main?.axis === "acquisition" ? "acquisition" : "time";
  const latest = object(main?.latest);
  const finding = object(root.finding);
  return {
    assetId, kind, operation,
    main: main ? {
      label: text(main.label) ?? "", unit: text(main.unit), axis, periodSeconds: optional(main.period_seconds),
      latest: latest ? {at: text(latest.at), position: optional(latest.position), value: finite(latest.value)} : null,
      trace: (Array.isArray(main.trace) ? main.trace : []).map((point: unknown) => {
        if (!Array.isArray(point) || point.length !== 2) invalid();
        const x = axis === "time" ? Date.parse(String(point[0])) : finite(point[0]);
        return Number.isFinite(x) ? {x, value: finite(point[1])} : invalid();
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
  return name.replace(/[\s_-]*\d[\w.-]*$/, "").trim() || name;
}

/** A path through the trace's points scaled into a width × height box. */
export function sparkline(trace: {x: number; value: number}[], width: number, height: number): string {
  if (trace.length < 2) return "";
  const xs = trace.map(point => point.x), values = trace.map(point => point.value);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)], [low, high] = [Math.min(...values), Math.max(...values)];
  const x = (value: number) => (value - x0) / Math.max(x1 - x0, 1e-9) * width;
  const y = (value: number) => height - 2 - (value - low) / Math.max(high - low, 1e-9) * (height - 4);
  return trace.map((point, index) => (index ? "L" : "M") + x(point.x).toFixed(1) + " " + y(point.value).toFixed(1)).join(" ");
}
