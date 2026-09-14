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

모델은 score/prediction을 생산하고 평가 계층은 이를 별도로 검증합니다. metric 계산을 LLM 또는 dashboard
코드에 위임하지 않습니다.

## 5. Artifacts require provenance

향후 학습 모델을 저장할 때 model binary만 단독으로 배포하지 않습니다. scaler, threshold, feature/config,
dataset version, code revision 등 재현과 추론에 필요한 provenance를 함께 관리합니다.

## 6. Compatibility is earned

새 Python version, OS, accelerator 또는 serialization format은 실제 CI 및 integration test로 확인한 후
지원 대상으로 선언합니다. `>=3.14`처럼 상한 없는 Python version 선언으로 미래 호환성을 가정하지 않습니다.

## 7. Architecture decisions remain reconstructable

장기 영향이 있는 선택은 ADR로 남깁니다. 기존 ADR의 역사적 문맥을 지우지 않고, 결정이 바뀌면 새 ADR이
이전 결정을 supersede하도록 기록합니다.
