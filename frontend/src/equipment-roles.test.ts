import assert from "node:assert/strict";
import {test} from "node:test";
import {equipmentRole} from "./equipment-roles.ts";

test("an equipment's role is found by its dataset and name", () => {
  assert.equal(equipmentRole("aihub-239", "공기압축기")?.short, "압축공기 공급");
  assert.equal(equipmentRole("xjtu-sy", "35 Hz · 12 kN")?.short, "회전축 지지");
  assert.equal(equipmentRole("aihub-239", "모르는 설비"), null);
  assert.equal(equipmentRole("connected", null), null);
});
