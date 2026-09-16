# Product and UX Baseline

이 문서는 Dashboard 구현보다 먼저 사용자 역할과 정보 소비 구조를 정리합니다. UI framework나 화면 디자인을
고정하기 위한 문서가 아니라, PHM 결과가 실제 의사결정에서 어떤 정보로 소비되어야 하는지 확인하기 위한
초기 기준선입니다.

## 1. User Roles

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
- 가능한 원인과 대안 가설
- 정비 이력 및 관련 문서

### 의사결정자

설비별 세부 waveform보다 fleet 수준 위험과 조치 우선순위를 봅니다.

- 위험도와 긴급도
- 유지보수 우선순위
- fleet-level summary
- 모델/데이터 적용 범위와 불확실성

## 2. Result Before Dashboard

Dashboard와 Generative AI가 model implementation을 직접 소비하지 않도록 향후 공통 `PHMResult` 경계를
둡니다. 구체적 schema는 실제 inference 요구가 확인된 뒤 정의하지만, UX 관점에서는 다음 정보 범주가
필요한지 검토합니다.

```text
Identity
- asset
- observation time

Assessment
- status
- anomaly score / threshold
- health index / trend
- RUL 또는 capability unavailable

Evidence
- supporting observations
- data quality
- applicable operating context

Provenance
- model/artifact version
- preprocessing/config revision
- dataset/source lineage

Decision support
- interpretation
- possible causes
- recommended inspection or maintenance action
```

모든 capability가 항상 존재한다고 가정하지 않습니다. RUL이나 label이 지원되지 않는 경우 이를 임의의 값으로
대체하지 않고 명시적으로 unavailable 상태로 표현합니다.

## 3. Human and AI Responsibilities

수치 계산과 PHM 판단의 source of truth는 deterministic PHM pipeline입니다. Generative AI는 구조화된 결과와
retrieved maintenance knowledge를 사용해 설명·가설 정리·권고 초안·보고서를 생성합니다.

UI는 사실, 모델 추정, 가설, 권고가 같은 시각적 수준에서 섞이지 않도록 구분해야 합니다. 특히 정비 조치가
실제 work order나 설비 제어로 이어지는 경우 승인 boundary를 별도로 둡니다.

## 4. CLI Is Also UX

현재 단계에서 가장 먼저 사용되는 제품 인터페이스는 CLI일 가능성이 높습니다. 따라서 CLI도 다음 UX 기준을
적용합니다.

- 명령과 option 이름이 일관적일 것
- 실패 이유와 다음 조치를 설명할 것
- 데이터가 어디에 저장되었는지 보여줄 것
- effective source/version/provenance를 확인할 수 있을 것
- destructive 또는 network-heavy 동작은 명시적으로 실행할 것

## 5. UI Implementation Timing

지금 할 일:

- 역할과 정보 요구 검증
- PHM Result에 필요한 정보 범주 정의
- low-fidelity information architecture 검토
- CLI workflow 설계

나중에 할 일:

- Dashboard framework 선택
- API schema 고정
- 시각화 library 선택
- 권한/인증/조직별 화면 구현

UI implementation을 늦춘다는 것은 UX를 늦춘다는 뜻이 아닙니다. 실제 모델·결과 계약이 안정되기 전에 특정
frontend 구조가 backend contract를 고정하는 상황을 피합니다.

## Reference

- ISO 9241-210 human-centred design overview: https://www.iso.org/standard/77520.html
