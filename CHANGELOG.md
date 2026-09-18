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

### Changed

- regular sampling rate가 제공되면 `CanonicalTimeSeries`가 explicit sample timestamp 없이도 waveform segment를
  표현할 수 있도록 확장.
- XJTU source/profile 검사를 production validator와 CLI로 이동하고 Notebook은 generated artifact를 소비하는
  exploratory interface로 제한.
- 첫 numerical baseline은 `fold-1` development/holdout 경계를 사용하며 configuration finalization 전에는
  다른 fold와 holdout test를 development decision에 사용하지 않도록 protocol을 명확화.
- `fold-1` holdout을 열기 전에 reference semantics만 한 번 더 비교하도록 configuration finalization 결정을
  고정. H0는 `all-train-observations`, H1은 train bearing별 early-third heuristic reference를 사용하며
  feature/sampling/scaling/model parameter/seed는 selected v2에 고정하고 H0/H1 판정 규칙도 결과 전에 명시.
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
