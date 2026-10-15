// One selected asset shared by every asset view: overview, signal exploration, anomaly detection
// and analysis records. The `monitor_asset` URL parameter keeps links and reloads on it.
const byId = (id) => document.getElementById(id);
const known = new Map();
const listeners = new Set();
let current = new URLSearchParams(location.search).get("monitor_asset") || "";

export const assetName = (id) => /^aihub-air-compressor-/.test(id) ? "공기압축기 " + id.replace("aihub-air-compressor-", "") : id;
export function currentAsset() {return current;}
export function onAssetChange(listener) {listeners.add(listener);}

export function setAsset(id) {
  if (!id || id === current) return;
  current = id;
  const url = new URL(location.href);
  for (const key of ["monitor_source", "monitor_channel", "monitor_range"]) url.searchParams.delete(key);
  url.searchParams.set("monitor_asset", id);
  history.replaceState(history.state, "", url);
  renderSwitch();
  for (const listener of listeners) listener(id);
}

// Each reader reports the assets it knows: stored observations, monitor fleet, PHM bindings.
export function registerAssets(origin, ids) {
  known.set(origin, [...new Set(ids.filter(Boolean))]);
  const all = allAssets();
  if (!current && all.length) setAsset(all[0]);
  else renderSwitch();
}

function allAssets() {return [...new Set([...known.values()].flat())].sort((a, b) => a.localeCompare(b));}

function renderSwitch() {
  const select = byId("asset-switch");
  const all = allAssets();
  const ids = !current || all.includes(current) ? all : [current, ...all];
  const option = (value, text) => Object.assign(document.createElement("option"), {value, textContent: text});
  if (!ids.length) {select.replaceChildren(option("", "설비 없음"));select.disabled = true;return;}
  if ([...select.options].map((o) => o.value).join("\u0000") !== ids.join("\u0000")) {
    select.replaceChildren(...ids.map((id) => option(id, assetName(id))));
  }
  select.value = current;select.disabled = false;
}

export function initializeAssetContext() {
  byId("asset-switch").addEventListener("change", (event) => setAsset(event.target.value));
  renderSwitch();
}
