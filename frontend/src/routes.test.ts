import assert from "node:assert/strict";
import { test } from "node:test";
import {
  assetTabUrl, assetUrl, canonicalUrl, parseRoute, reviewFocus, routeUrl, tabSelectionUrl, systemSection, systemUrl, PAGES, PRIMARY_PAGES, PAGE_INFO, TABS, TAB_INFO,
} from "./routes.ts";

test("tab activation carries the latest chosen signal while dropping workflow-specific settings", () => {
  const origin="http://127.0.0.1:2770";
  const current=origin+"/web/?page=assets&tab=signals&monitor_asset=pump&monitor_channel=temperature&monitor_range=15m";
  const next=tabSelectionUrl("/web/?page=assets&tab=outlook&monitor_asset=pump",current);
  assert.equal(new URL(next,origin).searchParams.get("monitor_channel"),"temperature");
  assert.equal(new URL(next,origin).searchParams.has("monitor_range"),false);
  assert.equal(new URL(tabSelectionUrl("/web/?page=assets&tab=outlook&monitor_asset=other",current),origin).searchParams.has("monitor_channel"),false);
  const wave=origin+"/web/?page=assets&tab=signals&monitor_asset=bearing&vibration_feature=vertical.rms";
  assert.equal(new URL(tabSelectionUrl("/web/?page=assets&tab=outlook&monitor_asset=bearing",wave),origin).searchParams.get("acq_forecast_feature"),"vertical.rms");
  const summary=tabSelectionUrl("/web/?page=assets&monitor_asset=bearing",wave);
  assert.equal(new URL(tabSelectionUrl("/web/?page=assets&tab=outlook&monitor_asset=bearing",origin+summary),origin).searchParams.get("acq_forecast_feature"),"vertical.rms");
});

test("primary navigation stays observation-first while old record links still resolve", () => {
  assert.deepEqual([...PRIMARY_PAGES], ["monitor", "assets", "system"]);
  assert.equal(parseRoute("?page=investigations&monitor_asset=motor-a").route.page, "investigations");
  assert.equal(parseRoute("?page=maintenance&monitor_asset=motor-a&finding_id=f").route.page, "maintenance");
});

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
  assert.equal(parseRoute("?page=assets&tab=change&method=electrical&data=vibration").route.data, null);
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
  const original = "http://localhost:2718/web/?page=assets&tab=outlook&data=history" +
    "&monitor_asset=motor-a&monitor_channel=R&projection_direction=lower&projection_management=7" +
    "&measurement_version=old&capture_id=unrelated&future_param=old";
  const changed = new URL(assetUrl(original, "motor-b"), "http://localhost");
  assert.deepEqual([...changed.searchParams.entries()],
    [["page", "assets"], ["tab", "outlook"], ["monitor_asset", "motor-b"]]);
  assert.equal(new URL(assetUrl("http://l/web/", "a"), "http://l").searchParams.get("page"),
    "assets");
  assert.throws(() => assetUrl(original, ""), /설비 식별자/);
});

test("links inside an asset carry only the asset, the task and a chosen signal", () => {
  const url = new URL(assetTabUrl("a & b", "change", "compare", "history", "R/S"), "http://local");
  assert.equal(url.searchParams.get("monitor_asset"), "a & b");
  assert.equal(url.searchParams.get("monitor_channel"), "R/S");
  assert.equal(url.searchParams.get("method"), "compare");
  assert.equal(routeUrl({page: "monitor", assetId: "", tab: "summary", method: null, data: null}),
    "/web/");
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
  assert.equal(systemUrl("status"),"/web/?page=system&section=status");
});

test("retired hash and model bookmarks keep their exact selection at the default address",()=>{
  const cases:[[string,string],string][]=[[["","#connect"],"page=system&section=connections"],[["","#system"],"page=system&section=status"],
    [["?phm_binding=b%2Fa&phm_position=2&phm_compare=1","#anomaly"],"page=assets&tab=anomaly&method=model&model_binding=b%2Fa&model_position=2&model_compare=1"]];
  for(const [[search,hash],expected] of cases){
    const actual=new URL(canonicalUrl(search,hash),"http://local");
    assert.equal(actual.pathname,"/web/");
    for(const [key,value] of new URLSearchParams(expected))assert.equal(actual.searchParams.get(key),value);
    assert.equal(actual.searchParams.has("phm_binding"),false);
  }
  assert.equal(parseRoute("?page=maintenance","#connect").route.page,"maintenance");
});

test("legacy forecast and exploration conditions move with their axis and exact series",()=>{
  const projection=new URL(canonicalUrl("?monitor_asset=a&forecast_series=history%7CR&forecast_horizon=7d&forecast_threshold=8&forecast_prior=0.2","#forecast"),"http://local");
  assert.equal(projection.searchParams.get("monitor_channel"),"R");
  assert.equal(projection.searchParams.get("projection_horizon"),"7d");
  assert.equal(projection.searchParams.get("projection_management"),"8");
  assert.equal(projection.searchParams.get("forecast_prior"),"0.2");
  const acq=new URL(canonicalUrl("?forecast_series=acquisition%7Cfeature.rms&forecast_horizon=24h&forecast_assumed_period=60","#rul"),"http://local");
  assert.equal(acq.searchParams.get("data"),"vibration");
  assert.equal(acq.searchParams.get("acq_forecast_unit"),"time");
  assert.equal(acq.searchParams.get("acq_assumed_period"),"60");
  const compare=new URL(canonicalUrl("?explore_kind=acquisition&explore_series=feature.rms&explore_a=1~8&explore_b=9~16","#signals"),"http://local");
  assert.equal(compare.searchParams.get("method"),"compare");
  assert.equal(compare.searchParams.get("acquisition_feature"),"feature.rms");
  assert.equal(compare.searchParams.get("feature_b_from"),"9");
});
