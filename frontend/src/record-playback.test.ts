import {test} from "node:test";
import assert from "node:assert/strict";
import {playbackScope, playbackStep, scopedUrl, scopeParams} from "./record-playback.ts";
import {tabSelectionUrl, investigationOriginUrl} from "./routes.ts";

test("accelerating delivery keeps the original measured time in requests", () => {
  const until=Date.parse("2020-10-05T00:00:00+09:00"),scope={kind:"history" as const,until};
  assert.deepEqual(playbackScope("?"+new URLSearchParams(scopeParams(scope))),scope);
  const next=playbackStep(until-86400_000,until,until-1000,20);
  assert.equal(next,until);
  assert.equal(new URL(scopedUrl("/api/v1/forecast?series=voltage",scope),"http://local").searchParams.get("record_until"),new Date(until).toISOString());
});
test("a waveform ordinal never becomes a wall clock timestamp", () => {
  assert.deepEqual(playbackScope("?acquisition_until=72"),{kind:"vibration",until:72});
  assert.equal(playbackScope("?acquisition_until=0"),null);
  assert.equal(playbackScope("?record_until=invalid"),null);
});
test("a replay cutoff travels to the same asset's analysis, but not another asset",()=>{
  const current="http://local/web/?monitor_asset=bearing&acquisition_until=72";
  const same=tabSelectionUrl("/web/?page=assets&monitor_asset=bearing&tab=outlook&data=vibration",current);
  assert.equal(new URL(same,"http://local").searchParams.get("acquisition_until"),"72");
  const suggested=investigationOriginUrl("/web/?page=assets&monitor_asset=bearing&tab=change&method=spectrum",current);
  assert.equal(new URL(suggested,"http://local").searchParams.get("acquisition_until"),"72");
  const other=tabSelectionUrl("/web/?page=assets&monitor_asset=motor&tab=outlook",current);
  assert.equal(new URL(other,"http://local").searchParams.has("acquisition_until"),false);
});
