import assert from "node:assert/strict";
import {test} from "node:test";
import {
  channelChoices,inspectCsv,intervals,numberOf,parseCsv,previewPoints,previewProblems,readTimes,summarize,suggestedSourceId,suggestSignalNames,
} from "./csv-preview.ts";

const csv=[
  "timestamp,current_a,note,blank",
  "2026-10-11T09:00:00+09:00,1.5,ok,",
  "2026-10-11T09:00:01+09:00,2.5,ok,",
  "2026-10-11T09:00:02+09:00,3.5,\"a,b\",",
  "2026-10-11T09:00:10+09:00,4.5,ok,",
].join("\n");

test("columns are read as the server will: quoted commas, numbers and times",()=>{
  const rows=parseCsv(csv);
  assert.equal(rows[3][2],"a,b");
  const table=inspectCsv(rows);
  assert.equal(table.sampleCount,4);
  assert.deepEqual(table.times.map(c=>c.name),["timestamp"]);
  assert.deepEqual(channelChoices(table,0).map(c=>[c.name,c.usable]),[["current_a",true],["note",false],["blank",false]]);
  assert.equal(numberOf("1e999"),null);
  assert.equal(numberOf("NaN"),null);
});

test("what would stop the file from being stored is named with its row",()=>{
  const table=inspectCsv(parseCsv(csv));
  assert.deepEqual(previewProblems(table,0,["current_a"]),[]);
  assert.match(previewProblems(table,0,[]).join(),/하나 이상/);
  const naive=inspectCsv(parseCsv("t,v\n2026-10-11T09:00:00,1\n2026-10-11T09:00:00,2\n"));
  const problems=previewProblems(naive,0,["v"]).join(" ");
  assert.match(problems,/시간대/);
  assert.match(problems,/3행의 시각이 앞 행보다 늦지 않습니다/);
  const ragged=inspectCsv(parseCsv("t,v\n2026-10-11T09:00:00Z,1,9\n"));
  assert.match(ragged.problems.join(),/2행의 값 개수/);
});

test("summary, intervals and preview come from the file's own values",()=>{
  const table=inspectCsv(parseCsv(csv));
  assert.deepEqual(summarize(table,"current_a"),{count:4,missing:0,min:1.5,median:3,max:4.5,mean:3});
  const timing=readTimes(table,0);
  const gaps=intervals(timing)!;
  assert.equal(gaps.usualSeconds,1);
  assert.equal(gaps.longestSeconds,8);
  assert.equal(gaps.uneven,1);
  assert.equal(gaps.longestAfter,Date.parse("2026-10-11T09:00:02+09:00"));
  const points=previewPoints(table,timing,"current_a",2);
  assert.equal(points.length,2);
  assert.deepEqual([points[0].min,points[0].max],[1.5,3.5]);
  assert.equal(suggestedSourceId("Pump Log #1.csv","ab12"),"csv-pump-log-1-ab12");
});

test("a column that says what it measures gets a Korean name to start from, never a unit", () => {
  const names = suggestSignalNames(["current_a", "temperature_c", "valve_state", "x1"]);
  assert.deepEqual([...names], [["current_a", "전류"], ["temperature_c", "온도"]]);
  // Three phases of one quantity keep their suffix so the names stay distinct.
  assert.deepEqual([...suggestSignalNames(["voltage_a", "voltage_b", "voltage_c"]).values()], ["전압 A", "전압 B", "전압 C"]);
  assert.equal(suggestSignalNames(["current_motor_inlet_side"]).size, 0);
});
