import assert from "node:assert/strict";
import {test} from "node:test";
import {bandName, bandRange, copiedGroups, findingLinks, findingText, parseRecordFindings, sharesText, shiftText, unjudgedText, type CheckedSignal} from "./record-findings.ts";

const body = () => ({
  schema_version: 1, asset_id: "comp", meaning: "departures-from-the-first-30-percent-not-fault-diagnosis",
  baseline: {from: "2020-10-21T15:00:22Z", to: "2020-10-23T17:24:04Z"},
  record: {from: "2020-10-21T15:00:22Z", to: "2020-10-28T14:59:22Z"}, bucket_seconds: 604.8,
  signals: [{channel: "T상전류", label: "T상전류", unit: "A", state: "scored"}, {channel: "R상전류", label: "R상전류", unit: "A", state: "scored"},
    {channel: "압력", label: "압력", unit: "bar", state: "constant", held: 6, later: {low: 6, high: 6}},
    {channel: "유량", label: "유량", unit: null, state: "short-baseline"}],
  judged: 3, unchecked: 0, interval_count: 9,
  intervals: [{start: "2020-10-24T07:10:33Z", end: "2020-10-25T23:19:26Z", channel: "T상전류", label: "T상전류", unit: "A",
    direction: "down", value: 0, usual: {low: 46.196, high: 78.4}, within: ["R상전류", "S상전류", "온도"]}],
});

test("summary trace preserves source continuity flags and accepts older saved samples",()=>{
  const root=body();
  const trace=[["2020-10-24T07:10:33Z",40],["2020-10-24T07:20:33Z",41],["2020-10-25T07:10:33Z",65]];
  const parsed=parseRecordFindings({...root,intervals:[{...root.intervals[0],trace,trace_join:[false,true,false]}]},"comp");
  assert.deepEqual(parsed.intervals[0].trace?.map(row=>row.join),[false,true,false]);
  const older=parseRecordFindings({...root,intervals:[{...root.intervals[0],trace:[[trace[0][0],40]]}]},"comp");
  assert.equal(older.intervals[0].trace?.[0].join,undefined);
  assert.throws(()=>parseRecordFindings({...root,intervals:[{...root.intervals[0],trace,trace_join:[false,"yes",false]}]},"comp"));
});

test("what the whole record held reads as when, how long, against which range, and what else moved", () => {
  const found = parseRecordFindings(body(), "comp");
  assert.deepEqual(found.record, body().record);
  assert.equal(found.count, 9);
  const told = findingText(found.intervals[0], found.bucketSeconds);
  assert.equal(told.when, "10. 24. 16:10 ~ 10. 26. 08:19 (약 1일 16시간)");
  assert.equal(told.what, "T상전류 · 기록 처음 30%의 비교 범위(46.2~78.4 A)보다 낮았습니다 · 10분 평균으로 가장 낮을 때 0 A");
  // Signals not judged say why, never "no change"; a held baseline also says what came after.
  assert.deepEqual(found.signals.filter((row) => row.state !== "scored").map(unjudgedText), [
    "압력(기준 기간과 이후 기록에서 같은 값이 유지됨 · 처음 30%는 6 bar, 그 뒤 6~6 bar)",
    "유량(기록 처음 30%의 값이 너무 적어 평소 범위를 정하지 못함)"]);
  // The judged count must match the signals, and intervals need a judged signal.
  assert.throws(() => parseRecordFindings({...body(), judged: 4}, "comp"));
  assert.throws(() => parseRecordFindings({...body(), judged: 0, signals: body().signals.slice(2)}, "comp"));
  const links = findingLinks("comp", found.intervals[0], found.baseline, found.bucketSeconds);
  assert.match(links.signal!, /tab=signals.*monitor_range=window/);
  assert.match(links.compare!, /method=compare.*compare_origin=departure/);
  assert.throws(() => parseRecordFindings({...body(), meaning: "fault"}, "comp"));
  assert.throws(() => parseRecordFindings({...body(), interval_count: 0}, "comp"));
  const reversed = body(); reversed.intervals[0].usual = {low: 80, high: 40};
  assert.throws(() => parseRecordFindings(reversed, "comp"));
});


test("representative changes keep their reference and preceding-period navigation", () => {
  const original=body();
  const interval={...original.intervals[0],reason:"sustained",baseline:original.baseline,
    reference_value:60,typical_value:0,
    related:[{channel:"R상전류",label:"R상전류",unit:"A",reference:60,current:60,state:"within"}]};
  const found=parseRecordFindings({...original,intervals:[interval]},"comp");
  const item=found.intervals[0];
  assert.equal(item.reason,"sustained");
  assert.equal(findingText(item,found.bucketSeconds).what,"대표값 60 → 0 A");
  assert.equal(item.related[0].state,"within");
  const links=findingLinks("comp",item,null,found.bucketSeconds,found.record);
  assert.match(links.previous!,/compare_origin=previous/);
  const params=new URL(links.previous!,"http://local").searchParams;
  const [a,b]=[params.get("compare_a")!,params.get("compare_b")!].map(raw=>raw.split("~").map(Date.parse));
  assert.equal(a[1],b[0]);
  assert.equal(a[1]-a[0],b[1]-b[0]);
  assert.ok(links.relation);
  const relation=new URL(links.relation.href,"http://local").searchParams;
  assert.equal(relation.get("relation_x"),item.channel);
  assert.equal(relation.get("relation_y"),item.related[0].channel);
  assert.equal(relation.get("compare_a"),params.get("compare_a"));
  assert.equal(relation.get("compare_b"),params.get("compare_b"));
  assert.match(links.outlook,/tab=outlook.*data=history.*monitor_channel=/);
  assert.ok(links.compare); // The interval's own reference survives even without a root reference.
  const early={...item,start:original.record.from};
  assert.equal(findingLinks("comp",early,found.baseline,found.bucketSeconds,found.record).previous,null);
  const long={...item,start:"2020-01-01T00:00:00Z",end:"2020-05-01T00:00:00Z"};
  const longLinks=findingLinks("comp",long,found.baseline,found.bucketSeconds);
  assert.ok(longLinks.signal);
  assert.equal(longLinks.compare,null); // The API cannot compare a period longer than 31 days.
});

test("a declared running total is stated with where it began and ended, not judged as a change",()=>{
  const counter:CheckedSignal={channel:"누적전력량",label:"누적전력량",unit:null,state:"cumulative",held:null,later:null,
    first:270288,last:15492723};
  assert.equal(unjudgedText(counter),"누적전력량(누적값이라 기록 처음과 견준 변화로 판단하지 않음 · 270,000 → 15,500,000)");
});

test("a level change carries its own source, point, meaning and reference into every investigation",()=>{
  const root=body(), original=root.intervals[0];
  const context={key:"a".repeat(64),source_id:"source-b",measurement_point_id:"bearing",interpretation_id:"b".repeat(64),
    record:{from:"2020-10-24T06:00:00Z",to:original.end}};
  const interval={...original,...context,kind:"level-change",baseline:{from:context.record.from,to:"2020-10-24T07:00:00Z"},reference_value:0,typical_value:1};
  const found=parseRecordFindings({...root,baseline:null,intervals:[interval],signals:[{...root.signals[0],state:"level-change"}],judged:1},"comp");
  assert.equal(findingText(found.intervals[0],600).what,"일정하던 값의 변화 · 0 → 1 A");
  const links=findingLinks("comp",found.intervals[0],null,600,{from:"2020-01-01T00:00:00Z",to:original.end});
  // The broader asset history must not make a previous-period comparison appear valid for B.
  assert.equal(links.previous,null);
  for(const link of [links.signal,links.compare]){
    const params=new URL(link!,"http://local").searchParams;
    assert.equal(params.get("monitor_source"),"source-b");
    assert.equal(params.get("monitor_point"),"bearing");
    assert.equal(params.get("monitor_interpretation"),"b".repeat(64));
  }
  const periods=new URL(links.compare!,"http://local").searchParams.get("compare_a");
  assert.equal(periods,interval.baseline.from+"~"+interval.baseline.to);
});

test("columns that held another item's values are listed once per period and are not changes",()=>{
  const span={from:"2020-09-15T15:00:00Z",to:"2020-10-16T06:15:00Z"};
  const root=body();
  const found=parseRecordFindings({...root,signals:[...root.signals,
    {channel:"R상선간전압",label:"R상선간전압",unit:null,state:"copied",copied:{origin:"R상전압",...span}},
    {channel:"R상전류고조파",label:"R상전류고조파",unit:null,state:"copied",copied:{origin:"R상전류",...span}},
    {channel:"S상선간전압",label:"S상선간전압",unit:null,state:"copied",copied:{origin:"S상전압",from:span.from,to:"2020-09-20T00:00:00Z"}}]},"comp");
  assert.equal(found.judged,3);
  assert.deepEqual(copiedGroups(found.signals),[
    {...span,items:[{label:"R상선간전압",origin:"R상전압"},{label:"R상전류고조파",origin:"R상전류"}]},
    {from:span.from,to:"2020-09-20T00:00:00Z",items:[{label:"S상선간전압",origin:"S상전압"}]},
  ]);
  // A copied signal must say which item and when.
  assert.throws(()=>parseRecordFindings({...root,signals:[...root.signals,{channel:"x",label:"x",unit:null,state:"copied"}]},"comp"));
});

test("how the equipment ran is read per current level and attached to the changes it explains", () => {
  const operation = {key: "k", label: "전류평균", unit: "A", stopped_below: 1, excluded: 0, bucket_seconds: 3600,
    baseline: {from: "2020-09-15T15:00:00Z", to: "2020-09-26T15:00:00Z"},
    levels: [{low: 1, high: 26.1, typical: 10.6}, {low: 26.1, high: 45.9, typical: 31.4}, {low: 45.9, high: null, typical: 61.9}],
    shares: {record: [0, 0.081, 0.294, 0.625], baseline: [0, 0.032, 0.242, 0.726], after: [0, 0.102, 0.316, 0.582]},
    timeline: [["2020-09-15T15:00:00Z", [0, 0, 0, 60]], ["2020-09-15T16:00:00Z", [0, 3, 50, 7]]]};
  const root = body();
  const change = {...root.intervals[0], operation: {key: "k", interval: [0, 0.12, 0.87, 0.01], baseline: [0, 0.03, 0.24, 0.73]}};
  const found = parseRecordFindings({...root, operation: [operation], intervals: [change]}, "comp");
  const [read] = found.operation;
  assert.deepEqual([0, 1, 2, 3].map(band => bandName(read, band)), ["정지", "약 11 A 운전", "약 31 A 운전", "약 62 A 운전"]);
  assert.deepEqual([0, 1, 3].map(band => bandRange(read, band)), ["1 A 미만", "1~26 A", "46 A 이상"]);
  assert.equal(sharesText(read, found.intervals[0].operation!.interval), "약 31 A 운전 87% · 약 11 A 운전 12% · 약 62 A 운전 1%");
  assert.equal(shiftText(read, found.intervals[0].operation!), "이 구간은 약 31 A 운전 87% · 처음 30%에는 24%");
  assert.equal(read.timeline[1].counts[2], 50);
  // Shares must name every band, and a change may only point at an operation that was sent.
  assert.throws(() => parseRecordFindings({...root, operation: [{...operation, shares: {...operation.shares, record: [0.5, 0.5]}}]}, "comp"));
  assert.throws(() => parseRecordFindings({...root, operation: [], intervals: [change]}, "comp"));
  assert.deepEqual(parseRecordFindings(root, "comp").operation, []);
});
