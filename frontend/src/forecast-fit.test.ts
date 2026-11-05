import assert from "node:assert/strict";
import {test} from "node:test";
import {parseForecastFit,worseThanPersistence,outsideRecentRange} from "./forecast-fit.ts";
import {forecastMessage} from "./analysis-messages.ts";

test("the model start gap remains an observed difference, without offsetting its forecast",()=>{
  const raw={history:[["2026-11-05T00:00:00Z",42.96],["missing",null]],forecast:[["2026-11-05T00:00:00Z",50.99,38.65,64.58],["2026-11-05T01:00:00Z",50.97,37,64]],bucket_seconds:3196.749,model:{points:1000,interval_width:0.8}};
  const fit=parseForecastFit(raw)!;
  assert.equal(fit.observed,42.96);
  assert.equal(fit.modeled,50.99);
  assert.ok(Math.abs(fit.gap-8.03)<1e-10);
  assert.equal(outsideRecentRange(fit),true);
  assert.equal(fit.bucketSeconds,3196.749);
  assert.equal(raw.forecast[0][1],50.99);
  assert.equal(worseThanPersistence({error:1e-12,naive:0}),false);
  assert.equal(worseThanPersistence({error:8,naive:0.5}),true);
  const told=forecastMessage({last:42.96,end:{estimate:50.97,lower:37.14,upper:64.43},unit:null,horizon:"1시간 뒤",
    checks:[{points:5,error:8,naive:0.5,coverage:1}]});
  assert.match(told.headline,/마지막 값 유지보다 모델 예측 오차가 큽니다/);
  assert.match(told.meaning!,/42.96|43/);
});
