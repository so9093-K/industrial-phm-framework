import assert from "node:assert/strict";
import {test} from "node:test";
import {noticeSentences, withParticle} from "./monitor-chat.ts";

test("particles follow how the word's last sound is read", () => {
  assert.equal(withParticle("R·S·T상 상전압", "이/가"), "R·S·T상 상전압이");
  assert.equal(withParticle("수직 진동 RMS", "이/가"), "수직 진동 RMS가");
  assert.equal(withParticle("전류평균", "은/는"), "전류평균은");
  assert.equal(withParticle("23 A", "으로/로"), "23 A로");
  assert.equal(withParticle("226 V", "으로/로"), "226 V로");
  assert.equal(withParticle("2.3 g", "으로/로"), "2.3 g로");
  assert.equal(withParticle("수직 진동 크기 (RMS)", "이/가"), "수직 진동 크기 (RMS)가");
  assert.equal(withParticle("1", "으로/로"), "1로");
  assert.equal(withParticle("3", "으로/로"), "3으로");
});

test("a 특이사항 is said as what, by how much, since when, and the load at the same time", () => {
  assert.deepEqual(noticeSentences({what: "R·S·T상 상전압", size: "초기보다 4.26 V(1.9%) 높음", before: "222 V", after: "226 V",
    when: "10월 4일(일) 09:19", still: false, duration: "22시간 12분", load: {label: "전류평균", before: "41 A", after: "23 A", ratio: 23 / 41}}), [
    "R·S·T상 상전압이 222 V에서 226 V로, 초기보다 4.26 V(1.9%) 높습니다.",
    "10월 4일(일) 09:19부터 22시간 12분 동안 이어졌고, 같은 때 전류평균은 41 A에서 23 A로 줄었습니다.",
  ]);
  assert.deepEqual(noticeSentences({what: "R상 상전압", size: "초기보다 7.59 V(3.5%) 높음", before: "217 V", after: "224 V",
    when: "9월 20일(일) 13:41", still: false, duration: "3시간 34분", load: {label: "전류평균", before: "62 A", after: "58 A", ratio: 58 / 62}})[1],
    "9월 20일(일) 13:41부터 3시간 34분 동안 이어졌고, 같은 때 전류평균은 62 A에서 58 A로, 거의 같았습니다.");
  assert.deepEqual(noticeSentences({what: "수직 진동 RMS", size: "초기의 약 3.7배", before: "0.623 g", after: "2.3 g",
    when: "72번째 측정", still: true, duration: "52회 측정", load: null}), [
    "수직 진동 RMS가 0.623 g에서 2.3 g로, 초기의 약 3.7배입니다.",
    "72번째 측정부터 마지막 측정까지 이어졌습니다.",
  ]);
  assert.equal(noticeSentences({what: "R상 상전압", size: "높음", before: null, after: null, when: "9월 22일", still: false,
    duration: "37분", load: null})[0], "R상 상전압이 높습니다.");
});
