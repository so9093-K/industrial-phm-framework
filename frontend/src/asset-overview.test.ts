import assert from "node:assert/strict";
import {test} from "node:test";
import {equipmentKind, latestReading, parseOverview, sparkline} from "./asset-overview.ts";
import {findingLinks} from "./record-findings.ts";

const row = {schema_version: 1, asset_id: "공기압축기 1306", kind: "history", finding_count: 3, judged: 25, copied: 9,
  operation: {key: "k", label: "전류평균", stopped_below: 1, shares: [0, 0.08, 0.29, 0.63],
    levels: [{low: 1, high: 26.1, typical: 10.6}, {low: 26.1, high: 45.9, typical: 31.4}, {low: 45.9, high: null, typical: 61.9}]},
  main: {label: "전류평균", unit: "A", axis: "time", latest: {at: "2020-10-22T14:59:08+00:00", value: 60.3},
    trace: [["2020-09-15T15:00:00+00:00", 62], ["2020-09-16T15:00:00+00:00", 61]]},
  finding: {label: "R상전압", unit: "V", band: 1, direction: "up", kind: "departure", value: 228,
    reference: 222, typical: 226, start: "2020-10-04T00:19:44+00:00", end: "2020-10-05T03:51:24+00:00"}};

test("an overview row reads the summary's first change with how the asset ran", () => {
  const read = parseOverview(row, "공기압축기 1306");
  assert.equal(read.finding?.band, 1);
  assert.equal(read.operation?.names.levels[2].typical, 61.9);
  assert.equal(read.main?.trace[1].x, Date.parse("2020-09-16T15:00:00+00:00"));
  assert.equal(read.copied, 9);
  const gapped=parseOverview({...row,main:{...row.main,trace_join:[false,false]}},row.asset_id);
  assert.equal(gapped.main?.trace[1].join,false);
  assert.throws(()=>parseOverview({...row,main:{...row.main,trace_join:[false]}},row.asset_id));
  assert.throws(() => parseOverview(row, "other"));
  assert.throws(() => parseOverview({...row, operation: {...row.operation, shares: [1]}}, "공기압축기 1306"));
  const empty = parseOverview({schema_version: 1, asset_id: "x", kind: null, operation: null, main: null, finding: null,
    finding_count: 0, judged: 0, copied: 0}, "x");
  assert.equal(empty.kind, null);
});

test("the last stored value next to a change is that changed signal's own, never the main signal's", () => {
  const changed = parseOverview({...row, finding: {...row.finding, latest: {at: "2020-10-22T14:59:08+00:00", value: 221.4}}}, row.asset_id);
  assert.deepEqual(latestReading(changed), {label: "R상전압", unit: "V", periodSeconds: null,
    latest: {at: "2020-10-22T14:59:08+00:00", position: null, value: 221.4}});
  // 변화한 신호의 값을 못 읽으면 대표 신호(전류평균) 값으로 대신하지 않는다.
  assert.equal(latestReading(parseOverview(row, row.asset_id))?.latest, null);
  const quiet = parseOverview({...row, finding: null}, row.asset_id);
  assert.equal(latestReading(quiet)?.label, "전류평균");
});

test("the kind of equipment is the name without its number", () => {
  assert.equal(equipmentKind("공기압축기 1306"), "공기압축기");
  assert.equal(equipmentKind("펌프·일반모터 4025"), "펌프·일반모터");
  assert.equal(equipmentKind("Bearing1_1"), "베어링");
  assert.equal(equipmentKind("보일러"), "보일러");
});

test("the first-screen change keeps its own record, plot gaps and investigation link", () => {
  const interval = {key:"record-b",source_id:"voltage-file",measurement_point_id:"motor",interpretation_id:"f".repeat(64),
    record:{from:"2020-09-15T00:00:00Z",to:"2020-10-22T15:00:00Z"},
    start:row.finding.start,end:row.finding.end,channel:"voltage",label:"R상전압",unit:"V",direction:"up",
    value:228,usual:{low:209,high:227},within:[],reference_value:222,typical_value:226,bucket_seconds:600,
    baseline:{from:"2020-09-15T00:00:00Z",to:"2020-09-26T00:00:00Z"},
    trace:[["2020-10-04T00:00:00Z",222],["2020-10-05T00:00:00Z",226]],trace_join:[false,false]};
  const read=parseOverview({...row,history_interval:interval},row.asset_id);
  assert.equal(read.historyInterval?.context?.sourceId,"voltage-file");
  assert.equal(read.historyInterval?.trace?.[1].join,false);
  const link=findingLinks(row.asset_id,read.historyInterval!,null,null).signal!;
  const query=new URL(link,"http://local").searchParams;
  assert.equal(query.get("record_key"),"record-b");
  assert.equal(query.get("monitor_source"),"voltage-file");
  assert.equal(query.get("monitor_point"),"motor");
  assert.equal(query.get("monitor_channel"),"voltage");
  assert.equal(parseOverview(row,row.asset_id).historyInterval,null);
});

test("a sparkline spans its box and draws nothing from a single point", () => {
  assert.equal(sparkline([{x: 0, value: 1}], 120, 28), "");
  assert.equal(sparkline([{x: 0, value: 0}, {x: 10, value: 10, join: true}], 120, 28), "M0.0 26.0 L120.0 2.0");
});

 test("a miniature trace breaks at gaps and never invents continuity for older responses",()=>{
  const points=[{x:0,value:0,join:false},{x:1,value:1,join:true},{x:9,value:9,join:false},{x:10,value:10,join:true}];
  assert.equal(sparkline(points,120,28),"M0.0 26.0 L12.0 23.6 M108.0 4.4 L120.0 2.0");
  assert.equal(sparkline(points.map(({join:_ignored,...point})=>point),120,28).includes("L"),false);
});

test("a vibration change keeps its own feature trace independently of the main signal",()=>{
  const vibration={source_id:"waves-b",binding_id:"binding-b",period_seconds:60,
    feature:"feature.Vertical_vibration_signals.absolute_peak",label:"수직 진동 피크",unit:"g",direction:"up",
    from:77,to:123,baseline:{from:1,to:37},reference_value:20,typical_value:90,value:100,
    usual:{low:10,high:30},trace:[[1,20],[2,21],[77,90],[123,100]],trace_join:[false,true,false,false]};
  const read=parseOverview({...row,kind:"vibration",history_interval:null,vibration_interval:vibration},row.asset_id);
  assert.equal(read.vibrationInterval?.change.feature,vibration.feature);
  assert.equal(read.vibrationInterval?.change.trace[2].value,90);
  assert.equal(read.vibrationInterval?.change.trace[2].join,false);
  assert.equal(read.vibrationInterval?.sourceId,"waves-b");
  assert.equal(read.vibrationInterval?.bindingId,"binding-b");
  assert.notEqual(read.main?.label,read.vibrationInterval?.change.label);
  assert.throws(()=>parseOverview({...row,vibration_interval:{...vibration,trace_join:[true]}},row.asset_id));
});
