# XJTU-SY RUL v1 Finalization Decision

상태: frozen decision before held-out benchmark  
Protocol: `xjtu-sy-rul-prognostics-protocol-v1`

이 문서는 fold-1 validation numerical evidence를 본 뒤 새로운 selection rule을 만들지 않고, 이미
`docs/research/xjtu-rul-prognostics-protocol.md` §8과 §10에 고정된 규칙을 적용해 RUL v1의
candidate finalization과 uncertainty 범위를 기록합니다.

## 1. 입력 evidence

Authoritative development artifact:

`docs/research/results/xjtu-sy-rul-three-model-fold-1-validation-v1.json`

공통 acquisition 8..N support에서 기록된 equal-bearing mean MAE:

| method | mean asset MAE | normalized MAE |
| --- | ---: | ---: |
| age-only | 844.889 | 1.1172 |
| feature-Ridge | 421.728 | 0.5346 |
| temporal LSTM | 415.966 | 0.3263 |

이 결과는 fold-1 validation development evidence입니다. Held-out benchmark 또는 field validation이 아닙니다.

## 2. Validation-selected candidate

Protocol §8은 candidate comparison이 필요한 경우 validation bearing만 사용하고, primary selection metric을
bearing별 MAE의 equal-bearing mean으로 고정했습니다. Exact tie일 때만 normalized MAE, parameter count,
experiment/configuration ID 순으로 tie-break합니다.

위 frozen rule을 그대로 적용하면:

```text
validation_selected_method_id = xjtu-sy-rul-lstm-fold-1-v1
```

입니다.

이 결정은 결과를 본 뒤 새로운 tolerance, per-bearing majority rule, Bearing3_2 우선 rule 또는 다른 metric을
도입한 것이 아닙니다. Aggregate MAE에서 temporal LSTM과 feature-Ridge의 차이가 작고 Bearing3_2에서는
Ridge의 MAE가 더 낮다는 관찰은 model limitation evidence로 보존하지만, 이미 고정한 selection rule을
소급 변경하는 근거로 사용하지 않습니다.

## 3. Operational primary와 분리

Validation-selected candidate는 operational answer가 아닙니다.

현재 상태:

```text
validation_selected_method_id = xjtu-sy-rul-lstm-fold-1-v1
operational_primary_method_id = null
```

Operational primary를 선언하려면 현재 evidence가 제공하지 않는 field/generalization evidence,
validated physical failure semantics, uncertainty/decision boundary가 추가로 필요합니다.

Analysis Explorer와 Generative AI는 held-out benchmark가 추가되더라도 operational primary가 별도로
검증되기 전에는 development/benchmark evidence를 maintenance deadline이나 live RUL answer로 승격하지 않습니다.

## 4. Uncertainty v1 decision

RUL protocol §10은 prediction interval capability를 제공하려면 method/configuration,
fit/calibration population, nominal level, held-out bearing별 empirical coverage와 interval width,
aggregate rule, assumptions/limitations을 함께 기록하도록 요구합니다.

현재 fold-1 validation population은 bearing 3개뿐이며, 같은 bearing 안의 acquisition/window는 시간적으로
종속됩니다. 많은 window를 iid calibration sample처럼 취급해서 nominal coverage를 주장할 근거가 없습니다.

따라서 RUL v1에서는:

```text
prediction_interval = unsupported/not validated
uncertainty_calibration = unsupported/not validated
```

로 freeze합니다.

임의 `estimate ± percent`, validation residual quantile을 window-iid로 취급한 conformal interval,
또는 모델 간 prediction span을 uncertainty interval로 표시하지 않습니다.

향후 uncertainty capability는 별도 protocol/configuration version에서 calibration population과 grouping
assumption을 먼저 고정한 뒤 추가합니다. RUL v1 held-out benchmark는 point prediction evidence만 생성합니다.

## 5. Held-out benchmark boundary

다음 numerical execution은 frozen temporal LSTM candidate로 fold-1 held-out bearing을 평가합니다.

```text
Bearing1_1
Bearing2_1
Bearing3_1
```

Project history에서 이 bearing들은 기존 anomaly/robustness 연구에 이미 노출된 적이 있으므로 결과는
`protocol-frozen retrospective benchmark evidence`로 기록합니다.

다음 표현은 사용하지 않습니다.

- pristine external holdout
- independent external validation
- field RUL validation
- validated physical failure-time prediction
- operational maintenance recommendation

Held-out 결과를 본 뒤 같은 RUL v1 configuration, target, lifecycle segmentation, evaluation metric 또는
selection rule을 수정해 같은 benchmark를 다시 unbiased evidence로 재사용하지 않습니다.

## 6. Benchmark 전에 남은 implementation

Held-out 실행 전에 protocol §9.1의 lifecycle-position diagnostics를 구현합니다.

- recorded lifecycle early / middle / late thirds
- per-bearing prediction count
- MAE
- mean signed error
- 필요 시 normalized MAE
- aggregate는 bearing별 metric을 먼저 계산한 equal-bearing mean
- selection metric은 변경하지 않음
- diagnostic은 state/degradation-onset label이 아님

그 뒤 frozen candidate benchmark runner/result schema를 추가하고 prepared XJTU source가 있는 clean tracked
checkout에서 numerical artifact를 생성합니다.

## 7. 실행된 held-out benchmark 기록

§6의 implementation이 완료된 뒤 runbook 절차대로 benchmark를 실행했습니다. 이 절은 실행 사실과 기록된
숫자만 남기며, 결과를 본 뒤 새로운 판정 기준이나 threshold를 만들지 않습니다.

```text
execution revision : 2ae41acc16c45bf922f3b6ad8a228103d16d0982
prepared source    : 3 conditions / 15 bearing runs / 9,216 acquisitions (profile PASS)
run 1 / run 2      : byte-identical
sha256             : 874860c9a959e62311e959dc4609b022058cfb75ca4f107cf901d43b641b0fbf
artifact           : docs/research/results/xjtu-sy-rul-lstm-fold-1-benchmark-v1.json
```

Equal-bearing mean point evidence (acquisition interval 단위, 3,131 predictions):

| metric | value |
| --- | ---: |
| mean asset MAE | 458.251 |
| mean asset RMSE | 541.233 |
| mean asset signed error | -445.204 |
| mean asset normalized MAE | 0.3313 |

Bearing별 기록:

| bearing | predictions | MAE | RMSE | signed | normalized MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bearing1_1 | 116 | 21.927 | 26.960 | 0.872 | 0.1797 |
| Bearing2_1 | 484 | 170.636 | 209.261 | -156.695 | 0.3482 |
| Bearing3_1 | 2,531 | 1,182.190 | 1,387.477 | -1,179.790 | 0.4660 |

Lifecycle-position diagnostic (evaluation-only, equal-bearing mean):

| position | predictions | MAE | normalized MAE |
| --- | ---: | ---: | ---: |
| early | 1,030 | 790.831 | 0.5585 |
| middle | 1,051 | 455.316 | 0.3289 |
| late | 1,050 | 133.096 | 0.1139 |

기록된 관찰:

- Absolute error는 recorded run length와 같은 방향으로 커졌습니다. 가장 짧은 Bearing1_1의 MAE가 가장
  작고 가장 긴 Bearing3_1이 가장 큽니다. Normalized MAE에서도 같은 순서가 유지되므로 run length로
  normalize해도 순서가 뒤집히지 않았습니다. 이 관찰은 원인 설명이 아니며, 3개 bearing으로 run length
  효과와 operating condition 효과를 분리할 수 없습니다.
- Signed error는 Bearing2_1과 Bearing3_1에서 크게 음수입니다. 기록된 잔여 수명을 과소추정한 방향입니다.
  Bearing1_1의 signed error는 +0.872로 거의 0입니다.
- Lifecycle position별 error는 early에서 late로 단조 감소했습니다. Lifecycle thirds는 complete recorded
  lifecycle 기준의 retrospective evaluation-only diagnostic이며 degradation-onset label이 아닙니다.

한계:

- 이 bearing들은 project history의 anomaly/robustness 연구에 이미 노출된 적이 있으므로 pristine external
  holdout이나 independent external validation이 아닙니다.
- `operational_primary_method_id`는 `null`로 유지됩니다.
- prediction interval, uncertainty calibration, validated physical failure threshold, field RUL validation,
  maintenance decision recommendation은 모두 unsupported입니다.
- Protocol §8에 따라 이 결과를 본 뒤 RUL v1의 target, split, feature schema, sequence, LSTM configuration,
  lifecycle boundary, primary metric, selection rule, uncertainty policy를 변경하지 않습니다.
