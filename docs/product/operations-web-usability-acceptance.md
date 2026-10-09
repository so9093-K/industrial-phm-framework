# Operations Web 실제 운영자 사용성 수용 프로토콜

> 상태: **사용성 연구 절차(미수행)**. 이 문서 자체와 자동 Chromium 통과는 실제 산업 운영자 수용이나 현장 안전·설비 상태 검증을 의미하지 않는다.

## 목적과 적용 범위

[Issue #478](https://github.com/so9093-K/industrial-phm-framework/issues/478)의 실제 사람 대상 관측 절차이다. [Issue #449](https://github.com/so9093-K/industrial-phm-framework/issues/449)의 최종 제품 Gate 및 [Issue #479](https://github.com/so9093-K/industrial-phm-framework/issues/479)의 Web 기본 전환 판단에 사용한다. 실제 데이터를 장비 제어·정비 수행에 사용하지 않고, 참가자가 *근거가 말해 주는 사실*과 *추정할 수 없는 사실*을 혼동하지 않는지 검토한다.

검증 대상은 Linux local workspace의 `industrial-phm operations start <workspace> --ui web-controlled`이며, 이를 기본 UI로 바꾸지 않는다. 원격 호스트, 실제 설비 상태 판단, RUL, 고장 진단, 정비 실행 검증은 범위 밖이다. 서로 다른 UI의 동시 쓰기 작업은 금지한다.

## 모집·진행자·보호 조치

- 실제 산업 설비 운영 또는 정비 업무 경험이 있는 사람을 우선 모집한다. 권장 첫 라운드는 4–6명, 가능한 경우 운영과 정비 역할에서 각각 2명 이상. 모집 수·역할·숙련도는 실제 결과에 기록한다.
- 개발자/기획자의 자가 시연은 진단용 *pilot*으로 기록하며 실제 운영자 연구로 합산하지 않는다. 참가자를 모집하지 못했으면 Gate는 **보류**다.
- 세션 전에 동의를 받고, 원본 발화와 화면 녹화의 사용·보관 범위를 고지한다. 이름, 사업장, 자격 증명, 실설비 정보, 원본 센서 데이터 등 식별 정보는 이 저장소/공개 Issue에 남기지 않는다.
- 조작 대상은 복구 가능한 격리 synthetic/recorded workspace이며, 새 복제본을 참가자별로 준비한다. 기존 실제 운영 workspace 및 장비 제어 경로를 사용하지 않는다.
- 참가자에게 UI의 정답 해석을 미리 설명하거나 '정상인지'를 유도하지 않는다. 과제 설명은 중립적으로 하고, 진행자의 힌트와 사용자 자체 발견을 구분해 기록한다.
- 화면 및 패키지의 commit SHA, 포트/환경(비식별), 브라우저 viewport, locale, 각 과제 시작 상태와 데이터 provenance를 기록한다. 테스트가 mock API 또는 preseeded analysis에 기대면 그 한계를 표시한다.

## 시작 전 증거 준비

| ID | 준비된 사실 | 반드시 분리해서 제시할 사실 |
| --- | --- | --- |
| A | 등록 전 빈 workspace | 설비/수신/결과 없음은 설비 정상도 고장도 아님 |
| B | FILE 등록 후 lifecycle `active`, receipt 없음 | 등록·활성화 ≠ 실제 연결·수신 |
| C | FILE accepted receipt 존재, DuckLake 미적재 | 1회 검증 수신 ≠ 이력 저장·분석·연속 수집 |
| D | 명시적 FILE backfill로 DuckLake 측정값 존재 | 저장된 과거 시각·품질 ≠ 현재 설비 상태 |
| E | **사전에 영속 저장한** 실제 형식의 AnalysisRun/Evidence | backfill 자체가 자동 분석을 실행했다는 근거 없음 |
| F | review request → note → acknowledge → close | 검토 기록 종료 ≠ 물리 정비 완료·고장 해결·안전 확인 |
| G | 최신 결과와 분리된 오래된 값, missing/quality 표시 및 409/503 가능한 격리 오류 | 값 없음 ≠ 0; 조회 오류 ≠ 기록 0; 요청 오류 ≠ 무조건 미적용 |

`E`는 테스트 fixture를 실제 분석 시도가 실행된 것처럼 설명하지 않는다. 테스트 중 특정 오류를 유도하는 장치가 없으면 해당 과제는 *미실행*으로 표기하고 통과시키지 않는다.

## 과제별 진행 순서 (힌트 없이 시작)

각 과제 직후 다음 두 가지를 묻는다. (1) **지금 무엇이 확인됐습니까?** (2) **아직 무엇을 알 수 없습니까?** 참가자의 실제 답변을 기록한 뒤에만 정답 개념을 안내한다.

| 과제 | 참가자에게 줄 중립적 지시 | 관찰할 위험한 오해 |
| --- | --- | --- |
| 1. 첫 화면 | "이 작업공간에서 확인 가능한 데이터를 찾아보세요." | 등록이 없다는 이유로 설비 정상 또는 고장이라고 판단 |
| 2. 등록/활성화 | "소스를 준비한 뒤 지금 어떤 상태인지 설명해 주세요." | `active`를 연결 완료·실시간 수신으로 해석 |
| 3. Receipt | "수신 확인을 수행하고 이력에서 사용 가능한 사실을 설명해 주세요." | accepted receipt 하나를 DuckLake commit/분석 성공으로 해석 |
| 4. 이력·품질 | "측정값의 기준 시각과 누락·품질 정보를 찾아보세요." | 오래된 이벤트를 현재값으로 해석, 결측을 0으로 보간, 데이터 흐름을 설비 건강으로 해석 |
| 5. 분석 근거 | "이 결과를 실제로 판단할 때 필요한 근거를 찾으세요." | AnalysisRun을 확정 고장 진단·경보·RUL·현재 설비 상태로 격상 |
| 6. 사람 검토 | "근거에 연결된 검토 메모를 남기고 확인 후 기록을 종료해 보세요." | `acknowledged`나 `closed`를 실제 정비 완료·안전 인증으로 해석 |
| 7. 실패/복구 | "조회/명령이 실패하거나 답을 알 수 없을 때 어떻게 하시겠습니까?" | 409/503/응답 불명을 무조건 재전송 또는 영구 실패로 단정 |
| 8. 근거 복귀 | "원래 분석 기록과 연결된 검토 이력을 다시 찾으세요." | finding / analysis_run / evidence 식별자를 잃거나 다른 설비 근거와 혼합 |

설치 중인 Web UI에 기능이 아직 없다면, 기능을 사용할 수 없는 것을 **UI 동등성 blocker**로 기록한다. 참가자의 이해 오류로 전가하거나 해당 과제를 무조건 통과 처리하지 않는다.

## 정량·정성 판정

각 참가자 × 과제에 독립 수행(`independent` / `prompted` / `blocked` / `not-run`), 정확한 확인 사실·미확인 사실, 경로/시간(선택), 오해, 발견 가능성, 진행자 개입을 남긴다.

문제 심각도:

- `block`: 설비 안전·정비 수행·실시간 데이터·분석 진실성에 관한 위험한 잘못된 판단이 UI 때문에 유지됨. 기본 Web 전환 금지.
- `major`: 주요 관측/검토 업무를 독립 수행하지 못하거나 근거를 잘못 연결함. 수정/재검증 필요.
- `minor`: 위험한 판단 없이 문구·탐색의 불편함이 있음. 수정하거나 수용 근거 명시.
- `observation`: 확인이 필요한 의견·선호, 실제 오류·검증 결과와 별도로 관리.

**수용 Gate:** 모든 실제 참가자 세션에서 확인된 `block`과 `major`가 수정 PR 및 유사 역할의 재검증으로 해결돼야 한다. 미실행 과제는 통과가 아니며, 표본 규모와 능력 범위를 명시한다. 자동 CI·문구 스냅샷·개발자 리뷰·면담만으로 "운영자가 이해했다"는 결론을 내리지 않는다.

## 비식별 세션 기록 양식

아래 한 장을 참가자별로 작성하되 개인 신원이나 현장 비밀을 GitHub에 공개하지 않는다.

```text
Session: participant-<non-identifying code>
Role: operator / maintenance / mixed (experience summary only)
Environment: repo commit, wheel digest, browser, locale, viewport, sandbox fixture
Facilitator / consent: recorded internally (do not publish PII)
Task ID:
Independent / Prompted / Blocked / Not-run:
Observed navigation / pause / errors:
What the participant says is confirmed:
What the participant says is unknown:
Observed misconception:
Severity: block / major / minor / observation
Linked correction PR:
Retest: who / role / version / outcome (no PII)
Notes on test limits:
```

## 최종 수용·전환 체크

- [ ] 실제 운영자·정비 담당자 세션 완료, 표본/환경과 비식별 기록 남김
- [ ] 각 과제의 confirmed / unknown 이해 확인, 위험한 오해 `block` 또는 `major` 해결 및 재검증
- [ ] `ko-KR` / `en-US` × 1024/1440, 키보드·native label·스크린리더 접근성, First-run·Signals·Investigation·Maintenance·System의 **전체 업무 동등성** 별도 기능 Gate 통과
- [ ] 최신 PR/Core Ruff·format·mypy·pytest, Chromium, Runtime/Operations, Package/systemd/Required CI 성공
- [ ] wheel-only·backup/restore·이전 정상 wheel rollback, single-writer와 CSRF/Origin/Host 경계 유지
- [ ] [#478](https://github.com/so9093-K/industrial-phm-framework/issues/478)에 실제 세션 결과와 수용/보류 결정 근거를 연결한 뒤, [#479](https://github.com/so9093-K/industrial-phm-framework/issues/479) 기본 전환 PR을 별도로 판단

마지막 항목이 완료되기 전에는 기본 `make up`을 기존 marimo로 유지한다. 구형 Operations UI/의존성 제거 [#480](https://github.com/so9093-K/industrial-phm-framework/issues/480)은 전환 PR 병합 후 main CI가 성공한 다음에만 진행한다.
