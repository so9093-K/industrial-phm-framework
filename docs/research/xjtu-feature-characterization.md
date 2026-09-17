# XJTU-SY Feature Characterization

상태: research protocol / `vibration-statistical-v1` baseline

이 문서는 XJTU-SY의 acquisition-level vibration feature를 한 번 선정하고 고정하는 절차가 아니라,
**feature가 bearing lifecycle과 operating condition에서 실제로 어떻게 동작하는지 관찰하고 다음 실험 결정을
근거화하는 방법**을 정의합니다. 프로젝트 공통 용어는 [`../terminology.md`](../terminology.md)를 따릅니다.

이 단계에서 관찰한 feature trajectory를 곧바로 degradation indicator나 fault-onset evidence로 해석하지 않습니다.
Feature characterization은 data understanding과 feature analysis에 해당하며, feature selection이나 reference-data
rule은 별도의 experiment decision입니다.

## 1. Baseline feature boundary

첫 baseline feature set은 `vibration-statistical-v1`입니다. 한 `CanonicalTimeSeries` acquisition의 각 channel에서
다음 통계를 독립적으로 계산합니다.

- mean
- RMS
- population standard deviation
- absolute peak
- peak-to-peak
- crest factor
- population standardized third moment (`skewness`)
- population standardized fourth moment minus 3 (`excess_kurtosis`)

이 feature set은 최종 선정 결과가 아니라 **작고 해석 가능한 reference representation**입니다. sampling rate에
의존하는 임의 FFT band, bearing geometry를 요구하는 BPFO/BPFI, learned embedding은 실제 분석 필요가 확인되기
전에는 포함하지 않습니다.

Feature extraction 자체는 acquisition 하나의 waveform만 사용하는 stateless transformation입니다. 따라서
scaler, normalizer, feature selection, threshold와 달리 data-derived fitted state를 만들지 않습니다.

## 2. Development와 holdout-test 경계

Feature 연구가 유연하다는 이유로 test bearing을 반복해서 보고 feature를 튜닝하면 holdout test의 의미가
사라집니다. 첫 baseline에서는 `vibration-statistical-v1`의 formula와 feature name/order를 모델 결과를 보기 전에
고정합니다.

[`xjtu-experiment-protocol.md`](xjtu-experiment-protocol.md)는 첫 numerical baseline의 **development fold를
`fold-1`로 고정**합니다. 이 선택은 fold 간 characterization/model 결과를 비교해 더 좋아 보이는 fold를 고른 것이
아니라, 반복적인 development analysis와 이후 holdout test evaluation을 분리하기 위한 절차적 경계입니다.

`fold-1`에서 다음 원칙을 사용합니다.

- train: feature behavior 탐색과 data-derived preprocessing/reference fitting의 근거
- validation: protocol에 미리 정의된 candidate selection/calibration과 development validation
- test: experiment configuration을 확정한 뒤 holdout test evaluation에만 사용

Test 결과를 보고 feature를 추가·제거하거나 reference-data rule을 바꾸고 싶다면 새로운 feature/protocol
version으로 기록합니다. 같은 test 결과를 이용해 변경한 뒤 그 결과를 다시 unbiased holdout evidence처럼 보고하지
않습니다.

현재 5-fold rotating holdout에서는 한 fold의 test bearing이 다른 fold의 train 또는 validation에 등장합니다.
따라서 experiment configuration finalization 전 characterization은 **`fold-1`의 train 또는 validation partition**만
사용하고, 다른 fold의 train/validation도 추가 development data로 미리 열지 않습니다. `fold-2`~`fold-5`는
`fold-1` holdout test 이후 cross-fold robustness analysis에서 사용할 수 있습니다. 이 characterization workflow는
어느 fold에서도 test partition을 허용하지 않습니다.

## 3. Characterization dimensions

Correlation 하나로 feature를 선택하지 않습니다. 최소한 다음 관점을 분리해 기록합니다.

### Numerical validity

- NaN/Inf 발생 여부
- zero/near-zero variance
- feature scale과 extreme value
- acquisition별 계산 실패 여부

### Lifecycle behavior

- bearing별 raw acquisition index에 따른 trajectory
- 필요할 때 smoothing을 보조선으로 사용하되 원값과 구분
- early/middle/late lifecycle에서 변화 형태가 다른지 확인

Lifecycle에 따라 값이 변한다는 사실만으로 degradation indicator라고 부르지 않습니다. 여러 bearing과 operating
condition에서의 일관성, downstream task에서의 의미가 추가로 확인되어야 합니다.

### Operating-condition / channel sensitivity

- `35Hz12kN`, `37.5Hz11kN`, `40Hz10kN` 사이 scale 또는 distribution 차이
- horizontal / vertical channel의 정보가 동일한지 또는 보완적인지 확인
- lifecycle 변화와 operating-condition 차이를 혼동하지 않도록 condition별 분석을 병행

### Cross-bearing consistency

- 같은 condition 안에서 bearing별 trajectory 차이
- 동일 feature가 여러 run에서 비슷한 방향으로 변화하는지 확인
- 특정 bearing 하나의 긴 trajectory가 전체 결론을 지배하지 않는지 확인

### Redundancy

Pearson/Spearman correlation은 기본 진단 도구로 사용하지만 자동 제거 규칙으로 사용하지 않습니다. 높은
correlation은 redundancy 후보를 보여줄 뿐, early sensitivity, condition robustness, physical interpretation,
downstream model utility까지 동일하다는 뜻은 아닙니다.

필요하면 correlation clustering이나 model-based ablation/permutation importance를 후속 단계에서 비교합니다.

### Change and degradation hypotheses

Rolling statistics, distribution shift, change-point detection 등으로 lifecycle change 후보를 탐색할 수 있습니다.
이 결과는 acquisition-level 공식 fault-onset ground truth가 아니며, degradation transition이라고 확정하지도
않습니다. 이후 normal-condition reference, early-warning 또는 degradation-indicator protocol을 정의할 때 검토할
수 있는 **candidate evidence**로만 취급합니다.

## 4. Run-length imbalance

XJTU-SY bearing lifetime은 acquisition 수가 크게 다릅니다. 따라서 여러 run의 acquisition을 단순히 한 테이블로
합쳐 계산한 pooled statistic은 긴 run의 영향을 과도하게 받을 수 있습니다.

Characterization에서는 pooled 결과만 보고 결론을 내리지 않고 최소한 per-bearing / per-condition summary를 함께
봅니다. 이후 Isolation Forest training에서도 모든 acquisition을 동일 가중할지, bearing-balanced sampling을
사용할지 별도 experiment decision이 필요합니다.

## 5. Normalized lifecycle은 retrospective analysis 전용

서로 다른 길이의 run을 시각적으로 비교하기 위해 failure endpoint를 `1.0`으로 둔 normalized lifecycle axis를
사용할 수 있습니다. 하지만 이 값은 최종 run length를 알고 있어야 계산할 수 있으므로 online inference에서
사용 가능한 feature가 아닙니다.

따라서 normalized lifecycle position은 visualization/retrospective analysis에만 사용하고 production feature
vector나 model input에는 넣지 않습니다.

## 6. Reference data는 가능한 experiment decision 중 하나

Characterization 결과에 따라 다음 후보를 비교할 수 있습니다.

- fixed early-life fraction/window
- train-bearing stability에 근거한 reference window
- change-point 후보를 이용한 reference boundary
- condition-specific population reference
- 별도 early-life normal-condition reference 없이 전체 train distribution을 사용하는 baseline

어떤 rule을 사용하더라도 dataset ground truth와 experiment assumption을 구분하고, data-derived state는 train
partition에서만 fit합니다. Test bearing 자신의 early-life data를 이용하는 normalization은 별도 test-time
adaptation protocol 없이는 사용하지 않습니다.

## 7. Automated characterization workflow

Acquisition을 사람이 하나씩 확인하는 방식으로 characterization하지 않습니다. 계산·집계·기초 진단은 반복
가능한 코드가 담당하고, 사람은 development data에서 생성된 characterization result를 바탕으로 experiment
candidate를 검토합니다.

첫 numerical baseline의 development fold는 `fold-1`입니다. 아래 명령은 현재 baseline의 실제 development scope를
나타내며, fold 간 성능 비교를 통해 `fold-1`을 고른 것이 아닙니다.

```bash
uv run python scripts/xjtu_feature_characterization.py \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \
  --output-dir data/processed/xjtu-sy/vibration-statistical-v1-characterization \
  --fold-id fold-1 \
  --partition train
```

Characterization API와 script는 향후 cross-fold robustness analysis를 위해 reference split의 다른 fold도 표현할 수
있지만, **experiment configuration finalization 전에는 `fold-1` 이외의 fold를 development data로 사용하지
않습니다.** `--partition`은 `train` 또는 `validation`만 허용합니다. `test`는 finalized configuration을 평가하는
holdout partition이므로 characterization script에서 의도적으로 지원하지 않습니다. Validation artifact 역시
사전에 정의한 selection/calibration 목적에서만 사용하며 train과 자동으로 합치지 않습니다.

Workflow는 complete prepared XJTU-SY source의 observed profile compatibility를 먼저 확인하고 production
`XjtuSyAdapter -> CanonicalTimeSeries -> vibration-statistical-v1` 경로를 사용합니다. 출력 artifact에는 선택한
fold/partition의 bearing만 포함하며 split/fold/partition provenance를 summary에 함께 기록합니다.

생성 artifact 예시는 다음과 같습니다.

- `vibration-statistical-v1-fold-1-train-features.csv`
  - 선택한 partition의 acquisition provenance와 고정 feature 값을 보존하는 table artifact
- `xjtu-feature-characterization-summary-v1-fold-1-train.json`
  - 선택한 partition의 global / condition / bearing-run feature distribution
  - run-length imbalance
  - Pearson·Spearman correlation candidate
  - known final run length를 사용한 retrospective early/middle/late thirds summary

CSV/JSON은 research artifact이며 feature contract나 experiment configuration 자체가 아닙니다. local
`data/processed/` workspace에 생성하고 대용량 결과를 repository에 그대로 commit하지 않습니다.

자동화의 경계도 명확히 둡니다.

```text
feature 계산 / numerical validity      자동
run / condition 통계                  자동
Pearson / Spearman 후보                자동
retrospective lifecycle 요약            자동

feature 선택                           사람의 experiment decision
reference-data rule 정의               사람의 experiment decision
anomaly onset ground truth 주장         자동화하지 않음
change point의 fault 의미 해석          자동화하지 않음
test 결과를 이용한 tuning               금지
```

첫 artifact는 현재 정당화된 descriptive analysis만 자동화합니다. Change-point algorithm, reference-window ranking,
feature ranking처럼 추가 가정이 필요한 로직은 실제 development artifact와 interactive analysis에서 필요가 확인된
뒤 별도 연구 변경으로 검토합니다.

## 8. Interactive analysis와 도구

Feature characterization 결과가 완성될 때까지 interactive analysis를 미루지 않습니다. 현재 생성된 feature table과
summary로 먼저 trajectory, condition/channel 차이, bearing별 차이와 redundancy를 탐색하고, 실제로 반복해서 필요한
분석이 확인되면 characterization code 또는 reusable analysis code로 승격합니다.

Jupyter나 향후 검토할 interactive tool은 production feature 계산식을 다시 구현하지 않고
`industrial_phm.features`와 characterization artifacts를 소비합니다. 도구 이름은 architecture 계층이나 Source of
Truth가 아니며, test partition을 feature decision 목적으로 열어보지 않습니다.

외부 도구는 research aid로 선택적으로 사용할 수 있습니다.

- Orange: correlation, distribution, clustering 등 interactive feature-table 탐색
- YData Profiling: distribution, correlation, interaction, data-quality quick scan
- catch22: 더 넓은 compact time-series feature 후보군과 비교하는 research benchmark
- ruptures: change-point candidate 탐색
- scikit-learn/SciPy: correlation clustering, model-based feature importance가 실제 필요해질 때 검토

이 도구들은 현재 runtime dependency가 아닙니다. 특히 자동 profiling/ranking 결과는 domain validation 없이 feature
selection contract가 되지 않습니다.

## 9. Experiment decisions supported by characterization

Characterization의 목적은 하나의 feature score를 만드는 것이 아니라 다음 experiment decision을 내릴 근거를
만드는 것입니다.

- `vibration-statistical-v1` 유지 또는 새로운 versioned feature set 도입
- frequency-domain / learned representation 확장 필요 여부
- train-only normalization/scaling 필요 여부
- reference-data strategy 필요 여부와 rule
- acquisition-count imbalance에 대한 model fitting/sampling policy
- Isolation Forest가 소비할 feature schema와 preprocessing state

실제 decision이 생기면 experiment configuration/code/document의 적절한 Source of Truth로 승격합니다. 연구 중
후보나 plot 자체를 architecture contract로 취급하지 않습니다.

## References

- Ayman et al., *Feature learning for bearing prognostics: A comprehensive review of machine/deep learning methods,
  challenges, and opportunities*, Measurement 245 (2025), DOI: 10.1016/j.measurement.2024.116589.
- scikit-learn, *Permutation Importance with Multicollinear or Correlated Features*.
- Lubba et al., *catch22: CAnonical Time-series CHaracteristics*, Data Mining and Knowledge Discovery 33 (2019),
  DOI: 10.1007/s10618-019-00647-x.
- ruptures documentation, PELT change-point detection.
- Orange Data Mining correlation widget documentation.
- YData Profiling concepts and multivariate profiling documentation.
