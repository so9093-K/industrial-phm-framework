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

고정 identity는 다음과 같습니다.

~~~text
protocol_id              = mimii-due-domain-shift-iforest-v1
development_split_id     = mimii-due-dev-sections-00-02-v1
external_evaluation_id   = mimii-due-eval-sections-03-05-v1
~~~

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

Representation 구현은 NumPy FFT와 명시된 수학식만 사용하고, 이 baseline을 위해 librosa/soundfile 같은
audio-specific runtime dependency를 추가하지 않습니다. Canonical waveform은 Adapter에서 clip 하나씩 받아 즉시
feature vector로 축약하고 다음 clip으로 넘어갑니다. Dataset 전체 waveform이나 여러 160,000-sample
CanonicalTimeSeries를 feature extraction을 위해 동시에 materialize하지 않습니다.

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

Harmonic mean은 다음 deterministic rule을 사용합니다.

~~~text
values 중 하나라도 0.0이면 harmonic_mean = 0.0
그 외에는 harmonic_mean = N / sum(1/value)
~~~

Negative metric value나 non-finite value는 허용하지 않습니다. DCASE evaluator처럼 epsilon을 넣어 0을 작은 양수로
바꾸지 않으며, source metric을 그대로 보존한 summary를 만듭니다.

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
- packaged dataset version
- acquisition provider
- source record URL
- citation DOI
- dataset license/redistribution notice
- verified prepared-source clip count
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

Numerical score를 보기 전에 다음 순서를 지킵니다. Authoritative development execution은
`--code-revision`이 현재 Git `HEAD`와 정확히 일치하고 tracked working tree가 clean인 checkout에서만
CLI가 시작됩니다. Untracked/ignored local dataset과 output은 이 clean check에 포함하지 않습니다.


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

실제 authoritative development execution 명령과 deterministic rerun/inspection 절차는
[`mimii-due-development-execution-runbook.md`](mimii-due-development-execution-runbook.md)가 소유합니다.

## 14.1 관찰된 development evidence

Runbook 절차를 clean `main` revision `40fd3d044ce8a511cd0ec5f437e1c55f63197dc3`에서 한 번 수행했습니다.
Authoritative numerical evidence는
[`results/mimii-due-iforest-domain-shift-development-v1.json`](results/mimii-due-iforest-domain-shift-development-v1.json)에
보존합니다.

실행 조건과 재현성:

- `data validate mimii-due --full`: WAV header 36,433개 전부 PASS, profile compatibility PASS
- 같은 revision/configuration/source로 두 번 실행한 결과가 byte-identical
- 두 run의 SHA-256 모두 `89b52add2e74298e235f9c71fb1b115e805a01669c24c4b380f2b6e74c1d4e2a`
- `experiment inspect` PASS, artifact `provenance.code_revision`이 실행 revision과 일치,
  `source_scope.dataset_record`가 packaged `mimii-due` manifest와 일치
- section model 15개, model-fit clip 15,062개(source 15,017 / target 45), scoring clip 6,221개

Domain별 harmonic summary(strata 15개씩)와 전체 요약(strata 30개):

| Scope | ROC AUC hmean | standardized pAUC hmean |
| --- | ---: | ---: |
| `domain:source` | 0.5859 | 0.5176 |
| `domain:target` | 0.5516 | 0.5013 |
| `mimii-only:all-strata` | 0.5682 | 0.5093 |

`mimii_domain_shift_summary` = 0.5372.

Machine type별 요약(각 strata 6개):

| Machine | ROC AUC hmean | standardized pAUC hmean |
| --- | ---: | ---: |
| fan | 0.5444 | 0.5057 |
| gearbox | 0.5809 | 0.4934 |
| pump | 0.5494 | 0.5151 |
| slider | 0.6251 | 0.5328 |
| valve | 0.5492 | 0.5012 |

관찰 범위:

- 이 값들은 sections 00–02 **development evidence**이며 sections 03–05 external evaluation이 아닙니다.
  DCASE official score도 아닙니다(`dcase_official_score = false`).
- Threshold, selection, calibration을 수행하지 않았습니다. Label은 evaluator edge에서만 결합했습니다.
- `capability` 필드가 선언한 대로 thresholded state detection, online alerting, fault diagnostics,
  fault classification, health assessment, health indicator, prognostics/RUL, causal explanation,
  maintenance recommendation은 이 evidence가 지원하지 않습니다.
- 이 수치를 보고 representation, preprocessing, model parameter, evaluator를 조정하지 않았습니다. 변경이
  필요하다고 판단되면 protocol/configuration v2를 먼저 version-control하고 별도 evidence로 분리합니다.

## 14.2 Development evidence 검토와 freeze 결정

§14.1의 artifact 안에서만 읽은 관찰입니다. 외부 수치나 다른 실행을 끌어오지 않았습니다.

### Stratum 분포

30개 stratum(machine type × section × domain)의 값은 다음과 같습니다.

| 통계 | ROC AUC | standardized pAUC |
| --- | ---: | ---: |
| 최소 | 0.4934 | 0.4779 |
| 중앙값 | 0.5660 | 0.5049 |
| 최대 | 0.7176 | 0.6233 |
| 0.5 미만 stratum 수 | 1 / 30 | 12 / 30 |

ROC AUC는 30개 중 29개가 0.5 이상이고 중앙값이 0.5660입니다. 반면 standardized pAUC는 중앙값이 0.5049이고
30개 중 12개가 0.5 아래입니다. 즉 **전체 순위에서는 chance보다 나은 방향이 관찰되지만, false positive rate
0.1 이하 구간으로 제한하면 chance 수준과 구분되지 않습니다.**

### Domain gap

Section별 `source AUC − target AUC`는 최소 `-0.0843`, 중앙값 `+0.0249`, 최대 `+0.1521`이고 15개 중 10개가
양수입니다. Domain summary 수준에서는 source 0.5859 > target 0.5516이지만, section 단위로 보면 방향이 일정하지
않습니다. 예를 들어 gearbox section 00은 target이 source보다 높고(`-0.0768`), slider section 02는 source가
target보다 높습니다(`+0.1521`).

따라서 이 evidence는 "target domain이 일관되게 더 어렵다"를 뒷받침하지 않습니다. 관찰할 수 있는 것은
**section 단위 변동이 domain 평균 차이보다 크다**는 사실까지입니다.

### Machine type

AUC harmonic mean은 slider 0.6251, gearbox 0.5809, pump 0.5494, valve 0.5492, fan 0.5444입니다. 이 차이가
machine type의 물리적 특성 때문인지, section 구성이나 clip 분포 때문인지는 이 artifact가 구분해 주지 않으므로
원인을 주장하지 않습니다.

### Population 비대칭

모든 section에서 target domain train clip은 3개이고 source domain train clip은 1,000~1,008개입니다. Reference와
model fit population은 이 둘을 합친 complete normal train입니다. 이 비대칭은 protocol이 사전에 고정한 source
구성에서 온 것이며 이번 실행에서 조정하지 않았습니다.

### Freeze 결정

**V1 configuration을 sections 03–05 external evaluation용으로 freeze합니다.**

근거는 development 수치가 아닙니다. 위 수치를 근거로 configuration을 바꾸면 결과를 보고 설정을 조정하는 것이
되어 external evaluation이 unbiased evidence로서 갖는 의미가 사라집니다. Freeze 근거는 다음 두 가지입니다.

1. V1은 §1의 질문(같은 evidence discipline이 vibration이 아닌 audio source에서도 성립하는가)을 위해 사전에
   고정한 baseline입니다. External evaluation은 그 baseline이 관찰하지 않은 section에서 어떤 evidence를
   만들어내는지를 묻는 별도 질문이며, baseline을 바꾸면 그 질문에 답할 수 없습니다.
2. External evaluation 실행 경로 자체(label을 보지 않고 score를 먼저 고정한 뒤 ground truth를 나중에 결합)가
   아직 한 번도 검증되지 않았습니다. 이 경로를 검증하는 데 필요한 것은 높은 점수가 아니라 고정된 configuration
   입니다.

더 강한 representation을 비교하고 싶다면 protocol/configuration v2로 별도 version을 만들고 자신의 development
evidence부터 생성합니다. V2는 이 artifact를 근거로 정당화하지 않으며, v1 external evidence를 v2의 evidence로
재사용하지도 않습니다.

## 14.3 External evaluation ground-truth label 의미

Ground truth record 5257674의 공식 description이 CSV 두 번째 열의 의미를 다음과 같이 정의합니다.

> The second column shows the condition label (i.e., 0: normal or 1: anomaly).

따라서 external evaluation에서 `0`은 normal, `1`은 anomaly로 결합합니다. 이 매핑은 source 문서 근거이며
score 분포나 결과를 보고 정한 값이 아닙니다.

## 14.4 관찰된 label-blind external scoring

Clean revision `479bd3fcee41544cc673350fad685aa9bc78621f`에서 §12 순서의 scoring 단계를 수행했습니다.
Artifact는
[`results/mimii-due-iforest-domain-shift-external-score-v1.json`](results/mimii-due-iforest-domain-shift-external-score-v1.json)
입니다.

- sections 03–05 normal train으로 section model 15개를 새로 fit했습니다. Development model을 재사용하지
  않았습니다.
- Evaluation test clip 6,235개를 모두 scoring했고 verified clip 수와 일치합니다(source 3,100 / target 3,135).
- 같은 revision/source/configuration으로 두 번 실행한 결과가 byte-identical이며 SHA-256은
  `ff7290ae67604c2595e75094cdb9856c8fa143a4f1ebee70e35c32589d979a96`입니다.
- Artifact에는 `source_file`, `domain`, `anomaly_score`만 있습니다. `clip_label`, `condition_label`,
  `"normal"`, `"anomaly"` 문자열이 0건입니다.

이 단계는 **성능 수치를 만들지 않습니다.** Label을 한 번도 읽지 않았으므로 AUC/pAUC는 evaluator가 ground
truth를 결합한 뒤에만 계산됩니다.

## 14.5 관찰된 external evaluation evidence

Clean revision `528645a875d5c9a0fbffd2745b03d6973e7c30a7`에서 §12의 마지막 단계를 수행했습니다. Evaluator는
SHA-256 `ff7290ae67604c2595e75094cdb9856c8fa143a4f1ebee70e35c32589d979a96` score artifact와 ground truth CSV만
읽었고 audio나 model에는 접근하지 않았습니다. Artifact는
[`results/mimii-due-iforest-domain-shift-external-result-v1.json`](results/mimii-due-iforest-domain-shift-external-result-v1.json)
이며 두 번 실행한 결과가 byte-identical입니다.

| Scope | ROC AUC hmean | standardized pAUC hmean |
| --- | ---: | ---: |
| `domain:source` (strata 15) | 0.5626 | 0.5073 |
| `domain:target` (strata 15) | 0.5355 | 0.5107 |
| `mimii-only:all-strata` (strata 30) | 0.5487 | 0.5090 |

`mimii_domain_shift_summary` = 0.5281.

Development(sections 00–02)와 나란히 보면 다음과 같습니다. 두 값은 서로 다른 section과 서로 다른 fit
population에서 나온 것이므로 같은 모집단의 반복 측정이 아닙니다.

| Scope | development | external |
| --- | ---: | ---: |
| source AUC | 0.5859 | 0.5626 |
| target AUC | 0.5516 | 0.5355 |
| overall AUC | 0.5682 | 0.5487 |
| overall pAUC | 0.5093 | 0.5090 |

Machine type별 AUC harmonic mean은 development 대비 gearbox `0.5809 → 0.5966`, fan `0.5444 → 0.5475`로
비슷하거나 소폭 높고, pump `0.5494 → 0.5300`, slider `0.6251 → 0.5826`, valve `0.5492 → 0.4984`로 낮습니다.
Development에서 가장 높았던 slider가 external에서는 gearbox보다 낮고, valve는 `0.5` 아래입니다. 즉
**machine type별 상대 순서가 development와 external에서 유지되지 않았습니다.**

30개 stratum 분포는 AUC가 최소 `0.4444`, 중앙값 `0.5494`, 최대 `0.7375`이고 8개가 `0.5` 아래입니다.
Standardized pAUC는 중앙값 `0.5014`이고 14개가 `0.5` 아래입니다. Development에서 관찰한 성질, 즉 전체 순위에서는
chance보다 나은 방향이 보이지만 FPR 0.1 이하 구간에서는 chance와 구분되지 않는다는 점이 external에서도
유지됩니다.

이 값은 DCASE official score가 아니며(`dcase_official_score = false`), threshold, selection, calibration을
수행하지 않았습니다. Capability 선언은 development와 동일하게 thresholded state detection, fault diagnostics,
health assessment, Health Indicator, prognostics/RUL을 지원하지 않습니다.

`fold-1` holdout과 마찬가지로 sections 03–05 external evaluation은 이 실행으로 소진됐습니다. 이 결과를 보고
configuration을 바꾼 뒤 같은 scope를 변경된 configuration의 unbiased evidence로 재사용하지 않습니다.

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
