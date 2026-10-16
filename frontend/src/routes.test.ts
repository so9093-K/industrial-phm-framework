import assert from "node:assert/strict";
import { test } from "node:test";
import { assetUrl, parseRoute, VIEW_INFO, VIEWS, viewUrl } from "./routes.ts";

test("only declared workflows can be opened; unknown routes are not invented", () => {
  assert.deepEqual(parseRoute("?view=unknown&monitor_asset=pump%2F1"),
    {view:"overview",assetId:"pump/1"});
  for (const view of VIEWS) {
    assert.equal(parseRoute(viewUrl(view,"motor-1",null).split("?")[1] ?? "").view,view);
    assert.ok(VIEW_INFO[view].title);
  }
});

test("changing assets removes all old evidence and conditions while keeping the task", () => {
  const original = "http://localhost:2718/web-next/?view=projection&monitor_asset=motor-a" +
    "&monitor_channel=R&projection_direction=lower&projection_management=7" +
    "&projection_end=12&measurement_version=old&capture_id=unrelated&future_param=old";
  const changed = new URL(assetUrl(original,"motor-b"),"http://localhost");
  assert.deepEqual([...changed.searchParams.entries()],
    [["view","projection"],["monitor_asset","motor-b"]]);
  assert.equal(changed.searchParams.get("monitor_channel"),null);
  assert.throws(()=>assetUrl(original,""),/설비 식별자/);
});

test("workflow links only carry chosen signal and asset, never stale conditions", () => {
  const url = new URL(viewUrl("departures","a & b","R/S"),"http://localhost");
  assert.equal(url.searchParams.get("view"),"departures");
  assert.equal(url.searchParams.get("monitor_asset"),"a & b");
  assert.equal(url.searchParams.get("monitor_channel"),"R/S");
  assert.equal(viewUrl("overview","",null),"/web-next/");
  assert.equal(new URL(viewUrl("overview","asset-a","R"),"http://localhost")
    .searchParams.has("monitor_channel"),false);
});
