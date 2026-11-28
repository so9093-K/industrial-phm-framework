import assert from "node:assert/strict";
import test from "node:test";
import type {AnalysisRecord} from "./analysis-records.ts";
import type {FleetChange, FleetGroup, FleetRead} from "./fleet-observation.ts";
import {changeActivity, monitorActivities, monitorLead} from "./monitor-activity.ts";
import type {Asset, OperationAttention, Snapshot} from "./monitor.ts";

const group: FleetGroup = {axis: "acquisition", focus: "rms", label: "진동", unit: "g", record: {from: 1, to: 123},
  bucketMs: null, periodSeconds: 60, series: []};
const change: FleetChange = {key: "rms", channel: "rms", label: "진동", from: 76, to: 123, up: true,
  before: 0.716, after: 7.27, reviewKey: "selected-review", ref: "selected-change"};
const read: FleetRead = {group, live: false, href: "/web/", changes: [change], others: [], companion: null};

test("a replay entry follows the graph range and keeps its bounded question scope", () => {
  assert.equal(monitorLead(group, [change], 75), null);
  assert.equal(monitorLead(group, [change], null), null);
  const lead = monitorLead(group, [change], 95)!;
  const entry = changeActivity("record", "베어링", read, group, lead, {kind: "vibration", until: 95}, "http://local");
  assert.equal(lead.to, 95);
  assert.match(entry.detail, /재생 기록 · 76–95번째 측정/);
  assert.equal(entry.question?.range, "76–95번째 측정");
  const href = new URL(entry.href, "http://local");
  assert.equal(href.searchParams.get("summary_change"), "selected-change");
  assert.equal(href.searchParams.get("acquisition_until"), "95");
});

test("only active receiving alerts and recent stored analyses appear beside record changes", () => {
  const asset = (assetId: string, flow: string): Asset => ({assetId, flow, attentionCount: null, lastObservedAt: null, lastReceivedAt: null});
  const assets = [asset("live", "delayed"), asset("record", "stored-history")];
  const alert = (id: string, assetId: string, code = "source-no-new-data"): OperationAttention => ({id, assetId, code,
    sourceId: "input", findingId: null, title: "No new data", status: "delayed", destination: "asset-signals", at: null});
  const result = (evidenceId: string, completedAt: string): AnalysisRecord => ({assetId: "record", evidenceId, completedAt, kind: "phase",
    runId: "run", sourceId: "file", pointId: null, capabilityId: "phase", version: null, observedStart: null, observedEnd: null,
    quality: null, issues: [], quantities: [], features: [], sha256: null});
  const snapshot: Pick<Snapshot, "assessedAt" | "operationsAttention" | "analyses"> = {assessedAt: "2026-11-28T03:00:00Z",
    operationsAttention: {complete: true, items: [alert("1", "live"), alert("2", "live", "source-connection-lost"), alert("3", "record"),
      alert("4", "live", "data-quality-review")]},
    analyses: {available: true, truncated: false, skipped: [], skippedComplete: true,
      records: [result("future", "2026-11-28T03:30:00Z"), result("latest", "2026-11-28T02:00:00Z"), result("old", "2026-11-26T02:00:00Z")]}};
  const entry = changeActivity("record", "베어링", read, group, change, null, "http://local");
  const normal = monitorActivities(snapshot, assets, [entry], false);
  assert.deepEqual(normal.map(item => item.kind), ["alert", "change", "analysis"]);
  assert.match(normal[2].href, /#record-latest$/);
  assert.deepEqual(monitorActivities(snapshot, assets, [entry], true).map(item => item.kind), ["alert", "change"]);
});
