import assert from "node:assert/strict";
import {test} from "node:test";
import {firstChecks,insights,kstInstant,parseCondition,segments,type Condition} from "./electrical-condition.ts";

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

test("lines never join across a missing value or a time gap",()=>{
  const runs=segments(ready(analyzed()).timeline,"currentMean");
  assert.deepEqual(runs.map(run=>run.length),[2,1,1]);
});

test("KST inputs are sent as the same instant with an explicit offset",()=>{
  assert.equal(kstInstant("2020-11-13T12:30:15"),"2020-11-13T12:30:15+09:00");
  assert.equal(kstInstant("2020-11-13T10:00"),"2020-11-13T10:00:00+09:00");
  assert.throws(()=>kstInstant("2020-11-13 10:00"),/시각 형식/);
});
