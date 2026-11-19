import assert from "node:assert/strict";
import { test } from "node:test";
import {
  assetTabUrl, assetUrl, parseRoute, reviewFocus, routeUrl, tabSelectionUrl, summarySelectionUrl, systemSection, systemUrl, PAGES, PAGE_INFO, TABS, TAB_INFO,
} from "./routes.ts";

test("analysis entered from monitoring retains the selected phenomenon after refresh",()=>{
  const current="http://local/web/?monitor_asset=bearing&summary_change=vertical-change&summary_kind=vibration&vibration_feature=feature.Vertical_vibration_signals.rms";
  const next=new URL(tabSelectionUrl("/web/?page=assets&monitor_asset=bearing&tab=outlook&data=vibration",current),current);
  assert.equal(next.searchParams.get("summary_change"),"vertical-change");
  assert.equal(next.searchParams.get("acq_forecast_feature"),"feature.Vertical_vibration_signals.rms");
});

test("end criteria belong to their feature, while a new interval of that feature keeps them",()=>{
  const current="http://local/web/?page=assets&tab=outlook&monitor_asset=bearing&acq_forecast_feature=feature.vertical.rms&acq_end=6";
  const changed=summarySelectionUrl(current,"/web/?page=assets&monitor_asset=bearing&vibration_feature=feature.vertical.skewness","other","vibration");
  assert.equal(new URL(changed,current).searchParams.has("acq_end"),false);
  const same=summarySelectionUrl(current,"/web/?page=assets&monitor_asset=bearing&vibration_feature=feature.vertical.rms","same-feature","vibration");
  assert.equal(new URL(same,current).searchParams.get("acq_end"),"6");
});

test("a frequency investigation keeps its channel and zoom across tabs and clears them for a new change",()=>{
  const base="http://local/web/?page=assets&monitor_asset=bearing";
  const focused=base+"&tab=change&method=spectrum&spectrum_channel=vertical&spectrum_hz_from=400&spectrum_hz_to=1600&spectrum_view=measurement&spectrum_measurement=72&spectrum_band=800&spectrum_scale=linear";
  const model=tabSelectionUrl(base+"&tab=anomaly&method=model",focused);
  const back=new URL(tabSelectionUrl(base+"&tab=change&method=spectrum","http://local"+model),"http://local");
  assert.equal(back.searchParams.get("spectrum_channel"),"vertical");
  assert.equal(back.searchParams.get("spectrum_hz_from"),"400");
  assert.equal(back.searchParams.get("spectrum_hz_to"),"1600");
  for(const key of ["spectrum_view","spectrum_measurement","spectrum_band","spectrum_scale"])
    assert.equal(back.searchParams.get(key),new URL(focused).searchParams.get(key));
  const other=new URL(summarySelectionUrl(back.href,base+"&feature_b_from=72&feature_b_to=123","other","vibration"),"http://local");
  assert.equal(other.searchParams.has("spectrum_hz_from"),false);
  assert.equal(other.searchParams.has("spectrum_channel"),false);
  assert.equal(other.searchParams.has("spectrum_measurement"),false);
});

test("returning to a model keeps its compared measurements but a new phenomenon clears them",()=>{
  const base="http://local/web/?page=assets&monitor_asset=pump";
  const selected=base+"&tab=anomaly&method=model&model_binding=history-B&model_position=1603378200000000&model_compare=1603377600000000";
  const away=tabSelectionUrl(base+"&tab=change&method=compare",selected);
  const back=new URL(tabSelectionUrl(base+"&tab=anomaly&method=model","http://local"+away),base);
  for(const key of ["model_binding","model_position","model_compare"])
    assert.equal(back.searchParams.get(key),new URL(selected).searchParams.get(key));
  const other=new URL(summarySelectionUrl(back.href,base+"&monitor_channel=temperature","another-change","history"),base);
  assert.equal(other.searchParams.has("model_binding"),false);
  assert.equal(other.searchParams.has("model_position"),false);
  assert.equal(other.searchParams.has("model_compare"),false);
});

test("tab activation carries the latest chosen signal while dropping workflow-specific settings", () => {
  const origin="http://127.0.0.1:2770";
  const current=origin+"/web/?page=assets&tab=signals&monitor_asset=pump&monitor_channel=temperature&monitor_range=15m&monitor_source=B&monitor_point=&monitor_interpretation=meaning&forecast_prior=0.5&capture_id=old";
  const next=tabSelectionUrl("/web/?page=assets&tab=outlook&monitor_asset=pump",current);
  assert.equal(new URL(next,origin).searchParams.get("monitor_channel"),"temperature");
  assert.equal(new URL(next,origin).searchParams.get("monitor_range"),"15m");
  assert.equal(new URL(tabSelectionUrl("/web/?page=assets&tab=outlook&monitor_asset=other",current),origin).searchParams.has("monitor_channel"),false);
  const retained=new URL(next,origin).searchParams;
  assert.equal(retained.get("monitor_source"),"B");
  assert.equal(retained.get("monitor_point"),"");
  assert.equal(retained.get("monitor_interpretation"),"meaning");
  assert.equal(retained.has("forecast_prior"),false);
  assert.equal(retained.has("capture_id"),false);
  const wave=origin+"/web/?page=assets&tab=signals&monitor_asset=bearing&vibration_feature=vertical.rms";
  assert.equal(new URL(tabSelectionUrl("/web/?page=assets&tab=outlook&monitor_asset=bearing",wave),origin).searchParams.get("acq_forecast_feature"),"vertical.rms");
  const summary=tabSelectionUrl("/web/?page=assets&monitor_asset=bearing",wave);
  assert.equal(new URL(tabSelectionUrl("/web/?page=assets&tab=outlook&monitor_asset=bearing",origin+summary),origin).searchParams.get("acq_forecast_feature"),"vertical.rms");
});

test("a chosen summary change replaces the prior record and carries its operating level and periods",()=>{
  const base="http://local/web/?page=assets&monitor_asset=pump";
  const before=base+"&monitor_channel=old&monitor_source=A&compare_level=1&vibration_feature=old";
  const picked=base+"&monitor_channel=pressure&monitor_source=B&monitor_point=&monitor_interpretation=pressure-meaning&compare_level=3&compare_a=a&compare_b=b&relation_x=pressure&relation_y=current";
  const chosen=summarySelectionUrl(before,picked,"change-B","history");
  const query=new URL(tabSelectionUrl(base+"&tab=change",'http://local'+chosen),'http://local').searchParams;
  assert.equal(query.get("monitor_channel"),"pressure");
  assert.equal(query.get("monitor_source"),"B");
  assert.equal(query.get("monitor_point"),"");
  assert.equal(query.get("monitor_interpretation"),"pressure-meaning");
  assert.equal(query.get("compare_level"),"3");
  assert.equal(query.get("compare_b"),"b");
  assert.equal(query.get("relation_x"),"pressure");
  assert.equal(query.get("data"),"history");
  assert.equal(query.has("vibration_feature"),false);
  assert.equal(query.get("summary_change"),"change-B");
  const edited=new URL('http://local'+chosen);edited.searchParams.set("monitor_channel","voltage");
  assert.equal(new URL(tabSelectionUrl(base+"&tab=change&method=relation",edited.href),'http://local').searchParams.get("relation_x"),"voltage");
  assert.throws(()=>summarySelectionUrl(before,picked.replace('pump','other'),"change-B","history"));
});

test("a selected bearing change keeps its feature and acquisition periods across analysis tabs",()=>{
  const base="http://local/web/?page=assets&monitor_asset=bearing";
  const choice=base+"&acquisition_feature=vertical.rms&vibration_feature=vertical.rms&feature_a_from=1&feature_a_to=10&feature_b_from=23&feature_b_to=30";
  const summary=summarySelectionUrl(base,choice,"vertical-change","vibration");
  const comparison=new URL(tabSelectionUrl(base+"&tab=change&method=compare",'http://local'+summary),'http://local');
  assert.equal(comparison.searchParams.get("data"),"vibration");
  assert.equal(comparison.searchParams.get("acquisition_feature"),"vertical.rms");
  assert.equal(comparison.searchParams.get("feature_b_from"),"23");
  const signal=tabSelectionUrl(base+"&tab=signals",comparison.href);
  assert.equal(new URL(tabSelectionUrl(base+"&tab=change",'http://local'+signal),'http://local').searchParams.get("data"),"vibration");
  assert.equal(new URL(tabSelectionUrl(base+"&tab=change&data=history",comparison.href),'http://local').searchParams.get("summary_kind"),"history");
  const relation=new URL(tabSelectionUrl(base+"&tab=change&method=relation",comparison.href),'http://local');
  assert.equal(relation.searchParams.get("acq_b_from"),"23");
  const revised=new URL(relation);revised.searchParams.set("acq_b_to","29");
  assert.equal(new URL(tabSelectionUrl(base+"&tab=change&method=compare",revised.href),'http://local').searchParams.get("feature_b_to"),"29");
  revised.searchParams.set("acq_relation_x","horizontal.rms");
  assert.equal(new URL(tabSelectionUrl(base+"&tab=signals",revised.href),'http://local').searchParams.get("vibration_feature"),"horizontal.rms");
  const defaultComparison=new URL(comparison);defaultComparison.searchParams.delete("method");defaultComparison.searchParams.set("feature_b_to","28");
  assert.equal(new URL(tabSelectionUrl(base+"&tab=change&method=relation",defaultComparison.href),'http://local').searchParams.get("acq_b_to"),"28");
  comparison.searchParams.set("acquisition_feature","horizontal.rms");
  assert.equal(new URL(tabSelectionUrl(base+"&tab=change&method=relation",comparison.href),'http://local').searchParams.get("acq_relation_x"),"horizontal.rms");
});

test("record links resolve directly to their pages", () => {
  assert.equal(parseRoute("?page=investigations&monitor_asset=motor-a").page, "investigations");
  assert.equal(parseRoute("?page=maintenance&monitor_asset=motor-a&finding_id=f").page, "maintenance");
});

test("pages and asset tabs are user tasks; unknown values are not invented", () => {
  assert.deepEqual(parseRoute("?page=unknown&tab=nope&monitor_asset=pump%2F1"),
    {page: "monitor", assetId: "pump/1", tab: "summary", method: null, data: null});
  for (const page of PAGES) assert.ok(PAGE_INFO[page].label);
  for (const tab of TABS) {
    assert.ok(TAB_INFO[tab]);
    assert.equal(parseRoute(routeUrl({page: "assets", assetId: "m", tab, method: null, data: null})
      .split("?")[1]).tab, tab);
  }
  // A method or data kind only exists inside the tab that offers it.
  assert.deepEqual(parseRoute("?page=assets&tab=signals&method=relation&data=vibration"),
    {page: "assets", assetId: "", tab: "signals", method: null, data: null});
  assert.equal(parseRoute("?page=assets&tab=change&method=spectrum&data=history").data, null);
  assert.equal(parseRoute("?page=assets&tab=change&method=electrical&data=vibration").data, null);
  assert.equal(parseRoute("?page=assets&tab=outlook&data=vibration").data, "vibration");
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



test("a selected waveform opens the same model measurement and spectrum keeps edited comparison periods",()=>{
  const base="http://local/web/?page=assets&monitor_asset=bearing";
  const wave=base+"&tab=signals&vibration_at=72&acquisition_binding=model-B";
  const model=new URL(tabSelectionUrl(base+"&tab=anomaly",wave),base);
  assert.equal(model.searchParams.get("model_position"),"72");
  assert.equal(model.searchParams.get("model_binding"),"model-B");
  const compare=base+"&tab=change&feature_a_from=1&feature_a_to=37&feature_b_from=72&feature_b_to=123";
  const spectrum=new URL(tabSelectionUrl(base+"&tab=change&method=spectrum",compare),base);
  assert.equal(spectrum.searchParams.get("spectrum_b_from"),"72");
  spectrum.searchParams.set("spectrum_b_to","120");
  const back=new URL(tabSelectionUrl(base+"&tab=change",spectrum.href),base);
  assert.equal(back.searchParams.get("feature_b_to"),"120");
});

test("the measurement picked in a vibration relationship travels to the model tab",()=>{
  const base="http://local/web/?page=assets&monitor_asset=bearing";
  const relation=base+"&tab=change&method=relation&data=vibration&vibration_at=81&model_position=76";
  const next=new URL(tabSelectionUrl(base+"&tab=anomaly&method=model",relation),base);
  assert.equal(next.searchParams.get("model_position"),"81");
});
