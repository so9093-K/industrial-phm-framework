import assert from "node:assert/strict";
import { test } from "node:test";

import { parseMonitor } from "./monitor.ts";

const observed = {
  assets: {
    items: [
      {
        asset_id: "pump-one",
        data_flow_status: "stored-history",
        last_data_at: null,
        attention_count: 0,
      },
    ],
    total: 1,
    truncated: false,
  },
  assessed_at: "2026-10-10T00:00:00Z",
  system_error_scopes: [],
};

test("the API's zero is an actual zero, not an implicit default", () => {
  const data = parseMonitor(observed);
  assert.equal(data.assets[0].attentionCount, 0);
  assert.equal(data.systemReadUncertain, false);
});

test("missing an attention value never becomes zero", () => {
  const data = parseMonitor({
    ...observed,
    assets: {
      ...observed.assets,
      items: [{ asset_id: "pump-one", data_flow_status: "waiting", last_data_at: null }],
    },
  });
  assert.equal(data.assets[0].attentionCount, null);
});

test("missing error-scope evidence is not declared healthy", () => {
  const { system_error_scopes: _omitted, ...withoutErrors } = observed;
  const data = parseMonitor(withoutErrors);
  assert.equal(data.systemReadUncertain, true);
});

test("an invalid payload is not represented as an empty workspace", () => {
  assert.throws(() => parseMonitor({ assets: { total: 0 } }), /관측 응답/);
});
