# XJTU-SY RUL / Prognostics Protocol v1

상태: protocol v1

이 문서는 XJTU-SY complete run-to-failure source에서 첫 Remaining Useful Life(RUL) capability를 구현하기 전에
target, split, leakage, prediction alignment, evaluation, uncertainty와 허용 가능한 claim의 범위를 고정합니다.
모델 결과를 본 뒤 target 또는 evaluation 의미를 바꾸지 않기 위해 numerical implementation보다 먼저
version-controlled protocol을 둡니다.

프로젝트 공통 용어는 [`../terminology.md`](../terminology.md), source 관찰 사실은
[`xjtu-source-profile.md`](xjtu-source-profile.md), 기존 bearing-run split의 authoritative assignment는
`src/industrial_phm/experiments/manifests/xjtu-sy-condition-stratified-5fold-v1.toml`을 따릅니다.

## 1. Prognostics question

v1의 질문은 다음과 같습니다.

> 같은 operating condition을 포함한 train bearing run에서 학습한 prognostics model이, model fit에 사용되지 않은
> bearing run의 각 prediction point에서 마지막으로 기록된 run endpoint까지 남은 acquisition interval을
> 재현 가능한 방식으로 추정할 수 있는가?

이 질문은 XJTU-SY에서의 retrospective benchmark question입니다. 실제 현장 failure threshold, 정비 시점 또는
future operating condition을 예측하는 operational prognosis라고 일반화하지 않습니다.

## 2. Source facts and endpoint boundary

XJTU-SY 공식 dataset page는 다음 source facts를 제공합니다.

- 3 operating conditions
- condition별 5 bearing, 총 15 run
- complete run-to-failure data
- 25.6 kHz waveform sampling
- acquisition 하나당 32,768 points / 1.28 seconds
- acquisition sampling period 1 minute
- bearing별 CSV file count와 lifetime/fault element

현재 local source profile은 모든 bearing run에서 numeric acquisition filename `1.csv ... N.csv`가 연속임을
확인했습니다.

v1은 **마지막으로 기록된 acquisition을 dataset-observed run endpoint**로 사용합니다. 이 endpoint를 새로운
physical failure threshold로 재정의하지 않습니다.

공개된 후속 연구에는 XJTU-SY failure criterion을 특정 g threshold 또는 healthy-amplitude 배수로 재구성한 서로
다른 관행이 존재합니다. 이 프로젝트는 공식 source와 현재 보존된 provenance가 직접 뒷받침하지 않는 threshold를
ground truth로 선택해 acquisition을 자르거나 EOL을 다시 만들지 않습니다.

따라서 v1에서 다음은 서로 다릅니다.

```text
last recorded acquisition
  = RUL target을 정렬하는 observed dataset endpoint

validated physical failure threshold
  = v1에서 정의하지 않음

operational maintenance threshold
  = v1에서 정의하지 않음
```

## 3. RUL target definition

Bearing run의 acquisition index를 1-based `k`, 마지막 recorded acquisition index를 `N`이라고 할 때
primary target은 다음과 같습니다.

```text
remaining_acquisition_intervals = N - k
```

따라서:

- first recorded acquisition target: `N - 1`
- final recorded acquisition target: `0`
- contiguous acquisition에서 target은 정확히 1씩 감소
- target unit: `acquisition-interval`

XJTU-SY의 공식 sampling period가 1 minute이므로 이 source에서는 acquisition interval 하나가 1 minute에
대응합니다. 그러나 artifact의 primary target unit은 `acquisition-interval`로 유지합니다. `minute` 표시는
source sampling-period provenance가 검증된 presentation에서만 파생할 수 있으며 별도 target을 만들지 않습니다.

### 3.1 No target clipping in v1

v1은 early-life RUL cap, piecewise-linear target 또는 arbitrary maximum-RUL clipping을 사용하지 않습니다.
그러한 정책은 서로 다른 bearing lifetime을 인위적으로 같은 target으로 만들 수 있고 별도의 prognostic assumption을
도입하기 때문입니다.

Model optimization을 위한 numerical transform이 필요해지는 경우에도:

- raw target semantics는 위 식이 계속 Source of Truth이고
- transform parameter는 train scope에서만 결정하며
- artifact/evaluation은 raw acquisition-interval unit으로 복원된 prediction을 기록합니다.

### 3.2 No normalized lifecycle target as model ground truth

`k / N`, `(N-k)/N`처럼 target bearing의 final lifetime `N`을 입력 시점에 알아야 하는 normalized lifecycle
quantity를 production-like model input으로 사용하지 않습니다. Evaluator가 bearing별 relative error나 lifecycle
bin을 계산할 때는 retrospective ground truth로 `N`을 사용할 수 있지만 model input에는 들어가지 않습니다.

## 4. Prediction-point alignment

Acquisition-level model의 prediction point는 해당 acquisition `k`입니다.

Sequence model은 기존 sequence contract와 동일하게 right-edge aligned prediction을 사용합니다.

예를 들어 length 8 window가 source acquisition `100 ... 107`을 소비하면:

```text
window right edge = acquisition 107
RUL target        = N - 107
```

window start의 target, window mean target 또는 future acquisition의 feature를 사용하지 않습니다.

Sequence construction은 다음을 반드시 보존합니다.

- one bearing run boundary
- one partition boundary
- acquisition order
- source observation identity
- window start/end lineage
- right-edge prediction identity

어떤 window도 bearing 또는 partition 경계를 넘을 수 없습니다.

## 5. Split and evidence status

Authoritative bearing assignment는 기존
`xjtu-sy-condition-stratified-5fold-v1` manifest를 재사용합니다. 새로운 RUL split을 만들어 이미 존재하는
data partition 사실을 중복 소유하지 않습니다.

첫 development scope는 기존과 동일한 `fold-1`입니다.

```text
train
  Bearing1_3 Bearing1_4 Bearing1_5
  Bearing2_3 Bearing2_4 Bearing2_5
  Bearing3_3 Bearing3_4 Bearing3_5

validation
  Bearing1_2 Bearing2_2 Bearing3_2

held-out benchmark
  Bearing1_1 Bearing2_1 Bearing3_1
```

### 5.1 Project-history limitation

`fold-1 test` bearing은 기존 anomaly-scoring protocol에서 이미 one-time holdout으로 사용되었고 repository
development 과정에서 source length와 일부 evidence가 관찰되었습니다. 따라서 RUL v1에서 이 population을
**project-history 전체에서 untouched인 pristine holdout 또는 external validation**이라고 다시 주장하지 않습니다.

RUL implementation에서는 다음 경계를 지킵니다.

- RUL target/model/evaluation configuration은 held-out RUL prediction을 보기 전에 고정
- model/preprocessing fit은 train only
- allowed candidate selection은 validation only
- held-out benchmark prediction은 frozen RUL configuration으로 실행
- held-out result를 본 뒤 같은 protocol version을 retune해 unbiased evidence라고 재사용하지 않음

v1 evidence class의 권장 의미는 `protocol-frozen-retrospective-benchmark-evidence`입니다.

### 5.2 Folds 2-5

folds 2-5는 fold-1 RUL benchmark 이후 robustness analysis에 사용할 수 있습니다. Rotating manifest 특성상 어떤
bearing은 다른 fold에서 train/validation에 등장하므로 이 결과를 서로 독립적인 external tests로 합산하지 않습니다.

Cross-fold 결과는 다음 질문만 답합니다.

> 동일한 fixed RUL method가 pre-defined bearing rotations에서 얼마나 안정적인가?

## 6. Leakage rules

기존 leakage policy에 더해 RUL v1은 다음을 명시적으로 금지합니다.

1. 같은 bearing의 acquisition 또는 sequence window가 여러 partition에 섞이는 것.
2. target bearing의 final lifetime `N`을 model feature 또는 inference-time normalization에 사용하는 것.
3. validation/test bearing의 target distribution을 보고 scaler, feature subset, sequence length 또는 model
   hyperparameter를 fit하는 것.
4. 전체 15 bearing의 target mean/std/min/max를 사용해 train target transform을 fit하는 것.
5. test bearing 자신의 early-life target 또는 future acquisition을 test-time adaptation에 사용하는 것.
6. sequence prediction point보다 미래 acquisition의 feature를 사용하는 것.
7. held-out trajectory를 반복해서 보고 target clipping, lifecycle segmentation 또는 metric을 변경하는 것.
8. uncertainty/calibration parameter를 held-out benchmark residual로 fit하는 것.

Stateless per-acquisition feature extraction은 각 partition에서 독립적으로 실행할 수 있습니다. Robust scaling 등
data-derived preprocessing state는 train에서만 fit하고 validation/held-out benchmark에는 같은 fitted state를
적용합니다.

## 7. Baseline ladder

v1은 복잡한 temporal model 하나의 성능만 기록하지 않습니다. 최소 비교 구조는 다음 세 수준입니다.

### A. Elapsed-acquisition baseline

현재까지 관찰한 acquisition index만 사용하는 time/age-only baseline입니다.

목적은 센서 evidence 없이 단순히 "시간이 지났기 때문에 RUL이 줄어든다"는 정보가 어느 정도 설명력을 가지는지
측정하는 것입니다.

v1의 첫 age-only comparator는 numerical validation 결과를 보기 전에 다음과 같이 고정합니다.

```text
fit:
  train bearing별 recorded endpoint acquisition N_i
  -> equal-bearing arithmetic mean N_bar_train

predict at acquisition k:
  predicted RUL = N_bar_train - k
```

즉 train bearing의 endpoint distribution에서 **평균 endpoint 하나만 fit**하고 prediction-time에는 현재
acquisition index `k`만 사용합니다. Operating condition, vibration feature value, target bearing의 endpoint,
normalized lifecycle fraction과 future acquisition count를 입력으로 사용하지 않습니다. Negative prediction도
0으로 clamp하지 않고 model bias/error evidence로 그대로 evaluator에 전달합니다.

이 comparator는 높은 성능을 목표로 하는 model이 아니라 이후 sensor-feature/sequence model이 단순 age information
이상으로 실제 추가 정보를 제공하는지 확인하기 위한 lower-complexity reference입니다.

금지되는 입력:

- target bearing total lifetime
- normalized lifecycle fraction
- future acquisition count
- operating condition
- vibration feature value

### B. Acquisition-feature baseline

현재 prediction acquisition까지 이용 가능한 versioned vibration feature와 train-fitted preprocessing을 사용하는
단순 regression baseline입니다.

이 baseline은 temporal sequence model이 아니라 **현재 acquisition의 sensor-derived feature가 age-only baseline에
비해 실제 추가 정보를 제공하는가**를 확인하는 비교점입니다.

정확한 estimator와 parameter는 numerical result를 보기 전에 version-controlled configuration에서 고정합니다.

### C. Sequence RUL model

동일 feature semantics와 split을 사용하되 contiguous historical feature sequence를 소비하는 temporal model입니다.
첫 implementation은 이미 검증된 deterministic CPU deep-learning runtime과 dataset-neutral sequence contract를
우선 재사용합니다.

Model family/hidden size/optimizer/epoch 등 numerical configuration은 별도 version-controlled experiment
configuration이 Source of Truth가 되며 이 protocol 문서에 중복 정의하지 않습니다.

## 8. Model selection and finalization

Candidate comparison이 필요한 경우 validation bearing만 사용합니다.

Primary selection metric은 **bearing별 MAE를 먼저 계산한 뒤 세 validation bearing을 동일 가중한 mean MAE**입니다.
Acquisition을 세 bearing 전체에서 pooling한 MAE를 selection metric으로 사용하지 않습니다.

정확한 동률에서는 다음 순서로 결정합니다.

1. bearing-equal mean normalized MAE가 작은 candidate
2. model parameter count가 작은 candidate
3. experiment/configuration ID 사전순

Arbitrary tolerance를 사용해 근소한 차이를 동률 처리하지 않습니다.

Final configuration은 held-out RUL benchmark를 실행하기 전에 version control에 고정합니다.

## 9. Point-prediction evaluation

각 evaluation bearing에서 최소 다음을 계산합니다.

- observation/window count
- MAE in acquisition intervals
- RMSE in acquisition intervals
- mean signed error: `prediction - target`
- normalized MAE: bearing MAE / max(`N - 1`, 1)

Aggregate는 bearing별 metric을 먼저 계산한 뒤 **equal-bearing arithmetic mean**을 사용합니다.

### 9.1 Lifecycle-position diagnostics

모델이 긴 early-life 구간에서는 좋아 보이고 실제 maintenance-relevant late-life에서 무너지는 문제를 숨기지 않기
위해 retrospective evaluator는 bearing의 recorded lifecycle을 early/middle/late thirds로 나누어 error를
기술할 수 있습니다.

이 thirds는 evaluation-only diagnostic입니다.

- model input이 아님
- state label이 아님
- degradation onset ground truth가 아님
- threshold calibration 근거가 아님

### 9.2 Model comparison is not deployment validation

낮은 MAE/RMSE만으로 다음을 주장하지 않습니다.

- field RUL accuracy
- physical failure-time prediction accuracy outside XJTU
- maintenance decision quality
- calibrated operational risk
- cross-condition/site generalization

## 10. Uncertainty and prediction range boundary

RUL point estimate와 prediction range는 별도 evidence입니다. UI convenience를 위해 `estimate ± arbitrary percent`
형태의 range를 만들지 않습니다.

Prediction interval 또는 uncertainty range를 available capability로 표시하려면 artifact가 최소한 다음을 보존해야
합니다.

- `uncertainty_method_id`
- method configuration
- fit/calibration population
- requested nominal level이 있다면 그 level
- held-out bearing별 empirical interval coverage
- held-out bearing별 mean interval width
- aggregate rule
- known assumptions/limitations

XJTU fold-1 validation은 세 bearing뿐이고 sequence/window observations는 같은 bearing 안에서 시간적으로
종속됩니다. 따라서 window-level sample 수가 많다는 이유만으로 iid calibration population이 충분하다고
주장하지 않습니다.

특히 conformal 또는 calibration method를 사용할 경우 exchangeability/grouping assumption을 명시하지 않은
nominal coverage guarantee를 사용자 화면에 표시하지 않습니다.

첫 uncertainty method는 point-model evidence와 분리된 version-controlled configuration으로 frozen한 뒤 held-out
benchmark를 봅니다. Method가 정당한 calibration evidence를 제공하지 못하면 RUL point estimate는 제공하되
prediction range capability는 `unsupported/not validated`로 남길 수 있습니다.

## 11. Artifact requirements

첫 prognostics result는 universal `PHMResult`를 미리 만들지 않고 실제 RUL consumer가 필요로 하는 concrete
schema로 시작합니다.

Artifact는 최소 다음 identity/evidence를 보존해야 합니다.

```text
artifact_type
schema_version
protocol_id
dataset_id
source scope
split_id / partition
target_definition
target_unit
prediction_alignment
feature/preprocessing identity
model configuration identity
training population
prediction population
per-asset predictions
point-evaluation metrics
uncertainty evidence or explicit unsupported status
capabilities / limitations
code revision
runtime/model provenance
```

Schema evolution 시 reader가 지원하는 version을 명시적으로 검증하고 unknown version을 추정해서 읽지 않습니다.

## 12. Dependency and responsibility boundary

RUL 추가는 현재 dependency direction을 뒤집지 않습니다.

```text
source / Adapter
    ↓
canonical + versioned features
    ↓
dataset-specific RUL target/split orchestration
    ↓
dataset-neutral model execution
    ↓
model-independent prognostics evaluation
    ↓
versioned prognostics evidence artifact
    ↓
analysis read model
    ↓
UI / GenAI / report
```

책임은 다음과 같이 분리합니다.

- Adapter: source parsing/canonicalization. RUL target을 만들지 않음.
- XJTU experiment edge: recorded endpoint와 acquisition identity를 이용한 dataset-specific target construction.
- Dataset-neutral prognostics/model layer: 이미 정렬된 input/target을 소비해 fit/predict.
- Evaluator: prediction과 target을 비교. model을 fit하거나 prediction을 다시 만들지 않음.
- Artifact: numerical Source of Truth와 provenance를 보존.
- Analysis layer: validated artifact를 presentation read model로 투영.
- UI/GenAI/report: RUL 또는 interval을 재계산하지 않고 read model을 소비.

두 번째 실제 capability가 추가된다는 이유만으로 generic workflow engine, universal result schema 또는 모든 PHM
capability를 가진 base class를 만들지 않습니다. Anomaly와 Prognostics가 실제로 공유하는 presentation 책임이
반복될 때만 작은 공통 composition을 승격합니다.

## 13. Required regression/contract protection

구현 change unit은 최소 다음 failure를 보호해야 합니다.

1. final acquisition target이 0이 아니게 되는 off-by-one 오류
2. contiguous acquisition target이 1씩 감소하지 않는 ordering 오류
3. source observation identity와 target alignment drift
4. bearing/partition을 넘는 sequence window
5. right-edge target 대신 start/mean/future target을 사용하는 오류
6. target bearing total lifetime이 model input에 유입되는 leakage
7. train 이외 population으로 preprocessing/target transform을 fit하는 leakage
8. evaluator가 unequal bearing length를 row pooling해 aggregate 의미를 바꾸는 오류
9. unknown artifact schema/version을 silent fallback으로 읽는 오류
10. UI/GenAI가 artifact에 없는 RUL range 또는 unsupported capability를 생성하는 오류

Production validation을 test helper에서 다시 구현하지 않고 public contract/validator를 통해 검증합니다.

## 14. Execution sequence

v1 구현 순서는 다음과 같습니다.

```text
protocol
  ↓
RUL target contract + XJTU construction
  ↓
baseline inputs/models
  ↓
model-independent point evaluator
  ↓
sequence RUL model
  ↓
validation comparison + configuration finalization
  ↓
held-out RUL benchmark
  ↓
uncertainty method/calibration evidence
  ↓
prognostics artifact/read model
  ↓
Analysis Explorer + GenAI
```

Numerical result가 생긴 뒤 target/split/evaluation rule을 소급 변경하지 않습니다. 변경이 필요하면 protocol/config
version을 올리고 이전 evidence와 의미를 구분합니다.

## 15. References

- XJTU-SY official dataset page:
  https://biaowang.tech/xjtu-sy-bearing-datasets/
- XJTU-SY official repository:
  https://github.com/WangBiaoXJTU/xjtu-sy-bearing-datasets
- Biao Wang, Yaguo Lei, Naipeng Li, Ningbo Li,
  *A Hybrid Prognostics Approach for Estimating Remaining Useful Life of Rolling Element Bearings*,
  IEEE Transactions on Reliability, 69(1), 401-412, 2020,
  DOI: 10.1109/TR.2018.2882682.
- ISO 13381-1:2025,
  *Condition monitoring and diagnostics of machine systems — Prognostics — Part 1: General guidelines and requirements*.

이 protocol의 용어 정렬은 ISO 적합성 선언이 아닙니다. 표준 적합성을 주장하려면 별도 requirements analysis와
verification이 필요합니다.
