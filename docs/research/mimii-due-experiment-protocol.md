# MIMII DUE Reference Experiment Protocol

상태: reference protocol v1 / numerical execution not yet performed

이 문서는 MIMII DUE에서 첫 numerical audio experiment가 어떤 source scope, label boundary, audio representation,
preprocessing, model, scoring과 evaluation 의미를 사용할지 **결과를 보기 전에** 고정합니다. Source record,
license, local inventory와 canonical mapping은
[미리 검증된 source profile](mimii-due-source-profile.md)이 소유하고, 이 문서는 그 위의 experiment 의미만
소유합니다.

이 protocol은 DCASE 2021 Task 2의 domain-shift 문제와 AUC/pAUC evaluation 구조를 참고하지만,
ToyADMOS2의 ToyCar/ToyTrain을 포함하지 않고 MIMII DUE의 다섯 real-machine type만 사용합니다. 따라서
이 프로젝트의 aggregate를 DCASE official score 또는 challenge ranking으로 부르지 않습니다.

## 1. 첫 질문

첫 MIMII experiment의 목적은 최고 anomalous-sound-detection 성능을 주장하는 것이 아닙니다.

> Vibration에서 검증한 source → canonical → feature/preprocessing → model → score → evidence 책임을
> machine audio와 source/target domain shift에서도 유지하면서, test label을 model path에서 격리한
> 재현 가능한 clip-level anomaly score를 만들 수 있는가?

첫 task는 **domain-shift clip-level unsupervised anomaly scoring**입니다.

V1에서 지원하는 numerical claim은 normal/anomaly test clip의 ranking discrimination을 AUC와 low-FPR pAUC로
기술하는 것까지입니다. Thresholded state detection, fault diagnosis, health assessment, Health Indicator와
RUL은 이 protocol의 capability가 아닙니다.

## 2. Official task facts와 project protocol의 구분

DCASE 2021 Task 2의 공식 setup은 다음 source facts를 제공합니다.

- Section은 machine type 안의 performance/evaluation unit입니다.
- Source domain은 충분한 normal training data가 있는 original condition입니다.
- Target domain은 shifted condition이며 section당 normal training clip이 매우 적습니다.
- Development section은 00, 01, 02이고 source/target train과 labeled source/target test를 모두 제공합니다.
- Additional-training/evaluation section은 03, 04, 05입니다.
- Training에는 normal clip만 제공됩니다.
- Official evaluation은 machine type × section × domain별 AUC와 pAUC를 사용하고 pAUC의 max FPR은 0.1입니다.

공식 DCASE rule은 여러 training strategy를 허용합니다. 아래 model grouping, representation, preprocessing,
Isolation Forest parameter와 development/finalization 절차는 **이 프로젝트의 v1 protocol 결정**이며 DCASE가
요구한 유일한 방법이라고 주장하지 않습니다.

Reference:

- DCASE 2021 Task 2:
  https://dcase.community/challenge2021/task-unsupervised-detection-of-anomalous-sounds
- DCASE 2021 evaluator:
  https://github.com/y-kawagu/dcase2021_task2_evaluator

## 3. Source scope와 두 단계 evidence

MIMII DUE v1은 development와 external evaluation을 명확히 분리합니다.

### 3.1 Development scope

Development numerical evidence는 source group **dev**만 사용합니다.

| role | sections | source domain | target domain |
| --- | --- | --- | --- |
| model train/reference | 00, 01, 02 | normal train 전체 | normal train 3 clips/section |
| scoring/evaluation | 00, 01, 02 | source_test 전체 | target_test 전체 |

Machine type은 다음 다섯 개를 모두 사용합니다.

- fan
- gearbox
- pump
- slider
- valve

Development test의 normal/anomaly label은 metric 계산을 위한 evaluator에만 사용합니다.
Representation, preprocessing fit, reference selection, model fit과 scoring에는 test label을 사용하지 않습니다.

### 3.2 External evaluation scope

Sections 03, 04, 05는 development score를 본 뒤에도 **fresh test evidence**로 남깁니다.

현재 repository가 검증한 source group eval은 normal training clips만 포함합니다. External evaluation을 실제로
시작할 때 다음 두 record를 별도로 획득·검증합니다.

- Zenodo 4884786: DCASE 2021 Task 2 evaluation test audio
- Zenodo 5257674: evaluation ground truth

Evaluation 단계에서는 frozen v1 representation/model configuration을 sections 03–05의 train source에 적용해
fresh model을 fit하고 evaluation test audio를 score합니다. Ground truth는 score artifact가 고정된 뒤에만
evaluation metric 계산에 연결합니다.

Development result는 configuration development evidence이며 external evaluation과 같은 의미의 holdout이라고
부르지 않습니다.

## 4. Model unit과 domain-shift training rule

V1 model unit은 **machine type × section**입니다.

Development에서는 5 machine types × 3 sections = 15개 model을 fit합니다.

한 section model의 training population은 다음을 합친 normal clips입니다.

~~~text
section source-domain normal train
        +
section target-domain normal train
        ↓
one section-level training population
        ↓
one preprocessing state
        ↓
one Isolation Forest
~~~

Source/target domain별로 별도 model을 만들지 않습니다. Target-domain normal clip 3개를 주어진 few-shot normal
evidence로 포함하되, upsampling, duplication, synthetic balancing 또는 domain weighting을 하지 않습니다.
각 clip은 정확히 한 번 training population에 들어갑니다.

Machine type 간 또는 section 간 training clip도 pooling하지 않습니다. V1은 section-specific domain shift와
representation/model portability를 먼저 분리해서 검증합니다.

Test-time domain metadata는 evaluation grouping에는 사용하지만 model feature로 넣지 않습니다.

## 5. Label과 leakage boundary

MIMII filename에는 development test의 normal/anomaly label이 포함되어 있고 Adapter metadata에도 source fact로
보존됩니다. 이 사실이 model path의 label access를 허용한다는 뜻은 아닙니다.

V1은 다음 규칙을 지킵니다.

1. Train clip은 source가 normal training data로 제공한 범위만 model fit에 사용합니다.
2. Development source_test/target_test clip은 representation transform과 scoring만 수행합니다.
3. Test clip의 clip_label은 feature formula, preprocessing fit, reference, sampling, model fit, score transform에
   사용하지 않습니다.
4. Scoring code는 normal/anomaly label에 따라 다른 model, parameter, normalization 또는 score transform을
   선택하지 않습니다.
5. Evaluator가 score rows와 test labels를 source identity로 결합한 뒤에만 AUC/pAUC를 계산합니다.
6. Test score distribution을 보고 threshold, calibration, normalization, domain correction을 fit하지 않습니다.
7. V1에는 threshold가 없으므로 precision, recall, F1과 normal/fault decision result를 생성하지 않습니다.
8. Development metric을 본 뒤 representation/model을 바꾸면 새 protocol/configuration version으로 기록합니다.
9. Sections 03–05 evaluation test/ground truth는 development decision에 사용하지 않습니다.

Adapter가 label metadata를 보존하는 것은 source provenance 책임이고, experiment edge가 label을 model input에서
격리하는 것은 experiment 책임입니다.

## 6. Audio representation: audio-logmel-statistical-v1

V1은 raw waveform을 기존 vibration-statistical-v1에 넣지 않습니다.

고정 representation ID는 **audio-logmel-statistical-v1**입니다. 하나의 10-second clip을 deterministic
128-dimensional feature vector로 변환합니다.

### 6.1 PCM numerical input

Adapter가 보존한 signed 16-bit PCM amplitude를 representation 단계에서 다음처럼 stateless full-scale
normalization합니다.

~~~text
x[n] = pcm_s16[n] / 32768.0
~~~

값을 clipping하지 않습니다. 따라서 -32768은 -1.0, +32767은 약 +0.999969입니다.

이 변환은 data-derived fitted state가 아니라 versioned representation formula입니다. Adapter는 계속 raw PCM
amplitude scale을 보존합니다.

### 6.2 Frame and spectrum contract

Sampling rate는 canonical contract가 검증한 16,000 Hz입니다.

~~~text
frame length = 1024 samples
hop length   = 512 samples
window       = symmetric Hann
centering    = false
padding      = none
FFT          = real FFT, 1024 points
~~~

Hann window는 길이 N=1024에서 다음 식으로 고정합니다.

~~~text
w[n] = 0.5 - 0.5 * cos(2*pi*n/(N-1)),  n = 0..N-1
~~~

10-second 160,000-sample clip은 start position 0부터 hop 512로 가능한 complete frame만 사용하므로
**311 frames**가 생성됩니다. 마지막 incomplete tail은 padding하지 않습니다.

각 frame의 one-sided power는 다음 의미로 계산합니다.

~~~text
spectrum = rfft(frame * w)
power[k] = abs(spectrum[k])^2 / sum(w^2)
~~~

Physical calibrated PSD를 주장하지 않습니다. 이 값은 versioned numerical representation입니다.

### 6.3 Mel filterbank and log contract

Mel scale은 HTK 식을 사용합니다.

~~~text
mel(f) = 2595 * log10(1 + f/700)
f(m)   = 700 * (10^(m/2595) - 1)
~~~

고정 parameter:

~~~text
mel bands = 64
f_min     = 0 Hz
f_max     = 8000 Hz
edges     = 66 equally spaced points in HTK mel space
filters   = triangular, peak weight 1.0, no area normalization
~~~

FFT bin center frequency에 대해 continuous triangular weight를 계산합니다. Mel-band energy는 해당
power bins의 weighted sum입니다.

각 energy는 다음처럼 natural log로 변환합니다.

~~~text
log_energy = ln(max(mel_energy, 1e-12))
~~~

### 6.4 Clip aggregation and feature order

각 64 mel band에 대해 311 frame log-energy의 다음 statistic 두 개를 계산합니다.

- arithmetic mean
- population standard deviation, ddof=0

Feature order는 band 00부터 63까지 **mean, std를 interleave**합니다.

~~~text
feature.logmel.band_00.mean
feature.logmel.band_00.std
feature.logmel.band_01.mean
feature.logmel.band_01.std
...
feature.logmel.band_63.mean
feature.logmel.band_63.std
~~~

총 width는 128입니다.

V1에는 delta, delta-delta, spectral augmentation, learned embedding, pretrained audio model 또는
feature selection이 없습니다.

## 7. Preprocessing, reference와 sampling

각 machine-section model은 자신의 complete training population에서 preprocessing state를 fit합니다.

~~~text
scaling_strategy   = robust
reference_strategy = all-train-observations
sampling_policy    = clip-uniform-v1
~~~

Robust scaling은 repository의 기존 train-fitted preprocessing contract와 동일한 median / IQR rule을
사용합니다. IQR이 0인 feature는 기존 contract에 따라 unit scale 1.0을 사용하고 해당 feature identity를
state에 기록합니다.

Reference-eligible population과 model-fit population은 같은 complete section train population입니다.

Target clip 3개에 추가 weight를 주지 않습니다. Source와 target train clip을 모두 한 번씩 사용합니다.

각 section result는 최소 다음 population을 분리해 기록해야 합니다.

- source-domain train clip count
- target-domain train clip count
- complete preprocessing-fit clip count
- reference-eligible clip count
- model-fit clip count
- source-domain scoring clip count
- target-domain scoring clip count

## 8. Model configuration

V1 model family는 기존 framework에서 검증된 **Isolation Forest**를 재사용합니다.

이 선택은 audio에 최적이라는 주장이 아니라, 새 modality에서 representation/evaluation 경계를 검증하면서
model-family axis를 닫기 위한 baseline입니다.

고정 parameter:

~~~text
model_family  = isolation-forest
n_estimators  = 256
max_samples   = auto
contamination = auto
max_features  = 1.0
bootstrap     = false
random_seed   = 42
~~~

각 machine-section model은 같은 parameter와 seed를 사용합니다.

Score semantics는 기존 model contract와 동일하게 **higher-is-more-anomalous**입니다.

V1에는 model candidate grid나 machine별 hyperparameter tuning이 없습니다.

## 9. Development evaluator

Development evaluator의 unit은 공식 task와 같은 **machine type × section × domain**입니다.

각 stratum에서 clip label을 y_true, higher-is-more-anomalous score를 y_score로 사용해 다음을 계산합니다.

~~~text
AUC  = sklearn.metrics.roc_auc_score(y_true, y_score)
pAUC = sklearn.metrics.roc_auc_score(y_true, y_score, max_fpr=0.1)
~~~

이는 DCASE 2021 official evaluator가 사용하는 AUC/pAUC 계산과 같은 sklearn API와 max-FPR parameter를
따릅니다.

각 stratum에는 normal과 anomaly가 모두 있어야 합니다. Label/score cardinality mismatch, duplicate source
identity, non-finite score, single-class stratum이 있으면 metric을 임의 값으로 대체하지 않고 execution을
실패시킵니다.

V1에는 thresholded decision이 없으므로 confusion matrix, precision, recall, F1을 계산하지 않습니다.

## 10. Aggregate summary

Per-stratum AUC/pAUC가 numerical evidence의 primary owner입니다. Aggregate는 이를 숨기지 않는 summary입니다.

다음 값을 함께 기록합니다.

1. machine별 6 strata의 harmonic-mean AUC
2. machine별 6 strata의 harmonic-mean pAUC
3. source-domain 15 strata의 harmonic-mean AUC와 pAUC
4. target-domain 15 strata의 harmonic-mean AUC와 pAUC
5. MIMII-only 전체 30 strata의 harmonic-mean AUC와 pAUC
6. 전체 30 strata × {AUC, pAUC} 60 values의 harmonic mean인
   **mimii_domain_shift_summary**

Harmonic mean은 positive metric values에 적용합니다. AUC/pAUC는 sklearn standardized ROC metric 범위에서
계산되므로 0이 관찰되면 epsilon으로 조용히 치환하지 않고 해당 값과 aggregate rule을 명시적으로 검토합니다.

mimii_domain_shift_summary는 DCASE official score와 구조적으로 유사한 project summary이지만,
ToyCar/ToyTrain이 없으므로 **DCASE official score라고 이름 붙이지 않습니다.**

Aggregate를 pass/fail criterion이나 model ranking으로 사용하지 않습니다.

## 11. Development configuration finalization

V1 development execution은 sections 00–02 labeled test를 한 번 평가해 architecture/evidence path를 확인하는
development evidence입니다.

Development result를 본 뒤 두 경로 중 하나를 명시적으로 선택합니다.

### A. V1 configuration을 external evaluation에 freeze

Representation, preprocessing, model, score semantics와 evaluator를 변경하지 않고 sections 03–05 external
evaluation으로 진행합니다.

### B. V1을 development evidence로 종료하고 v2 작성

Representation/model/evaluation 의미를 바꿔야 한다면 새 protocol/configuration version을 먼저 기록합니다.
V1 development result는 삭제하거나 v2의 unbiased test evidence로 재해석하지 않습니다.

Sections 03–05 evaluation test를 열기 전까지는 development revision이 가능합니다. Evaluation test/ground truth를
본 뒤에는 같은 scope를 변경된 configuration의 fresh evidence로 재사용하지 않습니다.

## 12. External evaluation one-shot boundary

External evaluation은 다음 순서를 지킵니다.

~~~text
frozen configuration
  ↓
verify sections 03-05 training source
  ↓
acquire + verify evaluation test audio record 4884786
  ↓
fit fresh 15 section models on sections 03-05 normal train
  ↓
score all evaluation test clips without ground truth
  ↓
write immutable anomaly-score artifact + code revision + SHA-256
  ↓
acquire + verify ground-truth record 5257674
  ↓
join labels in evaluator
  ↓
compute final AUC/pAUC evidence once
~~~

Ground-truth record를 먼저 local에 보유하게 되더라도 scoring code가 이를 읽지 않는 boundary를 contract test와
execution path로 분리합니다.

Evaluation test filename에는 normal/anomaly condition label이 없으므로 scorer는 filename에서 label을 복원하거나
추정하지 않습니다.

## 13. Result and provenance contract

Development result artifact에는 최소 다음 정보를 보존합니다.

### Identity

- result schema ID
- experiment/protocol ID and version
- dataset ID = mimii-due
- source group = dev
- sections = 00, 01, 02
- full 40-character code revision

### Representation

- representation ID = audio-logmel-statistical-v1
- PCM full-scale divisor
- frame length/hop/window
- FFT size and power normalization
- mel scale/formula/band count/frequency range
- log floor
- frame count per validated clip
- exact 128 feature names/order

### Per machine-section fit

- machine type / section
- source train count
- target train count
- preprocessing observation count
- reference/model-fit count
- fitted robust-scaling state provenance
- exact model parameter and seed

### Scoring

- source identity for every scored clip
- machine / section / domain
- one finite higher-is-more-anomalous score
- score count by stratum

The model-scoring record does not need normal/anomaly label to compute the score.

### Evaluation

- label source and join identity
- per machine/section/domain normal/anomaly count
- AUC / pAUC
- machine/domain/global harmonic summaries
- mimii_domain_shift_summary

### Capability

Available:

- clip-level anomaly scoring
- labeled offline development discrimination evaluation
- source/target domain-stratified AUC/pAUC evidence

Unsupported / not validated:

- thresholded state detection
- online alerting
- fault diagnosis or fault classification
- Health Assessment / Health Indicator
- Prognostic Assessment / RUL
- causal explanation
- maintenance recommendation or priority

## 14. Implementation order

Numerical score를 보기 전에 다음 순서를 지킵니다.

~~~text
this protocol PR
  ↓
audio-logmel-statistical-v1 representation contract + tests
  ↓
MIMII dataset-specific train/scoring boundary
  ↓
model-independent AUC/pAUC evaluator + DCASE-parity fixtures
  ↓
single frozen development configuration/result schema
  ↓
implementation/tests merge
  ↓
clean main revision에서 development execution
  ↓
development artifact review
  ↓
external evaluation freeze or explicit v2 decision
~~~

Protocol PR에는 model score나 generated numerical result를 넣지 않습니다.

## 15. V1에서 하지 않는 것

- vibration-statistical-v1을 audio에 재사용
- source/target test clip을 training에 사용
- test label에 따라 model/scoring path 변경
- target normal 3 clips upsampling 또는 domain reweighting
- machine/section 간 pooled training
- model candidate grid / hyperparameter search
- test-score distribution을 사용한 threshold/calibration
- precision/recall/F1 또는 normal/fault decision 생성
- pretrained audio embedding / foundation model
- data augmentation, source separation, denoising
- thresholded State Detection
- fault diagnostics
- Health Indicator / degradation score 명명
- RUL
- DCASE official score/ranking 주장
- sections 03–05 evaluation test/ground truth를 development tuning에 사용
- MIMII 결과 하나를 근거로 generic audio pipeline 또는 UniversalResult를 도입

## Sources

- MIMII DUE source profile:
  https://github.com/so9093-K/industrial-phm-framework/blob/main/docs/research/mimii-due-source-profile.md
- DCASE 2021 Task 2:
  https://dcase.community/challenge2021/task-unsupervised-detection-of-anomalous-sounds
- DCASE 2021 official evaluator:
  https://github.com/y-kawagu/dcase2021_task2_evaluator
- MIMII DUE record:
  https://zenodo.org/records/4740355
- DCASE 2021 Task 2 evaluation test audio:
  https://zenodo.org/records/4884786
- DCASE 2021 Task 2 ground truth:
  https://zenodo.org/records/5257674
