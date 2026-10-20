import assert from "node:assert/strict";
import {test} from "node:test";
import {nextReviewStatus,reviewNote} from "./review-writes.ts";

test("one review status policy for every review subject",()=>{
  assert.equal(nextReviewStatus("open","note"),"open");
  assert.equal(nextReviewStatus("open","acknowledge"),"acknowledged");
  assert.equal(nextReviewStatus("acknowledged","close"),"closed");
  assert.throws(()=>nextReviewStatus("open","close"),/전이/);
  assert.throws(()=>nextReviewStatus("closed","note"),/완료/);
});

test("a note is trimmed, bounded and optional with a confirm or close",()=>{
  assert.equal(reviewNote("note","  확인함 \n"),"확인함");
  assert.equal(reviewNote("acknowledge"," 베어링 소음 확인 \n"),"베어링 소음 확인");
  assert.equal(reviewNote("close",""),"");
  assert.throws(()=>reviewNote("close","가".repeat(700)),/1000자/);
  assert.throws(()=>reviewNote("note","   "),/메모를 입력/);
  assert.throws(()=>reviewNote("note","가".repeat(1001)),/1000자/);
  assert.throws(()=>reviewNote("note","bell\u0007"),/제어 문자/);
});
