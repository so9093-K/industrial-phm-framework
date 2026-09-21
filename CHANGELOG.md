# Changelog

이 프로젝트의 사용자 및 개발자에게 의미 있는 변경사항을 기록합니다. 형식은 Keep a Changelog의
분류 방식을 따릅니다.

개발 중 package version은 `0.0.1`로 유지하며 기능 PR이나 내부 구조 변경마다 버전을 올리지 않습니다.
릴리즈 가능한 public API와 배포 정책을 별도로 결정할 때 versioning 정책을 다시 검토합니다. 그 전까지
의미 있는 변경은 `[Unreleased]` 아래에 누적합니다.

## [Unreleased]

### Added

- XJTU RUL protocol의 first age-only comparator. Complete train bearing target에서 endpoint를 equal-bearing mean으로
  fit하고 validation/test prediction에는 current acquisition index만 사용합니다. Target bearing endpoint,
  operating condition과 vibration feature value를 prediction input에서 제외하고 negative prediction도 clamp하지
  않아 sensor-aware baseline의 실제 추가 가치를 비교할 수 있게 합니다.
- Dataset-neutral RUL prediction contract와 identity-aligned point evaluator. Sequence model의 dropped prefix를 허용하는
  ordered prediction subset을 target lifecycle에 결합하고 asset별 MAE/RMSE/mean signed error를 먼저 계산한 뒤
  equal-asset 평균으로 집계합니다. XJTU policy edge는 complete recorded-end target을 재검증하고 bearing별
  `N - 1` normalization scale만 제공해 model implementation과 평가 의미를 분리합니다.
- Dataset-neutral `RulTargetObservation` / `RulTargetSeries` contract와 기존 XJTU bearing-run split/source profile을
  재사용하는 fold-1 recorded-end RUL target construction. 각 acquisition을 canonical source identity에 맞춰
  `N - k` acquisition interval target으로 정렬하고 complete partition coverage, dataset/feature schema와
  duplicate/missing acquisition을 fail-fast 검증합니다.
- XJTU-SY RUL / Prognostics numerical implementation 전에 마지막 recorded acquisition을 dataset-observed endpoint로
  사용하는 `N - k` acquisition-interval target, bearing-run leakage boundary, age/feature/sequence baseline ladder,
  bearing-first evaluation, uncertainty evidence 요구와 UI/GenAI dependency boundary를 고정한 protocol v1.

- XJTU LSTM anomaly-evidence trajectory의 earliest-third scored-window q95를 descriptive review threshold로 사용해
  threshold 초과 acquisition-contiguous observation을 score-exceedance interval로 표시하는 Analysis Explorer
  기능. 이 interval은 retrospective review aid이며 validated fault/state/alarm semantics를 만들지 않습니다.
- Analysis Explorer의 `Run Analysis` view에서 prepared XJTU-SY source를 기존 frozen LSTM pipeline으로 실행하고,
  생성 result를 동일한 `AnalysisView`로 재검증해 Summary/Evidence/AI Explanation에 즉시 연결하는
  source-to-analysis product vertical slice.
- Analysis Explorer의 선택 asset에 대해 bounded structured PHM evidence만 전송하는 Generative AI 설명/Q&A.
  API credential과 model이 명시적으로 설정된 경우에만 run button으로 OpenAI Responses API를 호출하고,
  `store=false` stateless request와 capability/limitation instruction boundary를 적용합니다.
- Validated XJTU LSTM analysis evidence를 사용자 결과 중심으로 검토하는 첫 PHM Analysis Explorer.
  Acquisition-aligned anomaly-evidence trajectory, high-score observation, feature residual과 capability를 표시하고
  기존 `ExperimentInspection` pipeline/provenance를 Analysis Details drill-down으로 재사용합니다.
- XJTU/IMS Isolation Forest와 XJTU LSTM evidence를 같은 Experiment Overview와 Pipeline Lineage vocabulary로 검토하는
  marimo 기반 Developer Workbench. Acquisition-level model의 Sequence Construction을 `not applicable`로 표시하고,
  raw trajectory/residual이 없는 result의 detailed evidence를 `not recorded`로 구분합니다.
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

- XJTU finalized holdout와 IMS fixed cross-test result를 schema별로 검증하고 Source → Canonical → Feature →
  Preprocessing → Reference → Sequence Construction → Population → Model → Scoring → Evaluation → Capability →
  Provenance 순서의 immutable read model로 해석하는 inspection capability와 첫 presentation surface인
  `experiment inspect` CLI.

- XJTU `fold-1 train/validation`에 한정한 LSTM Autoencoder development protocol v1. Robust-scaled full 16-feature
  input, train-bearing early-third reference, length 8 / stride 1 / right-edge sequence construction, deterministic
  reconstruction training, residual evidence와 retrospective evaluation 경계를 numerical execution 전에 고정합니다.

- Python 3.14 CPU reference execution에서 LSTM forward/backward와 seeded deterministic update를 검증하는 PyTorch
  2.14 `deep-learning` optional runtime, CPU-only lock source와 CI compatibility contract.

- ordered feature observations를 asset·partition·sequence boundary 안에서 fixed-length window로 변환하고 source row,
  start/end identity, right-edge alignment, stride와 source observation→window population provenance를 보존하는
  dataset-neutral sequence contract.
- XJTU fold-1 complete train을 train-fitted preprocessing state로 transform한 뒤 bearing별 early-third reference
  1,084 acquisitions를 1,021 fit windows로, validation 2,818 acquisitions를 2,797 scoring windows로 구성하는
  dataset-specific boundary와 frozen population validation.
- XJTU LSTM protocol v1의 단일 packaged configuration과 complete-train preprocessing fit부터 sequence construction,
  deterministic CPU LSTM Autoencoder fit까지 연결하는 protocol-defined execution path.
- Immutable windows를 float32 tensor로 변환하고 fixed 50 epochs의 Adam, global-norm gradient clipping과 final-epoch
  model state를 적용하며 runtime·seed·loss·parameter count provenance를 보존하는 LSTM model contract.
- Sequence input과 reconstruction의 schema·window identity를 정확히 결합하고, 실제 model runtime이 소비한
  float32 input을 기준으로 feature별 시간축 MSE와 right-edge source observation에 정렬된
  higher-is-more-anomalous window score를 생성하는 reconstruction scoring contract.
- XJTU LSTM validation score를 original full-run lifecycle thirds에 정렬해 bearing별 acquisition-order Spearman ρ,
  late-vs-middle rank probability와 feature residual mean을 계산하고 3-bearing equal-weight summary를 보존하는
  development evaluation contract.
- XJTU LSTM preprocessing state, sequence population, deterministic training provenance, acquisition-aligned score
  trajectory, per-window feature residual과 evaluation을 `xjtu-lstm-development-result-v1` JSON으로 보존하고 source
  validation부터 artifact write까지 연결하는 one-shot retrospective development execution contract.
- `xjtu-lstm-development-result-v1`의 raw score/residual evidence에서 bearing-first statistic을 다시 계산하고 Sequence
  Construction, model training, reconstruction scoring, retrospective evaluation과 capability/provenance를 같은
  immutable `ExperimentInspection` read model로 노출하는 LSTM result inspection reader.
- Clean `main`의 frozen XJTU LSTM protocol을 두 번 실행해 byte-identical SHA-256을 확인한 fold-1 train/validation
  retrospective evidence. 세 validation bearing의 equal-weight mean Spearman ρ는 `0.627559`, mean late-vs-middle
  rank probability는 `0.681636`이며 acquisition-aligned score와 16-feature residual을 함께 보존합니다.

- `mimii-due` dataset manifest(`provider = "manual"`, CC BY-NC-SA 4.0)와 Zenodo record·file checksum·local
  inventory를 기록한 MIMII DUE source profile.
- MIMII DUE prepared source의 directory·filename grammar, observed clip population과 16-bit mono 16 kHz WAV
  header compatibility를 검증하는 dataset-specific validator와 `data validate mimii-due` CLI.
- MIMII DUE WAV clip을 `pcm_amplitude` single-channel `CanonicalTimeSeries`로 변환하고 source
  group·machine·section·domain·split·clip label·원문 attribute와 PCM encoding provenance를 metadata에 보존하는
  audio `DomainAdapter`. Clip label은 sample `labels`로 투영하지 않고 PCM amplitude도 Adapter에서 정규화하지 않습니다.
- XJTU LSTM retrospective evidence를 정비 엔지니어 역할의 Evidence Summary / Trend & Observations /
  Limits & Provenance로 재배치하는 Maintenance Evidence Review low-fidelity prototype. Threshold/state,
  diagnosis, maintenance priority, RUL을 생성하지 않고 experiment evidence와 future operational result 경계를
  product contract에 명시합니다.
- MIMII DUE sections 00–02를 development, sections 03–05를 external evaluation으로 분리하고
  label-blind scoring, `audio-logmel-statistical-v1` 128-feature representation, section-level Isolation Forest,
  machine/section/domain AUC·pAUC와 evaluation ground-truth late-binding을 numerical result 전에 고정한
  experiment protocol v1.
- 16 kHz mono signed-PCM 10-second clip을 symmetric-Hann STFT, 64 HTK mel bands와 log-energy mean/std로
  128-feature vector로 변환하는 `audio-logmel-statistical-v1` representation. Waveform은 clip 단위로 소비하고
  dataset 전체 waveform materialization이나 audio-specific runtime dependency를 추가하지 않습니다.
- `AnomalyScores`와 binary labels를 source observation ID로 late-bind해 full ROC AUC와 standardized
  partial ROC AUC를 계산하는 dataset-neutral evaluator 및 zero를 epsilon으로 바꾸지 않는 unit-interval
  harmonic-mean helper.
- MIMII development v1의 하나의 packaged base configuration을 15개 machine type × section model config로
  결정적으로 resolve하는 dataset-specific contract. Section별 source normal train 전체와 target normal 3개를
  complete population으로 검증해 robust preprocessing/all-train model input을 만들고, test `clip_label`을
  읽지 않는 source/target scoring input을 분리합니다.
- MIMII dev source를 machine/section 단위로 lazy decode→log-mel feature→robust preprocessing→Isolation Forest
  fit/score하고 test label을 evaluator에서 source identity로 late-bind하는 development runner. 30개
  machine/section/domain AUC·pAUC strata, section별 fitted preprocessing provenance, machine/domain/global harmonic
  summaries와 capability boundary를 `mimii-due-domain-shift-development-result-v1` JSON으로 기록합니다.
- `industrial-phm experiment mimii-development` CLI와 representation parameter spec을 추가해 clean revision의
  numerical execution이 protocol/feature/model/evaluator 설정을 결과 artifact에서 재현할 수 있게 했습니다.
- MIMII development result inspection reader. 15 section exact coverage와 population/preprocessing state,
  30 machine/section/domain AUC·pAUC, harmonic summaries, evaluator-only label join, DCASE non-official flag,
  capability와 code provenance를 다시 검증한 뒤 기존 ExperimentInspection stage vocabulary로 노출합니다.
- MIMII development result에 packaged dataset manifest의 version, provider, source URL, citation DOI와 license를
  source-record provenance로 보존하고 inspection 시 동일 manifest와 재검증합니다. Prepared source 실행은
  record checksum을 다시 계산한다고 주장하지 않으며, archive MD5 evidence는 source profile이 계속 소유합니다.
- `experiment mimii-development`가 expensive numerical execution 전에 declared code revision과 current Git
  HEAD의 일치 및 tracked working tree clean 상태를 확인하는 authoritative-evidence revision guard.

- MIMII development numerical evidence의 authoritative 실행 절차를 full source validation → clean revision
  verification → 두 번의 독립 execution → byte/SHA-256 reproducibility → result inspection → repository artifact
  승격 순서로 고정한 execution runbook.

- MIMII DUE sections 00–02 development numerical evidence artifact. 두 번의 deterministic 실행이 byte-identical이며
  full source validation과 inspection을 통과한 결과만 승격했습니다.

- MIMII DUE development evidence 검토와 sections 03–05 external evaluation을 위한 v1 configuration freeze 결정.

- MIMII DUE evaluation test audio(Zenodo 4884786)와 ground truth(5257674) record 검증 기록. evaluation test
  filename에 label이 없어 late-binding이 source 구조로 보장됨을 확인했습니다.

- label 없는 MIMII evaluation-test source reader와 validator. clip record에 label field가 없어 scorer가
  label을 복원할 수 없습니다.

- `experiment mimii-external-score`로 생성하는 label-blind MIMII external score artifact.

- `experiment mimii-external-evaluate`로 생성하는 sections 03–05 late-bound external evaluation evidence.

### Changed

- 첫 end-to-end Analysis Application vertical slice를 완료 상태로 전환하고, 현재 제품/연구 우선순위를
  XJTU run-to-failure 기반 RUL/prognostics v1 통합으로 이동했습니다.
- 프로젝트의 현재 제품 단계를 experiment/dataset 확장 중심에서 end-to-end PHM Analysis Application vertical slice로
  전환했습니다. 기존 analysis/evidence를 사용자 결과·시각화·Generative AI 설명으로 연결하고,
  `ExperimentInspection`은 transparency drill-down으로 재사용하며, RUL/prognostics는 지원 가능한 source에서
  같은 application에 추가되는 핵심 PHM capability로 정렬합니다.
- Dataset-specific execution boundary와 authoritative evidence artifact 용어를 문서 전반에서 정렬하고, dataset
  validation 순서를 Workbench cross-schema 검토 → MIMII DUE → 근거 기반 Health Indicator/RUL 재검토로 갱신했습니다.
- LSTM training provenance의 모호한 `final_loss` property를 실제 집계 의미가 드러나는
  `final_epoch_mean_training_loss`로 변경하고 protocol/terminology의 evidence 전 구현 순서를 현재 계약과 정렬.
- Developer Workbench의 low-fidelity information architecture를 Experiment Overview, Pipeline Lineage와 Evidence
  Explorer로 구체화하고 acquisition→window population unit transition, capability availability와 provenance를
  검토하는 acceptance criteria를 정의.

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
