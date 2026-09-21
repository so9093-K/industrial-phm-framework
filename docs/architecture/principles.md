# Architecture Principles

## 1. Stable boundaries before abstractions

추상화는 미래의 가능성이 아니라 실제 반복되는 변화 지점을 기준으로 도입합니다. 초기에는 단일 Python
package를 유지하고, Domain Adapter와 공통 데이터 계약처럼 이미 명확한 경계만 코드로 표현합니다.

## 2. Domain knowledge stays at the edge

파일 형식, 센서 이름, sampling metadata 해석, 데이터셋별 label 규칙은 adapter 책임입니다. 공통 PHM
코드에 `if domain == ...` 형태의 분기가 반복되기 시작하면 경계 실패로 간주하고 재검토합니다.

## 3. Optional capability is represented by data, not silent fallback

RUL이나 label처럼 데이터가 제공하지 않는 정보는 명시적으로 부재 상태를 표현합니다. 기능을 사용할 수
없을 때 임의의 값이나 추정 target으로 조용히 대체하지 않습니다.

## 4. Evaluation is independent of model implementation

모델은 자신의 numerical output을 생산하고 평가 계층은 그 output을 별도로 해석·검증합니다. Anomaly score,
reconstruction error, RUL estimate처럼 의미가 다른 출력을 모두 generic `prediction`으로 부르지 않으며,
metric 계산을 LLM 또는 dashboard 코드에 위임하지 않습니다.

## 5. Artifacts require provenance

향후 학습 모델을 저장할 때 model binary만 단독으로 배포하지 않습니다. scaler, threshold, feature/config,
dataset version, code revision 등 재현과 추론에 필요한 provenance를 함께 관리합니다.

## 6. Compatibility is earned

새 Python version, OS, accelerator 또는 serialization format은 실제 CI 및 integration test로 확인한 후
지원 대상으로 선언합니다. `>=3.14`처럼 상한 없는 Python version 선언으로 미래 호환성을 가정하지 않습니다.

## 7. Architecture decisions remain reconstructable

장기 영향이 있는 선택은 ADR로 남깁니다. 기존 ADR의 역사적 문맥을 지우지 않고, 결정이 바뀌면 새 ADR이
이전 결정을 supersede하도록 기록합니다.

## 8. Data acquisition is explicit

공개 연구 데이터의 download/cache/verify는 Domain Adapter와 분리합니다. package 설치나 import가 대용량
데이터를 암묵적으로 내려받지 않으며, acquisition은 사용자가 명시적으로 실행하고 source/version/license/hash를
추적 가능한 형태로 남깁니다.

## 9. One fact has one authoritative owner

같은 URL, version, threshold, split 또는 dependency 사실을 코드·문서·테스트에 중복 정의하지 않습니다.
`pyproject.toml`, `uv.lock`, dataset manifest, experiment config, artifact manifest, ADR 등 사실의 성격에 맞는
권위 있는 위치를 하나 정하고 다른 계층은 이를 참조합니다.

## 10. UX contracts precede UI implementation

Dashboard framework는 결과 계약과 service boundary가 안정된 이후 선택하되, 사용자 역할과 필요한 정보는
초기부터 검토합니다. CLI도 사용자 인터페이스로 취급하며 명령 구조, 오류 메시지, provenance 확인 경험을
일관되게 유지합니다.

## 11. Tests justify their maintenance cost

테스트는 public behavior, explicit contract 또는 known regression을 보호해야 합니다. coverage 수치만 높이거나
private implementation detail을 고정하는 테스트, production validation을 재구현하는 테스트를 만들지 않습니다.
대형 외부 데이터와 network 검증은 기본 unit/contract suite와 분리합니다.

## 12. Capability growth preserves dependency direction

Anomaly, Prognostics/RUL, Diagnostics처럼 새로운 PHM capability가 추가되어도 numerical 계산의 책임을
presentation 계층으로 올리지 않습니다.

```text
numerical capability
  -> validated evidence artifact
  -> analysis read model
  -> UI / GenAI / report
```

UI, 생성형 AI와 report는 artifact에 없는 수치나 capability를 재계산·보정·추정하지 않습니다. 새 capability는
먼저 자신의 numerical/evaluation/evidence 의미를 명시하고 Analysis 계층에서 조합합니다.

두 번째 구현이 생겼다는 이유만으로 universal result schema, generic workflow engine 또는 모든 PHM 기능을
포괄하는 base abstraction을 만들지 않습니다. 두 개 이상의 실제 consumer에서 같은 책임과 변경 이유가
반복될 때만 작은 공통 contract로 승격합니다. Core package는 `apps`나 특정 presentation framework에
의존하지 않으며 optional consumer가 numerical core의 import/runtime requirement를 역전시키지 않게 합니다.
