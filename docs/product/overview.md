# Product and UX Baseline

이 문서는 Dashboard 구현보다 먼저 사용자 역할과 정보 소비 구조를 정리합니다. UI framework나 화면 디자인을
고정하기 위한 문서가 아니라, PHM 결과가 실제 의사결정에서 어떤 정보로 소비되어야 하는지 확인하기 위한
초기 기준선입니다.

## 1. 사용자 역할

### 설비 관리자

관심사는 개별 모델의 내부 구조보다 현재 설비 상태와 운영 우선순위입니다.

- 현재 상태와 최근 변화
- 위험 설비와 alert
- fleet 또는 공정 단위 overview
- 데이터가 충분하지 않거나 분석이 불가능한 경우의 명시적 상태

### 정비 엔지니어

모델 출력의 근거와 정비 판단에 필요한 세부 정보를 소비합니다.

- anomaly score와 threshold
- health/degradation trend
- sensor 또는 feature evidence
- 데이터 품질과 분석 적용 범위
- 모델이 제공할 수 있는 설명 근거
- 가능한 원인과 대안 가설
- 정비 이력 및 관련 문서

### 의사결정자

설비별 세부 waveform보다 fleet 수준 위험과 조치 우선순위를 봅니다.

- 위험도와 긴급도
- 유지보수 우선순위
- fleet-level summary
- 모델/데이터 적용 범위와 불확실성

## 2. 대시보드 전에 PHM 결과 계약부터

Dashboard와 Generative AI가 model implementation을 직접 소비하지 않도록 향후 공통 `PHMResult` 경계를
둡니다. 구체적 schema는 실제 inference 요구가 확인된 뒤 정의하지만, UX 관점에서는 다음 정보 범주가
필요한지 검토합니다.

```text
식별 정보 (Identity)
- asset
- observation time

상태 평가 (Assessment)
- status
- anomaly score / threshold
- health index / trend
- RUL 또는 capability unavailable

판단 근거 (Evidence)
- supporting observations
- data quality
- applicable operating context

모델 설명 (Explanation, optional)
- feature/channel/time contribution
- reconstruction residual 또는 모델 고유 설명 근거
- explanation method / scope

불확실성 (Uncertainty, optional)
- confidence / interval / calibration information
- unsupported 또는 out-of-scope 상태

추적 정보 (Provenance)
- model/artifact version
- preprocessing/config revision
- dataset/source lineage

의사결정 지원 (Decision support)
- interpretation
- possible causes
- recommended inspection or maintenance action
```

모든 capability가 항상 존재한다고 가정하지 않습니다. RUL, uncertainty, explanation이 지원되지 않는 경우
임의의 값이나 그럴듯한 설명으로 채우지 않고 명시적으로 unavailable 상태로 표현합니다.

## 3. 사람·AI·XAI의 책임

수치 계산과 PHM 판단의 source of truth는 deterministic PHM pipeline입니다. Generative AI는 구조화된 결과와
retrieved maintenance knowledge를 사용해 설명·가설 정리·권고 초안·보고서를 생성합니다.

XAI는 별도의 만능 계층으로 두지 않습니다. 모델마다 설명 가능한 근거의 성격이 다르기 때문입니다. 예를 들어
feature 기반 모델은 feature-level contribution이나 sensitivity를 제공할 수 있고, reconstruction 기반 모델은
채널·시간·window별 residual 자체가 중요한 설명 근거가 될 수 있습니다. RUL과 같은 prognostics에서는 feature
attribution뿐 아니라 degradation trajectory, uncertainty, calibration이 판단에 더 직접적인 근거가 될 수 있습니다.

따라서 초기 원칙은 다음과 같습니다.

- 모델은 가능하면 자신의 수치 출력과 함께 검증 가능한 evidence/explanation artifact를 생성합니다.
- `PHMResult`는 explanation을 optional capability로 수용할 수 있어야 합니다.
- 설명 방법을 하나의 SHAP/LIME 인터페이스로 성급하게 표준화하지 않습니다.
- GenAI는 모델 score만 보고 원인을 만들어내지 않고, 전달된 evidence와 retrieved knowledge의 범위 안에서만 설명합니다.
- 설명이 제공되지 않거나 신뢰할 수 없는 경우 그 한계를 사용자에게 그대로 보여줍니다.

UI는 사실, 모델 추정, 모델 설명 근거, 원인 가설, 정비 권고가 같은 시각적 수준에서 섞이지 않도록 구분해야
합니다. 특히 정비 조치가 실제 work order나 설비 제어로 이어지는 경우 승인 boundary를 별도로 둡니다.

## 4. CLI도 UX

현재 단계에서 가장 먼저 사용되는 제품 인터페이스는 CLI일 가능성이 높습니다. 따라서 CLI도 다음 UX 기준을
적용합니다.

- 명령과 option 이름이 일관적일 것
- 실패 이유와 다음 조치를 설명할 것
- 데이터가 어디에 저장되었는지 보여줄 것
- effective source/version/provenance를 확인할 수 있을 것
- destructive 또는 network-heavy 동작은 명시적으로 실행할 것

## 5. UI 구현 시점

지금 할 일:

- 역할과 정보 요구 검증
- PHM Result에 필요한 정보 범주 정의
- 모델별 evidence/XAI 요구 확인
- low-fidelity information architecture 검토
- CLI workflow 설계

나중에 할 일:

- Dashboard framework 선택
- API schema 고정
- 시각화 library 선택
- 권한/인증/조직별 화면 구현

UI implementation을 늦춘다는 것은 UX를 늦춘다는 뜻이 아닙니다. 실제 모델·결과 계약이 안정되기 전에 특정
frontend 구조가 backend contract를 고정하는 상황을 피합니다.

## References

- ISO 9241-210 human-centred design overview: https://www.iso.org/standard/77520.html
- Human-in-the-Loop XAI for Predictive Maintenance (2025): https://doi.org/10.3390/electronics14173384
- Data-driven prognostics review: uncertainty, robustness, interpretability and feasibility (2025): https://doi.org/10.1016/j.ymssp.2025.113015
