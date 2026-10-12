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

Operations 수용 테스트는 실제 synthetic workspace에서 subprocess·저장 이력·Web 동작과
재시작 후 상태 보존 등을 검증합니다. 별도 optional 런타임·브라우저가 필요한 테스트는
기본 CI의 단위·계약 검사와 구별하여 해당 변경을 검토할 때 명시적으로 실행합니다.
의존성이 없어 skip된 테스트를 실행 성공으로 간주하지 않습니다.

## 4. Do Not Reimplement Validation in Tests

checksum, schema, split rule, artifact compatibility 같은 validation은 production code에 한 번 구현합니다.
테스트는 그 validator를 호출하여 기대 behavior를 검증합니다. 같은 validation logic을 test helper에서 다시
계산해 서로 같은 버그를 공유하는 구조를 만들지 않습니다.

## 5. External Data and Network Tests

PR 기본 test suite는 대형 공개 데이터셋을 내려받지 않습니다.

- unit: 작은 synthetic input
- contract: hand-written representative fixture
- integration: 필요한 최소 real sample 또는 명시적 opt-in local data
- full benchmark: 필요한 원본 데이터가 있을 때 명시적으로 실행하는 연구 평가

remote endpoint availability는 unit test가 아닙니다. 실제 provider smoke check가 필요하면 PR gate와 분리하고
실패가 코드 regression인지 외부 서비스 문제인지 구분할 수 있게 합니다.

## 6. Fixtures and Helpers

fixture/helper 추상화는 실제 중복이 반복된 이후 도입합니다. 단순한 테스트 input을 숨기는 과도한 fixture
계층은 읽기 어려운 테스트를 만들기 때문에 피합니다.

작은 contract example은 테스트 안에서 직접 보이는 편을 우선합니다.

## 7. Coverage

기본 CI는 coverage 비율을 측정하거나 합격 기준으로 사용하지 않습니다. 누락 경로를
조사할 필요가 있을 때만 별도로 분석하며, 테스트 추가 여부는 실제 회귀 위험으로 판단합니다.

## 8. Property and Mutation Testing

property-based testing이나 mutation testing은 기본 도구가 아닙니다. invariant 공간이 넓거나 기존 테스트의
실효성을 검증할 가치가 확인된 component에 선택적으로 적용합니다.

대표 후보는 canonical contract, split logic, serialization, artifact validation입니다.

## 9. Critical Regression Ownership

같은 failure를 여러 layer가 중복해서 보호하지 않도록 대표 regression의 primary owner를 명시합니다.
보조 smoke나 integration coverage가 존재할 수 있지만, 아래 owner가 해당 failure 의미의 기준입니다.

| Failure | Primary owner |
| --- | --- |
| OPC UA reconnect / delivery loss | live acquisition runtime contract / fault-recovery test |
| spool → DuckLake recovery와 idempotent replay | runtime contract |
| observation window cursor / restart | window contract |
| Operations first-run / navigation / isolated sample | Operations browser acceptance (해당 UI 변경 시 실행) |
| 실제 browser에서 Live observation 가시성 | browser acceptance / recorded fault-recovery test |
| 연구용 marimo same-cell `.value` runtime regression | 연구 marimo structural contract (Operations 제품 UI와 별개) |
| Operations Web의 read model·HTTP·Supervisor writer 경계 | Operations runtime/API integration 및 Chromium acceptance |
| presenter의 단순 문구·HTML 모양 | 기본적으로 regression owner를 두지 않음 |

새 회귀 테스트를 추가할 때는 먼저 이 표 또는 기존 테스트에서 같은 failure owner가 있는지 확인합니다.

## 선택 실행 테스트와 skip

Operations 의존성·Chromium·실제 데이터가 필요한 테스트는 해당 범위 검증 시 명시적으로 실행합니다.
실행 환경에 필요한 의존성이 준비됐는데 관련 테스트가 skip된다면 통과로 간주하지 않습니다.
원본 기록이 없어 실행하지 못한 실측 replay 역시 미실행으로 표시합니다.

소스 파일에 CSS selector나 함수 이름이 있다는 문자열 검사만으로 UI의 실제 동작을
증명하지 않습니다. 실제 브라우저 검증에서는 HTTP 상태, 화면 및 저장된 근거를 확인합니다.

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
