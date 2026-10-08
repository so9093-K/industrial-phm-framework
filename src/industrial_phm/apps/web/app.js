// Read-only Operations frontend. All server strings enter the DOM as text, never HTML.
// The user explicitly refreshes data; there is no polling, mutation or fallback sample.
const byId = (id) => document.getElementById(id);
const create = (tag, className, content) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined && content !== null) element.textContent = String(content);
  return element;
};
const clear = (node) => node.replaceChildren();
const fmt = (value) => (value === null || value === undefined || value === "" ? "확인된 값 없음" : String(value));
const num = (value) => (typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("ko-KR", {maximumFractionDigits: 3}) : "—");
const utc = (value) => value ? String(value) : "시각 없음";
const list = (root, rows) => rows.forEach((row) => root.append(row));
const withText = (name, value) => {
  const item = create("div", "fact");
  item.append(create("span", null, name), create("strong", null, fmt(value)));
  return item;
};
let monitor = null;
let selectedAsset = "";
let selectedChannels = [];
let generation = 0;
function setNotice(message, error = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.className = message ? "notice" + (error ? " error" : "") : "notice hidden";
}
function trendState(message, error = false) {
  const node = byId("trend-state");
  node.textContent = message;
  node.className = message ? "state" + (error ? " error" : "") : "state hidden";
}
function setActiveSection() {
  const selected = location.hash || "#monitor";
  document.querySelectorAll(".sidebar nav a").forEach((item) => {
    if (item.getAttribute("href") === selected) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
}
function rows(payload, key) {
  const collection = payload && payload[key];
  return collection && Array.isArray(collection.items) ? collection.items : [];
}
function empty(target, message) {
  clear(target);
  target.append(create("p", "empty", message));
}
async function getJSON(url) {
  const response = await fetch(url, {cache:"no-store",credentials:"same-origin"});
  if (!response.ok) throw new Error("http-" + response.status);
  const value = await response.json();
  if (value.schema_version !== 1) throw new Error("schema-mismatch");
  return value;
}
function presentError(error) {
  if (error.message === "http-503") return "이력 저장소를 확인할 수 없습니다. 시스템과 데이터 연결 상태를 확인하세요.";
  if (error.message === "schema-mismatch") return "지원되지 않는 API 응답입니다. 서버 버전을 확인하세요.";
  return "조회에 실패했습니다. 네트워크와 로컬 서버 상태를 확인하고 다시 시도하세요.";
}
function assetDetails() {
  const item = rows(monitor, "assets").find((row) => row.asset_id === selectedAsset);
  const box = byId("asset-facts"); clear(box);
  if (!item) {empty(box, "선택한 설비의 관측 요약이 없습니다."); return;}
  list(box, [
    withText("데이터 흐름 (설비 건강 아님)", item.data_flow_status),
    withText("마지막 관측 시각 · UTC", utc(item.last_data_at)),
    withText("마지막 분석 완료 · UTC", utc(item.latest_analysis_at)),
    withText("연결된 source 수", item.source_count),
    withText("확인할 항목", item.attention_count),
    withText("미처리 검토", item.pending_review_count),
  ]);
}
function record(target, heading, details) {
  const section = create("article", "record");
  section.append(create("h3", null, heading));
  details.forEach(([label, value]) => {
    const line = create("p");
    line.append(create("strong", null, label + "  "), document.createTextNode(fmt(value)));
    section.append(line);
  });
  target.append(section);
}
function evidenceViews() {
  const analyses = rows(monitor, "phase_unbalance_analyses").filter((r) => r.asset_id === selectedAsset);
  const attempts = rows(monitor, "skipped_analysis_attempts").filter((r) => r.asset_id === selectedAsset);
  const reviews = rows(monitor, "review_requests").filter((r) => r.asset_id === selectedAsset);
  const evidence = byId("evidence-results");
  const review = byId("review-results");
  clear(evidence); clear(review);
  if (!analyses.length && !attempts.length) empty(evidence, "이 설비의 저장된 3상 분석 기록이 없습니다. 분석 결과 없음은 정상 상태를 의미하지 않습니다.");
  analyses.forEach((run) => {
    const metrics = Array.isArray(run.quantities) ? run.quantities : [];
    const article = create("article", "record");
    article.append(create("h3", null, "분석 근거 · " + fmt(run.analysis_run_id)));
    const lines = [
      ["Capability", run.capability_id],
      ["계산 버전", run.algorithm_version],
      ["관측 구간 · UTC", utc(run.observed_start_at) + " → " + utc(run.observed_end_at)],
      ["Evidence ID", run.evidence_id],
    ];
    lines.forEach(([label, value]) => {
      const p = create("p"); p.append(create("strong", null, label + "  "), document.createTextNode(fmt(value))); article.append(p);
    });
    metrics.forEach((m) => {
      const counts = Object.entries(m.excluded_samples || {}).map(([reason, count]) => reason + ": " + count).join(" · ");
      const p = create("p", "stat", fmt(m.quantity) + " 불평형률 · 중앙값 " + num(m.median_percent) + "% · p95 " + num(m.p95_percent) + "%");
      article.append(p);
      article.append(create("p", null, "평가 표본 " + fmt(m.evaluated_samples) + " · 제외 " + (counts || "없음")));
    });
    evidence.append(article);
  });
  attempts.forEach((run) => record(evidence, "미수행 분석 · " + fmt(run.capability_id), [
    ["상태 / 이유", fmt(run.state) + " / " + fmt(run.reason)],
    ["관측 기간 · UTC", utc(run.observed_start_at) + " → " + utc(run.observed_end_at)],
  ]));
  if (!reviews.length) empty(review, "이 설비에 기록된 검토 요청이 없습니다. 검토 없음은 정비 완료를 뜻하지 않습니다.");
  reviews.forEach((reviewItem) => record(review, "검토 요청 · " + fmt(reviewItem.finding_id), [
    ["검토 상태", reviewItem.status],
    ["분석 Run", reviewItem.analysis_run_id],
    ["근거 ID", (reviewItem.evidence_ids || []).join(", ")],
  ]));
  if (monitor.system_error_scopes && monitor.system_error_scopes.length) {
    setNotice("일부 저장소를 읽지 못했습니다 (" + monitor.system_error_scopes.join(", ") + "). 표시되지 않은 근거가 있을 수 있습니다.", true);
  }
}
function checkedChannels() {
  return [...byId("channel-options").querySelectorAll('input[type="checkbox"]:checked')].map((n) => n.value);
}
function changeChannelSelection() {
  const ids = checkedChannels();
  byId("channel-options").querySelectorAll('input[type="checkbox"]:not(:checked)').forEach((node) => {
    node.disabled = ids.length >= 6;
  });
  selectedChannels = ids;
  byId("show-trend").disabled = !selectedAsset || !selectedChannels.length;
}
async function loadChannels(id, token) {
  const box = byId("channel-options");
  clear(box);
  const legend = create("legend", null, "비교할 신호 (최대 6개)");
  box.append(legend, create("p", "muted", "저장된 신호를 조회 중입니다."));
  try {
    const url = "/api/v1/history/channels?asset_id=" + encodeURIComponent(id);
    const response = await getJSON(url);
    if (token !== generation) return;
    clear(box); box.append(legend);
    const ids = rows(response, "channels");
    if (!ids.length) {box.append(create("p", "empty", "저장된 신호가 없습니다. 연결과 수신 기록을 확인하세요.")); return;}
    const choices = create("div", "choices");
    ids.forEach((channel, index) => {
      const label = create("label", "choice");
      const input = create("input"); input.type = "checkbox"; input.value = channel;
      input.checked = index === 0; input.addEventListener("change", changeChannelSelection);
      label.append(input, document.createTextNode(channel));
      choices.append(label);
    });
    box.append(choices);
    if (response.channels.truncated) box.append(create("p", "muted", "신호가 100개를 초과합니다. 목록에 표시되지 않는 항목이 있습니다."));
    changeChannelSelection();
    if (selectedChannels.length) await loadTrend(token);
  } catch (error) {
    if (token !== generation) return;
    clear(box);box.append(legend);
    box.append(create("p", "empty", presentError(error)));
    trendState("신호 목록을 확인할 수 없습니다.", true);
  }
}
const svgNode = (name) => document.createElementNS("http://www.w3.org/2000/svg", name);
function drawSeries(entries, group) {
  const root = create("div", "trend-group");
  root.append(create("div", "trend-title", group.channel_id + " · " + group.source_id));
  root.append(create("div", "trend-meta", "측정 지점: " + fmt(group.measurement_point_id) + " · 단위: " + fmt(group.semantics && group.semantics.unit) + " · " + fmt(group.semantics && group.semantics.observed_property)));
  const svg = svgNode("svg");
  svg.setAttribute("class", "trend-svg"); svg.setAttribute("viewBox", "0 0 640 130");
  svg.setAttribute("role", "img");svg.setAttribute("aria-label", "연속선을 그리지 않은 관측 버킷 평균 점 그래프. 비어 있는 시간대는 공백입니다.");
  const axis = svgNode("path");axis.setAttribute("d","M28 12 V110 H628");axis.setAttribute("class","axis");svg.append(axis);
  const vals = entries.map((e) => e.mean).filter((n) => typeof n === "number" && Number.isFinite(n));
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 0;
  const pad = hi === lo ? 1 : (hi - lo) * .16;
  const min = lo - pad, max = hi + pad;
  const start = Date.parse(group.start_at), end = Date.parse(group.end_at);
  entries.forEach((bucket) => {
    const t = Date.parse(bucket.bucket_start);
    const v = bucket.mean;
    if (!Number.isFinite(t) || !Number.isFinite(start) || end <= start) return;
    const x = 28 + (t - start) / (end - start) * 600;
    if (typeof v === "number" && Number.isFinite(v) && bucket.usable_count > 0) {
      const y = 106 - (v - min) / (max - min) * 87;
      const circle = svgNode("circle");
      circle.setAttribute("cx", String(x));circle.setAttribute("cy", String(y));circle.setAttribute("r", "4");circle.setAttribute("class", "trend-dot");
      const label = svgNode("title");label.textContent = bucket.bucket_start + " · mean " + num(v) + " · valid " + bucket.usable_count;
      circle.append(label);svg.append(circle);
    } else {
      const circle = svgNode("circle");
      circle.setAttribute("cx",String(x));circle.setAttribute("cy","105");circle.setAttribute("r","3.5");circle.setAttribute("class","trend-dot missing");
      svg.append(circle);
    }
  });
  root.append(svg);
  root.append(create("p", "legend", "버킷 " + entries.length + "개 · 원본 결측/품질/충돌 건수 확인 · 평균은 실시간 값이 아닙니다"));
  const quality = entries.reduce((acc, item) => {
    ["usable_count","null_count","non_good_count","conflict_count"].forEach((key) => acc[key] = (acc[key] || 0) + (Number(item[key]) || 0));
    return acc;
  },{});
  root.append(create("p", "trend-meta", "사용 가능 " + quality.usable_count + " · 결측 " + quality.null_count + " · 비정상 원본 품질 " + quality.non_good_count + " · 충돌 " + quality.conflict_count));
  return root;
}
function showTrend(data) {
  const box = byId("trend-results");const latest = byId("last-values");
  clear(box);clear(latest);
  const buckets = Array.isArray(data.buckets) ? data.buckets : [];
  if (!buckets.length) empty(box,"선택한 기간에 저장된 측정값이 없습니다. 최근 저장값은 별도 확인하세요.");
  const grouped = new Map();
  buckets.forEach((item) => {
    const key = [item.channel_id,item.source_id,item.measurement_point_id,item.interpretation_id].map(String).join("\u0000");
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(item);
  });
  grouped.forEach((items) => box.append(drawSeries(items, {...items[0], start_at:data.start_at, end_at:data.end_at})));
  const points = Array.isArray(data.latest_stored) ? data.latest_stored : [];
  if (points.length) latest.append(create("h3", null, "마지막 저장된 측정값 · 현재 상태가 아님"));
  points.forEach((p) => {
    const item = create("div","latest-item");
    item.append(create("small",null,p.channel_id + " / " + p.source_id));
    item.append(create("strong",null, p.usable_for_display ? num(p.value) : "표시 신뢰 불가"));
    item.append(create("small",null,utc(p.event_at)));
    item.append(create("small",null,"원본 품질 " + fmt(p.source_quality) + " · " + (p.conflicting_duplicate ? "충돌 있음" : "충돌 없음")));
    item.append(create("small",null,"evidence: " + fmt(p.raw_evidence_id)));
    latest.append(item);
  });
  trendState("이력 snapshot " + fmt(data.snapshot_id) + " · " + utc(data.start_at) + " ~ " + utc(data.end_at) + " · " + grouped.size + "개 신호/출처 조합");
}
async function loadTrend(token = generation) {
  if (!selectedAsset || !selectedChannels.length) return;
  trendState("실제 측정 이력을 읽는 중입니다.");
  clear(byId("trend-results"));clear(byId("last-values"));
  const params = new URLSearchParams({asset_id:selectedAsset,range:byId("range-select").value,buckets:"60"});
  selectedChannels.forEach((channel) => params.append("channel_id",channel));
  try {
    const data = await getJSON("/api/v1/history/trend?" + params.toString());
    if (token !== generation) return;
    showTrend(data);
  } catch (error) {
    if (token !== generation) return;
    trendState(presentError(error),true);
  }
}
async function selectAsset() {
  generation += 1;
  selectedAsset = byId("asset-select").value;
  selectedChannels = [];
  assetDetails();
  evidenceViews();
  clear(byId("trend-results"));clear(byId("last-values"));
  byId("show-trend").disabled = true;
  trendState("설비의 저장된 신호 목록을 확인합니다.");
  if (selectedAsset) await loadChannels(selectedAsset, generation);
}
async function refresh() {
  const token = ++generation;
  byId("refresh").disabled = true;
  setNotice("저장된 관측 현황을 불러오는 중입니다.");
  try {
    const data = await getJSON("/api/v1/monitor");
    if (token !== generation) return;
    monitor = data;
    byId("asset-count").textContent = fmt(data.assets && data.assets.total);
    byId("analysis-count").textContent = fmt(data.phase_unbalance_analyses && data.phase_unbalance_analyses.total);
    byId("review-count").textContent = fmt(data.review_requests && data.review_requests.total);
    byId("assessed-at").textContent = utc(data.assessed_at);
    const assets = rows(data,"assets");
    const select = byId("asset-select");
    const previous = selectedAsset;
    clear(select);
    if (!assets.length) {
      const option = create("option", null, "저장된 설비 없음");option.value = "";
      select.append(option);select.disabled = true; selectedAsset = "";
      empty(byId("asset-facts"),"현재 조회된 설비가 없습니다. 먼저 데이터 연결과 수신을 확인하세요.");
      empty(byId("evidence-results"),"설비를 선택한 뒤 기록된 분석 근거를 확인할 수 있습니다.");
      empty(byId("review-results"),"설비를 선택한 뒤 검토 기록을 확인할 수 있습니다.");
      clear(byId("channel-options"));byId("channel-options").append(create("legend",null,"비교할 신호 (최대 6개)"));
      trendState("관측 설비가 없습니다.");
      byId("show-trend").disabled = true;
    } else {
      assets.forEach((asset) => {
        const option = create("option",null,asset.asset_id);option.value=asset.asset_id;select.append(option);
      });
      select.disabled = false;
      selectedAsset = assets.some((a) => a.asset_id === previous) ? previous : assets[0].asset_id;
      select.value = selectedAsset;
      assetDetails();evidenceViews();
      await loadChannels(selectedAsset, token);
    }
    if (data.system_error_scopes && data.system_error_scopes.length) {
      setNotice("일부 저장소를 읽지 못했습니다 (" + data.system_error_scopes.join(", ") + "). 표시되지 않은 근거가 있을 수 있습니다.", true);
    } else if (data.assets && data.assets.truncated) {
      setNotice("설비 목록이 100건으로 제한되었습니다. 추가 설비 조회는 후속 페이지 API가 필요합니다.");
    } else {
      setNotice("");
    }
  } catch (error) {
    if (token !== generation) return;
    monitor = null;setNotice(presentError(error),true);
    for (const id of ["asset-facts","evidence-results","review-results"]) empty(byId(id),"조회 실패 · 이전 데이터를 현재 상태로 표시하지 않습니다.");
    for (const id of ["asset-count","analysis-count","review-count","assessed-at"]) byId(id).textContent = "—";
    clear(byId("asset-select"));byId("asset-select").disabled = true;selectedAsset = "";selectedChannels = [];
    clear(byId("trend-results"));clear(byId("last-values"));trendState(presentError(error),true);
    byId("show-trend").disabled = true;
  } finally {
    byId("refresh").disabled = false;
  }
}
byId("refresh").addEventListener("click",refresh);
byId("asset-select").addEventListener("change",selectAsset);
byId("show-trend").addEventListener("click",() => loadTrend());
window.addEventListener("hashchange",setActiveSection);
setActiveSection();
refresh();
