import {drawSignal, signalChoices, drawTrace, drawMeasuredTrend, measuredRows, recentMeasuredSegment, channelName} from "./monitor-signal.js";
import {formatTime} from "./time.js";
import {showStored, storedChannelState, invalidateStored, selectStoredChannel, selectStoredRange, repaintStored, leaveStored} from "./monitor-history.js";
// Observation first: concise asset facts, then the verified signal, then optional model details.
const POLL_MS = 3000;
const byId = (id) => document.getElementById(id);
const node = (tag, text = "", className = "") => {const e = document.createElement(tag);e.textContent = text;e.className = className;return e;};
const time = (at) => formatTime(at, {missing: "미확인"});
const number = (n) => typeof n === "number" ? n.toLocaleString("ko-KR", {maximumFractionDigits: 3}) : "미평가";
const active = () => document.body.dataset.view === "monitor" && !document.hidden;
const states = {processed: "입력 처리됨", pending: "새 입력 분석 대기", warmup: "LSTM 입력 준비", rejected: "입력 분석 거부", waiting: "확정 입력 대기", unavailable: "모델 실행 불가"};
const reviewLabels = {open: "검토 요청됨", acknowledged: "검토 확인됨", closed: "검토 종료 · 정비 완료 아님"};
// Data-flow evidence of the asset, independent of any connected model.
const flowLabels = {running: "수신 흐름 근거 있음", waiting: "수신 대기", delayed: "수신 지연", stopped: "수집 중지", "needs-attention": "수신 확인 필요",
  error: "수신 오류", unavailable: "수신 상태 미확인", "stored-history": "저장된 과거 기록"};
const HISTORY = "stored-history";
let timer = null, running = false, refreshRequested = false, readOperations;
let lastData = null, lastBase = null, selectedAsset = new URLSearchParams(location.search).get("monitor_asset") || "", selectedStream = "", previousInput = false;
let traceKey = "", traceVersion = 0, traceData = null;
let preview = null, previewKey = "", choiceId = "rms-0", signalVersion = 0, detailsKey = "";
const streamKey = (i) => JSON.stringify([i.source_id, i.measurement_point_id, i.step_kind]);
const replay = (i) => i.recorded_replay || i.latest_delivered?.replay || i.latest_analyzed?.replay;
const inputName = (i, v) => i.step_kind === "observation-window" ? time(v?.event_at || v?.event_start) : v ? "#" + v.position : "없음";
const assetName = (id) => /^aihub-air-compressor-/.test(id) ? "공기압축기 " + id.replace("aihub-air-compressor-", "") : id;
function measuredChange(previous, latest) {
  const difference = latest.value - previous.value;
  if (!difference) return "크기 변화 없음";
  const direction = difference > 0 ? "커짐" : "작아짐";
  if (previous.value <= 0) return "크기 " + direction;
  const percent = Math.abs(difference / previous.value * 100);
  return (percent < .05 ? "0.1% 미만" : percent.toLocaleString("ko-KR", {maximumFractionDigits: 1}) + "%") + " " + direction;
}
function friendlyReason(reason) {
  if (/sha.?256|checksum|digest/i.test(reason || "")) return "전달 후 원본 변경 감지";
  if (/channels differ|sampling rate|sample count|package expects/i.test(reason || "")) return "필요한 입력 규격과 다름";
  if (/file|snapshot.*unavailable/i.test(reason || "")) return "원본 입력을 읽을 수 없음";
  return "입력 조건 미충족";
}
function role(item) {
  const family = /lstm/i.test(item.recipe_id) ? "LSTM" : /ridge/i.test(item.recipe_id) ? "Ridge" : /pca/i.test(item.recipe_id) ? "PCA" : /iforest/i.test(item.recipe_id) ? "Isolation Forest" : "연결 모델";
  return (item.task === "rul-estimate" ? "기록 RUL" : item.step_kind === "observation-window" ? "전기 이상" : "진동 이상") + " · " + family;
}
function detailLink(item, position = item.latest_analyzed?.position) {
  const url = new URL(location.href), view = item.task === "rul-estimate" ? "rul" : "anomaly";
  url.searchParams.set("phm_binding", item.binding_id);url.searchParams.set("phm_position", position);
  url.searchParams.set("phm_view", view);url.searchParams.set("monitor_asset", item.asset_id);url.hash = view;return url.pathname + url.search + url.hash;
}
function assetFacts(assetId, items, base) {
  const notes = [];
  const count = (state) => items.filter((i) => i.processing_state === state).length;
  if (count("rejected")) {
    const causes = [...new Set(items.filter((i) => i.processing_state === "rejected").map((i) => friendlyReason(i.processing_reason)))];
    notes.push({kind: "refusal", label: items.some((i) => i.step_kind === "acquisition-snapshot") ? "최근 진동 파형을 읽을 수 없음" : "최근 측정 입력을 분석하지 못함", detail: causes.join(" · ") + " · 원본 입력 확인 (" + count("rejected") + "개 분석 거부)", priority: 0});
  }
  if (count("unavailable")) notes.push({kind: "unavailable", label: "분석 실행 불가", detail: count("unavailable") + "개 분석의 입력·모델 확인", priority: 0});
  const sources = (base.sources?.sources?.items || []).filter((s) => s.asset_id === assetId && s.continuous_collection_supported);
  if (base.errors.length) notes.push({kind: "read", label: "수신 근거 조회 미확인", detail: "데이터 연결 확인", priority: 1});
  else if (sources.some((s) => !s.last_live_receive_fresh)) notes.push({kind: "receipt", label: "최근 수신 미확인", detail: "30초 이내 수신 근거 없음 · 연결·재생 여부 확인", priority: 1});
  if (count("pending")) notes.push({kind: "pending", label: "새 입력 분석 대기", detail: count("pending") + "개 분석 · 이전 결과와 구분", priority: 2});
  const compared = items.filter((i) => i.processing_state === "processed" && typeof i.latest_analyzed?.output.exceeds_threshold === "boolean");
  const exceeded = compared.filter((i) => i.latest_analyzed.output.exceeds_threshold);
  if (exceeded.length) notes.push({kind: "threshold", label: items.some((i) => i.step_kind === "acquisition-snapshot") ? "진동 변화 확인 필요" : "전기 신호 변화 확인 필요", detail: "저장된 참고 기준 초과 · 신호 추세 확인 (" + exceeded.length + "개 분석)", priority: 3});
  if (items.some((i) => ["open", "acknowledged"].includes(i.latest_review_status))) notes.push({kind: "review", label: "사람 검토 대기", detail: "선택 분석의 검토 상태 확인", priority: 4});
  return {assetId, items, notes, compared, exceeded, warmup: count("warmup"), waiting: count("waiting"), priority: notes[0]?.priority ?? 5};
}
function selectAsset(assetId) {
  selectedAsset = assetId;selectedStream = "";previousInput = false;previewKey = "";detailsKey = "";
  const url = new URL(location.href);url.searchParams.set("monitor_asset", assetId);history.replaceState(history.state, "", url);
  if (lastData) render(lastData, lastBase);
}
function render(data, base) {
  lastData = data;lastBase = base;
  const grouped = new Map();
  for (const i of data.items) {if (!grouped.has(i.asset_id)) grouped.set(i.asset_id, []);grouped.get(i.asset_id).push(i);}
  for (const a of base.monitor?.assets?.items || []) if (!grouped.has(a.asset_id)) grouped.set(a.asset_id, []);
  const facts = [...grouped].map(([id, items]) => assetFacts(id, items, base)).sort((a, b) => a.priority - b.priority || a.assetId.localeCompare(b.assetId));
  if (!grouped.has(selectedAsset)) selectedAsset = facts[0]?.assetId || "";
  const replayAssets = facts.filter((f) => f.items.some(replay)).length;
  const mode = byId("monitor-data-mode");mode.className = "tag" + (replayAssets ? " replay" : "");
  mode.textContent = replayAssets === facts.length && replayAssets ? "기록 재생 데이터" : replayAssets ? "기록 재생·기타 입력 혼합" : "저장·수신 데이터";
  const received = (base.sources?.sources?.items || []).filter((s) => s.last_live_receive_fresh).length;
  const intake = base.errors.length ? "수신 상태 미확인" : (base.sources?.sources?.items || []).some((s) => s.continuous_collection_supported)
    ? "최근 " + (replayAssets ? "재생 " : "") + "수신 " + received + "개 소스 (30초)" : "저장된 기록 조회";
  byId("phm-monitor-summary").textContent = "설비 " + facts.length + "대 · 확인 필요 " + facts.filter((f) => f.notes.length).length + "대 · " + intake;
  byId("phm-monitor-state").className = "muted";
  byId("phm-monitor-state").textContent = "3초 자동 조회 · 확인 " + time(data.assessed_at) + (base.errors.length ? " · 운영 수신 조회 미확인" : "")
    + (data.truncated || base.monitor?.assets?.truncated ? " · 일부 설비·모델은 조회 범위 밖 (모델 " + data.items.length + "/" + data.total + ")" : "")
    + (data.review_read_error ? " · 검토 조회 미확인" : "");
  const attention = facts.filter((f) => f.notes.length);
  const attentionRoot = byId("monitor-attention-list");attentionRoot.replaceChildren();
  byId("monitor-attention-count").textContent = attention.length + "대 · 운영 확인 항목";
  if (!attention.length) attentionRoot.append(node("p", "현재 조회 범위에 별도 확인 항목이 없습니다. 설비 정상 판정이 아닙니다.", "muted"));
  for (const f of attention.slice(0, 4)) {
    const button = node("button", "", "monitor-attention-item");button.type = "button";button.dataset.assetId = f.assetId;
    button.append(node("strong", assetName(f.assetId)), node("span", f.notes.map((n) => n.label).join(" · ")), node("small", f.notes[0].detail + " → 신호 보기"));
    const observation = node("small", "", "monitor-attention-observation");observation.hidden = true;button.append(observation);
    button.addEventListener("click", () => {selectAsset(f.assetId);byId("monitor-signal-title").focus({preventScroll: true});});attentionRoot.append(button);
  }
  if (attention.length > 4) attentionRoot.append(node("p", "추가 " + (attention.length - 4) + "대는 아래 설비 목록에서 확인", "muted"));
  const root = byId("phm-monitor-assets");
  const focusAsset = root.contains(document.activeElement) ? document.activeElement.dataset.assetId : null;
  root.replaceChildren();
  for (const f of facts) {
    const button = node("button", "", "monitor-asset");button.type = "button";button.dataset.assetId = f.assetId;button.setAttribute("aria-pressed", f.assetId === selectedAsset);
    const heading = node("span", "", "monitor-asset-heading");heading.append(node("strong", assetName(f.assetId)), node("small", f.items.some(replay) ? "기록 재생" : "저장·수신"));
    const row = assetRow(base, f.assetId);
    const message = f.notes[0]?.label || (f.warmup ? "입력 준비 중" : f.waiting ? "확정 입력 대기" : f.compared.length
      ? (f.items.some((i) => i.step_kind === "observation-window") ? "전기 신호" : "진동 신호") + " · 기준 초과 없음" : f.items.length ? "신호 기준 비교 없음"
      : flowLabels[row?.data_flow_status] || "수신 상태 미확인");
    button.append(heading, node("span", message, f.notes.length ? "monitor-asset-status attention" : "monitor-asset-status"));
    const representative = f.items.find((i) => i.latest_delivered) || f.items[0];
    button.append(node("small", representative ? (representative.step_kind === "observation-window" ? "마지막 측정 " : "입력 ") + inputName(representative, representative.latest_delivered) : dataTime(row)));
    if (!f.items.length) button.append(node("small", data.unavailable ? "PHM 분석 조회 실패" : "PHM 분석 연결 안 됨"));
    button.append(node("small", "", "monitor-asset-observation"));
    button.addEventListener("click", () => selectAsset(f.assetId));root.append(button);
  }
  if (focusAsset) [...root.children].find((b) => b.dataset.assetId === focusAsset)?.focus({preventScroll: true});
  byId("monitor-board").hidden = !facts.length;
  if (!facts.length) {byId("monitor-analysis-details").hidden = true;root.append(node("p", "관측 설비 없음", "muted"));clearSignal();return;}
  const selected = facts.find((f) => f.assetId === selectedAsset);
  byId("monitor-analysis-details").hidden = !selected.items.length;
  const inputs = selected.items.filter((i, index, all) => all.findIndex((j) => streamKey(j) === streamKey(i)) === index);
  // Stored measurements are the model-independent stream: the only one without a model,
  // an explicit alternative to model inputs when the asset also has stored channels.
  const row = assetRow(base, selectedAsset), dataKey = storedDataKey(row, base);
  const stored = storedChannelState(selectedAsset, dataKey, () => {if (lastData && active()) render(lastData, lastBase);});
  const offerStored = !inputs.length || stored.state === "ready";
  const item = selectedStream === HISTORY && offerStored ? null
    : inputs.find((i) => streamKey(i) === selectedStream) || inputs.find((i) => i.latest_delivered) || inputs[0];
  selectedStream = item ? streamKey(item) : HISTORY;
  const streamSelect = byId("monitor-input-stream");streamSelect.replaceChildren();
  for (const input of inputs) {
    const source = (base.sources?.sources?.items || []).find((s) => s.source_id === input.source_id);
    const option = node("option", "분석 입력 · " + (source?.name || input.source_id) + (input.measurement_point_id ? " · " + input.measurement_point_id : ""));option.value = streamKey(input);streamSelect.append(option);
  }
  if (offerStored) {const option = node("option", "저장된 측정 이력 (모델 무관)");option.value = HISTORY;streamSelect.append(option);}
  streamSelect.value = selectedStream;byId("monitor-stream-field").hidden = streamSelect.options.length < 2;
  byId("monitor-signal-title").textContent = assetName(selectedAsset) + " · 측정 신호";byId("monitor-signal-title").tabIndex = -1;
  byId("monitor-analysis-context").textContent = assetName(selectedAsset) + " · 연결 분석 " + selected.items.length + "개 · 기준 비교는 고장 판정이 아닙니다.";
  if (byId("monitor-analysis-details").open) renderDetails(selected);
  else {byId("monitor-analysis-models").replaceChildren();detailsKey = "";}
  if (!item) {
    leavePhmSignal();
    if (selected.items.length) renderDetection(selected.items);
    else byId("monitor-detection-results").replaceChildren(node("p", data.unavailable
      ? "PHM 분석 결과를 읽지 못했습니다. 측정 신호는 분석 조회와 무관하게 표시합니다."
      : "연결된 PHM 분석 모델 없음 · 측정 신호는 모델 연결과 무관하게 표시합니다.", "muted"));
    showStored({assetId: selectedAsset, asset: row, dataKey, onChange: () => {if (lastData && active()) render(lastData, lastBase);},
      historyError: (base.monitor?.system_error_scopes || []).includes("asset-history")});
    return;
  }
  leaveStored();
  byId("monitor-signal-mode").textContent = replay(item) ? "기록 재생" : "저장 입력";
  renderDetection(selected.items.filter((i) => streamKey(i) === selectedStream));
  void loadSignal(item);void loadTrace(item);paintSignal();
}
function renderDetection(items) {
  const root = byId("monitor-detection-results");root.replaceChildren();
  const anomalies = items.filter((i) => i.task === "anomaly-score");
  anomalies.sort((a, b) => Number(/lstm/.test(b.recipe_id || "")) - Number(/lstm/.test(a.recipe_id || "")));
  if (!anomalies.length) root.append(node("p", "연결된 이상 탐지 모델 없음", "muted"));
  for (const item of anomalies.slice(0, 2)) {
    const row = node("article", "", "monitor-detection-result");row.dataset.bindingId = item.binding_id;
    const reconstruction = /autoencoder|pca/i.test(item.recipe_id || "");
    const label = reconstruction ? "재구성 오차 · " + (/lstm/i.test(item.recipe_id) ? "LSTM" : "PCA") : "이상 점수 · " + (/iforest/i.test(item.recipe_id || "") ? "IF" : "연결 모델");
    const heading = node("div", "", "monitor-detection-heading");heading.append(node("h5", label));row.append(heading);
    const last = item.latest_analyzed, prior = item.previous_analyzed;
    if (!last || typeof last.output.score !== "number") {
      row.append(node("p", states[item.processing_state] || "비교할 분석 결과 없음"));root.append(row);continue;
    }
    const current = item.processing_state === "processed" && !previousInput;
    const value = node("div", "", "monitor-detection-value");
    value.append(node("strong", number(last.output.score)), node("span", "참고 기준 " + number(last.output.threshold) + (last.output.exceeds_threshold ? " 초과" : " 이내")));
    row.append(value);
    if (!current) row.append(node("p", "이전 분석 결과 · 최신 입력 미평가", "monitor-detection-old"));
    if (prior && typeof prior.output.score === "number") {
      const delta = last.output.score - prior.output.score;
      const deltaText = delta === 0 ? "변화 없음" : (delta > 0 ? "+" : "−") + (Math.abs(delta) < .001 ? Math.abs(delta).toExponential(2) : number(Math.abs(delta)));
      const description = reconstruction ? "학습 패턴과 차이 " : "이상 점수 ";
      const relation = item.step_kind === "acquisition-snapshot" && prior.position + 1 === last.position ? "직전" : "앞선 분석";
      row.append(node("p", relation + " " + number(prior.output.score) + " · 변화 " + deltaText));
      row.append(node("p", description + (delta > 0 ? "증가" : delta < 0 ? "감소" : "변화 없음") + " · " + inputName(item, prior) + " → " + inputName(item, last), "muted"));
    } else row.append(node("p", "첫 분석 결과 · 이전값 비교 대기", "muted"));
    const link = node("a", "추세 보기");link.href = detailLink(item);heading.append(link);root.append(row);
  }
  if (anomalies.length > 2) root.append(node("p", "주요 모델 2개 표시 · 연결 모델 " + anomalies.length + "개는 모델·입력 상세에서 확인", "muted"));
}
function leavePhmSignal() {
  if (!preview && !previewKey && !traceKey) return;
  signalVersion++;traceVersion++;preview = null;previewKey = "";traceKey = "";traceData = null;
  byId("monitor-score-chart").replaceChildren();byId("monitor-score-state").textContent = "";
}
function assetRow(base, assetId) {return (base.monitor?.assets?.items || []).find((a) => a.asset_id === assetId);}
// New stored data is signalled by a history commit or, for a source-less recorded asset, a later
// recorded end. A live receipt alone is not stored history, so it does not trigger a history read.
function storedDataKey(row, base) {
  const sources = (base.sources?.sources?.items || []).filter((s) => s.asset_id === row?.asset_id)
    .map((s) => [s.source_id, s.last_live_history_snapshot_id ?? null]);
  return JSON.stringify([row?.data_flow_status === "stored-history" ? row.last_data_at : null, sources]);
}
function dataTime(row) {
  if (!row?.last_data_at) return "수신 근거 없음";
  return (row.data_flow_status === "stored-history" ? "마지막 기록 원본 측정 " : "마지막 수신 ") + time(row.last_data_at);
}
function clearSignal() {
  signalVersion++;traceVersion++;preview = null;previewKey = "";traceKey = "";traceData = null;byId("monitor-score-chart").replaceChildren();byId("monitor-score-state").textContent = "";
  byId("monitor-signal-chart").replaceChildren();byId("monitor-signal-legend").textContent = "";
  byId("monitor-signal-reading").hidden = true;byId("monitor-range-field").hidden = true;byId("monitor-history-range-field").hidden = true;
  byId("monitor-detection-results").replaceChildren();
  byId("monitor-signal-channel").replaceChildren();byId("monitor-signal-channel").disabled = true;
}
async function loadSignal(item) {
  const delivered = item.latest_delivered, chosen = previousInput ? item.latest_analyzed : delivered;
  const context = byId("monitor-signal-context");
  context.textContent = (previousInput ? " 이전 입력 · " : "최신 입력 · ") + (item.step_kind === "observation-window" ? "원본 측정 " : "") + inputName(item, chosen)
    + (delivered ? " · 최신 입력 수신 " + time(delivered.delivered_at) : "");
  const previous = byId("monitor-last-good");previous.hidden = !item.latest_analyzed || item.latest_analyzed.position === delivered?.position;
  previous.textContent = previousInput ? "최신 입력 보기" : "마지막 성공 입력 보기";
  if (!chosen) {clearSignal();byId("monitor-signal-state").textContent = "원본 입력 수신을 기다립니다.";return;}
  const key = JSON.stringify([item.binding_id, chosen.position, previousInput]);
  if (key === previewKey && preview?.available) return;
  const version = ++signalVersion;previewKey = key;preview = null;
  byId("monitor-signal-reading").hidden = true;byId("monitor-range-field").hidden = true;
  byId("monitor-signal-chart").replaceChildren();byId("monitor-signal-state").textContent = "원본 신호 조회 중";
  try {
    const route = item.step_kind === "observation-window" ? "window-input" : "snapshot";
    const response = await fetch("/api/v1/phm/" + route + "?binding_id=" + encodeURIComponent(item.binding_id) + "&position=" + chosen.position + "&bins=400", {signal: AbortSignal.timeout(5000)});
    const data = await response.json();
    if (version !== signalVersion || !active()) return;
    if (!response.ok || !data.available) throw new Error(data.reason || "원본 조회 실패");
    preview = data;
    const choices = monitorChoices(data), select = byId("monitor-signal-channel");select.replaceChildren();
    for (const choice of choices) {const option = node("option", choice.name);option.value = choice.id;select.append(option);}
    if (!choices.some((c) => c.id === choiceId)) choiceId = choices[0]?.id;
    select.value = choiceId;select.disabled = false;
    byId("monitor-signal-state").textContent = data.sample_count ? "최근 획득의 실제 파형 · " + data.sample_count.toLocaleString() + "개 표본 · 단위 미확인" : "확정된 입력 구간의 실제 관측 · 원본 측정 시각 KST";
    updateLegend();
    paintSignal();
  } catch (error) {
    if (version !== signalVersion || !active()) return;
    byId("monitor-signal-chart").replaceChildren();byId("monitor-signal-channel").disabled = true;
    byId("monitor-signal-state").textContent = "선택 입력의 원본을 표시할 수 없습니다: " + friendlyReason(error.message);
    byId("monitor-signal-legend").textContent = "다른 시점의 신호로 대체하지 않습니다.";
  }
}
async function loadTrace(item) {
  const key = JSON.stringify([item.binding_id, item.latest_processed?.position, item.processing_state]);
  if (traceKey === key) return;traceKey = key;
  const version = ++traceVersion;traceData = null;
  byId("monitor-score-chart").replaceChildren();
  const last = item.latest_analyzed, current = item.processing_state === "processed";
  byId("monitor-score-state").textContent = role(item) + (current ? " · 저장된 최근 결과" : " · 이전 분석 결과, 최신 입력 미평가")
    + (last ? item.task === "rul-estimate" ? " · RUL " + number(last.output.estimate) : " · 점수 " + number(last.output.score) + " / 기준 " + number(last.output.threshold) : " · 결과 대기");
  try {
    const response = await fetch("/api/v1/phm/trace?binding_id=" + encodeURIComponent(item.binding_id), {signal: AbortSignal.timeout(5000)});
    const data = await response.json();
    if (version !== traceVersion || !active()) return;
    if (!response.ok || data.binding_id !== item.binding_id) throw new Error("wrong_trace");
    traceData = {steps: data.steps, task: item.task, threshold: last?.output.threshold};
    drawTrace(byId("monitor-score-chart"), traceData.steps, traceData.task, traceData.threshold);paintSignal();
  } catch {
    if (version !== traceVersion || !active()) return;
    traceKey = "";byId("monitor-score-state").textContent = "저장 결과 추세 조회 실패 · 자동 재조회";
  }
}
function monitorChoices(data) {
  const originals = signalChoices(data);
  return data?.sample_count ? [
    ...data.channels.map((c, i) => ({id: "rms-" + i, name: (i === 0 ? "수평" : "수직") + " 진동 크기 추세 · RMS"})),
    ...originals.map((c) => ({...c, name: c.name + " · 최근 원본 파형"})),
  ] : originals;
}
function paintSignal() {
  if (!preview?.available) return;
  const reading = byId("monitor-signal-reading");reading.replaceChildren();reading.hidden = true;
  const observation = byId("phm-monitor-assets").querySelector('[aria-pressed="true"] .monitor-asset-observation');
  if (observation) observation.textContent = "";
  byId("monitor-range-field").hidden = true;
  if (choiceId.startsWith("rms-") && preview.sample_count) {
    const channelIndex = Number(choiceId.slice(4)), channel = preview.channels[channelIndex]?.channel;
    const steps = (traceData?.steps || []).filter((s) => s.position <= preview.position);
    const rows = measuredRows(steps, channel), last = rows.at(-1);
    if (rows.length < 2 || last.position !== preview.position) {
      drawSignal(byId("monitor-signal-chart"), preview, String(channelIndex));
      byId("monitor-signal-state").textContent = "크기 추세 축적 대기 · 선택 입력의 원본 파형";
      byId("monitor-signal-legend").textContent = "원본 표본 구간별 최솟값·최댓값 · 단위 미확인";return;
    }
    const before = rows.at(-2), contiguous = before.position + 1 === last.position;
    const change = measuredChange(before, last), relation = contiguous ? "직전 기록" : "앞선 조회 기록";
    const current = node("div");current.append(node("small", channelName(channel) + " · " + relation + " 대비"), node("strong", change));
    const comparison = node("div");comparison.append(node("small", "기록 #" + before.position + " → #" + last.position + " · RMS"), node("strong", number(before.value) + " → " + number(last.value)));
    reading.append(current, comparison);reading.hidden = false;
    if (observation) observation.textContent = channelName(channel) + "이 " + relation + " #" + before.position + "보다 " + change + (previousInput ? " · 이전 기록" : "");
    const alert = [...byId("monitor-attention-list").children].find((e) => e.dataset.assetId === selectedAsset)?.querySelector(".monitor-attention-observation");
    if (alert && !previousInput) {alert.textContent = observation?.textContent || "";alert.hidden = false;}
    const recent = recentMeasuredSegment(rows), all = byId("monitor-signal-range").value === "all";
    const shown = all ? rows : recent;
    byId("monitor-range-field").hidden = recent.length === rows.length;
    drawMeasuredTrend(byId("monitor-signal-chart"), shown, channel);
    byId("monitor-signal-state").textContent = "진동 크기(RMS) · 0부터 표시 · 단위 미확인";
    const absent = steps.at(-1).position - steps[0].position + 1 - steps.length;
    const rejected = steps.filter((s) => s.state === "skipped").length;
    byId("monitor-signal-legend").textContent = (all ? "조회 기록" : "최근 연속 기록") + " #" + shown[0].position + "–#" + shown.at(-1).position
      + (absent || rejected ? " · 기록 공백 " + absent + "개 · 분석 거부 " + rejected + "개" : "") + " · 크기 변화는 고장 판정이 아닙니다.";
    return;
  } else {
    drawSignal(byId("monitor-signal-chart"), preview, choiceId);
    byId("monitor-signal-state").textContent = preview.sample_count ? "최근 획득의 실제 파형 · " + preview.sample_count.toLocaleString() + "개 표본 · 단위 미확인" : "확정된 입력 구간의 실제 관측 · 원본 측정 시각 KST";
    if (!preview.sample_count) {
      const choice = signalChoices(preview).find((c) => c.id === choiceId);
      for (const [index, channel] of (choice?.channels || []).entries()) {
        const point = channel.points.at(-1), cell = node("div");
        cell.append(node("small", choice.channels.length === 3 ? ["R상", "S상", "T상"][index] : choice.name), node("strong", typeof point?.value === "number" ? number(point.value) + " " + channel.unit : "측정 미확인"));reading.append(cell);
      }
      reading.hidden = !reading.children.length;
    }
  }
  updateLegend();
}
function updateLegend() {
  if (!preview?.available) return;
  const choice = signalChoices(preview).find((c) => c.id === choiceId);
  byId("monitor-signal-legend").textContent = choiceId.startsWith("rms-") ? "원본에서 계산해 저장한 크기입니다. 미전달·미평가 구간은 연결하지 않습니다." : preview.sample_count ? "표본 구간별 최솟값·최댓값을 표시합니다."
    : choice?.channels.length === 3 ? "R상 ━ · S상 ┄ · T상 ⋯ · 원본 단위로 비교" : (choice?.name || "") + " · 원본 관측";
}
function renderDetails(facts) {
  const key = JSON.stringify(facts.items);
  if (detailsKey === key) return;detailsKey = key;
  const root = byId("monitor-analysis-models");root.replaceChildren();
  for (const item of facts.items) {
    const row = node("article", "", "monitor-model");row.dataset.bindingId = item.binding_id;
    row.append(node("h4", role(item)), node("p", states[item.processing_state] || "상태 미확인"));
    const last = item.latest_analyzed;
    if (last) {
      const o = last.output, older = item.processing_state !== "processed" ? "이전 결과 · " : "";
      row.append(node("p", older + (item.task === "rul-estimate" ? "RUL " + number(o.estimate) + " 획득 간격" : "점수 " + number(o.score) + " · 참고 기준 " + number(o.threshold) + (o.exceeds_threshold ? " 초과" : " 이하"))));
      row.append(node("p", "분석 " + inputName(item, last) + " · " + (reviewLabels[item.latest_review_status] || "검토 요청 없음"), "muted"));
      const link = node("a", item.task === "rul-estimate" ? "RUL·검토 상세" : "이 시점의 추세·원본 입력 보기");link.href = detailLink(item);row.append(link);
    }
    const technical = node("details", "", "monitor-technical");technical.append(node("summary", "모델·처리 근거"), node("p", "패키지 " + item.package_id), node("p", item.processing_reason || "입력 처리 근거 있음"), node("p", "성능 검증 " + (item.validation?.acceptance || "별도 검증 기록 확인")));
    row.append(technical);root.append(row);
  }
}
function schedule() {clearTimeout(timer);if (active()) timer = setTimeout(refreshMonitor, POLL_MS);}
async function readPhm() {
  const response = await fetch("/api/v1/phm/monitor", {cache: "no-store", signal: AbortSignal.timeout(5000)});
  const data = await response.json();
  if (!response.ok || data.schema_version !== 1 || !Array.isArray(data.items)) throw new Error("read_failed");
  return data;
}
export async function refreshMonitor({force = false} = {}) {
  if (!active()) return;
  if (force) invalidateStored();
  if (running) {refreshRequested = true;return;}
  running = true;clearTimeout(timer);
  try {
    const [phm, base] = await Promise.all([readPhm().catch(() => null), readOperations()]);
    // A PHM read failure must not hide equipment observation: render the stored-measurement
    // monitor without any model value, and say that the analysis read failed.
    if (!phm && !base.monitor) throw new Error("read_failed");
    const data = phm || {schema_version: 1, assessed_at: base.monitor.assessed_at, items: [], total: 0, unavailable: true};
    if (active()) render(data, base);
    if (phm) document.dispatchEvent(new CustomEvent("phm-monitor-count", {detail: phm.total}));
    if (!phm && active()) {
      byId("phm-monitor-state").className = "state error";
      byId("phm-monitor-state").textContent = "PHM 조회 실패 · 분석 결과를 표시하지 않습니다. 저장된 측정 신호는 계속 확인할 수 있으며 자동 재조회합니다.";
    }
  } catch {
    if (active()) {
      byId("phm-monitor-state").className = "state error";
      byId("phm-monitor-state").textContent = "관측 상태 조회 실패 · 이전 결과를 표시하지 않습니다. 자동 재조회합니다.";
      byId("phm-monitor-summary").textContent = "관측 상태 미확인";byId("phm-monitor-assets").replaceChildren();byId("monitor-attention-list").replaceChildren();
      byId("monitor-analysis-models").replaceChildren();byId("monitor-board").hidden = true;byId("monitor-analysis-details").hidden = true;clearSignal();
    }
  } finally {running = false;if (refreshRequested) {refreshRequested = false;void refreshMonitor();} else schedule();}
}
export function initializeMonitor(read) {
  readOperations = read;
  const start = () => {clearTimeout(timer);if (active()) void refreshMonitor();};
  window.addEventListener("hashchange", start);document.addEventListener("visibilitychange", start);
  byId("monitor-input-stream").addEventListener("change", (e) => {selectedStream = e.target.value;previousInput = false;previewKey = "";if (lastData) render(lastData, lastBase);});
  byId("monitor-signal-channel").addEventListener("change", (e) => {
    if (selectedStream === HISTORY) {selectStoredChannel(e.target.value);if (lastData) render(lastData, lastBase);return;}
    choiceId = e.target.value;paintSignal();
  });
  byId("monitor-history-range").addEventListener("change", (e) => {selectStoredRange(e.target.value);if (lastData) render(lastData, lastBase);});
  byId("monitor-signal-range").addEventListener("change", paintSignal);
  byId("monitor-last-good").addEventListener("click", () => {previousInput = !previousInput;previewKey = "";if (lastData) render(lastData, lastBase);});
  byId("monitor-analysis-details").addEventListener("toggle", () => {
    if (lastData && byId("monitor-analysis-details").open) {
      render(lastData, lastBase);
      if (traceData) drawTrace(byId("monitor-score-chart"), traceData.steps, traceData.task, traceData.threshold);
    }
  });
  new ResizeObserver(() => {if (active()) {if (selectedStream === HISTORY) repaintStored();else if (preview?.available) paintSignal();if (traceData) drawTrace(byId("monitor-score-chart"), traceData.steps, traceData.task, traceData.threshold);}}).observe(byId("monitor-signal-chart"));
  // Show the first observation immediately instead of after one polling interval.
  start();
}
