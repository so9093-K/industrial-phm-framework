/** Real public datasets found in the datasets folder (GET /api/v1/datasets) and their import:
 * an AI-Hub 239 member becomes one asset's stored history, an XJTU-SY bearing is replayed with
 * the two anomaly models. The server finds the files; the browser only names a dataset ID. */
import {object, postWrite} from "./writes.ts";

export type PublicDataset = {
  datasetId: string; kind: "aihub-239" | "xjtu-sy"; assetId: string; stored: boolean; partial: boolean;
  sourceChanged: boolean;
  /** AI-Hub: equipment group, 학습용/검증용, device and member size. */
  equipment: string | null; split: string | null; deviceId: string | null; bytes: number | null;
  /** XJTU-SY: operating condition and how many acquisitions the run holds. */
  speedHz: number | null; loadKn: number | null; acquisitions: number | null;
};
export type DatasetJob = {
  state: "running" | "succeeded" | "failed" | "interrupted"; step: string; done: number;
  assetId: string; failure: string | null;
};
export type PublicDatasets = {
  available: boolean; canImport: boolean; items: PublicDataset[]; jobs: Record<string, DatasetJob>;
};
export type DatasetGroup = {key: string; title: string; kind: PublicDataset["kind"]; items: PublicDataset[]};

function invalid(): never { throw new Error("공개 데이터 목록의 형식이 올바르지 않습니다."); }
const text = (raw: unknown) => typeof raw === "string" && raw ? raw : null;
const count = (raw: unknown) => typeof raw === "number" && Number.isFinite(raw) && raw >= 0 ? raw : null;

export function parsePublicDatasets(raw: unknown): PublicDatasets {
  const root = object(raw);
  if (!root || root.schema_version !== 1 || !Array.isArray(root.items)
    || root.meaning !== "public-datasets-found-in-the-datasets-folder-not-imported-evidence") invalid();
  const items = root.items.map((entry: unknown): PublicDataset => {
    const row = object(entry);
    if (!row || (row.kind !== "aihub-239" && row.kind !== "xjtu-sy")) invalid();
    return {datasetId: text(row.dataset_id) ?? invalid(), kind: row.kind, assetId: text(row.asset_id) ?? invalid(),
      stored: row.stored === true, partial: row.partial === true, sourceChanged: row.source_changed === true,
      equipment: text(row.equipment), split: text(row.split), deviceId: text(row.device_id),
      bytes: count(row.bytes), speedHz: count(row.rotational_speed_hz), loadKn: count(row.radial_load_kn),
      acquisitions: count(row.acquisitions)};
  });
  const states: readonly DatasetJob["state"][] = ["running", "succeeded", "failed", "interrupted"];
  const jobs: Record<string, DatasetJob> = {};
  for (const [key, entry] of Object.entries(object(root.jobs) ?? {})) {
    const row = object(entry);
    if (!row || !states.includes(row.state as DatasetJob["state"])) continue;
    jobs[key] = {state: row.state as DatasetJob["state"], step: text(row.step) ?? "", done: count(row.done) ?? 0,
      assetId: text(row.asset_id) ?? "", failure: text(row.failure)};
  }
  return {available: root.available === true, canImport: root.can_import === true, items, jobs};
}

export async function readPublicDatasets(signal: AbortSignal): Promise<PublicDatasets> {
  const response = await fetch("/api/v1/datasets", {signal, cache: "no-store", credentials: "same-origin"});
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new Error("공개 데이터 목록을 읽지 못했습니다.");
  }
  return parsePublicDatasets(await response.json() as unknown);
}

export async function startImport(datasetId: string, signal: AbortSignal): Promise<void> {
  await postWrite("/api/v1/datasets/import", {dataset_id: datasetId}, signal);
}

/** AI-Hub by equipment and 학습용/검증용, then the XJTU-SY bearings, in the server's order. */
export function groupDatasets(items: PublicDataset[]): DatasetGroup[] {
  const groups = new Map<string, DatasetGroup>();
  for (const item of items) {
    const key = item.kind === "xjtu-sy" ? "xjtu-sy" : item.equipment + "\n" + item.split;
    const title = item.kind === "xjtu-sy" ? "XJTU-SY 베어링 진동 기록"
      : "AI-Hub 239 · " + item.equipment + " 전력 기록 (" + item.split + ")";
    const group = groups.get(key) ?? {key, title, kind: item.kind, items: []};
    group.items.push(item);
    groups.set(key, group);
  }
  return [...groups.values()];
}

export function datasetName(item: PublicDataset): string {
  return item.kind === "xjtu-sy"
    ? item.assetId + (item.speedHz !== null && item.loadKn !== null ? " · " + item.speedHz + " Hz · " + item.loadKn + " kN" : "")
    : "설비 " + item.deviceId;
}

export function datasetFacts(item: PublicDataset): string {
  if (item.kind === "xjtu-sy") return item.acquisitions === null ? "" : "측정 " + item.acquisitions.toLocaleString("ko-KR") + "회";
  return item.bytes === null ? "" : "원천 기록 " + (item.bytes / 1e6).toLocaleString("ko-KR", {maximumFractionDigits: 1}) + " MB";
}

const FAILURE: Record<string, string> = {
  "models-unavailable": "이상 탐지 모델을 준비할 근거 파일이나 코드 버전을 찾지 못했습니다.",
  "source-incomplete": "XJTU-SY 베어링 15개가 모두 있어야 모델을 준비할 수 있습니다.",
  "reader-unavailable": "AI-Hub 원천 기록을 읽는 구성 요소가 설치되지 않았습니다.",
  "dataset-unavailable": "데이터 파일을 읽지 못했습니다.",
  "source-changed": "가져오는 동안 원본이 바뀌었습니다. 원본을 그대로 둔 뒤 다시 가져오세요. 기존 기록은 보존됩니다.",
};

/** One line for a running or finished import, in terms of what is being stored. */
export function jobText(job: DatasetJob): string {
  if (job.state === "running") {
    if (job.step === "models") return "이상 탐지 모델 준비 중 · 처음 한 번만, 몇 분 걸립니다";
    if (job.step === "replay") return "측정 기록 넣는 중 · " + job.done.toLocaleString("ko-KR") + "회";
    return "측정값 저장 중 · " + job.done.toLocaleString("ko-KR") + "개";
  }
  if (job.state === "succeeded") return "가져왔습니다";
  if (job.state === "interrupted") return "운영이 다시 시작돼 중단됐습니다. 다시 가져오면 저장된 부분은 건너뜁니다.";
  return "가져오지 못했습니다 · " + (FAILURE[job.failure ?? ""] ?? "원인을 확인하지 못했습니다.");
}
