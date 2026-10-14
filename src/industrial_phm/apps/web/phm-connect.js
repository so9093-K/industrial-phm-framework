// Connect a model package to the selected asset from its anomaly or RUL tab. The server matches
// packages to the asset's own input streams; the runner then analyzes that stream's stored and new inputs.
const TASK = {anomaly: "anomaly-score", rul: "rul-estimate"};
const NOUN = {anomaly: "이상 탐지", rul: "RUL"};
const STREAM_LABEL = {"acquisition-snapshot": "진동 파형", "observation-window": "OPC UA 관측"};
const MAX_AGE_MS = 30000;
const cache = new Map();
const pending = {anomaly: false, rul: false};
const node = (tag, text = "", className = "") => {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  if (className) element.className = className;
  return element;
};

export function modelFamily(recipe = "", task = "") {
  if (/autoencoder/.test(recipe)) return "재구성 오차 · LSTM";
  if (/pca/.test(recipe)) return "재구성 오차 · PCA";
  if (/iforest/.test(recipe)) return "이상 점수 · IF";
  if (/lstm/.test(recipe)) return "RUL · LSTM";
  if (/ridge/.test(recipe)) return "RUL · Ridge";
  return {"anomaly-score": "이상 점수", "rul-estimate": "RUL 추정"}[task] || recipe;
}

async function readModels(asset) {
  const known = cache.get(asset);
  if (known && Date.now() - known.at < MAX_AGE_MS) return known.data;
  const response = await fetch("/api/v1/phm/models?asset_id=" + encodeURIComponent(asset), {headers: {Accept: "application/json"}});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "read_failed");
  cache.set(asset, {at: Date.now(), data});
  return data;
}

async function connect(payload) {
  const session = await (await fetch("/api/v1/session", {cache: "no-store", credentials: "same-origin"})).json();
  if (session.write_scope !== "supervisor-owned-source-control") throw new Error("supervisor_required");
  const response = await fetch("/api/v1/phm/bindings/create", {method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token}, body: JSON.stringify(payload)});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "connect_failed");
  return data;
}

function streamText(stream) {
  const parts = [STREAM_LABEL[stream.kind] || stream.kind, stream.source_id];
  if (stream.channels?.length) parts.push(stream.channels.length + "채널");
  if (stream.sampling_rate_hz) parts.push((stream.sampling_rate_hz / 1000).toLocaleString("ko-KR", {maximumFractionDigits: 1}) + " kHz");
  return parts.join(" · ");
}

function emptyText(view, packages, streams) {
  if (!streams.length) return "이 설비에는 모델 입력으로 쓸 진동 파형이나 OPC UA 관측 데이터가 없습니다. CSV로 저장한 측정값은 개요와 신호 비교에서 볼 수 있습니다.";
  if (!packages.length) return "작업공간에 " + NOUN[view] + " 모델이 없습니다. 모델 패키지를 작업공간 models 폴더에 넣으면 여기에서 연결할 수 있습니다.";
  return "이 설비 데이터와 입력 형식이 맞는 " + NOUN[view] + " 모델이 없습니다.";
}

// Rendered from the poll cycle; unchanged content is left alone so a click is never interrupted.
// Without a model the list sits under the status line; with one it folds into the tab's end.
export async function renderModelConnect(view, asset, hasModel, onConnected) {
  const [first, more] = [document.getElementById(view + "-connect"), document.getElementById(view + "-connect-more")];
  const root = hasModel ? more : first;
  const other = hasModel ? first : more;
  if (other.childElementCount) {other.replaceChildren();other.dataset.key = "";}
  if (!asset) {root.replaceChildren();root.dataset.key = "";return;}
  if (pending[view]) return;
  let data;
  try {data = await readModels(asset);} catch {
    if (root.dataset.key !== "error") {root.replaceChildren(node("p", "연결할 수 있는 모델을 불러오지 못했습니다.", "muted"));root.dataset.key = "error";}
    return;
  }
  if (pending[view]) return;
  const packages = (data.packages || []).filter((item) => item.task === TASK[view]);
  const streams = data.streams || [];
  const ready = [];
  const blocked = [];
  for (const pkg of packages) {
    if (pkg.candidates.some((item) => item.connected)) continue;
    const fits = pkg.candidates.filter((item) => item.compatible);
    if (fits.length) for (const candidate of fits) ready.push({pkg, candidate});
    else if (pkg.candidates.length) blocked.push({pkg, reason: pkg.candidates[0].reason});
  }
  const key = JSON.stringify([asset, hasModel, ready.map((item) => [item.pkg.package_id, item.candidate.source_id]), blocked.length]);
  if (root.dataset.key === key) return;
  root.dataset.key = key;
  if (hasModel && !ready.length) {root.replaceChildren();return;}
  const list = node("div", "", "model-connect-list");
  for (const {pkg, candidate} of ready) {
    const stream = streams.find((item) => item.source_id === candidate.source_id && item.measurement_point_id === candidate.measurement_point_id);
    const row = node("div", "", "model-connect-row");
    const text = node("div");
    text.append(node("strong", modelFamily(pkg.recipe_id || "", pkg.task)), node("small", (pkg.recipe_id || pkg.package_id) + (stream ? " · 입력 " + streamText(stream) : "")));
    const button = node("button", "연결");
    button.type = "button";
    button.setAttribute("aria-label", modelFamily(pkg.recipe_id || "", pkg.task) + " 모델 연결");
    const status = node("small", "", "model-connect-status");
    status.setAttribute("role", "status");
    button.addEventListener("click", async () => {
      pending[view] = true;
      for (const other of root.querySelectorAll("button")) other.disabled = true;
      button.textContent = "연결 중…";
      try {
        const result = await connect({package_id: pkg.package_id, source_id: candidate.source_id, asset_id: asset,
          ...(candidate.measurement_point_id ? {measurement_point_id: candidate.measurement_point_id} : {})});
        cache.delete(asset);root.dataset.key = "";
        onConnected(result.binding_id);
      } catch (error) {
        status.textContent = error.message === "supervisor_required"
          ? "읽기 전용 화면입니다. make up으로 실행 중인 작업공간에서 연결할 수 있습니다."
          : "연결하지 못했습니다: " + error.message;
        button.textContent = "연결";
        for (const other of root.querySelectorAll("button")) other.disabled = false;
      } finally {
        pending[view] = false;
      }
    });
    row.append(text, button, status);
    list.append(row);
  }
  if (hasModel) {
    const details = node("details", "", "phm-options");
    details.append(node("summary", "다른 모델 연결 (" + ready.length + ")"), list);
    root.replaceChildren(details);
    return;
  }
  const box = node("section", "", "model-connect");
  box.append(node("h3", "연결할 수 있는 " + NOUN[view] + " 모델"));
  if (ready.length) {
    box.append(node("p", "연결하면 이 설비에 저장된 입력부터 분석해 결과를 여기에 표시합니다.", "muted"), list);
  } else {
    box.append(node("p", emptyText(view, packages, streams), "muted"));
    if (blocked.length) {
      const details = node("details", "", "phm-options");
      details.append(node("summary", "입력 형식이 맞지 않는 모델 " + blocked.length + "개"));
      for (const {pkg, reason} of blocked) details.append(node("p", modelFamily(pkg.recipe_id || "", pkg.task) + " · " + (pkg.recipe_id || pkg.package_id) + " — " + reason, "muted"));
      box.append(details);
    }
  }
  root.replaceChildren(box);
}
