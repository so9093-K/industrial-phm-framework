# IMS Bearing Reference Experiment Protocol

상태: reference protocol v1 / numerical execution not yet performed

이 문서는 IMS Bearing Data Set에서 첫 numerical model experiment가 어떤 source scope, split, feature,
reference, model, evaluation 의미를 사용할지 **결과를 보기 전에** 고정합니다. Source 구조와 canonical mapping은
[`ims-source-profile.md`](ims-source-profile.md)가 소유하고, 이 문서는 그 위에서 experiment 의미만 소유합니다.

## 1. 첫 질문

첫 IMS experiment의 목적은 IMS에서 fault-detection 성능이나 RUL 성능을 주장하는 것이 아닙니다.

> XJTU에서 검증한 dataset-neutral feature / preprocessing / Isolation Forest interface를, IMS의 test-level
> 독립성과 single-channel schema를 존중하면서 별도 tuning 없이 실행할 수 있는가?

따라서 첫 task는 **cross-test unsupervised anomaly scoring portability**입니다. Model output은
higher-is-more-anomalous score이며, acquisition-level fault label, failure onset, Health Indicator 또는 RUL을
정의하지 않습니다.

## 2. Source scope

첫 experiment는 sensor schema가 동일한 Set 2와 Set 3만 사용합니다.

| role | IMS source | scope | acquisition count | canonical bearing vectors |
| --- | --- | --- | ---: | ---: |
| train/reference/model fit | Set 2 | complete archive set | 984 | 3,936 |
| one-time cross-test evaluation | Set 3 | `readme-documented` only | 4,448 | 17,792 |

Set 1은 bearing당 2-channel이고 Set 2/3은 bearing당 1-channel이므로 첫 experiment에서 섞지 않습니다.
Set 1은 이후 별도 2-channel configuration 질문으로 남깁니다.

Set 3의 `archive-extension` 1,876 acquisitions은 v1의 train, scoring, diagnosis, tuning 어디에도 사용하지
않습니다. V1 execution은 full prepared-source profile을 검증한 뒤 Set 3에서
`archive_scope = readme-documented`인 처음 4,448 acquisitions만 선택합니다. Archive extension을 나중에
분석하려면 별도 post-evaluation protocol/version으로 기록하며 v1의 독립 평가를 소급 변경하지 않습니다.

## 3. Split unit과 leakage 경계

IMS의 split unit은 **test 전체**입니다. 한 test의 네 bearing은 같은 shaft에서 동시에 기록되어 acquisition
timeline을 공유하므로, 같은 test 안에서 bearing을 train/evaluation으로 나누지 않습니다.

V1 assignment는 하나뿐입니다.

```text
split_id: ims-single-channel-cross-test-v1
fold_id:  fold-1

train
  set-2-bearing-{1..4}
  acquisition_index 1..984

evaluation
  set-3-bearing-{1..4}
  archive_scope = readme-documented
  acquisition_index 1..4448
```

별도 validation partition은 두지 않습니다. V1에는 candidate grid, model selection, threshold calibration이
없기 때문입니다. Set 3 numerical score를 보기 전에 configuration을 하나로 고정하고, 그 뒤 한 번의
cross-test evaluation만 수행합니다.

Set 3 결과를 본 뒤 feature/reference/model parameter를 바꾸면 새 experiment version이며, 같은 Set 3
readme-documented 결과를 변경된 configuration의 새로운 unbiased evidence로 다시 사용하지 않습니다.

여기서 `one-time`은 공개 IMS source의 구조나 test 종료 범위가 blind하다는 뜻이 아닙니다. Source profile,
acquisition count, timestamp range와 README-documented scope는 이미 알려져 있습니다. One-time 경계가
보호하는 것은 **이 프로젝트의 model score와 그 numerical evaluation을 configuration freeze 전에 selection에
사용하지 않는 것**입니다.

## 4. Feature schema

Feature formula는 기존 `vibration-statistical-v1`을 그대로 사용합니다. Set 2/3의 canonical channel은
`vibration` 하나이므로 selected feature는 다음 8개 전부입니다.

```text
feature.vibration.mean
feature.vibration.rms
feature.vibration.standard_deviation
feature.vibration.absolute_peak
feature.vibration.peak_to_peak
feature.vibration.crest_factor
feature.vibration.skewness
feature.vibration.excess_kurtosis
```

XJTU에서 제거 후보였던 feature subset이나 robust scaling 축을 IMS에서 다시 열지 않습니다. 첫 portability
experiment는 feature selection을 하지 않고 full single-channel v1 schema를 사용합니다.

## 5. Reference, preprocessing, sampling

XJTU의 `train-bearing-early-third-v1`은 bearing별 retrospective lifecycle을 전제로 하므로 IMS에 복사하지
않습니다. IMS v1 reference는 다음처럼 고정합니다.

```text
reference_strategy = all-train-observations
```

즉 Set 2의 complete 984 acquisitions × 4 bearings = **3,936 canonical feature vectors 전체**가 reference-eligible
population입니다. 이는 healthy reference를 뜻하지 않으며, complete Set 2 distribution에 대한 rarity model을
fit한다는 뜻입니다.

Preprocessing과 model fit 순서는 다음과 같습니다.

```text
complete Set 2 source/profile validation
  -> 3,936 feature vectors 생성
  -> preprocessing fit on complete train
  -> identity transform
  -> all-train-observations reference eligibility
  -> acquisition-uniform-v1 model-fit input
  -> Isolation Forest fit
```

V1에서는 scaling은 `identity`, sampling은 `acquisition-uniform-v1`입니다. 모든 Set 2
bearing-acquisition vector를 정확히 한 번 model fit에 사용하며, bearing balancing이나 resampling을 추가하지
않습니다.

Artifact는 다음 population count를 분리해 기록해야 합니다.

- complete train observation count = 3,936
- reference-eligible observation count = 3,936
- model-fit observation count = 3,936

## 6. Model configuration

Model family와 parameter는 XJTU finalized configuration에서 이미 사용한 Isolation Forest 설정을 그대로
가져옵니다. 이것은 IMS에 최적이라고 주장하는 선택이 아니라 **IMS 결과를 보기 전에 model axis를 닫아
portability 질문만 남기기 위한 고정값**입니다.

```text
model_family   = isolation-forest
n_estimators   = 256
max_samples    = auto
contamination  = auto
max_features   = 1.0
bootstrap      = false
random_seed    = 42
```

IMS v1에는 model parameter candidate가 없습니다.

## 7. Acquisition order와 completeness

IMS acquisition order는 Adapter가 filename timestamp를 정렬해 부여한 `acquisition_index`를 사용합니다.

- Set 2: 각 bearing에 정확히 `1..984`
- Set 3 readme-documented: 각 bearing에 정확히 `1..4448`
- 같은 test의 네 bearing은 각 acquisition index를 모두 공유해야 함

Set 1/3에 존재하는 restart/gap은 timestamp provenance로 보존하지만 V1에서는 missing interval을 삽입하거나
elapsed-time grid로 재표본화하지 않습니다. Evaluation의 순서 변수는 physical elapsed seconds가 아니라
**observed acquisition order**입니다.

Execution은 profile의 timestamp uniqueness와 source count를 먼저 검증하고, experiment edge에서 위 scope별
acquisition coverage와 네-bearing 동기 coverage를 fail-fast로 확인해야 합니다.

## 8. Evaluation statistic의 의미

Set 3 scoring은 네 evaluation bearing 전체 acquisition에 대해 한 번 수행합니다. Bearing별로 다음 두
descriptive statistic을 기록합니다.

1. full-run acquisition-order Spearman ρ
2. test-stage `late_vs_middle_rank_probability`

두 번째 통계는 Set 3의 **공유 test timeline**을 retrospective thirds로 나눈 뒤 middle third와 late third의
score rank를 비교합니다. 이 thirds는 bearing별 failure lifecycle segment가 아니라 동일한 Set 3
acquisition timeline의 **test-stage segment**입니다.

Boundary는 결과 전에 다음처럼 고정합니다. Acquisition position을 0-based `p`, 전체 observation 수를 `N`이라
할 때 `p < ceil(N/3)`은 early, `ceil(N/3) <= p < ceil(2N/3)`은 middle, 나머지는 late입니다.
Set 3 readme-documented `N=4448`에서는 각 bearing의 segment count가 early 1,483 / middle 1,483 /
late 1,482가 됩니다.

`late_vs_middle_rank_probability`는 middle score `m`과 late score `l`의 모든 pair에 대해:

```text
l > m  -> 1
l = m  -> 0.5
l < m  -> 0
```

를 평균합니다.

Summary는 네 bearing의 동일가중 평균만 기록합니다. Acquisition pooling, run-length weighting, p-value,
threshold, pass/fail criterion, bearing ranking은 추가하지 않습니다. Score가 상수라 Spearman ρ가 정의되지
않거나 middle/late segment가 비어 statistic을 계산할 수 없으면 `0`으로 대체하지 않고 canonical execution
전체를 실패시킵니다.

IMS canonical metadata에는 `operating_condition` key를 새로 만들지 않습니다.
`rotational_speed_rpm=2000`과 `radial_load_lb=6000`은 experiment provenance로 기록하되 condition grouping
축으로 사용하지 않습니다.

두 statistic 모두 anomaly score의 temporal shape를 설명할 뿐이며 다음을 뜻하지 않습니다.

- fault detection accuracy
- fault-onset accuracy
- Health Indicator monotonicity
- degradation score 품질
- prognostic/RUL performance

## 9. Source failure description 사용 경계

V1은 source README에 기술된 어떤 bearing의 최종 failure description도 label, target, candidate selection,
metric 정의에 사용하지 않습니다. Repository가 아직 acquisition-level onset ground truth를 소유하지 않기
때문입니다.

향후 failure-element evidence를 사용하려면 source evidence를 별도 contract로 승격하고, 그 뒤 새로운
supervised/early-warning protocol에서 사용합니다.

## 10. 실행 순서와 재현성

Numerical result를 보기 전에 다음 순서를 지킵니다.

```text
this protocol decision
  -> dataset-owned IMS split/config + execution contract 구현
  -> implementation/tests merge
  -> clean main commit SHA로 one-time Set 3 cross-test evaluation
  -> generated result artifact 기록
```

Protocol PR에는 numerical score를 포함하지 않습니다. 다음 implementation PR도 실제 Set 3 result를 포함하지
않고, source scope / split / config / population / scoring contract와 synthetic contract tests만 고정합니다.

실제 execution artifact에는 최소 다음 provenance가 있어야 합니다.

- schema ID와 40-character code revision
- dataset/split/fold ID
- train test ID와 evaluation test ID
- Set 3 source scope = `readme-documented`
- selected 8-feature schema
- reference/scaling/sampling/model parameter/seed
- complete train / reference / model-fit observation count
- evaluation bearing별 full-run observation count와 두 statistic
- four-bearing equal-weight mean
- rotational speed / radial load context

한 bearing이라도 scope/coverage/statistic contract를 만족하지 못하면 partial canonical result를 기록하지
않습니다.

## 10.1 관찰된 one-time cross-test 결과

Clean main revision `37e876da301f13acee4081178b4cb33bfa5cc415`에서 preregistered 실행을 한 번 수행했습니다.
Authoritative numerical evidence는
[`results/ims-bearings-iforest-single-channel-cross-test-v1.json`](results/ims-bearings-iforest-single-channel-cross-test-v1.json)에
보존합니다. 실행 전 `data validate ims-bearings`는 profile/waveform compatibility 모두 `PASS`였고, CLI가
출력한 effective plan은 이 protocol이 고정한 scope와 일치했습니다.

Population flow는 complete train 3,936 / reference 3,936 / model fit 3,936 / scoring 17,792입니다.
Set 1과 Set 3 `archive-extension`은 실행 범위에서 제외됐습니다.

| bearing | N | middle stage | late stage | ρ | `late_vs_middle` |
| --- | ---: | ---: | ---: | ---: | ---: |
| set-3-bearing-1 | 4,448 | 1,483 | 1,482 | 0.1148 | 0.5549 |
| set-3-bearing-2 | 4,448 | 1,483 | 1,482 | 0.0579 | 0.4852 |
| set-3-bearing-3 | 4,448 | 1,483 | 1,482 | -0.0816 | 0.3735 |
| set-3-bearing-4 | 4,448 | 1,483 | 1,482 | -0.4017 | 0.3585 |
| **four-bearing equal-weight mean** | | | | **-0.0776** | **0.4430** |

**Set 3에서는 late stage anomaly score가 middle stage보다 일관되게 높아지는 temporal-shape pattern이
관찰되지 않았습니다.** 네 bearing 중 셋의 `late_vs_middle`이 `0.5` 아래이고 four-bearing equal-weight mean은
`0.4430`이었습니다. 이는 preregistered descriptive statistic에 대한 관찰이며, configuration 전체의
portability 성공/실패 판정이 아닙니다. §8이 pass/fail criterion을 두지 않기로 고정했으므로 이 문서도 그런
판정을 사후에 도입하지 않습니다.

Acquisition-order Spearman ρ는 bearing별로 `+0.1148`에서 `-0.4017`까지 방향과 크기가 달랐고, four-bearing
equal-weight mean은 `-0.0776`이었습니다. 평균이 `0`에 가까운 것은 bearing 간 방향이 일관되지 않아 상쇄된
결과이며 개별 run에 관계가 없다는 뜻이 아닙니다. 따라서 Set 3 bearing 전반에서 일관된 positive
acquisition-order association은 관찰되지 않았습니다.

정확한 관찰 범위는 **Set 2 전체 distribution을 reference로 학습한, XJTU에서 가져온 고정 Isolation Forest
configuration이 Set 3에서 preregistered temporal-shape statistic상 일관된 later-stage increase를 보이지
않았다**까지입니다. IMS-specific tuning을 수행하지 않았고 reference/feature/model parameter도 실행 전에
고정한 값을 그대로 사용했으므로, 이 결과는 "IMS에서 Isolation Forest anomaly scoring이 불가능하다"는 주장이
아닙니다. 또한 §8의 경계에 따라 fault-onset accuracy, thresholded State Detection, Health Assessment/Health
Indicator 품질, fault diagnostics, Prognostic Assessment/RUL 중 어느 것도 의미하지 않습니다.

§9에 따라 source README의 failure description은 이 해석에 사용하지 않았습니다. 어떤 bearing의 통계가 낮은지를
failure element와 연결해 설명하지 않습니다.

이 결과를 근거로 feature schema, reference strategy, sampling policy, scaling strategy, model parameter,
evaluation statistic 중 어느 것도 조정하지 않았습니다. 같은 Set 3 scope를 변경된 configuration의 fresh
evidence로 재사용하지 않으며, 변경이 필요하다면 새 protocol/experiment version으로 기록합니다.

## 11. V1에서 하지 않는 것

- Set 1과 Set 2/3를 하나의 model feature schema로 합치기
- Set 3 archive-extension 사용
- bearing별 train/evaluation split
- XJTU early-third reference 재사용
- IMS 결과 기반 feature/reference/model tuning
- threshold calibration
- failure bearing label 사용
- supervised fault classification
- Health Indicator 또는 degradation score 명명
- RUL target 생성
- Set 3 결과를 본 뒤 같은 evaluation을 새로운 configuration의 fresh holdout으로 재사용
