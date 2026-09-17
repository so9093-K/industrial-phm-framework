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

## 5. Terms to avoid as canonical names

다음 표현은 설명용 비유나 UI 임시 이름으로는 사용할 수 있지만 architecture/code의 canonical term으로 고정하지
않습니다.

- `Research Control Plane`: `research workflow` 또는 `interactive analysis`로 설명합니다.
- `Feature Observatory`: 기능은 `interactive feature analysis`로 설명하고 제품명이 필요할 때만 별도 검토합니다.
- `Evidence Bundle`: 실제 산출물은 `characterization artifacts`, `experiment artifacts`, `artifact manifest`로 부릅니다.
- `Decision Freeze`: `experiment configuration finalization`을 사용합니다.
- `Degradation score`: 실제 degradation 의미가 검증되지 않은 anomaly-model output에는 사용하지 않습니다.

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
