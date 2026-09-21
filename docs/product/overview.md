# Product and UX Baseline

이 문서는 PHM 결과가 실제 사용자에게 어떤 가치와 정보 구조로 전달되어야 하는지 정리하는 제품 기준선입니다.
초기 low-fidelity UX 단계에서는 UI framework 선택을 미뤘지만, 현재는 이미 검증된 분석·evidence 계층을
**end-to-end Analysis Application**으로 연결하면서 analysis contract와 사용자 화면을 함께 검증합니다.

Frontend/API 기술을 먼저 고정하지 않는 원칙은 유지하되, UI 구현 자체를 미래 단계로 미루지는 않습니다.
프로젝트 공통 용어는 [`../terminology.md`](../terminology.md)를 따릅니다.

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
  -> Sequence Construction (sequence model only)
  -> Sampling
  -> Model Fit
  -> Model Scoring
  -> Evaluation
  -> Result
```

이 목록은 새로운 `GenericPipeline` runtime이나 orchestration framework를 뜻하지 않습니다. 실제 실행 책임은
현재처럼 dataset-specific experiment edge와 dataset-neutral contract가 나눠 소유합니다. 여기서는 이미
존재하는 contract/provenance를 **사람이 같은 방식으로 검토하기 위한 information architecture**만 정의합니다.

`Sequence Construction`은 acquisition-level feature row를 직접 소비하는 모델에는 `not applicable`이며, LSTM
Autoencoder처럼 window를 소비하는 모델에서만 표시합니다. 이 stage는 window length/stride/input shape,
asset·partition boundary, input acquisition 수, generated window 수, dropped prefix와 score alignment를
보존합니다. 첫 구체적 계약은
[`../research/xjtu-lstm-autoencoder-protocol.md`](../research/xjtu-lstm-autoencoder-protocol.md)가 소유합니다.

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
- `not applicable`: 해당 model/protocol에는 stage가 적용되지 않으며 stage output을 추론하거나 생성하지 않음
- `failed`: 실행 또는 validation이 실패함
- `blocked`: 선행 contract/source 문제로 실행할 수 없음
- `excluded`: protocol/config에서 의도적으로 범위에서 제외됨
- `unsupported`: 현재 구현이 해당 capability를 제공하지 않음
- `consumed`: one-shot holdout처럼 이미 의사결정상 재사용하면 안 되는 evaluation scope

이 vocabulary 역시 persistent workflow state machine을 새로 만들자는 요구가 아닙니다. 현재 artifact/config와
protocol 상태를 UI/CLI에서 일관되게 설명하기 위한 표현 기준입니다.

### Evidence availability vocabulary

Pipeline stage 상태와 artifact가 보존한 evidence의 상세 수준을 분리합니다.

- `available`: artifact가 해당 detailed evidence와 provenance를 직접 보존함
- `not recorded`: artifact가 해당 detailed evidence를 보존하지 않으며 aggregate에서 이를 추론하거나 생성하지 않음

`not recorded`는 stage 실패나 capability `unsupported`를 뜻하지 않습니다. 예를 들어 Isolation Forest result는
anomaly scoring과 aggregate temporal evaluation을 제공하지만 acquisition-aligned raw trajectory와 per-feature
residual을 기록하지 않을 수 있습니다.

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
표현이 달라, schema별 result reader가 같은 stage 순서의 immutable inspection read model을 만들고 CLI가 이를
text로 표현합니다.

## 3. Developer Workbench low-fidelity baseline

Developer Workbench의 첫 대상은 운영 설비 dashboard가 아니라 version-controlled experiment evidence를 검토하는
PHM/ML 개발자와 연구자입니다. 기존 `ExperimentInspection` read model을 아래 세 view가 함께 소비하며, view별
persistent state나 별도 pipeline schema를 만들지 않습니다.

```text
Developer Workbench
├─ Experiment Overview
├─ Pipeline Lineage
└─ Evidence Explorer
```

세 view는 동일한 experiment identity와 현재 선택한 pipeline stage/evidence scope를 공유합니다. 사용자는 overview에서
실험 전체를 확인하고, lineage에서 population과 변환 경계를 추적한 뒤, evidence에서 수치 근거를 검토하고 원래
artifact/provenance로 돌아갈 수 있어야 합니다.

### Experiment Overview

한 experiment가 무엇을 실행했고 현재 어떤 의미로 사용할 수 있는지 먼저 보여줍니다.

```text
Experiment / status / capability
Effective configuration
Population summary
Evaluation summary
Warnings and excluded scope
Provenance
```

Acceptance criteria:

- artifact를 직접 열지 않아도 dataset/source scope, split·partition, model family와 random seed를 식별할 수 있습니다.
- complete/reference/model-fit/scoring population의 값과 단위를 함께 확인할 수 있습니다.
- pipeline stage의 `completed`, `not applicable`, `excluded`, `consumed` 상태가 numerical result와 분리되어
  보입니다.
- detailed evidence의 `available`과 `not recorded`가 capability 의미와 분리되어 보입니다.
- capability의 `available`과 `unsupported`가 evidence availability와 분리되어 보입니다.
- evaluation statistic과 aggregation rule을 함께 표시해 평균값의 계산 단위를 확인할 수 있습니다.
- artifact path, configuration identity와 declared code revision으로 원본 provenance를 추적할 수 있습니다.

### Pipeline Lineage

Source부터 Provenance까지 ordered stage를 따라 input, operation과 output의 변화를 보여줍니다. 각 stage는 앞서 정의한
Status, Input, Operation, Output, Configuration, Provenance, Validation, Warnings vocabulary를 사용합니다.

Sequence model에서는 acquisition과 window를 같은 population 단위처럼 합산하지 않고 unit transition을 명시합니다.

```text
Reference Selection
  1,084 acquisitions
        |
        | length 8 / stride 1 / asset boundary preserved
        v
Sequence Construction
  1,021 windows / 63 dropped prefix acquisitions
        |
        v
Model Fit
  1,021 windows
```

Acceptance criteria:

- 인접 stage마다 input/output population value와 unit이 보존되어 acquisition, sample, feature row와 window를 구분합니다.
- Sequence Construction은 window length, stride, alignment, feature width, generated window 수와 dropped prefix를
  표시합니다.
- window가 asset·partition·reference boundary를 넘지 않았다는 validation 결과를 확인할 수 있습니다.
- 선택한 stage의 effective configuration, validation과 warning을 다른 stage의 사실과 섞지 않고 검토할 수 있습니다.
- 해당 모델에 적용되지 않는 stage는 생략하지 않고 `not applicable`로 표현합니다.

### Evidence Explorer

Validated result가 실제로 제공하는 model/evaluation evidence를 population scope와 함께 탐색합니다. 첫 sequence-model
consumer에서는 acquisition-aligned reconstruction score trajectory, lifecycle retrospective statistic과 per-feature
residual을 다룹니다.

Acceptance criteria:

- score의 방향, alignment target, population unit과 evaluation scope를 plot/table 가까이에 표시합니다.
- bearing 또는 asset을 선택하면 해당 trajectory와 bearing-first statistic이 같은 selection context를 사용합니다.
- per-feature residual은 robust-scaled feature space의 model evidence로 표시하고 physical fault contribution으로
  이름을 바꾸지 않습니다.
- threshold가 없는 result는 threshold line이나 normal/fault state를 만들지 않고 capability를 `unsupported`로
  표시합니다.
- displayed aggregate에서 source observation 또는 raw artifact까지 provenance를 따라갈 수 있습니다.

### Prototype 진입 기준

첫 interactive prototype은 LSTM result schema와 `ExperimentInspection` reader가 실제 Sequence Construction 및
reconstruction evidence를 제공한 뒤 시작합니다. Prototype은 위 세 view의 navigation과 정보 이해도를 검증하며,
frontend framework, API schema, authentication 또는 persistent workflow state를 선택하는 단계가 아닙니다.

다음 질문을 representative XJTU와 IMS artifact로 답할 수 있으면 low-fidelity baseline을 충족한 것으로 봅니다.

- 무엇을 어떤 data scope와 configuration으로 실행했는가?
- 어느 stage에서 population의 값 또는 단위가 바뀌었는가?
- model이 실제로 fit/scoring한 population은 무엇인가?
- 현재 result가 제공하는 evidence와 제공하지 않는 PHM capability는 무엇인가?
- 표시된 수치를 어떤 artifact, config와 code revision까지 추적할 수 있는가?

Cross-schema low-fidelity implementation은 `notebooks/02_developer_workbench.py`에 있습니다. Version-controlled XJTU
Isolation Forest holdout, IMS Isolation Forest cross-test와 XJTU LSTM development artifact를 각각 schema-specific
reader로 검증하고 같은 `ExperimentInspection` stage vocabulary로 표시합니다. Acquisition-level model은 Sequence
Construction을 `not applicable`로, raw trajectory/residual을 보존하지 않은 result는 detailed evidence를
`not recorded`로 표현합니다. 이 implementation은 navigation, population unit, evidence availability와 provenance
이해도를 검토하기 위한 research-tooling interface이며 frontend/API/persistent state 결정을 만들지 않습니다.

## 4. Maintenance Evidence Review low-fidelity baseline

Developer Workbench가 PHM/ML 개발자의 pipeline transparency를 검증했다면, 두 번째 role-specific prototype은
정비 엔지니어가 **기록된 anomaly evidence를 과도하게 해석하지 않고 이해할 수 있는지**를 확인합니다.

현재 대표 consumer는 `notebooks/03_maintenance_evidence_review.py`이며 XJTU LSTM development artifact의
acquisition-aligned reconstruction score와 per-feature residual을 재계산하지 않고 그대로 소비합니다. 이 화면은
운영 dashboard가 아니라 retrospective experiment evidence를 정비 역할의 정보 밀도로 다시 배치한
research-tooling interface입니다.

```text
Maintenance Evidence Review
├─ Evidence Summary
├─ Trend & Observations
└─ Limits & Provenance
```

### Evidence Summary

정비 사용자가 첫 화면에서 확인해야 하는 것은 "고장인가?"가 아니라 **무슨 evidence가 기록되어 있고 어디까지
해석 가능한가**입니다.

- 선택한 bearing/evidence scope
- score window 수와 score 방향
- acquisition-order association과 late-vs-middle retrospective statistic
- 현재 evidence가 지원하는 검토 질문
- threshold/state/diagnosis/priority/RUL이 지원되지 않는다는 제한
- experiment warning과 artifact provenance

`consumed`, `unsupported`, `not recorded` 같은 기존 vocabulary를 역할별 화면에서 다른 의미로 바꾸지 않습니다.

### Trend & Observations

Trajectory와 high-score observation을 보여주되 threshold line, normal/fault state, alarm level을 만들지 않습니다.
Per-feature reconstruction residual은 robust-scaled model space의 mismatch evidence로 표시하고 physical fault
contribution이나 root-cause attribution으로 이름을 바꾸지 않습니다.

### Limits & Provenance

사용자는 최소한 다음을 확인할 수 있어야 합니다.

- 이 결과가 retrospective development evidence인지 operational inference인지
- thresholded state detection, diagnosis, health assessment, RUL 중 무엇이 unsupported인지
- 어떤 evaluation scope와 code/artifact provenance에서 수치가 나왔는지
- 화면이 제공하지 않는 의미를 어디에서도 추론해 생성하지 않았는지

Acceptance criteria:

- 사용자가 선택한 evidence scope와 score semantics를 artifact JSON을 직접 열지 않고 식별할 수 있습니다.
- anomaly evidence와 fault diagnosis가 다른 capability라는 점이 화면에서 즉시 보입니다.
- threshold가 없는 experiment에서 alarm/state/maintenance priority를 생성하지 않습니다.
- feature residual을 causal fault contribution으로 표현하지 않습니다.
- displayed evidence에서 repository artifact와 declared code revision으로 돌아갈 수 있습니다.
- role-specific presentation을 위해 별도 result storage, duplicated numerical state 또는 `PHMResult` schema를
  만들지 않습니다.
- frontend framework, API, authentication과 work-order action은 이 prototype의 결정 범위가 아닙니다.

## 5. Experiment evidence와 operational result 경계

현재 repository의 authoritative result는 주로 **experiment evidence**입니다. 이는 dataset/split, fit/reference
population, model configuration, retrospective/fixed evaluation과 code revision을 설명하기 위한 artifact입니다.

향후 운영 UI가 소비할 **operational result**는 다른 질문을 가져야 합니다.

```text
Experiment evidence                 Future operational result
-------------------------------     --------------------------------
dataset / source scope              physical asset / measurement point
split / partition                   observation time
fit/reference/scoring population    inference input and data quality
experiment configuration            deployed model/config identity
evaluation statistic                validated score/state semantics
consumed/excluded scope             availability/out-of-scope state
code/artifact provenance            deployment/inference provenance
```

Experiment artifact에서 observation time, validated alarm state, maintenance priority 또는 current asset health를
추론해 operational field로 만들지 않습니다. 반대로 향후 operational result가 생겨도 experiment split이나
development statistic을 억지로 항상 포함시키지 않습니다.


### Analysis Application read model

현재 Analysis Application을 만들기 위해 full operational result contract가 먼저 완성될 때까지 기다리지 않습니다.
이미 검증된 experiment/analysis output을 사용자에게 보여주기 위한 **presentation-oriented read model**을 둘 수
있습니다. 이 read model은 새로운 numerical Source of Truth나 universal `PHMResult`가 아니며, 기존 result와
evidence를 재계산하거나 의미를 승격하지 않습니다.

초기 범주는 다음과 같습니다.

```text
Identity / data summary
Analysis summary
Sensor or feature trajectory
Anomaly score trajectory
Anomaly interval (validated threshold policy가 있는 경우)
Supporting evidence
Capability / limitation
Provenance
Generative AI explanation context
```

RUL/prognostics가 구현되면 같은 read model에 지원 가능한 capability로 추가합니다. 해당 source나 model이 RUL을
지원하지 않으면 임의 값을 만들지 않고 unavailable로 유지합니다. 이 경계의 목적은 experiment artifact의 내부
schema를 UI가 직접 해석하게 만들지 않으면서도, field source나 live inference가 오기 전부터 완결된 분석 경험을
제공하는 것입니다.

Operational schema의 이름과 구체적인 public type은 아직 고정하지 않습니다. 첫 실제 inference workflow 또는
private/field source에서 identity, time, data quality, threshold/state semantics와 deployment provenance가 실제로
필요해지는 시점에 contract를 정의합니다. 그 전까지 `ExperimentInspection`을 operational result로 확장하거나
범용 `PHMResult`를 선제적으로 만들지 않습니다.

UX 관점에서 향후 operational boundary에서 검토할 정보 범주는 다음과 같습니다.

```text
Identity
- asset / measurement point
- observation time

Assessment
- validated score / state semantics
- threshold, health indicator, RUL 또는 capability unavailable

Evidence
- supporting observations
- data quality
- applicable operating context

Explanation (optional)
- feature/channel/time contribution
- reconstruction residual 또는 모델 고유 설명 근거
- explanation method / scope

Uncertainty (optional)
- confidence / interval / calibration information
- unsupported 또는 out-of-scope 상태

Provenance
- deployed model/artifact version
- preprocessing/config revision
- source/inference lineage

Decision support (optional)
- interpretation
- possible causes
- recommended inspection or maintenance action
```

모든 capability가 항상 존재한다고 가정하지 않습니다. RUL, health indicator, uncertainty, explanation이 지원되지
않는 경우 임의의 값이나 그럴듯한 설명으로 채우지 않고 명시적으로 unavailable 상태로 표현합니다.

## 6. 사람·AI·XAI의 책임

수치 계산과 PHM 판단의 source of truth는 deterministic PHM pipeline입니다. Generative AI는 구조화된 결과와
retrieved maintenance knowledge를 사용해 설명·가설 정리·권고 초안·보고서를 생성합니다.

XAI는 별도의 만능 계층으로 두지 않습니다. 모델마다 설명 가능한 근거의 성격이 다르기 때문입니다. 예를 들어
feature 기반 모델은 feature-level contribution이나 sensitivity를 제공할 수 있고, reconstruction 기반 모델은
채널·시간·window별 residual 자체가 중요한 설명 근거가 될 수 있습니다. RUL과 같은 prognostics에서는 feature
attribution뿐 아니라 degradation trajectory, uncertainty, calibration이 판단에 더 직접적인 근거가 될 수 있습니다.

따라서 초기 원칙은 다음과 같습니다.

- 모델은 가능하면 자신의 수치 출력과 함께 검증 가능한 evidence/explanation artifact를 생성합니다.
- 향후 operational result boundary는 explanation을 optional capability로 수용할 수 있어야 합니다.
- 설명 방법을 하나의 SHAP/LIME 인터페이스로 성급하게 표준화하지 않습니다.
- GenAI는 모델 score만 보고 원인을 만들어내지 않고, 전달된 evidence와 retrieved knowledge의 범위 안에서만 설명합니다.
- 설명이 제공되지 않거나 신뢰할 수 없는 경우 그 한계를 사용자에게 그대로 보여줍니다.

UI는 사실, 모델 추정, 모델 설명 근거, 원인 가설, 정비 권고가 같은 시각적 수준에서 섞이지 않도록 구분해야
합니다. 특히 정비 조치가 실제 work order나 설비 제어로 이어지는 경우 승인 boundary를 별도로 둡니다.

## 7. CLI도 UX

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

Schema-specific reader는 immutable `ExperimentInspection` read model을 만들고 CLI renderer가 이를 text로
표현합니다. 이 경계는 inspection semantics를 presentation에서 분리해 이후 developer UI/API가 같은 lineage를
소비할 수 있게 하며, operational model output을 위한 `PHMResult` 책임과는 구분됩니다.

## 8. End-to-End Analysis Application 전환

현재 단계에서는 UI implementation을 더 이상 별도 미래 작업으로 두지 않습니다. 이미 존재하는 production
validator, Adapter, feature/sequence, model, result artifact와 inspection을 재사용해 다음 vertical slice를
실제로 연결합니다.

```text
데이터 선택
  -> validation
  -> Python PHM analysis
  -> score / trend / capability
  -> anomaly interval and evidence
  -> visualization
  -> Generative AI explanation / Q&A
  -> transparency drill-down
```

현재 구현 범위:

- analysis use case와 presentation read model
- sensor/feature trajectory와 anomaly score의 동일 context 시각화
- validated threshold policy가 존재할 때 contiguous anomaly interval 표시
- 선택한 interval 또는 analysis scope의 supporting evidence 표시
- 구조화된 evidence만 소비하는 Generative AI 설명과 analysis-scoped Q&A
- `ExperimentInspection`과 기존 Workbench의 pipeline/provenance를 상세 보기로 재사용
- capability unavailable 상태를 정상적인 제품 상태로 표시

이 vertical slice를 위해 frontend framework, service API, authentication 또는 persistent workflow engine을 먼저
고정할 필요는 없습니다. 첫 사용자 surface는 현재 project dependency와 evidence ownership 원칙을 지키는 가장
작은 구현으로 시작하고, 실제 사용 요구가 생길 때 presentation 기술을 교체하거나 확장할 수 있어야 합니다.

후속 확장:

- XJTU run-to-failure data에서 검증된 RUL/prognostics capability와 uncertainty를 같은 화면에 추가
- analysis bundle과 report/export
- local/general sensor input
- private/field source와 live inference
- 역할별 operational view, work-order integration과 조직/권한 기능
- 정비 지식 retrieval이 실제 설명 품질에 필요할 때 Generative AI RAG 확장

완성의 기준은 모든 PHM capability를 동시에 제공하는 것이 아닙니다. 사용 가능한 capability를 끝까지 연결해
사용자가 결과, evidence, limitation과 분석 과정을 이해할 수 있으면 하나의 완결된 시스템으로 취급하고, 이후
RUL·diagnosis·새 모델·새 source를 같은 시스템 안에서 확장합니다.

## References

- ISO 9241-210 human-centred design overview: https://www.iso.org/standard/77520.html
- Human-in-the-Loop XAI for Predictive Maintenance (2025): https://doi.org/10.3390/electronics14173384
- Data-driven prognostics review: uncertainty, robustness, interpretability and feasibility (2025): https://doi.org/10.1016/j.ymssp.2025.113015
