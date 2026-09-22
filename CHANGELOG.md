# Changelog

이 프로젝트의 사용자 및 개발자에게 의미 있는 변경사항을 기록합니다. 형식은 Keep a Changelog의
분류 방식을 따릅니다.

개발 중 package version은 `0.0.1`로 유지하며 기능 PR이나 내부 구조 변경마다 버전을 올리지 않습니다.
릴리즈 가능한 public API와 배포 정책을 별도로 결정할 때 versioning 정책을 다시 검토합니다. 그 전까지
의미 있는 변경은 `[Unreleased]` 아래에 누적합니다.

## [Unreleased]

### Added

- Prepared field CSV export를 Python 코드 없이 검증하는 `industrial-phm data validate-csv` CLI. Asset/channel/time mapping을 명시적으로 받고 sample/channel/time basis, source SHA-256, quality PASS/WARN을 출력하며 모델 fitting이나 thresholding은 실행하지 않습니다.
- Dataset-neutral RUL endpoint semantics. `RulTargetSeries`가 `observed-record-end`, `confirmed-failure`, `right-censored`, `unknown` endpoint 의미를 구분하며, exact RUL target으로 표현할 수 없는 right-censored lifecycle은 fail-fast로 차단합니다. XJTU-SY `N-k` target은 기존 수치/JSON을 바꾸지 않고 `observed-record-end`를 명시합니다.
- 일반 산업 센서 export를 위한 `CsvSensorAdapter`와 최소 data-quality/provenance boundary. 한 CSV 파일을 한 asset segment로 mapping하고 channel/time basis를 명시적으로 요구하며, missing/non-numeric/non-finite 값과 timestamp 역행을 차단합니다. Irregular timestamp interval은 재격자화하지 않고 warning으로 보존하며 source SHA-256과 byte size를 canonical metadata/validation report에 기록합니다.
- XJTU-SY RUL v1 held-out benchmark의 실제 numerical artifact
  `docs/research/results/xjtu-sy-rul-lstm-fold-1-benchmark-v1.json`. Prepared local source(3 conditions /
  15 bearing runs / 9,216 acquisitions, profile PASS)에서 clean tracked revision
  `2ae41acc16c45bf922f3b6ad8a228103d16d0982`로 runbook 절차를 실행했고, 독립 실행 두 개가 byte-identical
  (SHA-256 `874860c9a959e62311e959dc4609b022058cfb75ca4f107cf901d43b641b0fbf`)이며 두 artifact 모두 shared
  inspection read model을 통과했습니다. Validation-selected temporal LSTM을 fold-1 held-out
  Bearing1_1 / Bearing2_1 / Bearing3_1에 적용해 3,131개 prediction에서 equal-bearing mean MAE 458.251
  acquisition interval, normalized MAE 0.3313을 기록했습니다. Lifecycle-position diagnostic은 early 790.831 →
  middle 455.316 → late 133.096으로 감소합니다. 이 bearing들은 project history의 anomaly/robustness 연구에
  노출된 적이 있어 pristine external holdout이 아니며, `operational_primary_method_id`는 `null`로 유지되고
  prediction interval / uncertainty calibration / validated physical failure threshold / field RUL validation /
  maintenance decision recommendation은 모두 unsupported입니다.

- Frozen XJTU RUL held-out benchmark result를 기존 `ExperimentInspection` stage vocabulary로 검증·요약하는 reader. Validation-selected LSTM identity, null operational primary, test-bearing population, point/lifecycle aggregate, capability boundary와 retrospective benchmark limitation을 확인하며 aggregate/capability drift를 거부합니다.
- Validated AnalysisView를 deterministic Markdown으로 내보내는 `analysis report` CLI와 report renderer. Anomaly artifact를 primary scope로 사용하고 compatible한 prognostics artifact만 attached evidence로 포함하며, 별도 revision/source-byte-identity 한계와 capability/inspection warning을 report에 보존합니다.
- Analysis evidence compatibility/provenance contract. AnalysisView가 dataset/split/fold/revision과 train/evaluation population, excluded scope, verified source acquisition count를 artifact에서 보존하고, 서로 다른 anomaly/prognostics artifact는 population scope가 맞을 때만 같은 Explorer surface에서 attached evidence로 표시합니다. Exact source byte identity는 현재 artifact가 기록하지 않으므로 미검증 상태를 명시하며, revision이 달라도 하나의 실행으로 합치지 않습니다.
- Validation-selected temporal LSTM을 fold-1 held-out bearing에 적용하는 XJTU RUL benchmark result schema/runner/CLI와 execution runbook. Point error와 protocol-fixed early/middle/late lifecycle diagnostics를 기록하고, operational primary와 uncertainty/physical-failure/field/maintenance capability는 승격하지 않습니다.
- XJTU RUL protocol §9.1 lifecycle-position evaluator. Complete recorded lifecycle을 `early/middle/late` thirds로 고정하고, sequence dropped prefix로 boundary를 다시 나누지 않은 채 bearing별 prediction count·MAE·RMSE·signed error·normalized MAE와 equal-bearing aggregate를 기록할 수 있게 했습니다.
- XJTU RUL v1 finalization decision. Protocol §8의 frozen equal-bearing validation MAE rule을 그대로 적용해 `xjtu-sy-rul-lstm-fold-1-v1`을 validation-selected candidate로 기록하되 operational primary와 분리하고, 현재 calibration population으로 nominal coverage를 정당화하지 않아 v1 prediction interval/uncertainty calibration을 `unsupported/not validated`로 freeze했습니다. 당시 다음 단계로 lifecycle-position diagnostics와 frozen candidate held-out benchmark를 고정했으며, 해당 benchmark 실행은 이후 canonical numerical artifact로 완료되었습니다.
- Generative AI explanation의 prognostics evidence scope. Analysis Explorer `AI Explanation` 화면에서
  anomaly evidence와 prognostics evidence 중 설명 대상을 고르며, prognostics context는 validated read model에서
  읽은 method별 recorded estimate와 as-of acquisition, target 의미/unit/formula/clipping 여부, common support,
  retrospective validation 오차, unavailable capability, 그리고 아직 `None`인 `primary_method_id`만 전달합니다.
  Boundary 지시는 RUL 재계산·외삽·단위 변환, physical failure time이나 calendar date로의 번역, failure
  threshold·alarm/state·maintenance deadline·confidence interval 생성, 검증되지 않은 primary method 선택을
  금지하고, clipping이 없는 target이므로 음수 추정도 0으로 올리지 않고 기록된 대로 보고하게 합니다.

- 기존 `xjtu-rul-baseline-validation-result-v1`을 변경하지 않고 age-only, feature-Ridge, temporal-LSTM을
  같은 fold-1 validation target/evaluator에서 비교하는 `xjtu-rul-three-model-validation-result-v1` evidence
  schema/runner/CLI. Temporal method의 train-only preprocessing, right-edge sequence population, deterministic
  PyTorch training provenance와 acquisition-8..N prediction subset을 보존합니다. 기존 age/Ridge full-run
  비교는 별도로 유지하고, 세 method의 pairwise MAE/RMSE/normalized-MAE delta는 모두 동일 acquisition-8..N
  common support에서 계산해 support mismatch를 비교 결과에 섞지 않습니다. Held-out test와 uncertainty/field
  validation은 결과 범위에서 제외합니다.
- XJTU RUL protocol의 frozen temporal LSTM comparator. Complete fold-1 train acquisition에서만 robust scaling을
  fit하고 8-acquisition right-edge sequence window를 구성해 raw `N - k` target을 aligned source identity에
  결합합니다. Dataset-neutral supervised LSTM regressor는 deterministic CPU execution과 final-epoch provenance를
  보존하며 prediction을 clamp하지 않습니다. Validation/test의 첫 7 acquisition은 필요한 sequence context가
  없으므로 prediction subset에서 제외하고 기존 bearing-first RUL evaluator가 동일 target 의미로 평가합니다.
- XJTU RUL age-only/feature-Ridge fold-1 validation을 실제 prepared source에서 동일 target/evaluator로 실행하는
  versioned evidence schema, deterministic JSON writer와 CLI. Artifact는 clean tracked Git revision, train/validation
  source scope, test exclusion, target semantics, preprocessing/model provenance, per-bearing prediction/evaluation과
  baseline delta를 보존하며 prediction interval/field validation을 지원 범위로 승격하지 않습니다.
- XJTU RUL protocol의 frozen acquisition-feature Ridge comparator. 전체 16개 vibration-statistical feature를
  complete train partition에서 robust scaling하고 bearing-balanced resampling으로 fit하며, raw `N - k` target을
  source observation identity로 정렬합니다. Validation/test에서는 동일 preprocessing state와 model을 사용하고
  output을 clamp하지 않은 채 기존 bearing-first RUL evaluator에 전달합니다.
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

- XJTU fold-1 three-model RUL validation numerical artifact. age-only / feature-Ridge / temporal LSTM을
  acquisition 8..N common support에서 비교한 development evidence입니다.

- XJTU three-model RUL validation result를 공통 `ExperimentInspection` stage vocabulary로 읽는 inspection
  reader.

- `AnalysisView`의 capability composition과 XJTU RUL prognostics evidence read model.

- Analysis Explorer Prognostics 화면과 presentation-independent prognostics summary helper.

### Changed

- Field CSV validation provenance에 CSV delimiter, minimum sample count, optional sampling-rate tolerance를 추가했습니다. Validation report, canonical metadata와 `data validate-csv` 출력이 같은 policy를 보존해 quality PASS/WARN이 어떤 입력 정책에서 결정됐는지 추적할 수 있습니다.
- Field CSV parsing과 SHA-256/byte-size provenance를 동일 byte snapshot에서 계산하도록 바꿔, source file이 실행 중 변경될 때 parsed values와 기록된 digest가 서로 다른 file state를 가리킬 수 있는 TOCTOU 간극을 제거했습니다.
- Field CSV validation에서 관찰한 source-quality state/issue code와 sampling interval 최대 편차를 canonical metadata에 보존하고, 기존 vibration feature projection이 해당 provenance를 그대로 전달하도록 계약 테스트를 추가했습니다.
- Field CSV timestamp quality 검증에 explicit sampling-rate consistency check를 추가했습니다. Timestamp와 `sampling_rate_hz`를 함께 제공하면서 사용자가 `sampling_rate_tolerance_ratio`를 명시한 경우에만 관측 interval 편차를 계산하고, 허용 범위를 넘으면 `sampling-rate-mismatch` warning을 남깁니다. 자동 resampling이나 metadata 보정은 하지 않습니다.
- Analysis Explorer가 detailed projector가 없는 inspectable artifact를 오류로 종료하지 않고 inspection-only 화면으로 엽니다. IMS/MIMII 같은 schema에서는 저장된 pipeline/capability/provenance만 표시하고, artifact에 없는 observation-level trajectory나 RUL evidence는 재구성하지 않습니다.
- Analysis Explorer의 새 분석 실행 흐름을 `데이터 입력 -> 사전 검증/실행 계획 -> 실제 실행`으로 분리했습니다. 실행 계획은 application-level source validation을 재사용하며, 입력이 변경된 stale plan이나 blocker가 있는 plan으로 실제 LSTM 실행을 시작하지 않습니다.
- Analysis Explorer의 첫 화면을 기술 지표 중심에서 사용자 검토 흐름 중심으로 재구성했습니다. 집중 확인 구간과 가장 높은 구간을 먼저 보여주고 Spearman rho/검토 기준값은 상세 정보로 이동했으며, AI 설명은 독립 메뉴 대신 이상 근거와 RUL 결과 문맥 안에서 사용하도록 배치했습니다.
- Generative AI explanation 요청에 API credential을 붙일 수 있는 endpoint를 configured OpenAI Responses API endpoint로 제한해, 호출자가 임의 host로 secret-bearing request를 보낼 수 없도록 경계를 강화했습니다.
- `CanonicalTimeSeries` canonical boundary가 sensor `values`, optional RUL과 sampling rate의 NaN/Inf를 거부하고, sensor/RUL payload의 non-numeric 및 boolean 값을 fail-fast 처리하도록 numeric/finite invariant를 강화했습니다.
- Analysis Explorer에서 저장하는 Markdown 보고서를 사용자 결과 중심 한국어 구조로 개편했습니다. 이상 변화와 RUL 모델 비교를 먼저 보여주고 split/revision/artifact/capability와 inspection warning은 뒤쪽 기술 정보로 이동했습니다.
- CLI onboarding을 개선했습니다. `doctor`가 Python, repository checkout, data root, research/deep-learning runtime 상태와 다음 Explorer 실행 명령을 보여주고, `data status/fetch/verify/inspect/validate`가 실패 또는 완료 후 다음 데이터 준비·검증 행동을 안내합니다.
- Git clone부터 Analysis Explorer 실행까지의 사용자 여정을 정리했습니다. README의 첫 실행을 `clone → Python 3.14 → marimo run`으로 단순화하고, Explorer 주요 화면을 한국어 결과 중심으로 재구성했습니다. 새 XJTU 분석은 데이터 폴더만 입력하면 현재 clean Git revision을 자동 기록하며, 결과 화면에서 Markdown 보고서를 바로 저장할 수 있습니다.
- Root README를 한국 사용자 중심의 제품 소개 흐름으로 다시 구성했습니다. 영문 섹션 제목과 미지원 기능/신뢰 경계 중심 설명을 제거하고 전체 구조, 주요 기능, 빠른 시작, 사용 데이터, 개발 방향과 문서 링크에 집중했습니다. Analysis Explorer 화면 캡처는 향후 `assets/analysis-explorer.png`만 추가하면 상단 소개 영역에 연결할 수 있도록 위치와 자산 규칙을 준비했습니다.
- Root README를 197-line minimal landing page로 다시 압축했습니다. Capability, architecture, quickstart, evidence/limits, roadmap과 핵심 docs만 남기고 중복된 RUL 상세·research direction·repository layout 설명을 authoritative 문서로 이동했습니다.
- Root README를 experiment history 중심 문서에서 capability/status, quickstart, evidence boundary와 roadmap 중심의 product landing page로 재구성했습니다. 2025–2026 PHM의 uncertainty·robustness·domain shift·human-in-the-loop·LLM copilot·industrial integration 흐름과 관련 표준/산업 사례는 별도 research note로 분리했습니다.
- CLI implementation handler를 `commands/data.py`, `commands/feature.py`, `commands/experiment.py`, `commands/analysis.py`로 분리했습니다. Public command/parser surface는 유지하고 `cli.py`는 parser wiring과 entrypoint 중심으로 축소했습니다. Evidence artifact는 canonical machine evidence와 deterministic human-review representation을 분리하는 저장·리뷰 정책을 추가했습니다.
- Prognostics GenAI context가 retrospective development validation scope, holdout 사용 여부, field validation 여부와 Scoring/Evaluation inspection warnings를 구조화해 전달합니다. 모델 instruction은 이 범위를 넓혀 해석하지 못하도록 명시합니다.
- Prognostics presentation capability는 `available` 목록에 명시된 경우에만 활성화되는 fail-closed 규칙으로 판정합니다. `target_clipping`/`target_normalization`도 result artifact의 target semantics를 `PrognosticsEvidence`까지 그대로 전달해 summary/GenAI 계층이 같은 사실을 별도로 하드코딩하지 않도록 정리했습니다.
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
