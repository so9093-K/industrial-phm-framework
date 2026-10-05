# Project Terminology

이 문서는 `industrial-phm-framework`에서 연구·실험·PHM 기능을 설명할 때 사용하는 용어의 기준선입니다.
새로운 프로젝트 고유 용어를 만들기보다 **ISO condition-monitoring vocabulary와 concepts, 널리 쓰이는
ML/data-science 용어, 일반적인 software-engineering 용어**를 우선합니다.

용어는 구현 이름보다 먼저 의미를 고정하기 위한 문서입니다. 코드나 artifact 이름은 실제 기능이 생겼을 때 이
정의와 일치하는 범위에서 추가합니다. ISO 표준의 정의를 임의로 재작성하거나 이 문서만으로 표준 적합성을
주장하지 않습니다.

## 1. Terminology principles

1. ISO 13372처럼 명시적인 vocabulary 표준이나 널리 쓰이는 용어가 있으면 프로젝트 고유 조어를 만들지 않습니다.
2. 같은 단어가 여러 의미를 가질 수 있으면 대상을 붙입니다. 예: `dataset validation`, `development validation`.
3. 관찰된 값과 해석을 구분합니다. 모델이 직접 생성한 값은 그 의미가 검증되기 전까지 더 강한 PHM 의미를
   부여하지 않습니다.
4. 연구용 UI나 Notebook 이름이 architecture 계층이나 Source of Truth가 되지 않습니다.
5. 표준 용어와 일반 ML 용어가 서로 다른 문제를 다루면 억지로 하나로 합치지 않습니다. 연구 lifecycle에는
   일반적인 data-science/ML 용어를, machine condition monitoring 기능에는 ISO 계열 용어를 우선합니다.
6. 용어의 의미가 바뀌면 관련 문서와 public contract를 함께 검토합니다.

## 2. Research and experiment lifecycle

아래 용어는 주로 일반적인 data-science/ML 연구 lifecycle을 설명하기 위한 것입니다. ISO 13374 기능 block의
이름을 연구 단계 이름으로 억지로 재사용하지 않습니다.

### Research objective

실험이 답하려는 질문과 허용되는 claim의 범위입니다. 데이터셋, task, evaluation protocol보다 먼저 명확히 합니다.

### Data acquisition

데이터를 명시적으로 획득·보존하고 source/version/license/provenance를 기록하는 과정입니다. Domain Adapter의
변환 책임과 구분합니다.

### Dataset validation

원천 또는 준비된 데이터가 프로젝트의 구조·sequence·metadata·numerical validity contract를 만족하는지
확인하는 과정입니다. 모델 성능의 `validation`과 구분하기 위해 대상 이름을 함께 씁니다.

### Data understanding / exploratory data analysis (EDA)

데이터 분포, 품질, operating condition, lifecycle, imbalance, 이상한 패턴 등을 탐색해 후속 분석·모델링 가설을
형성하는 반복적 과정입니다. CRISP-DM의 Data Understanding 단계와 같은 일반적 의미로 사용합니다.

### Data preparation

모델이나 분석이 소비할 입력을 준비하는 과정입니다. 이 프로젝트에서는 signal preprocessing, feature extraction,
feature selection, scaling/normalization, sampling/weighting 등이 포함될 수 있습니다. 데이터에서 학습되는 상태는
train partition에서만 fit합니다.

### Feature extraction

한 observation/acquisition에서 고정된 규칙으로 numerical feature를 계산하는 변환입니다. 현재
`vibration-statistical-v1`처럼 fitted state가 없는 계산은 stateless feature extraction으로 구분합니다.

### Feature characterization

Feature가 lifecycle, operating condition, channel, bearing/run, scale, redundancy 측면에서 실제로 어떻게
동작하는지 기술적으로 분석하는 과정입니다. Characterization result는 feature selection과 같은 experiment
결정을 지원하지만 자동으로 그 결정을 대신하지 않습니다.

### Interactive analysis

Feature table, characterization result, model output 같은 이미 계산된 결과를 필터링·비교·시각화하면서 가설과
추가 분석 요구를 탐색하는 연구 활동입니다. Jupyter, marimo 등은 이 활동을 지원하는 도구이며 architecture
계층의 이름이 아닙니다.

### Model development

정의된 training data와 experiment configuration을 사용해 모델을 fit하고 candidate를 비교하는 과정입니다.

### Model scoring

Fitted model을 준비된 observation에 적용해 numerical model output을 생성하는 과정입니다. Isolation Forest의
`score_samples`처럼 observation별 값을 계산하는 단계가 여기에 해당합니다. Model scoring 자체는 candidate
quality를 판단하는 evaluation이 아니며, 이 프로젝트에서는 모델 출력의 방향과 의미를 명시적으로 정의한 뒤
development evaluator가 그 값을 해석·비교합니다.

### ML execution and PHM functional terminology

ML 실행 용어와 PHM 기능 용어는 서로 다른 관점을 설명하며 자동으로 동의어가 되지 않습니다. 아래 대응은
architecture 위치를 이해하기 위한 경계 설명이지 ISO/OSA-CBM functional block과의 적합성 선언이 아닙니다.

| ML / experiment term | 현재 의미 | PHM 기능 용어와의 관계 |
| --- | --- | --- |
| feature extraction / preprocessing | observation을 model-ready representation으로 변환 | PHM data-processing 기능의 일부가 될 수 있지만 그 자체로 특정 functional block 적합성을 의미하지 않음 |
| model fitting | train data로 model state를 학습 | research/model-development activity이며 runtime PHM functional block이 아님 |
| model scoring | fitted model에서 observation별 numerical output 생성 | anomaly score 생성만으로 State Detection이 완료됐다고 보지 않음 |
| anomaly score | 기준 분포 대비 비정상성을 나타내는 numerical model output | threshold·decision semantics·운영 검증이 생기면 State Detection의 evidence가 될 수 있음 |
| development evaluation | candidate output을 validation data에서 비교·해석 | Health Assessment와 동의어가 아니며 experiment lifecycle에 속함 |
| health assessment | 설비 condition/health에 대한 PHM-level assessment | generic model score보다 강한 의미이며 이를 지원하는 semantics와 evidence가 필요함 |
| prognostic assessment | future condition, failure progression 또는 RUL 같은 미래 상태 평가 | generic `prediction`이라는 ML 표현과 구분하며 prognostic target과 uncertainty contract가 필요함 |
| advisory generation | PHM 결과를 바탕으로 decision support 제공 | numerical model output 자체와 구분하고 사용자 승인·운영 절차를 별도로 고려함 |

따라서 code/API 이름은 실제 계산 책임에 맞는 ML 용어를 우선합니다. `ModelScoringInput`이나
`AnomalyScores`를 PHM 기능 이름으로 성급하게 바꾸지 않으며, State Detection·Health Assessment·Prognostic
Assessment 같은 이름은 해당 기능의 의미와 검증 경계가 실제로 구현된 뒤 사용합니다.

### Development validation

Train에서 만든 feature/preprocessing/model candidate가 별도의 validation partition에서도 유지되는지 확인하고,
사전에 허용된 selection/calibration을 수행하는 과정입니다. Dataset validation과 구분합니다.

### Experiment configuration

재현 가능한 실험 입력의 version-controlled 정의입니다. 실제 필요가 확인되면 feature subset, preprocessing,
reference-data rule, sampling/weighting, model parameter 등을 포함할 수 있습니다.

### Experiment configuration finalization

Holdout test를 보기 전에 사용할 experiment configuration을 확정하는 시점입니다. `decision freeze` 같은 별도
프로젝트 용어 대신 이 표현을 사용합니다.

### Holdout test evaluation

Finalized experiment configuration을 사람이 개발 과정에서 사용하지 않은 holdout test partition에 적용해 결과를
평가하는 과정입니다. Test 결과를 보고 같은 protocol을 재튜닝한 뒤 동일 결과를 다시 unbiased evaluation으로
취급하지 않습니다.

### Cross-fold robustness analysis

Development/holdout evaluation 이후 다른 pre-defined fold에서도 결과가 얼마나 안정적인지 확인하는 분석입니다.
Parameter나 assumption을 의도적으로 바꾸는 sensitivity analysis와 구분합니다. 이 표현은 ISO vocabulary가 아니라
현재 split design을 설명하기 위한 일반적인 ML 용어입니다.

### Cross-dataset validation

다른 데이터셋에 동일하거나 명시적으로 대응되는 pipeline을 적용해 dataset-specific overfitting과 portability를
검토하는 과정입니다. 다른 기관·환경의 독립 데이터가 실제 외부 검증 조건을 만족할 때는 `external validation`을
사용할 수 있습니다.

## 3. PHM and condition-monitoring terms

이 절은 ISO 13372 vocabulary와 ISO 13374/13379/13381 계열의 machine condition monitoring, diagnostics,
prognostics 개념에 가능한 범위에서 정렬합니다. 아래 설명은 프로젝트에서의 사용 경계를 정리한 것이며 ISO
원문의 normative definition을 대체하지 않습니다.

### Condition monitoring

설비 상태를 측정·관찰하고 상태 변화에 관한 정보를 생산하는 상위 활동을 가리킵니다. 단순 anomaly detection,
diagnostics, prognostics를 서로 동의어로 사용하지 않습니다.

### Anomaly score

Anomaly-detection model이 observation의 기준 분포 대비 비정상성을 수치화한 모델 출력입니다. Isolation Forest의
첫 numerical output에는 이 표현을 사용합니다.

`Anomaly score`가 lifecycle degradation과 일관되게 연결된다는 근거가 생기기 전에는 이를 자동으로
`degradation score`라고 부르지 않습니다.

### Descriptive review threshold

이미 기록된 anomaly score trajectory에서 사람이 변화 구간을 검토하기 위해 사용하는 명시적 descriptive
threshold입니다. 현재 Analysis Explorer의 첫 정책은 earliest-third recorded scored windows의 nearest-rank
95th percentile입니다.

이 threshold는 retrospective presentation/analysis aid이며 State Detection의 validated normal/fault threshold,
alarm threshold 또는 maintenance decision rule과 동의어가 아닙니다. Threshold를 초과한 contiguous observation은
`score-exceedance interval`로 표시할 수 있지만 이를 자동으로 fault interval이라고 부르지 않습니다.

### Score-exceedance interval

Descriptive review threshold를 초과한 acquisition-aligned score observation이 연속해서 나타난 구간입니다.
사용자가 anomaly evidence가 집중된 위치를 찾기 위한 presentation-level evidence이며, 별도의 state semantics가
검증되기 전에는 normal/fault state, alarm 또는 diagnostic event를 의미하지 않습니다.

### Degradation indicator

설비 lifecycle에서 열화 진행과 의미 있게 연결된다고 분석·검증된 지표를 가리키기 위한 프로젝트 용어입니다.
단순 anomaly score나 feature trajectory에 이 이름을 선제적으로 부여하지 않습니다. 표준의 특정 normative term을
재정의하는 용도로 사용하지 않습니다.

### Health indicator (HI)

설비의 health/degradation state를 요약하도록 구성되고 그 의미가 검토된 지표를 가리키는 PHM 문헌상의 일반적인
표현으로 사용합니다. `Health Index`는 특정 방법이나 문헌이 그 명칭을 명시적으로 사용할 때 그대로 사용합니다.
ISO 13372의 특정 정의를 이 문장으로 대체한다고 주장하지 않습니다.

### Diagnostics

관찰된 상태나 이상과 관련된 fault, 원인 또는 상태를 식별·구분하는 활동입니다. 단순 anomaly detection과
동의어로 사용하지 않습니다.

### Prognostics

미래 상태, failure progression 또는 remaining useful life와 같은 미래 거동을 추정하는 활동입니다. RUL은
prognostics capability 중 하나이며 데이터와 target contract가 정당하게 지원할 때만 도입합니다.

### Remaining useful life (RUL)

정의된 end-of-life 또는 prognosis endpoint까지 남은 사용량·시간·cycle 등을 추정한 prognostics output입니다.
RUL 값은 endpoint와 unit이 함께 정의되어야 하며, 단순 anomaly score 또는 lifecycle ordering에서 자동으로
파생되는 의미가 아닙니다.

### Recorded-end RUL target

완전한 run-to-failure record처럼 마지막 recorded observation이 존재하는 retrospective source에서, 그 recorded
endpoint까지 남은 interval을 target으로 정의하는 방식입니다. XJTU-SY RUL protocol v1에서는 acquisition index
`k`, final recorded acquisition `N`에 대해 `N - k` acquisition intervals를 사용합니다.

이 target은 dataset-observed endpoint에 대한 retrospective target이며 validated physical failure threshold,
field failure definition 또는 maintenance threshold와 동의어가 아닙니다.

### Prediction interval / uncertainty evidence

RUL point estimate 주변의 불확실성을 표현하는 numerical evidence입니다. Range를 표시하려면 사용한 method,
fit/calibration population, interval level의 의미와 empirical evaluation을 함께 기록합니다. 임의 percentage나
UI 편의를 위해 만든 범위를 prediction interval로 부르지 않습니다. Calibration 근거가 충분하지 않으면 point
estimate는 제공하더라도 interval capability는 `unsupported` 또는 `not validated`로 유지할 수 있습니다.

### Normal-condition reference / reference data

Anomaly 또는 상태 비교의 기준으로 사용하는 train-derived reference population/data입니다. XJTU-SY에 공식
acquisition-level healthy/onset label이 없으므로 임의 early-life 구간을 ground truth `normal`로 표현하지 않습니다.

## 4. Artifacts and provenance

### Artifact

재현 가능한 분석·학습·평가 과정에서 생성되는 파일 또는 직렬화된 결과입니다. 예: feature table,
characterization summary, fitted preprocessing state, model artifact, evaluation result.

### Artifact manifest

Artifact가 실제로 여러 파일로 구성되고 공통 provenance를 연결할 필요가 확인된 경우 dataset/split/feature/config/
code revision과 파일 관계를 기술하는 metadata artifact입니다. 필요가 생기기 전에는 별도 bundle abstraction을
만들지 않습니다.

### Provenance

결과가 어떤 source, dataset version, split, feature/config, code revision 및 fitted state에서 생성됐는지 추적할
수 있게 하는 정보입니다.

### Model training provenance

하나의 model fit이 어떤 framework/version, device, numeric precision, seed, fit population과 optimization
configuration에서 실행됐는지 추적하는 training-specific provenance입니다. Model output이나 evaluation result와
구분하며, framework-native tensor/module 자체를 public artifact에 노출한다는 의미는 아닙니다.

### Final-epoch mean training loss

마지막 training epoch에서 각 batch loss를 해당 batch의 observation/window 수로 가중해 전체 fit population에
대해 계산한 평균 training loss입니다. Validation loss, checkpoint selection metric 또는 최종 evaluation
metric과 구분합니다. 의미가 이 값인 경우 모호한 `final loss` 대신 이 표현을 사용합니다.

## 5. Terms to avoid as canonical names

다음 표현은 설명용 비유나 UI 임시 이름으로는 사용할 수 있지만 architecture/code의 canonical term으로 고정하지
않습니다.

- `Research Control Plane`: `research workflow` 또는 `interactive analysis`로 설명합니다.
- `Feature Observatory`: 기능은 `interactive feature analysis`로 설명하고 제품명이 필요할 때만 별도 검토합니다.
- `Evidence Bundle`: 실제 산출물은 `characterization artifacts`, `experiment artifacts`, `artifact manifest`로 부릅니다.
- `Decision Freeze`: `experiment configuration finalization`을 사용합니다.
- `Degradation score`: 실제 degradation 의미가 검증되지 않은 anomaly-model output에는 사용하지 않습니다.
- `Final loss`: 어떤 population·epoch·aggregation의 loss인지 불분명하므로, 현재 LSTM training provenance에는
  `final-epoch mean training loss`를 사용합니다.

## 6. Reference alignment

이 문서는 표준 내용을 복제하는 문서가 아니라 프로젝트 vocabulary를 정렬하기 위한 기준입니다.

- ISO 13372:2012, *Condition monitoring and diagnostics of machines — Vocabulary* (2023 재확인)
- ISO 13374-1:2003, *Condition monitoring and diagnostics of machines — Data processing, communication and
  presentation — Part 1: General guidelines* (2025 재확인)
- ISO 13374-4:2015, *Condition monitoring and diagnostics of machine systems — Data processing, communication and
  presentation — Part 4: Presentation*
- ISO 13379-1:2025, *Condition monitoring and diagnostics of machine systems — Data interpretation and diagnostics
  techniques — Part 1: General guidelines*
- ISO 13381-1:2025, *Condition monitoring and diagnostics of machine systems — Prognostics — Part 1: General
  guidelines and requirements*
- CRISP-DM, Data Understanding / Data Preparation / Modeling / Evaluation lifecycle terminology

표준의 세부 requirement를 구현했다고 주장하려면 별도의 요구사항 분석과 적합성 검증이 필요합니다. 이 문서의
용어 정렬만으로 ISO conformance를 주장하지 않습니다.

## 7. Observation and reference vocabulary

분석 결과가 **무엇과 비교되었는지** 정확히 답할 수 있도록 아래 개념을 하나의 `label`로 묶지 않습니다.

### Observation

Source가 전달한 측정값과 그 시각·quality·provenance입니다. 해석을 포함하지 않습니다.

### Event

Source 또는 운영 system이 기록한 이산적 사건입니다. 예: 기동/정지 신호, alarm 발생, 수집 연결 끊김.
Event의 발생 기록은 그 원인이나 설비 상태 판정이 아닙니다.

### Assessment

분석 capability나 사람이 observation/event를 해석해 만든 판단입니다. 누가(어떤 capability/version 또는
reviewer), 어떤 근거로 만들었는지를 함께 보존합니다. Review finding은 사람의 assessment입니다.

### Provider annotation

데이터 제공자가 붙인 label입니다. 예: AI-Hub 239의 기동패턴(Stop/Loading/Unloading)과 SOH(정상/주의/경고).
Provider, annotation type, value, interval과 provenance를 보존하고, 산정 방법이 문서로 확인되지 않으면
method unresolved로 둡니다. Research 평가 비교에만 사용하며 production 입력이나 설비 상태로 승격하지 않습니다.

### Maintenance record

작업 지시, 부품 교체, 점검 결과, 고장 코드처럼 정비 과정에서 생긴 기록입니다. 기록 자체는 사실이지만
기록된 원인이나 상태가 검증되었다는 뜻은 아닙니다.

### Verified ground truth

독립 근거(예: 분해 점검, 시험실 확인, 확인된 고장 event)로 검증된 설비 상태나 사건입니다. 검증 방법과
근거를 함께 기록할 때만 이 용어를 사용합니다. Provider annotation, model output, maintenance record를 검증
없이 ground truth로 부르지 않습니다.

## 8. Source and validation context

Source를 `현장/비현장`, `진짜/가짜`처럼 하나의 축으로 분류하지 않습니다. 데이터가 물리 설비에서
기록되었는지, 현재 runtime protocol로 직접 수집되는지, 프로젝트의 실제 적용 대상으로 검증되었는지는 서로 다른
질문입니다. Source와 validation 범위를 설명할 때는 필요한 차원을 명시합니다.

### Source origin

데이터가 어디에서 왔는지를 설명합니다.

- **Synthetic source/data**: 프로젝트나 test fixture가 생성한 값입니다.
- **Provider-recorded data**: 외부 provider가 기록해 dataset/archive 형태로 제공한 값입니다. 실제 측정 기록일 수
  있지만 archive만으로 당시 live protocol, gateway, timestamp, deadband 또는 security 동작까지 검증되었다고
  주장하지 않습니다.
- **Organization-provided data**: 적용 조직이 승인된 export/snapshot/history 형태로 제공한 데이터입니다. 소유
  조직이나 비공개 여부 자체가 operational validation을 의미하지 않습니다.

### Acquisition mode

프로젝트가 값을 어떤 방식으로 소비하는지를 설명합니다.

- **Prepared FILE source**: 명시적으로 준비된 snapshot 또는 timestamped file history를 읽습니다.
- **Recorded archive**: provider/organization이 이미 기록한 archive를 직접 읽습니다.
- **Replay source**: recorded data를 OPC UA 같은 runtime protocol로 재생합니다.
- **Live source**: 현재 실행 중인 endpoint/service와 runtime protocol로 직접 통신합니다.

Replay와 live는 protocol 형태가 같을 수 있지만 validation claim은 다릅니다. Replay는 수집·복구·분석 pipeline을
반복 검증하는 데 유용합니다. 다만 replay configuration에서 관찰된 publish interval, DataChange cadence, deadband,
timestamp 동작은 우리가 설정한 것이며 다른 source의 runtime behavior를 대신 증명하지 않습니다.

### Validation role

어떤 claim을 위해 source를 사용하는지를 설명합니다.

- **Research/evaluation source**: 모델·방법·연구 protocol의 성능과 한계를 평가합니다.
- **Contract/runtime validation source**: adapter, ingestion, persistence, recovery, analysis contract를 검증합니다.
- **Target operational source**: 적용 대상으로 명시적으로 선택된 live source입니다. 이 source에서 runtime protocol,
  timing, semantics, quality, recovery, security 가정을 검증하는 것을 **target-source validation**이라고 합니다.

`target operational source`는 다른 dataset/source보다 더 "진짜"라는 의미가 아닙니다. 프로젝트가 적용하려는
구체적인 runtime source라서 그 source에 대한 별도의 validation claim이 필요한 것입니다. Target-source validation은
그런 source가 선택되었을 때 그 source의 요구와 evidence로 수행하며, 다른 검증 뒤에 항상 이어지는 roadmap 단계나
상위 진위 등급이 아닙니다.

### Terms to avoid as standalone technical categories

`현장 데이터`, `실제 데이터`, `field source` 같은 표현은 문맥상 사용할 수 있지만 단독 canonical category로
사용하지 않습니다. 필요한 경우 `provider-recorded data`, `prepared FILE source`, `replay source`,
`live source`, `target operational source`처럼 획득 방식과 validation 역할을 직접 씁니다.

