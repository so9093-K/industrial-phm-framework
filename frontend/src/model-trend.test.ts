import assert from "node:assert/strict";
import {test} from "node:test";
import type {ModelBinding} from "./model-evidence.ts";
import {beforeInterval,exceedanceStory,exceedanceText,firstExceedance,inputCheck,measurementTime,mergeSeries,overlayModels,parseWaveform,parseWindow,thresholdRatios,trendSummary,type TrendPoint} from "./model-trend.ts";

const binding={bindingId:"anomaly-a",stepKind:"acquisition-snapshot"} as ModelBinding;
const step=(position:number,state:"analyzed"|"skipped",score?:number)=>({position,state,step_key:"k"+position,
  analysis_run_id:"run-"+position,change_seq:position,reason:state==="skipped"?"warm-up":null,
  event_start:null,output:state==="analyzed"?{score,threshold:2,exceeds_threshold:(score??0)>2}:{}});

test("stored scores merge by input order; a skipped step has no score",()=>{
  const known=new Map<number,TrendPoint>();
  const page=mergeSeries({schema_version:1,binding:{binding_id:"anomaly-a"},change_seq:3,has_more:false,
    steps:[step(1,"skipped"),step(2,"analyzed",0.5),step(3,"analyzed",3.1)],
    intervals:[{start_position:3,end_position:3,step_count:1,peak_score:3.1,open:true}]},binding,known);
  assert.equal(page.cursor,3);
  assert.equal(known.get(1)!.score,null);
  assert.equal(known.get(3)!.exceeds,true);
  assert.deepEqual(trendSummary({points:[...known.values()],intervals:page.intervals,truncated:false}),
    {analyzed:2,skipped:1,exceeded:1,open:1});
  assert.throws(()=>mergeSeries({schema_version:1,binding:{binding_id:"other"},steps:[],intervals:[]},binding,known),/형식/);
});

test("raw input previews keep unreadable and unusable values apart from data",()=>{
  assert.deepEqual(parseWaveform({position:3,available:false,reason:"sha mismatch"},3),{available:false,reason:"sha mismatch"});
  const wave=parseWaveform({position:3,available:true,file_name:"3.csv",sampling_rate_hz:25600,sample_count:800,samples_per_bin:2,
    channels:[{channel:"h",envelope:[[-1,1],[-2,2]]}]},3);
  assert.equal(wave.available&&wave.channels[0].bands.length,2);
  assert.throws(()=>parseWaveform({position:4,available:true},3),/형식/);
  const window=parseWindow({position:7,available:true,start:"2026-10-17T00:00:00Z",end:"2026-10-17T00:05:00Z",
    channels:[{channel_id:"current_r",unit:"A",points:[{at:"2026-10-17T00:00:01Z",value:5,quality:"good"},
      {at:"2026-10-17T00:00:02Z",value:9,quality:"conflict"}]}]},7);
  assert.deepEqual(window.available&&window.channels[0].points.map(p=>p.value),[5,null]);
});

test("scores of models with different scales share one axis as a ratio to each model's own threshold",()=>{
  const known=new Map<number,TrendPoint>();
  const page=mergeSeries({schema_version:1,binding:{binding_id:"anomaly-a"},change_seq:4,has_more:false,
    steps:[step(1,"skipped"),step(2,"analyzed",1),step(3,"analyzed",3),step(4,"analyzed",4)],
    intervals:[{start_position:3,end_position:4,step_count:2,peak_score:4,open:true}]},binding,known);
  const line=thresholdRatios({points:[...known.values()],intervals:page.intervals,truncated:false});
  assert.deepEqual(line.points.map(p=>p.ratio),[0.5,1.5,2]);
  assert.deepEqual(line.latest,{position:4,ratio:2});
  assert.equal(line.sustainedFrom,3);
  assert.equal(line.exceeded,2);
  const noThreshold=thresholdRatios({points:[{...known.get(2)!,threshold:0}],intervals:[],truncated:false});
  assert.deepEqual(noThreshold.points,[]);
});

test("a flagged measurement is compared with the last analyzed one before its interval",()=>{
  const intervals=[{start:34,end:38,steps:5,peak:2,open:false},{start:76,end:123,steps:48,peak:12,open:true}];
  const analyzed=[8,9,70,75,76,100,123];
  assert.equal(beforeInterval(intervals,analyzed,123),75);
  // The first flagged measurement is compared with the last one before it, as the rest are.
  assert.equal(beforeInterval(intervals,analyzed,76),75);
  assert.equal(beforeInterval(intervals,analyzed,34),9);
  assert.equal(beforeInterval(intervals,analyzed,50),null);
  assert.equal(beforeInterval(intervals,[],100),null);
});

test("every model on a stream can be chosen; the chosen one is always drawn",()=>{
  const models=["a","b","c","d","e","f"].map(bindingId=>({bindingId}));
  const drawn=(selected:string)=>overlayModels(models,selected,4).map(item=>item.bindingId);
  assert.deepEqual(drawn("b"),["a","b","c","d"]);
  assert.deepEqual(drawn("f"),["a","b","c","f"]);
  assert.deepEqual(drawn("missing"),["a","b","c","d"]);
  assert.deepEqual(overlayModels(models.slice(0,2),"b",4).map(item=>item.bindingId),["a","b"]);
});

test("the first exceeded measurement is visible even without a sustained interval", () => {
  const known = new Map<number, TrendPoint>();
  mergeSeries({schema_version:1,binding:{binding_id:"anomaly-a"},change_seq:5,has_more:false,
    steps:[step(1,"skipped"),step(2,"analyzed",2),step(3,"analyzed",3),step(4,"analyzed",1),step(5,"analyzed",4)],
    intervals:[]}, binding, known);
  const points = [...known.values()];
  assert.equal(firstExceedance(points)?.pointer.position, 3);
  assert.equal(thresholdRatios({points,intervals:[],truncated:false}).firstExceedance?.pointer.position, 3);
  assert.equal(firstExceedance(points.slice(0,2)), null); // Equal to the threshold is not exceeded.
  assert.equal(firstExceedance([{...points[2], exceeds: false}]), null); // Respect the stored flag.
  assert.equal(measurementTime(points[2], 60), "기록 시작 후 2분");
  assert.equal(measurementTime(points[2], null), null); // No receipt-time clock is invented.
  assert.match(measurementTime({...points[2], eventStart:"2026-10-20T00:00:00Z"}, null)!, /09:00:00.*KST/);
  assert.equal(measurementTime({...points[2], eventStart:"2026-10-20T00:00:00"}, null), null);
});

test("a run still going on is read first; one-off and ended crossings are counted, not led with", () => {
  const point = (position: number, exceeds: boolean): TrendPoint => ({
    pointer: {position, runId: "run-" + position, state: "analyzed", stepKey: "k" + position, changeSeq: position, reason: null},
    score: exceeds ? 2 : 0.5, threshold: 1, exceeds, eventStart: null});
  const over = (positions: number[]) => Array.from({length: 12}, (_, i) => point(i + 1, positions.includes(i + 1)));
  const place = (position: number) => "#" + position;
  // One crossing at #2, a run #4–#5 that ended, and a run from #9 still going on.
  const sustained = {points: over([2, 4, 5, 9, 10, 11, 12]), truncated: false,
    intervals: [{start: 4, end: 5, steps: 2, peak: 2, open: false}, {start: 9, end: 12, steps: 4, peak: 2, open: true}]};
  const story = exceedanceStory(sustained);
  assert.equal(story.state, "ongoing");
  assert.equal(story.anchor?.pointer.position, 9);
  assert.deepEqual(exceedanceText(story, place), {headline: "#9부터 계속 기준 초과 · 4회",
    earlier: "그 전 · 끝난 기준 초과 구간 1개 · 한 번만 넘은 측정 1번 · 처음 넘은 측정 #2"});
  // A run still open within the model's allowed gap, with the latest measurement below.
  const gap = exceedanceStory({points: over([9, 10, 11]), truncated: false,
    intervals: [{start: 9, end: 11, steps: 3, peak: 2, open: true}]});
  assert.equal(exceedanceText(gap, place)?.headline, "#9부터 기준 초과 구간 · 3회 · 최근 측정은 기준 이하");
  // The latest measurement crosses alone: said as such, never as "since".
  const lone = exceedanceStory({points: over([7, 12]), intervals: [], truncated: false});
  assert.equal(lone.state, "latest");
  assert.deepEqual(exceedanceText(lone, place), {headline: "#12에서 기준 초과 · 연속 초과는 아님",
    earlier: "그 전 · 한 번만 넘은 측정 1번 · 처음 넘은 측정 #7"});
  // Crossed earlier, below now.
  const below = exceedanceStory({points: over([3, 6, 7]), truncated: false,
    intervals: [{start: 6, end: 7, steps: 2, peak: 2, open: false}]});
  assert.equal(below.state, "below");
  assert.equal(exceedanceText(below, place)?.headline, "지금은 기준 이하 · 마지막 기준 초과 #7");
  assert.equal(exceedanceText(exceedanceStory({points: over([]), intervals: [], truncated: false}), place), null);
});

test("the raw input check says what was verified before drawing, and only what the server checked", () => {
  const waveform = parseWaveform({position: 3, available: true, file_name: "3.csv", sampling_rate_hz: 25600,
    sample_count: 32768, samples_per_bin: 82, channels: [{channel: "h", envelope: [[0, 1]]}, {channel: "v", envelope: [[0, 1]]}],
    checks: {sha256_matches: true, non_finite_values: 0}}, 3);
  assert.equal(inputCheck(waveform), "원본 확인 · 전달 당시 확인값(SHA-256)과 일치 · 표본 32,768개 × 2채널 · 결측 없음");
  const older = parseWaveform({position: 3, available: true, file_name: "3.csv", sampling_rate_hz: 25600,
    sample_count: 10, samples_per_bin: 1, channels: [{channel: "h", envelope: [[0, 1]]}]}, 3);
  assert.equal(inputCheck(older), null); // A server that did not report its checks claims nothing.
  const window = parseWindow({available: true, position: 7, start: "2026-10-01T00:00:00Z", end: "2026-10-01T00:01:00Z",
    channels: [{channel_id: "a", points: [{at: "x", value: 1, quality: "good"}, {at: "y", value: null, quality: "unusable"},
      {at: "z", value: 2, quality: "conflict"}]}]}, 7);
  assert.equal(inputCheck(window), "원본 확인 · 측정값 3개 · 쓸 수 없는 값 1개 · 값 충돌 1개");
});
