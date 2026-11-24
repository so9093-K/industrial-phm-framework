import assert from "node:assert/strict";
import {test} from "node:test";
import {analysisView, changeRef, focusOf} from "./analysis-chat.ts";
import {parseRecordFindings} from "./record-findings.ts";
import {carriedConversation, withConversation} from "./change-investigation.ts";
import {investigationOriginUrl, tabSelectionUrl} from "./routes.ts";

const search = (ref: unknown) => "?" + new URLSearchParams({summary_change: JSON.stringify(ref)});

test("an analysis screen finds the change the investigation handed over, or none for a direct address", () => {
  assert.deepEqual(changeRef(search(["vibration", "vertical.rms", 72, 123])), {kind: "vibration", feature: "vertical.rms", from: 72, to: 123});
  assert.equal(changeRef(""), null);
  assert.equal(changeRef("?summary_change=%7Bbroken"), null);
  const span = {from: "2020-10-01T00:00:00Z", to: "2020-10-05T00:00:00Z"};
  const record = parseRecordFindings({schema_version: 1, asset_id: "compressor", meaning: "departures-from-the-first-30-percent-not-fault-diagnosis",
    baseline: {from: span.from, to: "2020-10-02T00:00:00Z"}, record: span, bucket_seconds: 60, judged: 1, unchecked: 0, interval_count: 1,
    signals: [{channel: "R상전압", label: "R상전압", unit: "V", state: "scored"}],
    intervals: [{channel: "R상전압", label: "R상전압", unit: "V", start: "2020-10-03T00:00:00Z", end: "2020-10-03T01:00:00Z", direction: "up",
      value: 225, usual: {low: 219, high: 221}, within: [], review_key: "a".repeat(64)}]}, "compressor");
  const item = record.intervals[0];
  const ref = changeRef(search(["history", item.context?.key ?? item.channel, item.start, item.end]))!;
  const focus = focusOf(ref, record, null);
  assert.equal(focus?.kind === "history" ? focus.item.reviewKey : null, "a".repeat(64));
  // 다른 기간이면 같은 신호여도 그 특이사항이 아니다.
  assert.equal(focusOf({...ref, end: "2020-10-03T02:00:00Z"} as typeof ref, record, null), null);
});

test("the screen a question is asked on names what the server reads with it", () => {
  assert.equal(analysisView("change", "spectrum"), "spectrum");
  assert.equal(analysisView("change", null), "compare");
  assert.equal(analysisView("anomaly", "model"), "anomaly");
  assert.equal(analysisView("summary", null), null);
});

test("the conversation follows the person to the analysis screen and across its tabs", () => {
  const conversation = "c".repeat(32);
  const link = withConversation("/web/?page=assets&tab=change&method=spectrum&monitor_asset=B", conversation);
  assert.equal(carriedConversation(new URL(link, "http://local").search), conversation);
  assert.equal(carriedConversation("?chat=nope"), null);
  // 분석 탭을 옮겨도, 조사 화면에서 다른 분석으로 가도 같은 대화 번호가 실린다.
  const here = "http://local" + link + "&summary_change=" + encodeURIComponent(JSON.stringify(["vibration", "f", 1, 2]));
  const next = tabSelectionUrl("/web/?page=assets&tab=change&method=compare&monitor_asset=B", here);
  assert.equal(new URL(next, "http://local").searchParams.get("chat"), conversation);
  assert.equal(new URL(investigationOriginUrl("/web/?page=assets&tab=outlook&monitor_asset=B", here), "http://local").searchParams.get("chat"), conversation);
});
