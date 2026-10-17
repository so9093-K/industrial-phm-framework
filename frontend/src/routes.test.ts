import assert from "node:assert/strict";
import { test } from "node:test";
import {
  assetTabUrl, assetUrl, canonicalUrl, parseRoute, reviewFocus, routeUrl, systemSection, systemUrl, PAGES, PAGE_INFO, TABS, TAB_INFO,
} from "./routes.ts";

test("pages and asset tabs are user tasks; unknown values are not invented", () => {
  assert.deepEqual(parseRoute("?page=unknown&tab=nope&monitor_asset=pump%2F1").route,
    {page: "monitor", assetId: "pump/1", tab: "summary", method: null, data: null});
  for (const page of PAGES) assert.ok(PAGE_INFO[page].label);
  for (const tab of TABS) {
    assert.ok(TAB_INFO[tab]);
    assert.equal(parseRoute(routeUrl({page: "assets", assetId: "m", tab, method: null, data: null})
      .split("?")[1]).route.tab, tab);
  }
  // A method or data kind only exists inside the tab that offers it.
  assert.deepEqual(parseRoute("?page=assets&tab=signals&method=relation&data=vibration").route,
    {page: "assets", assetId: "", tab: "signals", method: null, data: null});
  assert.equal(parseRoute("?page=assets&tab=change&method=spectrum&data=history").route.data, null);
  assert.equal(parseRoute("?page=assets&tab=outlook&data=vibration").route.data, "vibration");
});

test("every former workflow address lands on its new place with its own parameters", () => {
  const cases: Array<[string, string]> = [
    ["view=departures", "page=assets&tab=anomaly&method=baseline"],
    ["view=model-evidence", "page=assets&tab=anomaly&method=model"],
    ["view=features", "page=assets&tab=change&method=compare&data=vibration"],
    ["view=acq-relation", "page=assets&tab=change&method=relation&data=vibration"],
    ["view=spectrum", "page=assets&tab=change&method=spectrum"],
    ["view=acq-outlook", "page=assets&tab=outlook&data=vibration"],
    ["view=projection", "page=assets&tab=outlook&data=history"],
    ["view=reviews", "page=maintenance"],
    ["view=overview", ""],
  ];
  for (const [legacy, expected] of cases) {
    const {legacy: isLegacy} = parseRoute("?" + legacy);
    assert.equal(isLegacy, true);
    const url = new URL(canonicalUrl("?" + legacy + "&monitor_asset=a"), "http://local");
    const want = new URLSearchParams(expected);
    for (const [key, value] of want) assert.equal(url.searchParams.get(key), value, legacy);
    assert.equal(url.searchParams.has("view"), false);
    assert.equal(url.searchParams.get("monitor_asset"), "a");
  }
  const kept = new URL(canonicalUrl("?view=projection&monitor_asset=m&projection_management=7"),
    "http://local");
  assert.equal(kept.searchParams.get("projection_management"), "7");
});

test("changing assets removes all old evidence and conditions while keeping the task", () => {
  const original = "http://localhost:2718/web-next/?page=assets&tab=outlook&data=history" +
    "&monitor_asset=motor-a&monitor_channel=R&projection_direction=lower&projection_management=7" +
    "&measurement_version=old&capture_id=unrelated&future_param=old";
  const changed = new URL(assetUrl(original, "motor-b"), "http://localhost");
  assert.deepEqual([...changed.searchParams.entries()],
    [["page", "assets"], ["tab", "outlook"], ["monitor_asset", "motor-b"]]);
  assert.equal(new URL(assetUrl("http://l/web-next/", "a"), "http://l").searchParams.get("page"),
    "assets");
  assert.throws(() => assetUrl(original, ""), /설비 식별자/);
});

test("links inside an asset carry only the asset, the task and a chosen signal", () => {
  const url = new URL(assetTabUrl("a & b", "change", "compare", "history", "R/S"), "http://local");
  assert.equal(url.searchParams.get("monitor_asset"), "a & b");
  assert.equal(url.searchParams.get("monitor_channel"), "R/S");
  assert.equal(url.searchParams.get("method"), "compare");
  assert.equal(routeUrl({page: "monitor", assetId: "", tab: "summary", method: null, data: null}),
    "/web-next/");
  assert.equal(new URL(routeUrl({page: "maintenance", assetId: "x", tab: "summary", method: null,
    data: null}, "R"), "http://local").searchParams.has("monitor_channel"), false);
});

test("a review subject is only read on the maintenance page", () => {
  assert.deepEqual(reviewFocus("?page=maintenance&monitor_asset=a&capture_id=c"), {captureId: "c", findingId: null});
  assert.deepEqual(reviewFocus("?page=maintenance&finding_id=f"), {captureId: null, findingId: "f"});
  assert.deepEqual(reviewFocus("?page=assets&capture_id=c"), {captureId: null, findingId: null});
});

test("운영 관리 opens data connections unless the address asks for system status",()=>{
  assert.equal(systemSection("?page=system"),"connections");
  assert.equal(systemSection("?page=system&section=status"),"status");
  assert.equal(systemSection("?page=system&section=unknown"),"connections");
  assert.equal(systemUrl("status"),"/web-next/?page=system&section=status");
});
