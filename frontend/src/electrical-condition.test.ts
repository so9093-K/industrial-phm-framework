import assert from "node:assert/strict";
import {test} from "node:test";
import {firstChecks,insights,shiftedPeriod,kstInstant,parseCondition,segments,type Condition} from "./electrical-condition.ts";

const MEANING="measured-operating-change-and-reference-pattern-not-fault-diagnosis";
function analyzed(extra:Record<string,unknown>={}){
  return {schema_version:1,asset_id:"motor",meaning:MEANING,state:"analyzed",
    sources:[{source_id:"s1",point_id:"meter"},{source_id:"s2",point_id:null}],source_id:"s1",point_id:"meter",
    target_start:"2020-11-13T03:00:00+00:00",target_end:"2020-11-13T04:00:00+00:00",
    reference_start:"2020-11-13T02:00:00+00:00",reference_end:"2020-11-13T03:00:00+00:00",
    last_observed_at:"2020-11-13T03:59:00+00:00",source_quality:"unknown",snapshot_id:7,time_evidence:[],
    reference:{current_mean_a:11,current_above_floor_hours:1,current_floor_a:1,sample_count:60},
    target:{current_mean_a:81,current_above_floor_hours:0.5,current_floor_a:1,current_peak_a:83,
      current_peak_at:"2020-11-13T03:30:00+00:00",voltage_unbalance_max_at:"2020-11-13T03:10:00+00:00",sample_count:60},
    pattern:{state:"scored",threshold:2.5,above_reference_count:3,scored_samples:60,above_reference_percent:5,model:"IsolationForest",
      fit_samples:60,notable:[{at:"2020-11-13T03:05:00+00:00",score:4,above_reference:true,channel_id:"vR",value:240,
        reference_p05:229,reference_p95:232,unit:"V"},{at:"2020-11-13T03:06:00+00:00",above_reference:false}]},
    timeline:[
      {at:"2020-11-13T03:00:00+00:00",current_mean_a:80,voltage_phase_v:[230,231,229],current_phase_a:[80,81,82]},
      {at:"2020-11-13T03:01:00+00:00",current_mean_a:81},
      {at:"2020-11-13T03:02:00+00:00",current_mean_a:null},
      {at:"2020-11-13T03:03:00+00:00",current_mean_a:82},
      {at:"2020-11-13T03:30:00+00:00",current_mean_a:83},
    ],
    excluded:{reference:{"missing-value":2},target:{}},...extra};
}
const ready=(raw:unknown)=>parseCondition(raw,"motor",null) as Extract<Condition,{analyzed:true}>;

test("a stored analysis reads as the comparison an operator checks, never another asset or source",()=>{
  const condition=ready(analyzed());
  assert.equal(condition.analyzed,true);
  assert.equal(condition.target.currentMean,81);
  assert.deepEqual(condition.timeline[0].voltage,[230,231,229]);
  assert.equal(condition.details.snapshotId,"7");
  assert.deepEqual(condition.details.excluded.reference,{"missing-value":2});
  // Only observations over the reference range are times to check first.
  assert.equal(condition.pattern.scored&&condition.pattern.notable.length,1);
  assert.throws(()=>parseCondition(analyzed(),"other",null),/형식/);
  assert.throws(()=>parseCondition({...analyzed(),meaning:"fault-diagnosis"},"motor",null),/형식/);
  assert.throws(()=>parseCondition(analyzed(),"motor",{sourceId:"s2",pointId:null}),/다른 분석 결과/);
  const waiting=parseCondition({schema_version:1,asset_id:"motor",meaning:MEANING,state:"select-source",
    sources:[{source_id:"s1",point_id:"meter"}]},"motor",null);
  assert.deepEqual(waiting,{analyzed:false,state:"select-source",sources:[{sourceId:"s1",pointId:"meter"}]});
});

test("insights compare like with like and say when the reference pattern was not scored",()=>{
  const lines=insights(ready(analyzed()));
  assert.match(lines[0],/기준 기간보다 0\.5 h 줄었습니다/);
  assert.match(lines[1],/83 A/);
  assert.match(lines[2],/3개 \/ 60개 \(5%\)/);
  const longer=insights(ready(analyzed({reference_start:"2020-11-13T00:00:00+00:00",
    reference:{current_above_floor_hours:1,current_above_floor_fraction:0.25},
    target:{current_above_floor_hours:1,current_above_floor_fraction:1}})));
  assert.match(longer[0],/기준 기간 25% → 분석 기간 100%.*비율로 비교/);
  const same=insights(ready(analyzed({target:{current_above_floor_hours:1,current_floor_a:1}})));
  assert.match(same[0],/기준 기간과 같습니다/);
  const unscored=ready(analyzed({pattern:{state:"insufficient-reference"}}));
  assert.match(insights(unscored).at(-1)!,/패턴을 비교하지 않았습니다/);
  assert.deepEqual(firstChecks(unscored).map(check=>check.metric),["currentMean","voltageUnbalance"]);
  assert.equal(firstChecks(ready(analyzed()))[0].metric,"voltageUnbalance");
});

test("a time to check first gives all three phases, so all phases at 0 A never reads as one lost phase",()=>{
  const stopped=ready(analyzed({
    pattern:{state:"scored",threshold:2.5,above_reference_count:1,scored_samples:60,above_reference_percent:2,
      notable:[{at:"2020-11-13T03:00:00+00:00",score:4,above_reference:true,channel_id:"iT",value:0,
        reference_p05:38.4,reference_p95:75.6,unit:"A"}]},
    timeline:[{at:"2020-11-13T03:00:00+00:00",current_mean_a:0,voltage_phase_v:[222,224,222],current_phase_a:[0,0,0]}],
  }));
  assert.equal(firstChecks(stopped)[0].detail,"전류 R/S/T 0 / 0 / 0 A · 가장 멀리 벗어난 iT의 기준 5–95% 범위 38.4–75.6 A");
  const unmatched=ready(analyzed({timeline:[]}));
  assert.equal(firstChecks(unmatched)[0].detail,"vR 240 V · 기준 5–95% 범위 229–232 V");
});

test("lines never join across a missing value or a time gap",()=>{
  const runs=segments(ready(analyzed()).timeline,"currentMean");
  assert.deepEqual(runs.map(run=>run.length),[2,1,1]);
});

test("KST inputs are sent as the same instant with an explicit offset",()=>{
  assert.equal(kstInstant("2020-11-13T12:30:15"),"2020-11-13T12:30:15+09:00");
  assert.equal(kstInstant("2020-11-13T10:00"),"2020-11-13T10:00:00+09:00");
  assert.throws(()=>kstInstant("2020-11-13 10:00"),/시각 형식/);
});

test("minutes in a row that read the same are one time to check, with their end and count",()=>{
  const at=(minute:number)=>"2020-11-20T18:"+String(23+minute).padStart(2,"0")+":35+00:00";
  const stopped=ready(analyzed({
    pattern:{state:"scored",threshold:2.5,above_reference_count:5,scored_samples:60,above_reference_percent:8,
      notable:[0,1,2,3,4].map(minute=>({at:at(minute),score:4,above_reference:true,channel_id:"iS",value:0,
        reference_p05:23.5,reference_p95:73.38,unit:"A"}))},
    timeline:[0,1,2,3,4].map(minute=>({at:at(minute),current_mean_a:0,voltage_phase_v:[222,224,222],current_phase_a:[0,0,0]})),
  }));
  const checks=firstChecks(stopped);
  assert.equal(checks.length,1);
  assert.equal(checks[0].label,"2020. 11. 21. 오전 3:23:35 ~ 오전 3:27:35 · 5회");
  assert.equal(checks[0].at,at(0));
});


test("period movement preserves an explicitly chosen reference; next availability is server-owned",()=>{
  const current=ready(analyzed());
  const fixed={end:"",referenceStart:"2020-11-01T00:00",referenceEnd:"2020-11-02T00:00"};
  const next=shiftedPeriod(current,1,fixed), previous=shiftedPeriod(current,-1,fixed);
  assert.equal(next.end,"2020-11-13T14:00:00");
  assert.equal(previous.end,"2020-11-13T12:00:00");
  assert.equal(next.referenceStart,fixed.referenceStart);
  assert.equal(previous.referenceEnd,fixed.referenceEnd);
  assert.equal(current.nextPeriodAvailable,false);
  assert.equal(ready(analyzed({next_period_available:true})).nextPeriodAvailable,true);
});

test("each operating level is compared with the same level, and levels the reference hardly ran at are said apart",()=>{
  const base=analyzed();
  const condition=ready({...base,
    operating_levels:{stopped_below:1,levels:[{low:1,high:45.9,typical:31.4},{low:45.9,high:null,typical:61.9}]},
    pattern:{...base.pattern,split:"operating-level",threshold:1,above_reference_count:2,scored_samples:40,above_reference_percent:5,unscored_samples:20,
      notable:[{...base.pattern.notable[0],score:1.6,band:2}],
      levels:[{band:1,reference_samples:0,target_samples:20,state:"insufficient-reference"},
        {band:2,reference_samples:60,target_samples:40,state:"scored",above_reference_count:2}]}});
  assert.ok(condition.pattern.byLevel);
  const lines=insights(condition);
  assert.ok(lines.includes("같은 운전 상태끼리 견준 기준 패턴의 99% 점수 범위를 넘은 관측 2개 / 40개 (5%)."));
  assert.ok(lines.includes("기준 기간에 드물었던 운전 상태라 견주지 않은 관측 · 약 31 A 운전 20개(기준 기간 0개)."));
  assert.equal(firstChecks(condition)[0].detail,"약 62 A 운전 중 · vR 240 V · 기준 5–95% 범위 229–232 V");
  // A split result must name its levels.
  assert.throws(()=>ready({...base,pattern:{...base.pattern,split:"operating-level",levels:[]}}),/형식/);
  assert.equal(ready(base).pattern.byLevel,null);
});
