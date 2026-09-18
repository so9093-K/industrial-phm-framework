# Product and UX Baseline

이 문서는 Dashboard 구현보다 먼저 사용자 역할과 정보 소비 구조를 정리합니다. UI framework나 화면 디자인을
고정하기 위한 문서가 아니라, PHM 결과가 실제 의사결정에서 어떤 정보로 소비되어야 하는지 확인하기 위한
초기 기준선입니다. 프로젝트 공통 용어는 [`../terminology.md`](../terminology.md)를 따릅니다.

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

### PHM/ML 개발자·연구자

현재 pre-alpha 단계의 직접 사용자는 pipeline을 구현·검토하고 experiment evidence를 해석하는
PHM/ML 개발자와 연구자입니다. 이 역할에는 최종 anomaly score만큼 **어떤 변환과 population 경계를 거쳐
그 결과가 만들어졌는지**가 중요합니다.

- effective dataset/source, split/partition과 source scope
- canonical channel/schema와 feature 생성·선택 결과
- preprocessing fit scope와 실제 fitted state
- complete source → reference-eligible → model-fit → scoring population 변화
- effective model family/parameter/random seed와 score 방향
- evaluation statistic, aggregation, 사용하지 않은 capability
- artifact/config/code revision을 연결하는 provenance
- leakage, excluded scope, unsupported capability, consumed holdout 같은 경고 상태

## 2. Developer Pipeline Transparency

개발자 UX에서 가장 먼저 투명해야 하는 것은 model explainability가 아니라 **pipeline lineage**입니다. 같은
numerical score라도 source, feature schema, preprocessing fit population, reference rule, sampling, scoring
partition이 다르면 의미가 달라집니다. 따라서 개발자용 CLI·interactive view·향후 UI는 아래 단계를 하나의
추적 가능한 흐름으로 보여줄 수 있어야 합니다.

```text
Source
  -> Canonicalization
  -> Feature Extraction
  -> Preprocessing
  -> Reference Selection
  -> Sampling
  -> Model Fit
  -> Model Scoring
  -> Evaluation
  -> Result
```

이 목록은 새로운 `GenericPipeline` runtime이나 orchestration framework를 뜻하지 않습니다. 실제 실행 책임은
현재처럼 dataset-specific experiment edge와 dataset-neutral contract가 나눠 소유합니다. 여기서는 이미
존재하는 contract/provenance를 **사람이 같은 방식으로 검토하기 위한 information architecture**만 정의합니다.

### 단계별 표시 계약

각 단계는 가능한 범위에서 다음 항목을 같은 순서로 보여줍니다.

| 항목 | 개발자가 확인할 질문 |
| --- | --- |
| Status | 실행 가능한가, 완료됐는가, 실패/차단/제외됐는가? |
| Input | 몇 개 observation, 어떤 schema/partition이 들어왔는가? |
| Operation | 실제로 어떤 변환·선택·fit·score가 수행됐는가? |
| Output | observation/schema가 어떻게 바뀌었는가? |
| Configuration | 어떤 versioned setting이 유효했는가? |
| Provenance | source/config/code revision을 어디까지 추적할 수 있는가? |
| Validation | 어떤 invariant를 확인했고 무엇이 PASS/FAIL인가? |
| Warnings | leakage 위험, excluded scope, unsupported capability가 있는가? |

모든 단계가 모든 항목을 억지로 채울 필요는 없습니다. 예를 들어 stateless feature extraction에는 fitted state가
없고 identity scaling에는 learned center/scale이 실질적으로 없습니다. 없는 정보를 추정해서 채우지 않고
`not applicable` 또는 해당 capability가 없음을 명시합니다.

### Pipeline stage 상태 vocabulary

초기 표시 vocabulary는 아래 정도로 제한합니다.

- `not-started`: 아직 실행하지 않음
- `ready`: 필요한 선행 조건이 충족됨
- `completed`: 해당 단계의 contract와 output이 정상적으로 생성됨
- `failed`: 실행 또는 validation이 실패함
- `blocked`: 선행 contract/source 문제로 실행할 수 없음
- `excluded`: protocol/config에서 의도적으로 범위에서 제외됨
- `unsupported`: 현재 구현이 해당 capability를 제공하지 않음
- `consumed`: one-shot holdout처럼 이미 의사결정상 재사용하면 안 되는 evaluation scope

이 vocabulary 역시 persistent workflow state machine을 새로 만들자는 요구가 아닙니다. 현재 artifact/config와
protocol 상태를 UI/CLI에서 일관되게 설명하기 위한 표현 기준입니다.

### Population flow는 first-class evidence

특히 model fitting 전후의 population 변화는 별도 설명 없이도 볼 수 있어야 합니다.

```text
complete configured source
        |
        | fit preprocessing state on configured fit scope
        | transform complete source with fitted state
        v
transformed complete source
        |
        | reference eligibility
        v
reference-eligible population
        |
        | sampling / weighting
        v
actual model-fit population

scoring source
        |
        | transform with the same fitted preprocessing state
        v
scoring population --------------------> model scoring
```

현재 `ModelFitInput`의 `source_observation_count`, `reference_observation_count`,
`fit_observation_count`처럼 이미 존재하는 contract를 이 표시의 Source of Truth로 사용합니다. UI를 위해
동일 숫자를 별도 상태 저장소에 복제하지 않습니다.

예를 들어 XJTU early-third reference와 IMS all-train reference는 다음처럼 차이가 즉시 보여야 합니다.

```text
XJTU:  complete 3,246 -> reference 1,084 -> fit 1,084
IMS:   complete 3,936 -> reference 3,936 -> fit 3,936
```

### Effective configuration과 schema

실행 전에는 source와 model parameter만 보여주는 것이 아니라 아래 effective configuration을 한 묶음으로
검토할 수 있어야 합니다.

- dataset / source scope / split / partition
- input channels와 `feature_set_id`
- generated feature 수, selected feature 이름과 수
- preprocessing strategy와 fit partition
- reference strategy와 sampling policy
- model family / effective parameter / random seed
- score 방향, 예: higher-is-more-anomalous
- evaluation statistic과 aggregation rule
- explicitly excluded source/partition/capability

Feature formula가 같아도 channel-derived schema가 다를 수 있으므로 `feature_set_id`와 exact
`feature_names`를 구분해서 보여줍니다.

### 실행 전 plan과 실행 후 summary

위험하거나 one-time 의미가 있는 experiment는 실행 전에 최소한의 effective plan을 보여줄 수 있어야 합니다.

```text
Train        Set 2 / 3,936 observations
Evaluation   Set 3 README-documented / 17,792 observations
Feature      vibration-statistical-v1 / 8 selected
Reference    all-train-observations
Model        isolation-forest / seed 42

Excluded
- Set 1
- Set 3 archive-extension

No candidate selection or threshold calibration will be performed.
```

실행 후에는 단순히 result path만 출력하지 않고 source validation, feature/preprocessing/model/scoring/evaluation
완료 여부와 artifact/code revision을 요약할 수 있어야 합니다. 세부 fitted state나 observation-level table은
필요할 때 drill-down합니다.

### Result drill-down과 capability boundary

개발자 결과 UX의 기본 순서는 다음과 같습니다.

```text
Summary
  -> Pipeline / Population Flow
  -> Effective Configuration
  -> Evaluation Evidence
  -> Data & Model Scope
  -> Provenance
  -> Raw Artifact
```

또한 현재 결과가 실제로 지원하는 capability와 지원하지 않는 capability를 함께 보여줍니다. 예를 들어 anomaly
score와 retrospective temporal statistic만 존재한다면 이를 health assessment나 prognostics로 승격해서
표시하지 않습니다.

```text
available
- anomaly scoring
- descriptive score-trajectory evaluation

unsupported / not validated
- thresholded state detection
- health assessment
- fault diagnostics
- prognostics / RUL
```

### Pipeline transparency와 model explainability의 분리

Pipeline transparency는 "어떤 데이터와 변환·설정으로 이 score가 만들어졌는가"를 설명합니다.
Model explainability는 "왜 이 observation의 score가 높았는가"를 설명합니다. 둘은 별도 책임입니다.

현재 우선순위는 pipeline transparency입니다. 모델별 feature contribution, residual attribution 같은 XAI는
실제 model-specific evidence가 생겼을 때 추가하고, pipeline provenance 부족을 XAI로 대체하지 않습니다.

XJTU finalized holdout과 IMS fixed cross-test를 이 information architecture로 대조한 결과는
[`../research/xjtu-ims-pipeline-transparency-review.md`](../research/xjtu-ims-pipeline-transparency-review.md)에
기록합니다. 두 실행은 공통 계산 계약을 재사용하지만 result schema의 정보 배치와 source-to-canonical cardinality
표현이 달라, 다음 developer UX는 schema별 result reader가 같은 stage 순서의 read-only summary를 제공하는 범위로
좁힙니다.

## 3. 대시보드 전에 PHM 결과 계약부터

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
- health indicator / trend
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

모든 capability가 항상 존재한다고 가정하지 않습니다. RUL, health indicator, uncertainty, explanation이 지원되지
않는 경우 임의의 값이나 그럴듯한 설명으로 채우지 않고 명시적으로 unavailable 상태로 표현합니다.

## 4. 사람·AI·XAI의 책임

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

## 5. CLI도 UX

현재 단계에서 가장 먼저 사용되는 제품 인터페이스는 CLI일 가능성이 높습니다. 따라서 CLI도 다음 UX 기준을
적용합니다.

- 명령과 option 이름이 일관적일 것
- 실패 이유와 다음 조치를 설명할 것
- 데이터가 어디에 저장되었는지 보여줄 것
- effective source/version/provenance를 확인할 수 있을 것
- destructive 또는 network-heavy 동작은 명시적으로 실행할 것

현재 `experiment inspect <result.json>`은 XJTU finalized holdout와 IMS fixed cross-test result를 schema별로
검증하고, source acquisition과 canonical/model observation 단위, effective configuration, population flow,
capability와 declared provenance를 같은 stage 순서로 표시합니다. one-time evaluation scope는 `consumed`, 현재
제공하지 않는 PHM 기능은 `unsupported`로 표현합니다.

## 6. UI 구현 시점

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
