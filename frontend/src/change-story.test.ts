import assert from "node:assert/strict";
import {test} from "node:test";
import {changeEnded} from "./change-story.ts";

test("a change that ended well before the record's end is told apart from one that reached it", () => {
  // 마지막 두 구간 안에서 끝났으면 기록 끝까지 이어진 변화다.
  assert.notEqual(changeEnded("2020-10-05T07:31:42+09:00", "2020-10-22T23:59:09+09:00", 3196.7), null);
  assert.equal(changeEnded("2020-10-22T22:30:00+09:00", "2020-10-22T23:59:09+09:00", 3196.7), null);
  assert.equal(changeEnded("2020-10-05T07:31:42+09:00", null, 60), null);
});
