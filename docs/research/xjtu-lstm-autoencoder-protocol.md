# XJTU LSTM Autoencoder Development Protocol

상태: development protocol v1 / numerical execution 전 사전 고정

Protocol ID: `xjtu-lstm-autoencoder-fold-1-development-v1`

이 문서는 XJTU-SY acquisition-level feature sequence를 사용하는 첫 LSTM Autoencoder experiment의 질문,
population, sequence construction, reconstruction score와 evidence 해석을 구현 및 numerical result보다 먼저
고정합니다. Dataset split과 일반 leakage 규칙은
[`xjtu-experiment-protocol.md`](xjtu-experiment-protocol.md), pipeline 표시 의미는
[`xjtu-ims-pipeline-transparency-review.md`](xjtu-ims-pipeline-transparency-review.md)가 소유합니다.

## 1. Research question and evidence class

첫 질문은 다음과 같습니다.

> XJTU의 기존 acquisition-level 16-feature sequence에서, train bearing의 heuristic early-life reference만
> 학습한 LSTM Autoencoder가 unseen validation bearing에 대해 재현 가능한 higher-is-more-anomalous
> reconstruction-error trajectory를 생성할 수 있는가?

이 experiment는 **retrospective development benchmark**입니다. Isolation Forest의 fold-1 validation,
holdout과 cross-fold evidence를 이미 관찰한 뒤 두 번째 model protocol을 정의하므로, LSTM 결과를 새로운 blind
holdout 성능이나 unbiased model-family 우위로 해석하지 않습니다.

현재 capability는 다음으로 제한합니다.

```text
available
- sequence reconstruction
- reconstruction-error anomaly scoring
- descriptive score-trajectory evaluation
- feature-level reconstruction residual evidence

unsupported / not validated
- thresholded state detection
- fault-onset detection
- health assessment
- fault diagnostics
- prognostics / RUL
```

## 2. Dataset and partition scope

첫 consumer는 XJTU-SY이며 기존 `xjtu-sy-condition-stratified-5fold-v1`의 `fold-1` assignment를 그대로
사용합니다.

| role | partition | bearing runs | acquisition count |
| --- | --- | ---: | ---: |
| preprocessing fit / reference / model fit | train | 9 | 3,246 |
| development scoring and evaluation | validation | 3 | 2,818 |
| excluded from protocol v1 | test | 3 | 3,152 |

`fold-1 test`는 Isolation Forest configuration의 one-shot holdout으로 이미 소진됐습니다. Folds 2~5도 해당
configuration의 post-holdout robustness evidence로 관찰됐습니다. Protocol v1은 이 partition들을 LSTM
scoring, parameter 선택, diagnosis 또는 결과 주장에 사용하지 않습니다.

새 independent dataset이나 사전에 격리된 source가 생기기 전까지 LSTM evidence는 development scope로
표시합니다. 이후 test/cross-fold 실행이 연구상 필요하면 별도 retrospective protocol version으로 기록합니다.

## 3. Feature, preprocessing and reference

Feature formula와 순서는 `vibration-statistical-v1` full 16 schema를 사용합니다. 이는 XJTU finalized
Isolation Forest와 같은 H/V feature information을 사용하기 위한 선택이며, 이 protocol에서 14-feature subset을
다시 비교하지 않습니다.

처리 순서는 다음과 같습니다.

```text
fold-1 complete train acquisitions (3,246)
  -> fit robust PreprocessingState on complete train
  -> transform complete train
  -> train-bearing-early-third-v1 reference eligibility (1,084)
  -> construct reference windows
  -> LSTM Autoencoder fit

fold-1 validation acquisitions (2,818)
  -> transform with the same train-fitted PreprocessingState
  -> construct full-run validation windows
  -> reconstruction scoring
```

Scaling은 `robust`로 고정합니다. Feature별 median과 IQR은 complete `fold-1 train` 3,246 observations에서만
fit하고, zero-IQR 처리는 기존 `PreprocessingState` contract를 따릅니다. Gradient/MSE 기반 model에서 feature
scale이 reconstruction loss를 임의로 지배하지 않게 하는 model-specific 선택입니다.

Reference는 `train-bearing-early-third-v1`입니다. 각 train bearing의 최종 run length를 이용하는 retrospective
heuristic이며 acquisition-level normal ground truth가 아닙니다. Model은 “검증된 정상 상태”가 아니라 이
heuristic reference distribution의 sequence를 재구성하도록 학습합니다.

Preprocessing statistics는 sampling이나 sequence construction보다 먼저 complete train에서 fit합니다. Reference
window 수나 run length가 scaling state를 바꾸지 않으므로 preprocessing, reference와 sequence 축의 책임을
분리합니다.

## 4. Sequence Construction v1

Sequence construction은 `Preprocessing`과 `Model Fit` 사이의 명시적 pipeline stage입니다.

```text
sequence_id          = bearing-run asset_id
window_id            = sequence_id + start acquisition + end acquisition
window_length        = 8 acquisitions
stride               = 1 acquisition
feature_width        = 16
input shape          = [8, 16]
ordering             = ascending acquisition_index
boundary             = one asset + one partition + one contiguous acquisition run
padding              = none
partial window       = excluded
score alignment      = right edge / window end acquisition
```

길이 8은 모든 train bearing을 fit population에 유지하는 첫 engineering baseline입니다. 가장 짧은 train run인
`Bearing2_4`는 42 acquisitions이고 early-third reference가 14 acquisitions입니다. 길이 8에서는 이 bearing도
7개 reference window를 제공합니다. 이 선택이 물리적으로 최적인 degradation timescale이라는 주장은 하지
않으며 v1 numerical result를 본 뒤 같은 protocol에서 길이를 조정하지 않습니다.

Window는 asset, partition 또는 reference boundary를 넘지 않습니다. Feature row를 global table에서 연속으로
잘라 bearing 끝과 다음 bearing 시작을 연결하는 동작을 허용하지 않습니다. Window 생성 전에 asset별 acquisition
identity가 정확히 `1..N`으로 연속인지 검증합니다.

Stride 1 window는 오른쪽 끝 acquisition에 하나의 score를 정렬합니다. 각 asset의 첫 7 acquisitions에는 complete
history가 없으므로 score를 만들지 않으며 padding이나 임의 값으로 채우지 않습니다. 이 prefix drop을
asset별·partition별 provenance로 기록합니다.

인접 window는 7개 acquisition을 공유합니다. 따라서 window를 독립 표본으로 간주하는 p-value나 confidence
interval을 계산하지 않습니다. Overlap은 acquisition-resolution score를 만들기 위한 construction semantics이며
별도의 evidence replication을 뜻하지 않습니다.

### Frozen population arithmetic

길이 `L=8`, stride `S=1`일 때 contiguous sequence 길이 `N`의 window 수는 `N-L+1`입니다.

Train reference population은 다음과 같습니다.

| train bearing | full acquisitions | early-third reference | fit windows |
| --- | ---: | ---: | ---: |
| Bearing1_3 | 158 | 53 | 46 |
| Bearing1_4 | 122 | 41 | 34 |
| Bearing1_5 | 52 | 18 | 11 |
| Bearing2_3 | 533 | 178 | 171 |
| Bearing2_4 | 42 | 14 | 7 |
| Bearing2_5 | 339 | 113 | 106 |
| Bearing3_3 | 371 | 124 | 117 |
| Bearing3_4 | 1,515 | 505 | 498 |
| Bearing3_5 | 114 | 38 | 31 |
| **Total** | **3,246** | **1,084** | **1,021** |

Validation scoring population은 다음과 같습니다.

| validation bearing | source acquisitions | scoring windows | dropped prefix |
| --- | ---: | ---: | ---: |
| Bearing1_2 | 161 | 154 | 7 |
| Bearing2_2 | 161 | 154 | 7 |
| Bearing3_2 | 2,496 | 2,489 | 7 |
| **Total** | **2,818** | **2,797** | **21** |

Model fit population의 단위는 acquisition이 아니라 **window**입니다. Inspection과 result artifact는
`reference acquisition count = 1,084`와 `model-fit window count = 1,021`을 별도 필드로 유지합니다.

모든 1,021 reference window를 epoch마다 정확히 한 번 사용합니다. Batch 순서만 seeded shuffle하며 bearing
balancing, resampling 또는 sample weighting은 적용하지 않습니다. 이 policy는
`reference-window-uniform-v1`로 식별합니다. 긴 reference sequence가 더 많은 window를 제공한다는 population
특성은 artifact와 inspection에서 표시합니다.

## 5. Model and training configuration

V1은 하나의 deterministic baseline configuration만 사용하며 validation metric으로 architecture candidate를
선택하지 않습니다.

```text
model family               lstm-autoencoder
input                      8 x 16 robust-scaled feature sequence
encoder                    1 unidirectional LSTM layer, hidden size 32
latent                     encoder final hidden vector, width 32
decoder input              latent vector repeated for 8 steps
decoder                    1 unidirectional LSTM layer, hidden size 32
output                     timestep-wise linear projection to 16 features
reconstruction order       chronological input order
dropout                    0

loss                       mean squared reconstruction error over time x feature
optimizer                  Adam
learning rate              0.001
Adam beta1 / beta2         0.9 / 0.999
Adam epsilon               1e-8
weight decay               0
gradient clipping          global norm 1.0
batch size                 64
epochs                     50 fixed
early stopping             none
checkpoint                 final epoch
numeric precision          float32
random seed                42
reference execution        CPU deterministic mode
```

Reference runtime은 [ADR-0006](../adr/0006-use-pytorch-cpu-reference-runtime.md)에 따라 PyTorch 2.14 CPU로
고정합니다. 구현은 위 수학·shape·seed 의미를 보존하고 실제 framework version, deterministic setting과 device를
artifact provenance에 기록해야 합니다. Runtime 제약으로 위 configuration을 구현할 수 없으면 numerical result를
만들기 전에 protocol version을 갱신합니다.

Training은 non-finite input, loss, gradient 또는 reconstructed value를 실패로 처리합니다. Final artifact에는
epoch별 train loss, final loss, model parameter count, runtime/library version과 seed를 기록합니다. Fixed 50
epochs는 최적 epoch 주장이나 convergence 보장이 아니라 validation-driven stopping decision을 추가하지 않는 첫
재현성 기준입니다.

## 6. Reconstruction score and evidence

한 window의 scaled input을 `X`, reconstruction을 `X_hat`이라 하고 shape를 `[8, 16]`이라 합니다. Feature `j`의
residual evidence와 window anomaly score는 다음으로 고정합니다.

```text
feature_residual[j] = mean_t((X[t, j] - X_hat[t, j])^2)
window_score        = mean_j(feature_residual[j])
```

Score는 `higher-is-more-anomalous`이며 window의 end acquisition identity에 정렬합니다. 이는 reconstruction
error이고 다음 acquisition을 예측한 forecast error가 아닙니다. Window가 현재 acquisition feature를 입력으로
포함하므로 score를 early-warning lead time으로 해석하지 않습니다.

Per-feature residual은 model-specific evidence로 보존합니다. Channel/feature별 reconstruction mismatch를
설명하지만 robust-scaled feature space의 값이며 original engineering unit이 아닙니다. Physical fault
contribution이나 원인 attribution으로 승격하지 않으며 raw waveform sample-level residual도 아닙니다.

Threshold, binary state, percentile calibration과 Gaussian error model은 v1에 포함하지 않습니다. XJTU가
defensible acquisition-level onset label을 제공하지 않으므로 reconstruction score의 연속 trajectory만 평가합니다.

## 7. Development evaluation

Validation scoring은 `Bearing1_2`, `Bearing2_2`, `Bearing3_2`의 full run에서 생성된 2,797 right-edge-aligned
window score를 사용합니다.

Bearing별로 다음을 기록합니다.

1. scored acquisition index와 reconstruction score의 Spearman ρ
2. original full-run lifecycle thirds에 따른 late-vs-middle rank probability
3. feature별 mean reconstruction residual
4. source acquisition, scoring window와 dropped-prefix count

Lifecycle third boundary는 source acquisition count `N`에서 계산합니다. Prefix 7개에 score가 없다는 이유로
나머지 observations를 다시 3등분하지 않습니다. Middle/late statistic은 해당 original segment에 정렬된 score만
사용합니다.

Summary는 bearing별 statistic의 동일가중 평균을 사용합니다. Window pooling이나 run-length weighting을 model
selection criterion으로 사용하지 않습니다. Undefined statistic, missing window, duplicate score alignment 또는
non-finite residual은 canonical execution을 실패시킵니다.

Isolation Forest와의 대조는 descriptive retrospective comparison입니다. 두 경로는 split, feature formula,
reference assumption과 bearing-first statistic을 공유하지만 LSTM은 robust scaling과 sequence windows를
사용합니다. 따라서 score 차이를 model family 하나의 causal effect로 해석하지 않습니다. 공통 pass/fail,
우승 model 또는 production promotion rule도 두지 않습니다.

## 8. Result, inspection and provenance

향후 result schema는 최소 다음 사실을 보존해야 합니다.

- dataset, split, fold, partition과 evidence class
- feature schema와 train-fitted preprocessing provenance
- reference strategy와 acquisition population
- sequence length/stride/alignment/boundary, input shape와 window population
- asset별 source count, generated window count, dropped prefix
- exact model/training configuration, runtime/device, seed와 epoch loss
- score semantics, bearing별 evaluation과 feature residual summary
- available/unsupported capability
- declared code revision과 artifact identity

Inspection stage 순서는 다음과 같습니다.

```text
Source
-> Canonical
-> Feature
-> Preprocessing
-> Reference
-> Sequence Construction
-> Population
-> Model
-> Scoring
-> Evaluation
-> Capability
-> Provenance
```

LSTM result가 실제로 생성될 때 schema-specific reader를 추가하고 `ExperimentInspection`에 위 stage를 표현합니다.
현재 XJTU/IMS Isolation Forest reader나 기존 result JSON을 이 protocol을 위해 변경하지 않습니다.

## 9. Implementation order and acceptance boundary

Numerical evidence 전에 다음 순서를 지킵니다.

```text
protocol v1 merge
  -> Python 3.14 / PyTorch 2.14 CPU compatibility contract 유지
  -> dataset-neutral sequence/window contract와 XJTU edge 구현
  -> frozen configuration과 deterministic LSTM Autoencoder fit/reconstruction contract 구현
  -> reconstruction-error score와 per-feature residual contract 구현
  -> clean main revision에서 fold-1 train/validation execution
  -> result와 inspection reader 기록
```

LSTM model implementation의 acceptance boundary는 다음과 같습니다.

- canonical XJTU execution이 complete train feature vectors에서 `PreprocessingState`를 직접 fit하고 같은 population을
  sequence construction에 전달
- immutable reference windows를 model 경계 안에서 CPU float32 tensor로 변환
- encoder/latent/decoder architecture와 fixed 50 epochs, Adam, global-norm clipping, final-epoch state 적용
- runtime version, device, precision, deterministic setting, seed, parameter count와 epoch loss provenance 보존
- reconstruction을 window와 right-edge source observation identity에 정렬
- reconstruction score와 per-feature residual은 별도 scoring contract가 소유

Reconstruction scoring contract는 다음 경계를 소유합니다.

- sequence input과 reconstruction의 feature schema, window spec과 ordered identity를 정확히 대조
- feature별 시간축 mean squared residual과 전체 feature 평균인 window score를 robust-scaled space에서 계산
- window·sequence·asset·partition identity와 right-edge source observation identity·position을 score에 보존
- score 방향을 `higher-is-more-anomalous`로 고정하고 threshold나 binary state 없이 연속 evidence를 제공

IMS, MIMII, thresholding, test execution, dashboard와 `PHMResult` schema는 이 protocol PR의 범위가 아닙니다.

## References

- Malhotra et al., [*LSTM-based Encoder-Decoder for Multi-sensor Anomaly Detection*](https://arxiv.org/abs/1607.00148),
  arXiv:1607.00148, 2016. Sequence reconstruction model과 reconstruction-error anomaly scoring의 연구 근거로
  사용하며, 논문의 supervised threshold selection이나 dataset별 window 설정을 XJTU contract로 복사하지 않습니다.
