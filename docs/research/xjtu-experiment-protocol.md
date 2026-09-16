# XJTU-SY Reference Experiment Protocol

상태: reference protocol v1

이 문서는 XJTU-SY를 이용한 첫 numerical PHM baseline이 어떤 질문을 검증하고, 어떤 데이터 분할과 leakage
규칙을 따라야 하는지 고정합니다. 모델 성능을 본 뒤 split이나 label 정의를 바꾸는 일을 막기 위해 모델 구현보다
먼저 version-controlled protocol을 둡니다.

## 1. Evidence boundary

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
> pipeline이 재현 가능한 anomaly/degradation score trajectory를 생성할 수 있는가?

따라서 첫 단계의 task는 acquisition-level **unsupervised anomaly/degradation scoring**입니다.

이번 protocol에서 아직 하지 않는 것:

- supervised fault-class classification
- acquisition별 failure-onset ground truth 생성
- 마지막 일정 비율을 임의로 anomaly label로 간주
- sample-level RUL target 생성
- cross-condition generalization 성능 주장

RUL은 degradation trajectory와 lifecycle-level target 계약이 실제로 필요하다고 확인된 뒤 별도 protocol에서
다룹니다.

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

## 5. Leakage rules

모든 preprocessing, feature engineering, model fitting, threshold/statistics fitting은 다음 규칙을 지켜야 합니다.

1. bearing run은 한 fold 안에서 train/validation/test 중 정확히 하나에만 속합니다.
2. acquisition order는 lifecycle order `1..N`을 유지합니다.
3. scaler, normalizer, dimensionality reduction, feature selection, model parameter, threshold처럼 데이터에서
   학습되는 상태는 **train partition에서만 fit**합니다.
4. validation partition은 model/preprocessing 선택이나 threshold calibration이 실제로 정의된 경우에만 사용합니다.
5. test partition은 최종 평가 전까지 fitting이나 parameter 선택에 사용하지 않습니다.
6. test bearing 자신의 초기 구간을 이용한 per-bearing normalization은 별도의 test-time adaptation protocol로
   명시하지 않는 한 허용하지 않습니다.

특히 `전체 데이터 feature 통계 계산 -> split` 순서의 구현은 금지합니다. Architecture 문서의
`전처리/특징 생성 -> 데이터 분할` 도식은 책임 흐름을 나타내며 learned state를 전체 데이터에 fit하라는 의미가
아닙니다.

## 6. Normal reference and anomaly labels

XJTU-SY는 complete run-to-failure trajectory를 제공하지만 acquisition별 정상/이상 onset label은 공식 source에서
직접 제공하지 않습니다. 따라서 첫 split protocol은 `first 20% = healthy` 같은 가정을 ground truth로 고정하지
않습니다.

다음 preprocessing/feature PR에서 normal-reference window가 필요해지면:

- 비율 또는 rule을 version-controlled experiment parameter로 명시하고
- train bearing에서만 reference statistics를 fit하며
- 해당 rule이 **heuristic/reference assumption**임을 ground truth와 구분합니다.

Precision, Recall, F1, PR-AUC, Early Detection Time 같은 supervised/early-warning metric도 defensible onset/label
protocol이 정의된 뒤 independent evaluator에서 계산합니다. 그 전에는 score trajectory와 feature behavior를
sanity check할 수는 있지만 이를 detection accuracy로 보고하지 않습니다.

## 7. Reproducibility contract

Split assignment는 모델 코드 안에 하드코딩하지 않습니다. Downstream experiment code는
`industrial_phm.experiments.get_xjtu_reference_split()`을 통해 packaged manifest를 읽습니다.

Production validator는 다음을 fail-fast로 확인합니다.

- 5개 fold 존재
- fold마다 15개 bearing run 전체 coverage
- partition 간 bearing overlap 없음
- condition마다 `train 3 / validation 1 / test 1`
- 각 bearing의 전체 protocol 등장 횟수 `train 3 / validation 1 / test 1`

이 규칙은 모델 종류와 무관합니다. Isolation Forest, LSTM Autoencoder 및 이후 모델은 같은 reference split을
사용해야 비교가 의미를 가집니다.

## 8. Next implementation boundary

이 protocol 이후의 다음 구현 단계는 다음 순서입니다.

```text
reference split
  -> leakage-free numerical feature boundary
  -> train-only preprocessing state
  -> Isolation Forest reference model
  -> independent evaluation
```

Feature set, normal-reference rule, model hyperparameter, threshold는 이 문서에 미리 고정하지 않습니다. 실제
preprocessing/feature 요구와 evidence가 생길 때 별도 experiment config로 추가합니다.
