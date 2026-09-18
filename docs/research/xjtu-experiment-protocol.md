# XJTU-SY Reference Experiment Protocol

상태: reference protocol v1

이 문서는 XJTU-SY를 이용한 첫 numerical PHM baseline이 어떤 질문을 검증하고, 어떤 데이터 분할과 leakage
규칙을 따라야 하는지 고정합니다. 모델 성능을 본 뒤 split이나 label 정의를 바꾸는 일을 막기 위해 모델 구현보다
먼저 version-controlled protocol을 둡니다. 프로젝트 공통 용어는 [`../terminology.md`](../terminology.md)를
따릅니다.

## 1. Dataset and ground-truth boundary

공식 XJTU-SY 자료는 3개 operating condition에서 각각 5개 bearing을 시험한 총 15개 run-to-failure bearing
데이터를 설명합니다. 각 acquisition은 25.6 kHz로 32,768 point를 기록하며 sampling period는 1분입니다.

- official dataset page: https://biaowang.tech/xjtu-sy-bearing-datasets/
- official repository: https://github.com/WangBiaoXJTU/xjtu-sy-bearing-datasets
- local source evidence: [`xjtu-source-profile.md`](xjtu-source-profile.md)

공식 자료는 bearing lifetime과 최종 fault element를 제공하지만 train/validation/test assignment나 acquisition별
anomaly onset label을 공식 split/ground truth로 제공하지 않습니다. 따라서 아래 split은 **이 프로젝트의 reference
protocol**이며 XJTU-SY의 공식 split이라고 주장하지 않습니다.

## 2. First baseline question

첫 baseline의 목적은 최고 성능이나 RUL 정확도를 주장하는 것이 아닙니다.

> 같은 operating condition에서 학습에 사용되지 않은 bearing run에 대해, 공통 preprocessing/feature/model
> pipeline이 재현 가능한 acquisition-level anomaly-score trajectory를 생성할 수 있는가?

따라서 첫 단계의 task는 acquisition-level **unsupervised anomaly scoring**입니다. Anomaly score가 bearing
lifecycle의 degradation과 일관되게 연결되는지는 별도의 characterization/evaluation 질문이며, 그 근거가 생기기
전에는 모델 출력을 `degradation score`라고 부르지 않습니다.

이번 protocol에서 아직 하지 않는 것:

- supervised fault-class classification
- acquisition별 failure-onset ground truth 생성
- 마지막 일정 비율을 임의로 anomaly label로 간주
- sample-level RUL target 생성
- cross-condition generalization 성능 주장

RUL은 degradation trajectory와 lifecycle-level target 계약이 실제로 필요하다고 확인된 뒤 별도 prognostics
protocol에서 다룹니다.

## 3. Split unit

분할 단위는 waveform sample이나 acquisition이 아니라 **bearing run 전체**입니다.

```text
Bearing1_1
  1.csv
  2.csv
  ...
  123.csv
```

`Bearing1_1`의 일부 acquisition을 train에 두고 나머지를 validation/test에 두는 방식은 허용하지 않습니다.
같은 physical run의 시간적으로 인접한 acquisition이 여러 partition에 섞이면 모델이 asset-specific 상태를 쉽게
재사용할 수 있고 실제 unseen-bearing generalization을 과대평가할 수 있기 때문입니다.

Authoritative assignment는 package에 포함된 다음 split manifest가 소유합니다.

```text
src/industrial_phm/experiments/manifests/
  xjtu-sy-condition-stratified-5fold-v1.toml
```

문서는 rationale을 설명하고, 실제 bearing assignment의 Source of Truth는 manifest로 유지합니다.

## 4. Condition-stratified rotating holdout

각 operating condition에는 5개 bearing run이 있으므로 5개의 deterministic fold를 사용합니다. 각 fold는
condition마다 다음 역할을 가집니다.

```text
3 train bearings
1 validation bearing
1 test bearing
```

세 operating condition을 합치면 fold 하나당:

```text
train       9 bearing runs
validation  3 bearing runs
test        3 bearing runs
```

fold가 회전하면서 각 bearing run은 전체 protocol에서 정확히:

```text
train       3회
validation  1회
test        1회
```

등장합니다. 모든 fold는 세 operating condition을 포함하므로 첫 baseline에서는 operating-condition 차이와
unseen-bearing 차이를 한 번에 혼동하지 않습니다.

이 protocol은 cross-condition generalization protocol이 아닙니다. 두 operating condition에서 학습하고 세 번째
condition 전체를 holdout하는 LOCO 계열 평가는 feature/model baseline이 안정된 뒤 별도 protocol로 추가합니다.

## 5. Development fold and holdout test

Rotating holdout manifest는 재현 가능한 bearing assignment를 정의하지만, 사람이 모든 fold를 반복해서 관찰하면서
feature/reference/model을 바꾼 뒤 각 fold의 test 결과를 모두 독립적인 final test처럼 해석한다는 의미는 아닙니다.
특히 한 fold의 test bearing은 다른 fold의 train 또는 validation에 등장하므로, cross-fold human tuning이 시작되면
holdout independence가 약해집니다.

첫 numerical baseline에서는 **`fold-1`을 development fold로 고정**합니다. 이 선택은 fold 간 결과를 비교해
성능이 좋은 fold를 고른 것이 아니라 development와 holdout test의 경계를 하나로 고정하기 위한 절차적
선택입니다.

각 partition의 역할은 다음과 같습니다.

```text
fold-1 train
  feature characterization
  data-derived preprocessing/reference fitting
  model fitting

fold-1 validation
  protocol에 미리 정의된 candidate selection/calibration
  train에서 만든 결정을 확인하는 development validation

fold-1 test
  experiment configuration finalization 이후 한 번 사용하는
  holdout test evaluation
```

`fold-1 test`는 experiment configuration을 확정하기 전에는 feature characterization, reference discovery,
parameter 선택, 시각적 tuning에 사용하지 않습니다. Test를 관찰한 뒤 결정을 바꾸면 새로운 protocol/version으로
기록하고, 같은 test 결과를 변경된 protocol의 unbiased holdout evidence로 다시 사용하지 않습니다.

`fold-2`부터 `fold-5`는 `fold-1` holdout test 이후 **cross-fold robustness analysis**에 사용할 수 있습니다.
각 fold 내부의 train/validation/test 분리는 그대로 지키되, 해당 결과는 `fold-1` holdout test evaluation과
구분해 해석합니다. Development 중에는 다른 fold의 train/validation을 미리 열어 `fold-1 test` bearing에
간접적으로 노출되지 않습니다.

Split manifest는 계속 5-fold assignment의 Source of Truth입니다. `fold-1`을 development fold로 사용하는 연구
의미는 이 protocol이 소유하며, 실제 feature/reference/preprocessing/model input을 고정해야 하는 시점에는
version-controlled experiment configuration으로 승격합니다.

## 6. Leakage rules

모든 preprocessing, feature engineering, model fitting, threshold/statistics fitting은 다음 규칙을 지켜야 합니다.

1. bearing run은 한 fold 안에서 train/validation/test 중 정확히 하나에만 속합니다.
2. acquisition order는 lifecycle order `1..N`을 유지합니다.
3. scaler, normalizer, dimensionality reduction, feature selection, model parameter, threshold처럼 데이터에서
   학습되는 상태는 **train partition에서만 fit**합니다.
4. validation partition은 model/preprocessing 선택이나 threshold calibration이 실제로 정의된 경우에만 사용합니다.
5. test partition은 holdout test evaluation 전까지 fitting이나 parameter 선택에 사용하지 않습니다.
6. test bearing 자신의 초기 구간을 이용한 per-bearing normalization은 별도의 test-time adaptation protocol로
   명시하지 않는 한 허용하지 않습니다.
7. test trajectory를 반복해서 관찰해 feature formula, feature subset, reference-data rule을 바꾸는 행위도
   data-derived selection으로 취급합니다.
8. Experiment configuration finalization 전에는 `fold-2`~`fold-5`를 추가 development data로 사용하지 않습니다.
9. Data-derived preprocessing state는 **configured train partition 전체**에서 한 번 fit하며, model-fit sampling
   policy는 그 뒤에 적용합니다. Sampling policy는 `PreprocessingState`를 다시 fit하거나 바꾸지 않습니다.
   자세한 의미는 [`xjtu-feature-characterization.md`](xjtu-feature-characterization.md) §4를 따릅니다.

특히 `전체 데이터 feature 통계 계산 -> split` 순서의 구현은 금지합니다. Architecture 문서의
`전처리/특징 생성 -> 데이터 분할` 도식은 책임 흐름을 나타내며 learned state를 전체 데이터에 fit하라는 의미가
아닙니다.

Acquisition 하나만을 입력으로 하는 고정된 stateless feature formula는 fitted state를 만들지 않으므로 각
partition에 독립적으로 적용할 수 있습니다. 반면 어떤 feature를 유지할지, 어떻게 scaling할지, 어떤 reference
data를 사용할지 결정하는 과정은 위 partition 경계를 따라야 합니다.

## 7. Feature characterization, reference data, and anomaly labels

XJTU-SY는 complete run-to-failure trajectory를 제공하지만 acquisition별 정상/이상 onset label은 공식 source에서
직접 제공하지 않습니다. 따라서 첫 protocol은 `first 20% = healthy` 같은 가정을 ground truth로 고정하지
않습니다.

먼저 [`xjtu-feature-characterization.md`](xjtu-feature-characterization.md)에 따라 `fold-1 train` 중심의 feature
behavior, operating-condition sensitivity, bearing 간 일관성, redundancy, run-length imbalance를 관찰합니다.
Normal-condition reference 또는 별도 reference data는 반드시 만들어야 하는 결과가 아니라 가능한 experiment
configuration 중 하나입니다.

Reference window가 실제 필요해지면:

- 비율 또는 rule을 version-controlled experiment parameter로 명시하고
- train bearing에서만 reference statistics를 fit하며
- 해당 rule이 **heuristic/reference assumption**임을 ground truth와 구분합니다.

Feature set이나 reference-data rule을 test 결과를 보고 변경하면 새로운 version으로 기록하고, 같은 test 결과를
변경된 protocol의 unbiased evidence로 다시 사용하지 않습니다.

Precision, Recall, F1, PR-AUC, Early Detection Time 같은 supervised/early-warning metric도 defensible onset/label
protocol이 정의된 뒤 independent evaluator에서 계산합니다. 그 전에는 score trajectory와 feature behavior를
sanity check할 수는 있지만 이를 detection accuracy로 보고하지 않습니다.

## 8. Development evaluation criterion

첫 Isolation Forest candidate 비교에서는 acquisition-level onset label을 만들지 않습니다. Validation evidence는
각 bearing run에서 **acquisition index와 higher-is-more-anomalous anomaly score의 Spearman rank correlation**으로
요약합니다.

이 값은 anomaly score가 acquisition order와 얼마나 일관된 순위 관계를 보이는지 설명하는 통계이며
`Health Indicator monotonicity`, fault-detection accuracy 또는 prognostic performance라고 부르지 않습니다.

평가 규칙은 다음과 같습니다.

- validation bearing마다 acquisition `1..N` 전체를 사용합니다.
- bearing별 Spearman ρ를 먼저 계산하고, acquisition 수를 pooling하지 않습니다.
- 전체 요약은 bearing별 ρ의 동일가중 산술평균을 사용합니다.
- 한 bearing의 anomaly score가 상수라 correlation이 정의되지 않으면 `0`으로 대체하지 않고 undefined로 유지하며
  전체 평균도 정의하지 않습니다.
- iid significance를 가정하는 p-value를 candidate selection 근거로 사용하지 않습니다.
- early/late 구간을 임의 healthy/fault label처럼 만들어 accuracy metric을 계산하지 않습니다.

Candidate selection은 validation 결과를 실행하기 전에 다음 순서로 고정합니다.

1. bearing별 correlation이 모두 정의되어 bearing-equal mean Spearman ρ가 계산된 candidate만 selection 대상으로 둡니다.
2. mean bearing Spearman ρ가 가장 큰 candidate를 선택합니다.
3. 정확한 동률에서는 selected feature 수가 적은 candidate를 우선합니다.
4. feature 수도 같으면 원래 acquisition distribution을 보존하는 `acquisition-uniform-v1`을 우선합니다.
5. 위 조건도 같으면 `experiment_id`의 사전순으로 하나를 결정합니다.

모든 candidate의 mean이 정의되지 않으면 candidate를 선택하지 않습니다. 해당 결과는 그대로 evidence로 보존하고
새 evaluation/configuration version에서 다음 결정을 다룹니다. Tie-breaker는 primary metric이 정확히 같은 경우에만
적용하며 근소한 metric 차이를 임의 tolerance로 동률 처리하지 않습니다.

이 criterion은 `fold-1 validation`의 candidate 비교를 위한 descriptive development evidence입니다. 실제
degradation indicator나 Health Indicator 의미를 주장하려면 별도의 분석과 검증이 필요합니다.

네 candidate는 다음 명령으로 같은 production feature/preprocessing/model 경로에서 실행합니다. `code-revision`은
실행 코드가 포함된 full Git commit SHA이며, output JSON은 candidate별 config provenance, validation bearing별
observation count와 ρ, bearing-equal mean 및 선택 결과를 기록합니다.

```bash
uv run industrial-phm experiment validate xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \
  --output docs/research/results/xjtu-sy-iforest-fold-1-validation-v1.json \
  --code-revision "$(git rev-parse HEAD)"
```

현재 fold-1 validation의 authoritative numerical evidence는
[`results/xjtu-sy-iforest-fold-1-validation-v1.json`](results/xjtu-sy-iforest-fold-1-validation-v1.json)에
보존합니다. Artifact의 selection은 사전에 고정한 규칙을 그대로 적용한 결과입니다. Bearing별 correlation 방향이
서로 다른 현재 evidence는 configuration finalization에서 condition/bearing variability를 함께 검토해야 함을
보여줍니다.


### Score-trajectory diagnosis

Bearing별 Spearman ρ 하나는 **방향과 크기만** 알려주고 trajectory의 형태를 알려주지 않습니다. 같은 음의 ρ가
전체 lifecycle에 걸친 단조 감소에서 나올 수도 있고, 특정 구간이 rank mass를 지배해서 나올 수도 있습니다. 이
둘을 구분하지 못하면 configuration finalization에서 무엇을 바꿔야 하는지 결정할 수 없습니다.

따라서 candidate selection과 **별개의 development diagnosis artifact**로 acquisition별 anomaly score를 보존합니다.

```bash
uv run industrial-phm experiment validate xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \
  --output docs/research/results/xjtu-sy-iforest-fold-1-validation-v1.json \
  --code-revision "$(git rev-parse HEAD)" \
  --score-trajectory-dir data/processed/xjtu-sy/fold-1-score-trajectory
```

이 diagnosis의 경계는 다음과 같습니다.

- `--score-trajectory-dir`는 fit, score, selection 중 무엇도 바꾸지 않습니다. 같은 실행에서 이미 계산된 score를
  기록할 뿐이므로 canonical validation artifact는 flag 유무와 무관하게 동일합니다.
- `train` partition을 함께 scoring합니다. 이 값은 **in-sample**이며 model이 학습한 reference distribution이
  어떤 모양인지 설명하기 위한 것입니다. Candidate selection이나 generalization 근거로 사용하지 않습니다.
- `test` partition은 scoring하지 않습니다. Score trajectory 생성 경로는 `train`과 `validation`만 허용합니다.
- Retrospective lifecycle thirds는 최종 run length를 알아야 계산되므로 online feature가 아니라 시각적·기술적
  요약입니다. Feature characterization의 `early/middle/late_third` 구분과 같은 규칙을 사용합니다.
- Bearing별 acquisition 수가 크게 다르므로 full-run ρ와 third별 ρ를 함께 봅니다. 둘이 다른 이야기를 하면
  긴 run의 특정 구간이 full-run 요약을 지배하고 있다는 신호입니다.

Score trajectory는 detection accuracy, Health Indicator monotonicity, degradation 해석이 아닙니다.
[`xjtu-feature-characterization.md`](xjtu-feature-characterization.md) §7의 자동화 경계를 그대로 따릅니다.


### Observed fold-1 validation evidence (2026-09-18)

아래는 위 score-trajectory diagnosis로 관찰한 내용입니다. 수치의 authoritative owner는 생성 artifact이며,
여기에는 configuration finalization 판단에 필요한 관찰만 남깁니다. 네 candidate 모두 같은 방향을 보였으므로
아래 설명은 selected candidate 기준입니다.

**1. Bearing3_2의 음의 ρ는 전체 lifecycle의 단조 감소가 아닙니다.**

Lifecycle third별 ρ는 `early -0.14 / middle -0.70 / late +0.60`입니다. 즉 late third는 나머지 validation
bearing(`+0.40`, `+0.40`)과 같은 양의 방향을 보이고, full-run ρ의 부호는 middle third가 결정합니다.
Decile median anomaly score도 `0.514 → 0.447`까지 완만히 감소한 뒤 `0.482`로 다시 상승합니다.

**2. operating condition만으로는 설명되지 않습니다.**

Bearing3_2는 첫 decile부터 median `0.514`로 시작합니다. 이는 Bearing1_2/Bearing2_2가 **lifecycle 마지막**에
도달하는 수준(`0.552`, `0.528`)에 가깝습니다. 반면 같은 `40Hz10kN`의 train bearing인 Bearing3_3과 Bearing3_4는
`0.35` 부근에서 시작합니다. 따라서 `40Hz10kN`이 score를 전반적으로 올린다는 condition-only 설명은 현재
evidence와 맞지 않습니다. 조건이 다른 Bearing1_4도 in-sample에서 음의 ρ(`-0.21`)를 보이므로 방향 역전은
`40Hz10kN` 고유 현상도 아닙니다.

현재 evidence로 확정할 수 있는 것은 여기까지입니다. 즉 **Bearing3_2가 fitted reference에서 lifecycle 초기부터
높은 anomaly-score 위치에 있다**는 관찰과, condition-only 설명이 이를 설명하지 못한다는 것입니다. 왜 그 위치에
있는지는 bearing-specific initial state, feature distribution 차이, 초기 latent damage 등 여러 설명이 남아
있으므로 이 문서에서 하나의 원인으로 좁히지 않습니다.

**3. 현재 evaluation criterion은 sharp onset에 거의 반응하지 않습니다.**

`reference_strategy = all-train-observations`로 fit한 model은 train bearing Bearing3_3/Bearing3_4에서
9개 decile 동안 median score가 `0.35` 부근으로 평탄하다가 마지막 decile에서 `0.56` / `0.49`로 상승합니다.
이는 run-to-failure에서 기대할 수 있는 형태이지만, 같은 run의 full-run Spearman ρ는 `-0.16`과 `+0.06`으로
사실상 0입니다. 반대로 전 구간에 걸쳐 완만히 상승하는 Bearing1_2/Bearing2_2는 `+0.75` 부근을 받습니다.

즉 현재 criterion은 **점진적 drift를 높게, 후기 집중 onset을 낮게** 평가합니다. 이 성질은 §8 서두에서 이미
"detection accuracy가 아니다"라고 선언한 범위 안에 있지만, 같은 통계를 candidate selection의 primary metric으로
사용하고 있으므로 configuration finalization에서 함께 판단해야 합니다.

이 관찰들은 development evidence이며 holdout test를 열지 않았습니다. Criterion, candidate, selection rule은
이 관찰을 근거로 이 변경에서 수정하지 않았습니다. 변경이 필요하다고 판단되면 §8의 규칙과 candidate manifest를
새 version으로 기록합니다.

## 9. Reproducibility contract

Split assignment는 모델 코드 안에 하드코딩하지 않습니다. Downstream experiment code는
`industrial_phm.experiments.get_xjtu_reference_split()`을 통해 packaged manifest를 읽습니다.

Split manifest validation은 다음을 fail-fast로 확인합니다.

- 5개 fold 존재
- fold마다 15개 bearing run 전체 coverage
- partition 간 bearing overlap 없음
- condition마다 `train 3 / validation 1 / test 1`
- 각 bearing의 전체 protocol 등장 횟수 `train 3 / validation 1 / test 1`

이 규칙은 모델 종류와 무관합니다. Isolation Forest, LSTM Autoencoder 및 이후 모델은 같은 reference split을
사용해야 비교가 의미를 가집니다.

Development fold 선택은 split manifest의 bearing assignment를 변경하지 않습니다. 현재 baseline에서는 이 문서가
`fold-1`의 development/holdout-test 역할을 설명하고, generated artifacts는 항상 실제 `split_id`, `fold_id`,
`partition` provenance를 함께 기록해야 합니다.

## 10. Experiment lifecycle

첫 baseline은 다음 lifecycle을 따릅니다. Project-level current status는 root README가 소유합니다.

```text
versioned candidate experiment configuration
  -> train-only fitted preprocessing state
  -> Isolation Forest fit on train
  -> fold-1 development validation
  -> experiment configuration finalization
  -> fold-1 holdout test evaluation
  -> cross-fold robustness analysis
```

Feature characterization과 interactive analysis는 반복적으로 진행할 수 있습니다. 현재 결과에서 부족한 분석이
확인되면 train 범위에서 characterization을 개선하고 다시 관찰합니다. 다만 test 결과를 사용한 변경은 같은
protocol의 unbiased evaluation으로 되돌려 보고하지 않습니다. Reference-data rule, feature subset, model
hyperparameter, threshold도 실제 필요가 생긴 시점에 적절한 experiment Source of Truth로 추가합니다.
