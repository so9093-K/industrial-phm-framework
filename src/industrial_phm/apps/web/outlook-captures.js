// An operator explicitly captures one current server-validated outlook.
// This is immutable evidence for a later human review, NOT a finding or maintenance action.
import { currentAsset, onAssetChange } from "./asset-context.js";
import { byId, canChange, clear, create, num, OPERATIONS_REQUIRED } from "./web-utils.js";
import { formatTime } from "./time.js";

let current = null, ticket = 0, allowed = false;
const STATES = {
  already: "마지막 측정에서 이미 도달",
  expected: "중심 예측에서 도달 예상",
  possible: "예측 범위에서만 도달 가능",
  beyond: "계산 기간 내 미도달",
};

const place = (data, point) => data.axis === "acquisition" ? "#" + point
  : formatTime(point, {seconds: false});
const limit = (data, name) => {
  const scenario = data.scenarios.find((item) => item.id === "current");
  if (!scenario || data.conditions[name] === null) return "기준 미입력";
  const reached = scenario.limits[name], unit = data.offset_unit === "acquisition" ? "개 획득" : "초";
  const offset = reached.expected ?? reached.earliest;
  return STATES[reached.state] + (offset === null ? "" : " · " + num(offset) + unit + " 뒤");
};
const json = async (url, options = {}) => {
  const response = await fetch(url, {cache: "no-store", credentials: "same-origin", ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(body.error?.code || body.error || "unavailable"),
    {status: response.status});
  return body;
};

function capturePayload(data) {
  const payload = {
    asset_id: data.asset_id, kind: data.kind, series: data.series,
    direction: data.conditions.direction, measurement_version: data.measurement_version,
    data_version: data.data_version,
    changepoint_prior_scale: String(data.settings.changepoint_prior_scale),
    changepoint_range: String(data.settings.changepoint_range),
    seasonality: data.settings.seasonality,
  };
  if (data.conditions.management !== null) payload.management_limit = String(data.conditions.management);
  if (data.conditions.end !== null) payload.end_limit = String(data.conditions.end);
  if (data.settings.training_points !== null) payload.training_points = String(data.settings.training_points);
  if (data.time_basis === "assumed") payload.assumed_period_seconds = String(data.period_seconds);
  return payload;
}

function entry(capture, now) {
  const old = capture.snapshot.outlook, wrapper = create("article", "outlook-saved-entry");
  const head = create("strong", null, "확정 저장한 전망 · " + place(old, old.record.last));
  wrapper.append(head, create("p", "muted", "저장 " + formatTime(capture.captured_at)
    + " · " + old.source_id + " · " + old.series));
  const review = create("details", "outlook-saved-evidence");
  review.append(create("summary", null, "당시의 계산 사실 확인"));
  review.append(create("p", null, "관측 내용 버전 " + old.measurement_version),
    create("p", null, "관리 기준 " + limit(old, "management")),
    create("p", null, "종료 기준 " + limit(old, "end")),
    create("p", "muted", "검토용 계산을 보존한 것이며 고장 판정이나 정비 완료 기록은 아닙니다."));
  wrapper.append(review);
  const human = capture.review || {status: "open", events: []};
  const reviewBox = create("section", "outlook-saved-review");
  const statusNames = {open: "확인 필요", acknowledged: "확인함", closed: "완료"};
  reviewBox.append(create("p", null, "담당자 검토 · " + (statusNames[human.status] || human.status)));
  if (human.events.length) {
    const notes = create("ol", "outlook-saved-notes");
    for (const event of human.events) {
      const label = {note: "메모", acknowledge: "확인", close: "검토 종료"}[event.action]
        || event.action;
      notes.append(create("li", null, label + " · " + formatTime(event.recorded_at)
        + (event.note ? " · " + event.note : "")));
    }
    reviewBox.append(notes);
  }
  if (allowed && human.status !== "closed") {
    const field = create("textarea");field.maxLength = 1000;
    field.setAttribute("aria-label", "이 전망의 검토 메모");
    const controls = create("div", "outlook-review-actions");
    const notice = create("p", "muted");notice.setAttribute("role", "status");
    const note = create("button", "secondary", "메모 남기기");
    const action = create("button", "secondary",
      human.status === "open" ? "확인함으로 표시" : "검토 완료로 표시");
    for (const button of [note, action]) button.type = "button";
    const post = async (nextAction, noteText) => {
      for (const button of [note, action]) button.disabled = true;
      notice.textContent = "검토 기록을 저장합니다.";
      try {
        const session = await json("/api/v1/session");
        if (!canChange(session)) throw new Error("read_only");
        await json("/api/v1/outlook/captures/review/action", {
          method: "POST",
          headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
          body: JSON.stringify({
            asset_id: capture.snapshot.outlook.asset_id,
            capture_id: capture.capture_id,
            event_id: crypto.randomUUID(),
            action: nextAction,
            note: noteText,
          }),
        });
        if (current === now) void show(now);
      } catch (error) {
        if (current !== now) return;
        notice.textContent = error.status === 409 ? "검토 상태가 이미 바뀌었습니다. 새로고침하세요."
          : "검토 결과를 확인하지 못했습니다. 중복 전송하지 말고 저장 기록을 새로 확인하세요.";
        for (const button of [note, action]) button.disabled = false;
      }
    };
    note.addEventListener("click", () => {
      const text = field.value.trim();
      if (!text) {notice.textContent = "메모를 입력하세요.";return;}
      void post("note", text);
    });
    action.addEventListener("click", () => {
      if (human.status === "acknowledged"
          && !window.confirm("이 전망의 검토를 완료로 표시할까요?")) return;
      void post(human.status === "open" ? "acknowledge" : "close", "");
    });
    controls.append(note, action);reviewBox.append(field, controls, notice);
  }
  wrapper.append(reviewBox);
  const compare = create("div", "outlook-reobservation");
  const sameIdentity = old.asset_id === now.asset_id && old.source_id === now.source_id
    && old.measurement_point_id === now.measurement_point_id
    && old.kind === now.kind && old.series === now.series
    && old.axis === now.axis && old.time_basis === now.time_basis;
  const sameConditions = JSON.stringify(old.conditions) === JSON.stringify(now.conditions)
    && JSON.stringify(old.settings) === JSON.stringify(now.settings);
  if (!sameIdentity) {
    compare.textContent = "현재 선택 신호와 다른 출처·축의 기록입니다. 직접 비교하지 않습니다.";
  } else if (!sameConditions) {
    compare.textContent = "계산 조건이 달라 단순 비교하지 않습니다. 당시 설정을 확인하세요.";
  } else if (old.measurement_version === now.measurement_version) {
    compare.textContent = "같은 측정 내용에 대한 전망입니다. 새로운 관측 변화 비교가 아닙니다.";
  } else {
    const type = old.record.last === now.record.last ? "같은 마지막 위치에서 관측 내용 수정"
      : "관측 위치가 변경됨";
    compare.append(create("p", null, "새로운 측정 내용 · " + type + " ("
      + place(old, old.record.last) + " → " + place(now, now.record.last) + ")"));
    for (const [name, title] of [["management", "관리 기준"], ["end", "종료 기준"]]) {
      if (now.conditions[name] === null) continue;
      compare.append(create("p", null, title + ": 이전 " + limit(old, name)
        + " → 현재 " + limit(now, name)));
    }
    compare.append(create("p", "muted",
      "같은 설정의 서로 다른 관측을 비교한 것이며, 원인·고장 가능성·정비 시점을 확정하지 않습니다."));
  }
  wrapper.append(compare);
  return wrapper;
}

async function show(data) {
  const mine = ++ticket, root = byId("outlook-saved");
  current = data;
  if (!root || !data || data.asset_id !== currentAsset()) return;
  root.hidden = false;
  root.replaceChildren(create("h3", null, "검토 대상으로 저장한 전망"),
    create("p", "muted", "필요할 때만 명시적으로 보존합니다. 일반 조회·AI 답은 자동 저장하지 않습니다."));
  const status = create("p", "muted");status.setAttribute("role", "status");
  const button = create("button", "secondary", "현재 전망을 검토 대상으로 저장");
  button.type = "button";button.disabled = !allowed;
  const row = create("div", "outlook-capture-action");
  row.append(button, status);root.append(row);
  if (!allowed) status.textContent = OPERATIONS_REQUIRED;
  button.addEventListener("click", async () => {
    button.disabled = true;status.textContent = "현재 전망의 버전과 설정을 서버에서 다시 확인합니다.";
    try {
      const session = await json("/api/v1/session");
      if (!canChange(session)) throw new Error("read_only");
      await json("/api/v1/outlook/captures/confirm", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
        body: JSON.stringify(capturePayload(data)),
      });
      if (current !== data) return;
      status.textContent = "서버에서 검증한 계산 근거를 저장했습니다.";
      void show(data);
    } catch (error) {
      if (current !== data) return;
      status.textContent = error.status === 400
        ? "관측 또는 설정이 달라졌습니다. 새로고침한 뒤 다시 확인하세요."
        : "검토 근거를 저장하지 못했습니다. 저장 여부를 확인하고 다시 시도하세요.";
      button.disabled = !allowed;
    }
  });
  const list = create("div", "outlook-saved-list");root.append(list);
  try {
    const all = await json("/api/v1/outlook/captures?asset_id=" + encodeURIComponent(data.asset_id));
    if (mine !== ticket || current !== data) return;
    if (!all.captures.length) list.append(create("p", "muted", "아직 저장한 전망이 없습니다."));
    else for (const stored of all.captures) list.append(entry(stored, data));
  } catch {
    if (mine === ticket && current === data) list.append(
      create("p", "state error", "저장된 전망 기록을 읽지 못했습니다. 새로고침해 주세요."));
  }
}

export function initializeOutlookCaptures() {
  void json("/api/v1/session").then((session) => {
    allowed = canChange(session);
    if (current) void show(current);
  }).catch(() => {allowed = false;});
  document.addEventListener("outlook-shown", (event) => {void show(event.detail);});
  const discard = () => {
    ticket++;current = null;
    const root = byId("outlook-saved");
    if (root) {clear(root);root.hidden = true;}
  };
  document.addEventListener("outlook-cleared", discard);
  onAssetChange(discard);
}
