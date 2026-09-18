# Changelog

이 프로젝트의 사용자 및 개발자에게 의미 있는 변경사항을 기록합니다. 형식은 Keep a Changelog의
분류 방식을 따릅니다.

개발 중 package version은 `0.0.1`로 유지하며 기능 PR이나 내부 구조 변경마다 버전을 올리지 않습니다.
릴리즈 가능한 public API와 배포 정책을 별도로 결정할 때 versioning 정책을 다시 검토합니다. 그 전까지
의미 있는 변경은 `[Unreleased]` 아래에 누적합니다.

## [Unreleased]

### Added

- Python 3.14 기반 installable package, uv lockfile, CLI와 CI 기준선.
- dataset manifest 기반 `data list/status/fetch/verify/inspect/validate` acquisition·inspection workflow.
- dataset/source 차이를 격리하는 `DomainAdapter`와 domain-neutral `CanonicalTimeSeries` contract.
- 실제 XJTU-SY와 IMS source profile, dataset-specific validator와 canonical Adapter.
- XJTU-SY condition-stratified 5-fold bearing-run split과 leakage-aware experiment protocol.
- acquisition별 `vibration-statistical-v1` feature와 split-aware characterization artifact workflow.
- generated characterization artifact를 소비하는 optional marimo/Matplotlib research tooling environment.
- dataset-neutral `ExperimentConfig v1`과 XJTU fold-1 Isolation Forest candidate configuration.
- train provenance와 feature order를 고정하는 identity/robust `PreprocessingState`.
- sampling-aware `ModelFitInput`과 unsampled `ModelScoringInput`의 dataset-neutral model input contract.
- scikit-learn 1.9 기반 Isolation Forest baseline과 observation-aligned `AnomalyScores` contract.
- XJTU fold-1 candidate validation 실행, 결과 artifact와 deterministic selection rule.
- XJTU validation을 bearing-first로 평가하는 acquisition-order Spearman ρ development evaluator.
- `experiment validate --score-trajectory-dir`로 생성하는 train/validation acquisition별 anomaly-score
  trajectory artifact. Candidate selection과 분리된 development diagnosis이며 holdout test는 scoring하지 않습니다.

- `ReferenceStrategy.train-bearing-early-third-v1`과 `experiment reference-compare`로 실행하는 fold-1
  reference-only H0/H1 development 비교. complete train / reference-eligible / model-fit population을
  `ModelFitInput`에서 의미상 분리합니다.

- fold-1 development가 확정한 단일 `xjtu-sy-iforest-fold-1-finalized-v1` experiment configuration과
  축 drift를 로드 시점에 차단하는 검증. 비교용 v2/v3 manifest는 역사적 evidence로 보존합니다.

- `experiment holdout`으로 실행하는 fold-1 holdout evaluation 경로. finalized configuration 하나만
  소비하며 candidate/reference selection, threshold calibration, tunable parameter가 없습니다.

- finalized configuration의 `fold-1` holdout test 1회 실행 결과 artifact.

- `experiment cross-fold`로 folds 2~5의 test partition을 한 번에 실행하는 post-holdout robustness 경로와
  결과 artifact. fold별로 preprocessing을 새로 fit하며 `fold-1 test`는 다시 scoring하지 않습니다.

- verified IMS source profile과 canonical mapping을 기준으로 확인한 feature 계층의 cross-dataset
  portability 관찰과, IMS experiment protocol이 결정해야 할 항목 정리. feature 계층이 dataset-neutral하게
  유지됨을 두 domain의 channel 구성으로 고정하는 contract 테스트를 함께 추가합니다.

- IMS single-channel 첫 model experiment의 source scope와 평가 경계를 결과 전에 고정한
  `ims-experiment-protocol.md`. Set 2 complete train을 fit/reference로 사용하고 Set 3의
  `readme-documented` 4,448 acquisitions만 one-time cross-test evaluation에 사용하며, Set 1과
  archive-extension은 v1에서 제외합니다.

- PHM/ML 개발자·연구자를 위한 pipeline transparency UX baseline. Source → canonicalization → feature →
  preprocessing → reference/sampling → model fit/scoring → evaluation/result를 stage별로 검토하고,
  complete/reference/fit/scoring population flow, effective configuration, provenance, unsupported capability를
  일관되게 표시하는 information architecture를 정의합니다.

- `experiment cross-test`로 실행하는 IMS single-channel fixed cross-test 경로. Set 2 complete train에서
  preprocessing과 Isolation Forest를 fit하고 Set 3의 `readme-documented` scope만 scoring하며,
  source/reference/fit/scoring population과 effective configuration, capability scope, code revision을
  developer-transparent result JSON에 기록합니다.

- IMS Set 2 → Set 3 one-time cross-test evaluation 결과 artifact.

### Changed

- XJTU finalized holdout과 IMS cross-test lineage를 같은 developer pipeline stage로 비교하고 schema-specific
  experiment inspection에 필요한 information gap을 명시.

- XJTU 내부에 있던 Spearman ρ와 late-vs-middle rank probability의 순수 수학 계산을 두 번째 dataset
  consumer가 생긴 시점에 dataset-neutral score-statistics helper로 승격하고 XJTU public wrapper는 유지합니다.
- regular sampling rate가 제공되면 `CanonicalTimeSeries`가 explicit sample timestamp 없이도 waveform segment를
  표현할 수 있도록 확장.
- XJTU source/profile 검사를 production validator와 CLI로 이동하고 Notebook은 generated artifact를 소비하는
  exploratory interface로 제한.
- 첫 numerical baseline은 `fold-1` development/holdout 경계를 사용하며 configuration finalization 전에는
  다른 fold와 holdout test를 development decision에 사용하지 않도록 protocol을 명확화.
- `fold-1` holdout을 열기 전에 reference semantics만 한 번 더 비교하도록 configuration finalization 결정을
  고정. H0는 `all-train-observations`, H1은 train bearing별 early-third heuristic reference를 사용하며
  feature/sampling/scaling/model parameter/seed는 selected v2에 고정하고 H0/H1 판정 규칙도 결과 전에 명시.
- `fold-1` holdout 소진 이후 `fold-2`~`fold-5`는 fresh holdout이 아니라 post-holdout robustness evidence로
  만 사용하도록 규칙을 고정. 각 fold의 test partition만 한 번의 동일 실행에서 평가하고 finalized
  configuration의 model/feature/reference/sampling/scaling/seed semantics와 descriptive metric을 유지합니다.
- 정확한 experiment parameter와 seed는 version-controlled config가, train-fitted scaling statistics는
  `PreprocessingState`가 소유하도록 Source of Truth를 분리.
- XJTU model-fit/scoring 준비가 research characterization artifact가 아니라 production `VibrationFeatureVector`를
  직접 소비하도록 경계를 정리하고, Isolation Forest active candidate를 sampling × feature subset 4개 v2로 축소.
- model input의 `rows`, `input/output observation count`를 `feature_rows`, `source/fit observation count`로
  명확화해 sampling 전후 의미를 이름에서 구분.
- XJTU model input이 source profile의 acquisition sequence 전체성을 검증하고, train feature vectors에서
  preprocessing fit과 sampling-aware model input을 함께 생성하도록 실행 경계를 강화.
- architecture PNG는 reference diagram으로 유지하고 이미지 전용 binary/canvas 검증을 CI에서 제거.

### Fixed

- Isolation Forest integer `max_samples`가 model-fit observation 수를 초과할 때 estimator가 silently fallback하지 않도록 fail-fast.
- `CanonicalTimeSeries`가 mutable input container를 그대로 보관해 생성 이후 invariant가 깨질 수 있던 문제.
- dataset acquisition User-Agent가 package version과 별도의 값을 사용하던 중복 version 문제.
- `data inspect`가 empty directory를 usable source처럼 성공 처리하던 동작.
