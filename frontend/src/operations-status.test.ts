import assert from "node:assert/strict";
import {test} from "node:test";
import {parseRuntimeStatus,parseSources,receiptText} from "./operations-status.ts";

const runtime={schema_version:1,assessed_at:"2026-10-17T00:00:00Z",
  meaning:"local-process-readiness-not-collection-receipt-or-asset-health",ready:false,
  supervisor:{condition:"stopped",pid:null,heartbeat_at:null},
  components:["collection","analysis","ui"].map(kind=>({kind,condition:"stopped",pid:null,runtime_state:null,heartbeat_at:null}))};
function source(extra:Record<string,unknown>={}){
  return {source_id:"s1",name:"Pump CSV",source_type:"file",asset_id:"pump-1",measurement_point_id:"panel",
    lifecycle_state:"active",receipt_confirmed:false,last_accepted_received_at:null,last_accepted_observed_at:null,
    live_telemetry_read_error:false,file_history_job:null,...extra};
}
const sources=(...items:unknown[])=>({schema_version:1,assessed_at:"2026-10-17T00:00:00Z",
  meaning:"registration-does-not-imply-accepted-receipt-or-live-connection",
  sources:{items,total:items.length,truncated:false},read_error_scopes:[],live_evidence_error_scopes:[]});

test("process readiness is read as stated and never invented",()=>{
  const parsed=parseRuntimeStatus(runtime);
  assert.equal(parsed.ready,false);
  assert.deepEqual(parsed.components.map(item=>item.kind),["collection","analysis","ui"]);
  assert.throws(()=>parseRuntimeStatus({...runtime,meaning:"asset-health"}),/실행 상태/);
  assert.throws(()=>parseRuntimeStatus({...runtime,supervisor:{condition:"healthy"}}),/실행 상태/);
});

test("registration is not receipt, and a connection claim needs live evidence",()=>{
  const [file]=parseSources(sources(source())).items;
  assert.equal(receiptText(file),"파일 확인 대기");
  assert.equal(receiptText(parseSources(sources(source({receipt_confirmed:true}))).items[0]),"파일 읽기 확인됨");
  const live=(extra:Record<string,unknown>)=>parseSources(sources(source({source_type:"opcua",...extra}))).items[0];
  assert.equal(receiptText(live({})),"수신 미확인");
  assert.equal(receiptText(live({receipt_confirmed:true})),"1회 수신 확인 · 연속 수신 미확인");
  assert.equal(receiptText(live({last_live_received_at:"2026-10-17T00:00:00Z"})),"최근 수신 미확인");
  assert.equal(receiptText(live({last_live_receive_fresh:true,opcua_session_last_state:"CONNECTED"})),"수신 확인됨");
  assert.equal(receiptText(live({last_live_receive_fresh:true,opcua_session_last_state:"DISCONNECTED"})),"현재 연결 미확인");
  assert.equal(receiptText(live({live_telemetry_read_error:true})),"수신 상태 조회 실패");
  assert.throws(()=>parseSources({...sources(),meaning:"connected"}),/데이터 연결 목록/);
});
