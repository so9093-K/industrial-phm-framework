import assert from "node:assert/strict";
import {test} from "node:test";
import {explainWrite,nextStep,otherActions,parsePreflight} from "./connections.ts";
import {parseSources} from "./operations-status.ts";
import {errorCode,OutcomeUnknown,WriteRejected} from "./writes.ts";

function source(extra:Record<string,unknown>={}){
  const items=[{source_id:"s1",name:"Pump CSV",source_type:"file",asset_id:"pump-1",measurement_point_id:null,
    lifecycle_state:"active",receipt_confirmed:false,live_telemetry_read_error:false,file_history_job:null,
    phase_binding_count:0,...extra}];
  return parseSources({schema_version:1,meaning:"registration-does-not-imply-accepted-receipt-or-live-connection",
    sources:{items,total:1,truncated:false},read_error_scopes:[],live_evidence_error_scopes:[]}).items[0];
}

test("a file connection moves from use to read to storage to analysis",()=>{
  assert.equal(nextStep(source({lifecycle_state:"registered"}),false).action,"activate");
  assert.equal(nextStep(source(),false).action,"receive");
  assert.equal(nextStep(source({receipt_confirmed:true}),false).action,"store");
  const stored=source({receipt_confirmed:true,file_history_job:{state:"succeeded",started_at:"2026-10-17T00:00:00Z",
    event_count:4,history_snapshot_id:3}});
  assert.equal(nextStep(stored,false).action,"analyze");
  assert.equal(nextStep(stored,true).action,null);
  assert.equal(nextStep(source({receipt_confirmed:true,file_history_job:{state:"running"}}),false).action,null);
  assert.deepEqual(otherActions(source({receipt_confirmed:true,phase_binding_count:3}),"store"),["pause","receive","analyze","phase"]);
});

test("an OPC UA connection is confirmed by one read before collection is requested",()=>{
  const live=(extra:Record<string,unknown>)=>source({source_type:"opcua",...extra});
  assert.equal(nextStep(live({}),false).action,"diagnose");
  assert.equal(nextStep(live({receipt_confirmed:true}),false).action,"collect");
  assert.equal(nextStep(live({receipt_confirmed:true,collection_desired_state:"running"}),false).action,null);
  assert.deepEqual(otherActions(live({receipt_confirmed:true,collection_desired_state:"running"}),null),["pause","diagnose","stop"]);
});

test("preflight results and refusals are read as the server states them",()=>{
  const ready=parsePreflight({schema_version:1,meaning:"csv-preflight-only-not-registered-or-ingested",status:"ready",
    sample_count:4,channel_columns:["a"],first_timestamp:"2026-10-11T00:00:00+00:00",quality_warnings:["gap"],
    registration_match:"absent",issue:null});
  assert.equal(ready.match,"absent");
  assert.deepEqual(ready.warnings,["gap"]);
  assert.throws(()=>parsePreflight({meaning:"registered",status:"ready"}),OutcomeUnknown);
  assert.equal(errorCode({error:{code:"source_id_exists"}}),"source_id_exists");
  assert.equal(errorCode({error:"invalid_phm_query"}),"invalid_phm_query");
  assert.match(explainWrite(new WriteRejected(409,"source_id_exists")),/다른 ID/);
  assert.match(explainWrite(new WriteRejected(409,"workspace_writer_busy")),/작업공간/);
});
