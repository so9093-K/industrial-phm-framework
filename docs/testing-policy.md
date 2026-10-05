# Testing Policy

테스트의 목적은 줄 수나 coverage percentage를 늘리는 것이 아니라, public behavior·명시적 contract·이미
발견된 regression이 다시 깨지는 것을 방지하는 것입니다.

## 1. Every Test Protects a Failure

모든 테스트는 다음 질문에 한 문장으로 답할 수 있어야 합니다.

> 이 테스트가 없을 때 어떤 의미 있는 실패가 회귀할 수 있는가?

명확한 답이 없다면 테스트를 추가하지 않습니다. implementation detail만 고정하거나 coverage를 올리기 위한
테스트는 유지보수 비용만 증가시키므로 피합니다.

## 2. Test Public Behavior and Contracts

우선순위는 다음과 같습니다.

1. public contract와 invariant
2. known regression
3. 데이터 손상·leakage·잘못된 artifact 같은 critical failure path
4. 사용자에게 노출되는 CLI/API behavior

private helper 호출 횟수, 내부 collection 종류, refactor 가능한 구현 순서처럼 외부 동작과 무관한 세부사항은
직접 검증하지 않습니다.

## 3. Test Layers Grow with Real Features

현재 repository는 unit과 contract에 더해, 실제로 생긴 adapter → application 경계를 보호하는 최소
integration test를 유지합니다. Local Operations service/browser workflow가 생긴 뒤에는 clean-workspace
product lifecycle을 `tests/acceptance/`에서 보호합니다.

```text
tests/
├── unit/          # 한 component의 작은 behavior/invariant
├── contract/      # adapter/result/artifact 등 공유 경계
├── integration/   # 실제 component/application 경계
└── acceptance/    # service/browser user workflow가 생긴 뒤 추가
```

Integration test도 concrete boundary를 보호해야 하며 미래용 directory나 fixture framework를 미리 만들지
않습니다.

현재 Operations acceptance gate는 외부 dataset/network를 사용하지 않습니다. Packaged synthetic demo를 실제
subprocess로 시작해 workspace 생성 → runtime ready → finalized window/analysis evidence → graceful stop →
같은 workspace restart/state 보존을 확인합니다. Base unit suite에서는 optional Operations runtime이 없으면
skip하고, CI의 `operations` extra 환경에서 별도 gate로 실행합니다.

## 4. Do Not Reimplement Validation in Tests

checksum, schema, split rule, artifact compatibility 같은 validation은 production code에 한 번 구현합니다.
테스트는 그 validator를 호출하여 기대 behavior를 검증합니다. 같은 validation logic을 test helper에서 다시
계산해 서로 같은 버그를 공유하는 구조를 만들지 않습니다.

## 5. External Data and Network Tests

PR 기본 test suite는 대형 공개 데이터셋을 내려받지 않습니다.

- unit: 작은 synthetic input
- contract: hand-written representative fixture
- integration: 필요한 최소 real sample 또는 명시적 opt-in local data
- full benchmark: 별도 manual/scheduled research workflow

remote endpoint availability는 unit test가 아닙니다. 실제 provider smoke check가 필요하면 PR gate와 분리하고
실패가 코드 regression인지 외부 서비스 문제인지 구분할 수 있게 합니다.

## 6. Fixtures and Helpers

fixture/helper 추상화는 실제 중복이 반복된 이후 도입합니다. 단순한 테스트 input을 숨기는 과도한 fixture
계층은 읽기 어려운 테스트를 만들기 때문에 피합니다.

작은 contract example은 테스트 안에서 직접 보이는 편을 우선합니다.

## 7. Coverage

coverage는 누락된 경로를 발견하는 진단 정보이지 품질 목표 자체가 아닙니다. 전체 coverage percentage를
높이기 위해 가치 없는 branch test를 생성하지 않습니다.

특히 다음 경로를 우선 확인합니다.

- contract invariant
- data provenance/integrity validation
- split leakage prevention
- artifact compatibility
- CLI/API error path

coverage threshold가 필요해지는 경우 repository 규모와 regression history가 충분히 쌓인 뒤 별도 결정으로
도입합니다.

## 8. Property and Mutation Testing

property-based testing이나 mutation testing은 기본 도구가 아닙니다. invariant 공간이 넓거나 기존 테스트의
실효성을 검증할 가치가 확인된 component에 선택적으로 적용합니다.

대표 후보는 canonical contract, split logic, serialization, artifact validation입니다.

## 9. Critical Regression Ownership

같은 failure를 여러 layer가 중복해서 보호하지 않도록 대표 regression의 primary owner를 명시합니다.
보조 smoke나 integration coverage가 존재할 수 있지만, 아래 owner가 해당 failure 의미의 기준입니다.

| Failure | Primary owner |
| --- | --- |
| OPC UA reconnect / delivery loss | live acquisition runtime contract / fault gate |
| spool → DuckLake recovery와 idempotent replay | runtime contract |
| observation window cursor / restart | window contract |
| Operations first-run / navigation | Operations integration |
| 실제 browser에서 Live observation 가시성 | acceptance / fault browser gate |
| marimo same-cell `.value` runtime regression | marimo structural contract |
| Operations UI의 concrete storage/runtime composition 침범 | Operations architecture import contract |
| presenter의 단순 문구·HTML 모양 | 기본적으로 regression owner를 두지 않음 |

새 회귀 테스트를 추가할 때는 먼저 이 표 또는 기존 테스트에서 같은 failure owner가 있는지 확인합니다.

## 10. Review Checklist

테스트 PR 리뷰에서는 다음을 확인합니다.

- 새로운 production behavior 또는 regression과 연결되는가?
- 같은 failure를 이미 다른 test가 보호하고 있지 않은가?
- public behavior 대신 implementation detail을 고정하지 않는가?
- network/대용량 dataset을 기본 suite에 끌어들이지 않는가?
- production validator를 test에서 복제하지 않는가?
- 새로운 helper/fixture가 실제 중복을 줄이는가?

## References

- pytest good integration practices: https://docs.pytest.org/en/stable/explanation/goodpractices.html
- Google Testing Blog, test behavior rather than implementation: https://testing.googleblog.com/2013/08/testing-on-toilet-test-behavior-not.html
- Hypothesis documentation: https://hypothesis.readthedocs.io/
