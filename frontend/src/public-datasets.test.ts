import assert from "node:assert/strict";
import {test} from "node:test";
import {datasetFacts, datasetName, groupDatasets, jobText, parsePublicDatasets} from "./public-datasets.ts";

const MEANING = "public-datasets-found-in-the-datasets-folder-not-imported-evidence";
const aihub = (device: string, split = "학습용", stored = false) => ({
  dataset_id: "aihub239:training:3.공기압축기.zip:SourceData_" + device + ".json", kind: "aihub-239",
  asset_id: "공기압축기 " + device, stored, equipment: "공기압축기", split, device_id: device, device_board_id: "1",
  bytes: 219594348,
});
const xjtu = {dataset_id: "xjtu-sy:Bearing1_1", kind: "xjtu-sy", asset_id: "Bearing1_1", stored: false,
  bearing: "Bearing1_1", rotational_speed_hz: 35, radial_load_kn: 12, acquisitions: 123};

test("the listing groups AI-Hub records by equipment and split before the XJTU-SY bearings", () => {
  const found = parsePublicDatasets({schema_version: 1, available: true, can_import: true, meaning: MEANING,
    items: [aihub("1338"), aihub("2194", "검증용"), aihub("1339", "학습용", true), xjtu],
    jobs: {"xjtu-sy:Bearing1_1": {state: "running", step: "models", done: 0, asset_id: "Bearing1_1"}}});
  assert.deepEqual(groupDatasets(found.items).map((group) => [group.title, group.items.length]), [
    ["AI-Hub 239 · 공기압축기 전력 기록 (학습용)", 2],
    ["AI-Hub 239 · 공기압축기 전력 기록 (검증용)", 1],
    ["XJTU-SY 베어링 진동 기록", 1],
  ]);
  assert.equal(datasetName(found.items[0]), "설비 1338");
  assert.equal(datasetFacts(found.items[0]), "원천 기록 219.6 MB");
  assert.equal(datasetName(found.items[3]), "Bearing1_1 · 35 Hz · 12 kN");
  assert.equal(datasetFacts(found.items[3]), "측정 123회");
  assert.equal(found.items[2].stored, true);
  assert.equal(found.items[0].partial, false);
  assert.equal(jobText(found.jobs["xjtu-sy:Bearing1_1"]), "이상 탐지 모델 준비 중 · 처음 한 번만, 몇 분 걸립니다");
  assert.throws(() => parsePublicDatasets({schema_version: 1, items: [], meaning: "imported"}), /형식/);
});

test("an import says what it is storing, and why it stopped in the reader's terms", () => {
  const job = (state: string, step: string, done = 0, failure: string | null = null) =>
    ({state: state as "running", step, done, assetId: "x", failure});
  assert.equal(jobText(job("running", "history", 1509725)), "측정값 저장 중 · 1,509,725개");
  assert.equal(jobText(job("running", "replay", 42)), "측정 기록 넣는 중 · 42회");
  assert.match(jobText(job("failed", "models", 0, "source-incomplete")), /15개가 모두 있어야/);
  assert.match(jobText(job("failed", "history", 0, "unknown")), /원인을 확인하지 못했습니다/);
  assert.match(jobText(job("interrupted", "history")), /저장된 부분은 건너뜁니다/);
});

test("a partly stored dataset is not reported as fully imported", () => {
  const found = parsePublicDatasets({schema_version: 1, available: true, can_import: true, meaning: MEANING,
    items: [{...aihub("1338"), partial: true, stored: false}],
    jobs: {"aihub239:training:3.공기압축기.zip:SourceData_1338.json":
      {state: "interrupted", step: "history", done: 2000, asset_id: "공기압축기 1338"}}});
  assert.equal(found.items[0].stored, false);
  assert.equal(found.items[0].partial, true);
  assert.match(jobText(Object.values(found.jobs)[0]), /다시 가져오면/);
});
