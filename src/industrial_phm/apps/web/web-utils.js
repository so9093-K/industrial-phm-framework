// Shared text-only DOM and authenticated read helpers. No workspace state.
export const byId = (id) => document.getElementById(id);
export const create = (tag, className, content) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined && content !== null) element.textContent = String(content);
  return element;
};
export const clear = (node) => node.replaceChildren();
export const fmt = (value) => (value === null || value === undefined || value === "" ? "확인된 값 없음" : String(value));
export const num = (value) => (typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("ko-KR", {maximumFractionDigits: 3}) : "—");
export const withText = (name, value) => {
  const item = create("div", "fact");
  item.append(create("span", null, name), create("strong", null, fmt(value)));
  return item;
};

export function rows(payload, key) {
  const collection = payload && payload[key];
  return collection && Array.isArray(collection.items) ? collection.items : [];
}
export function empty(target, message) {
  clear(target);
  target.append(create("p", "empty", message));
}
export async function getJSON(url, {signal} = {}) {
  const response = await fetch(url, {cache:"no-store",credentials:"same-origin", signal});
  if (!response.ok) throw new Error("http-" + response.status);
  const value = await response.json();
  if (value.schema_version !== 1) throw new Error("schema-mismatch");
  return value;
}
export function presentError(error) {
  if (error.message === "workspace-writer-busy") return "다른 Operations 또는 Web 작업이 현재 작업공간을 사용 중입니다. 변경 작업이 끝난 뒤 다시 시도하세요. 조회는 계속 가능합니다.";
  if (error.message === "http-503") return "이력 저장소를 확인할 수 없습니다. 시스템과 데이터 연결 상태를 확인하세요.";
  if (error.message === "schema-mismatch") return "지원되지 않는 API 응답입니다. 서버 버전을 확인하세요.";
  return "조회에 실패했습니다. 네트워크와 로컬 서버 상태를 확인하고 다시 시도하세요.";
}
export async function checkWorkspaceWriterConflict(response) {
  if (response.status !== 409) return;
  const payload = await response.json().catch(() => null);
  if (payload && payload.error && payload.error.code === "workspace_writer_busy") {
    throw new Error("workspace-writer-busy");
  }
}
export function record(target, heading, details) {
  const section = create("article", "record");
  section.append(create("h3", null, heading));
  details.forEach(([label, value]) => {
    const line = create("p");
    line.append(create("strong", null, label + "  "), document.createTextNode(fmt(value)));
    section.append(line);
  });
  target.append(section);
  return section;
}
