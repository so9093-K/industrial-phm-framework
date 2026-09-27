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

XJTU finalized holdout과 IMS fixed cross-test에서 확인한 공통 presentation 책임은 현재
`ExperimentInspection`의 ordered stage vocabulary와 schema-specific reader에 반영되어 있습니다. 두 실행은 공통
계산 계약을 재사용하지만 result schema의 정보 배치와 source-to-canonical cardinality 표현은 계속 다르므로,
저장 schema를 통합하지 않고 각 reader가 같은 immutable inspection read model을 만든 뒤 CLI와 interactive
surface가 이를 소비합니다. Canonical artifact와 human-review representation의 운영 경계는
[`../research/evidence-artifact-policy.md`](../research/evidence-artifact-policy.md)를 따릅니다.

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

## 4. Experiment evidence와 operational result 경계

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

현재 loading boundary는 `AnalysisSurface`와 optional `AnalysisView`로 나뉩니다.

```text
versioned artifact
  -> ExperimentInspection
  -> AnalysisSurface
       ├ artifact identity / inspection
       └ AnalysisView?  # detailed projector가 있을 때만
```

`ExperimentInspection`은 supported schema의 pipeline stage, capability, provenance를 검증합니다.
`AnalysisSurface`는 이 inspection을 항상 보존하며, artifact가 실제로 detailed evidence를 기록하고 해당
schema projector가 있을 때만 `AnalysisView`를 붙입니다. detailed projector가 없다는 이유로 aggregate
artifact를 observation-level trajectory처럼 재구성하지 않습니다.

`AnalysisView`가 제공하는 초기 범주는 다음과 같습니다.

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

RUL/prognostics는 `AnalysisView`의 optional capability로 구현되어 있습니다. Compatible한 prognostics artifact가
있을 때만 attached evidence로 구성하고, 해당 source나 artifact가 RUL을 지원하지 않으면 임의 값을 만들지 않고
unavailable로 유지합니다. 반면 IMS/MIMII처럼 inspection은 가능하지만 detailed projector가 없는 artifact는
같은 Explorer에서 inspection-only surface로 pipeline/capability/provenance까지만 표시합니다.

Prepared field CSV validation에서 이미 반복해서 필요한 첫 application-level 관측 read model은
AssetObservationSummary로 분리합니다. 이 read model은 asset_id, explicit source_id, optional
measurement_point_id, observation time range, channel/sample population과 aggregate data-quality state만
보존합니다. 이는 current asset health나 operational PHM result가 아니며 anomaly/state/diagnosis/RUL 의미를
추가하지 않습니다.

첫 stronger operational contract로 `AnalysisRun`과 `OperationalFinding`을 application layer에 추가했습니다.

`AnalysisRun`은 다음 실행/provenance 사실만 보존합니다.

- analysis run ID, asset/source/optional measurement-point identity
- timezone-aware observation start/end와 execution start/end
- aggregate `DataQualityAssessment`
- optional model deployment identity
- exact prepared source snapshot evidence
- 해당 run이 실제로 생성한 capability ID 목록

`OperationalFinding`은 state-like finding의 공통 envelope이며 finding/run/asset/measurement-point identity,
observation time, capability ID, versioned finding-semantics ID, opaque state와 evidence reference만 보존합니다.
Generic finding에 score, threshold, severity, diagnosis payload, RUL 또는 maintenance priority를 넣지 않습니다.
Finding과 run의 identity/measurement-point/observation-window linkage와 capability declaration 일치는 별도 validator로
fail-fast 검증합니다. `OperationalFinding.observed_at`도 operational absolute time이므로 timezone-aware datetime만
허용합니다.

현재 field analysis producer는 아직 없습니다. 따라서 contract가 존재한다는 이유만으로 Operations가 finding을
표시하지 않으며, 실제 source-appropriate analysis protocol이 이 contract를 생성할 때까지
`Not connected`/`Unavailable` 상태를 유지합니다. Prognostics는 별도 capability type으로 다룰 예정이며
field RUL semantics가 검증되기 전에 `OperationalPrognosticEstimate`를 선제 구현하지 않습니다.

`ExperimentInspection`을 operational result로 확장하거나 범용 `PHMResult`를 만들지 않는 원칙은 그대로
유지합니다.

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

## 5. 사람·AI·XAI의 책임

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

## 6. CLI도 UX

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

## 7. End-to-End Analysis Application 현재 상태

첫 vertical slice는 현재 구현되어 있습니다. XJTU LSTM retrospective path를 기준으로 prepared source에서 기존
production analysis runner를 실행하고, 생성 artifact를 inspection과 detailed projection 경계를 거쳐 같은 사용자
화면에서 결과·evidence·AI 설명·pipeline transparency로 이어서 검토할 수 있습니다.

```text
prepared XJTU source
  -> validation / Adapter / feature / preprocessing / sequence
  -> frozen LSTM fit / scoring / evaluation
  -> evidence artifact
  -> ExperimentInspection
  -> AnalysisSurface
  -> XJTU detailed projector / AnalysisView
  -> anomaly-evidence trajectory
  -> descriptive score-exceedance interval
  -> human review acknowledgement / note (artifact/asset/policy-scoped durable local state)
  -> supporting residual evidence
  -> Generative AI explanation / Q&A
  -> pipeline / provenance drill-down
```

현재 구현 범위:

- prepared XJTU source에서 analysis를 명시적으로 실행하는 application use case
- experiment JSON을 UI가 직접 해석하지 않게 하는 `AnalysisSurface` / `AnalysisView` loading boundary
- acquisition-aligned score trajectory와 model-space feature residual evidence 시각화
- earliest-third scored-window q95를 사용한 retrospective **descriptive review threshold**
- threshold 초과 acquisition-contiguous observation을 score-exceedance interval로 표시
- review threshold/interval을 validated normal/fault State Detection, alarm, diagnosis와 명시적으로 분리
- review interval이 있으면 사용자가 note와 acknowledgement를 남기는 durable local human-review action. exact artifact SHA-256 + asset + review-policy identity로 재시작 이후 복원하되 이 상태를 `OperationalFinding`이나 maintenance case/work order로 승격하지 않음
- bounded structured evidence만 소비하는 Generative AI 설명과 analysis-scoped Q&A
- `ExperimentInspection`의 pipeline/provenance를 Analysis Details drill-down으로 재사용
- unavailable capability를 임의 값으로 채우지 않는 명시적 capability boundary
- 동일 Explorer shell을 XJTU detailed artifact와 IMS/MIMII inspection-only artifact에 대해 CI export로 검증
- prepared single-asset CSV export를 명시적 channel/time mapping으로 검증하고 canonical vibration feature 경계까지 연결하는 field-input baseline
- validated field CSV의 asset/source/measurement-point/time/channel/data-quality 사실을 AssetObservationSummary application read model로 투영하는 operational observation baseline

따라서 첫 vertical slice의 완성 조건인 **분석 실행 → 변화 구간 확인 → evidence 시각화 → AI 설명 →
분석 과정 확인**은 충족합니다. 이 상태를 유지한 채 새로운 PHM capability를 같은 application에 추가합니다.

현재 RUL/prognostics vertical slice는 development evidence 기준으로 application까지 연결되어 있습니다.

- XJTU run-to-failure data의 RUL target/split/evaluation semantics 고정
- age-only / feature-Ridge / temporal LSTM을 같은 evidence lifecycle에서 비교
- protocol-fixed lifecycle-position diagnostics 추가
- validation-selected method와 operational primary method를 분리
- uncertainty/calibration 근거가 부족한 v1에서는 prediction interval을 explicit unsupported로 유지
- compatible한 prognostics artifact를 `AnalysisView`와 Analysis Explorer에 attached evidence로 구성
- frozen held-out benchmark runner/schema/inspection은 구현 완료, 실제 numerical artifact 실행은 prepared source 단계로 남김

### Capability composition

`AnalysisSurface`는 inspectable artifact와 detailed analysis 가능 여부를 분리합니다. 모든 supported schema는
inspection을 가질 수 있지만, 모든 schema가 observation-level detailed evidence를 가질 필요는 없습니다.

```text
AnalysisSurface
├ artifact_path
├ ExperimentInspection
└ AnalysisView?
     ├ identity / provenance / inspection
     ├ available / unsupported capabilities
     ├ anomaly_evidence?
     └ prognostics_evidence?
```

Detailed projector가 없으면 `AnalysisSurface.analysis`는 `None`이며 Explorer는 inspection-only 화면을
사용합니다. 이는 artifact가 invalid하다는 뜻이 아니라 detailed evidence가 기록되지 않았다는 뜻입니다.

`AnalysisView` 안에서도 artifact가 어떤 capability를 담지 않으면 해당 evidence는 **없는 상태로 둡니다.**
빈 값이나 0으로 채우지 않습니다. Surface가 없는 capability를 요구하면
`require_anomaly_evidence()` / `require_prognostics_evidence()`가 명시적으로 실패하므로, 값이 비어 있는
이유가 capability 부재인지 데이터 부재인지 혼동되지 않습니다.

Prognostics evidence는 `primary_method_id`를 갖지만 method 선택이 검증되기 전까지 `None`으로 유지합니다.
여러 method를 동시에 보여주는 화면은 **development comparison evidence**이며, 같은 asset에 대한 여러 개의
답으로 표시하지 않습니다.

### Prognostics 화면이 함께 보여야 하는 것

RUL 숫자 하나만 보여주면 사용자가 물리적 failure time으로 읽습니다. 따라서 추정치와 다음 항목을 **같은
화면에서** 함께 제시합니다.

| 항목 | 현재 evidence가 말할 수 있는 것 |
| --- | --- |
| Target 의미 | 기록된 run의 마지막 acquisition까지 남은 acquisition interval (`N-k`) |
| As-of | 추정이 기록된 마지막 acquisition index |
| Method | 비교된 method와 각각의 validation 오차 |
| Uncertainty interval | not available |
| Physical failure threshold | not validated |

Target에 clipping이 없으므로 음수 추정이 기록될 수 있습니다. 화면은 이를 0으로 바닥 처리하지 않고 기록된 값
그대로 보여주며, 음수가 있으면 그 사실을 함께 표시합니다.

### Generative AI가 RUL evidence를 설명하는 경계

Generative AI 설명은 evidence scope로 분리합니다. Anomaly scope와 prognostics scope는 서로 다른 structured
context와 서로 다른 boundary 지시를 사용하며, 한 scope의 evidence가 다른 scope의 설명에 섞이지 않습니다.

Prognostics context에 담기는 것은 validated read model에서 읽어온 값뿐입니다.

| 전달 항목 | 목적 |
| --- | --- |
| method별 recorded estimate와 as-of acquisition | 재계산 없이 기록된 값만 설명하게 함 |
| target 의미·unit·formula·clipping 여부 | 숫자가 무엇을 세는지 숫자와 분리되지 않게 함 |
| support 정의와 prediction 수 | 오차가 어떤 구간에서 계산됐는지 고정 |
| retrospective validation 오차 | 해석의 근거를 development evidence로 한정 |
| unavailable capability 목록 | 없는 capability를 만들어내지 않게 함 |
| `primary_method_id` (현재 `None`) | 여러 method를 하나의 운영 답으로 고르지 않게 함 |

모델에게 주는 지시는 다음을 금지합니다: RUL 재계산·외삽·단위 변환, calendar date나 물리적 failure time으로의
번역, failure threshold·alarm/state·maintenance deadline·confidence interval 생성, 그리고 검증되지 않은 primary
method 선택. Target에 clipping이 없으므로 음수 추정도 0으로 올리지 않고 기록된 대로 보고하게 합니다.

Deterministic report/export는 validated AnalysisView를 그대로 Markdown으로 렌더링하며 수치 재계산을 하지
않습니다. `industrial-phm analysis report`는 anomaly artifact를 primary scope로 사용하고, 별도 prognostics
artifact는 dataset/split/fold/population compatibility를 통과한 경우에만 attached evidence로 포함합니다.
Report에는 timestamp를 넣지 않아 동일 입력에서 byte-stable text를 만들 수 있고, exact source byte identity가
artifact에 기록되지 않은 현재 한계도 그대로 표시합니다.

Prepared single-asset CSV export에 대해서는 local validation, source byte identity, data-quality provenance,
canonical mapping과 vibration feature projection까지 baseline이 구현되어 있습니다. 이 경계는 아직 generic field
analysis runtime이 아니며, MIMII WAV adapter도 generic field WAV contract로 승격하지 않습니다.

다음 확장은 실제 private/field source conformance와 Operations UI를 함께 진행하면서 asset/sensor identity,
vendor quality flag, maintenance/configuration event와 source-specific diagnostics 요구를 확인합니다.
AssetObservationSummary는 이 UI가 관측 사실을 experiment artifact와 분리해 소비하기 위한 첫 경계입니다.
Historian/API/live inference, service API, authentication, work-order integration, RAG 같은 기술은 해당 vertical
slice에서 실제 요구가 확인될 때 도입합니다.

완성의 기준은 모든 PHM capability를 동시에 제공하는 것이 아닙니다. 사용 가능한 capability를 끝까지 연결해
사용자가 결과, evidence, limitation과 분석 과정을 이해할 수 있으면 하나의 완결된 시스템으로 취급하고, 이후
RUL·diagnosis·새 모델·새 source를 같은 시스템 안에서 확장합니다.

## 8. PHM Operations 현재 상태

Operations의 제품 기준을 "미래 정보구조를 먼저 모두 노출"하는 방식에서 **현재 수행 가능한 사용자 행동과 다음 연결 작업을 우선**하는 방식으로 조정합니다.

현재 제품 milestone은 다음 한 줄입니다.

```text
Source -> Analyze -> Results -> Finding -> Maintenance review
```

### 현재 실제 가능한 것

- prepared FILE source와 OPC UA source 등록
- source lifecycle 제어와 one-shot runtime 실행
- bounded OPC UA DataChange collection과 event/channel evidence 확인
- prepared observation/timeline과 data-quality/provenance 확인
- 별도 Analysis Explorer에서 XJTU anomaly/RUL 분석 실행과 result/evidence 검토

### 현재 끊긴 지점

```text
Registered source / observation
  -> source-appropriate operational analysis producer   # not connected
  -> AnalysisRun
  -> capability-specific evidence
  -> OperationalFinding
  -> maintenance review action
```

`AnalysisRun`과 `OperationalFinding` 계약이 존재한다는 사실만으로 기능이 완성된 것으로 취급하지 않습니다. producer와 사용자 action이 연결되지 않은 capability는 primary navigation에서 완성 기능처럼 노출하지 않습니다.

Operations primary navigation은 현재 행동 가능한 **Overview / Sources / Investigation / Data Quality**에 집중합니다. 기존 Asset/Maintenance/System Health read-model 코드는 삭제하지 않고 후속 vertical slice에서 실제 data/action이 연결될 때 다시 navigation에 올립니다.

### 다음 vertical slice의 Definition of Done

다음 milestone은 새로운 infrastructure가 아니라 아래 흐름을 실제 UI에서 끝까지 수행하는 것입니다.

1. registered source 또는 준비된 observation을 analysis 대상으로 선택할 수 있다.
2. 사용자가 analysis를 실행하면 실제 `AnalysisRun`이 생성된다.
3. capability-specific result/evidence가 저장되고 Results/Investigation에서 확인된다.
4. 검증된 최소 semantics로 operational finding을 생성하거나, 생성할 수 없으면 그 이유를 명확히 표시한다.
5. 생성된 finding에 사용자가 최소 review action(acknowledge/note)을 수행할 수 있다.
6. 같은 결과에서 지원되는 경우 RUL evidence를 확인할 수 있다.

이 milestone 전에는 persistent OPC UA session, reconnect/backoff, continuous ingestion, 새 connector/model/dataset, generic workflow framework를 우선 작업으로 올리지 않습니다.

## References

- ISO 9241-210 human-centred design overview: https://www.iso.org/standard/77520.html
- Human-in-the-Loop XAI for Predictive Maintenance (2025): https://doi.org/10.3390/electronics14173384
- Data-driven prognostics review: uncertainty, robustness, interpretability and feasibility (2025): https://doi.org/10.1016/j.ymssp.2025.113015
