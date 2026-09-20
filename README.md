# industrial-phm-framework

이기종 산업 설비 시계열 데이터를 공통 분석 구조로 연결하기 위한 모듈형 PHM
(Prognostics and Health Management) 프레임워크입니다.

설비·데이터셋별 차이는 Domain Adapter에 격리하고, 공통 데이터 계약을 기준으로
전처리, 상태 평가, 이상 탐지, prognostics, 평가 및 서비스 계층을 확장하는 것을 목표로 합니다.
생성형 AI는 PHM 모델의 수치 출력을 대신 계산하지 않고, 구조화된 분석 결과를 해석하고 정비 의사결정을
지원하는 상위 계층으로 통합합니다.

> 현재 상태: first experiment implementation / pre-alpha (`0.0.1`)

## Architecture

![System Architecture](assets/system-architecture.png)

아키텍처의 현재 기준선과 각 계층의 책임은
[`docs/architecture/overview.md`](docs/architecture/overview.md)에 유지합니다.

## Design Principles

- **Domain boundary first**: 원천 데이터 차이는 Domain Adapter가 흡수합니다.
- **Contract-driven core**: 공통 PHM 계층은 특정 데이터셋 형식이 아니라 명시적 데이터 계약에 의존합니다.
- **Model-independent evaluation**: 모델 구현과 평가 로직을 분리해 비교 실험의 재사용성을 유지합니다.
- **Reproducible by default**: 코드, 환경, 데이터 provenance, 모델 artifact를 추적 가능한 형태로 관리합니다.
- **GenAI after PHM**: LLM은 계산된 PHM 결과를 해석하며, 핵심 수치 산출의 source of truth가 되지 않습니다.
- **Grow by evidence**: workspace, plugin, MLOps 구성은 실제 확장 요구가 생긴 시점에 도입합니다.

상세 원칙은 [`docs/architecture/principles.md`](docs/architecture/principles.md)를 따릅니다.
실행 인터페이스, 데이터 획득, Source of Truth, configuration 및 packaging 경계는
[`docs/architecture/operational-foundation.md`](docs/architecture/operational-foundation.md)에 정리합니다.
테스트 생성 기준은 [`docs/testing-policy.md`](docs/testing-policy.md), 사용자 역할과 결과 UX 기준은
[`docs/product/overview.md`](docs/product/overview.md)를 참조합니다. 연구·실험·PHM 기능에서 사용하는 공통 용어는
[`docs/terminology.md`](docs/terminology.md)를 기준으로 합니다.

## Python Compatibility

- CPython `3.14.x` (GIL-enabled build): 검증 대상
- CPython 3.14 free-threaded build: Python 자체에서는 공식 지원되지만 이 프로젝트에서는 아직 검증하지 않음
- 다른 Python minor version: 지원 범위에 포함하기 전에 CI 및 주요 ML dependency 호환성을 검증

프로젝트의 `requires-python`은 현재 `>=3.14,<3.15`로 제한합니다. 새 Python minor version을 암묵적으로
지원하지 않고, 검증 후 명시적으로 범위를 확장합니다.

## Development

[uv](https://docs.astral.sh/uv/)를 프로젝트 및 dependency 관리 도구로 사용합니다.
저장소의 `uv.lock`을 재현 가능한 개발 환경의 기준선으로 취급합니다.

```bash
uv python install 3.14
uv lock --check
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv build
```

LSTM/sequence model runtime을 다룰 때는 CPU reference extra와 compatibility contract를 함께 실행합니다.

```bash
uv sync --locked --extra deep-learning
uv run --locked --extra deep-learning pytest tests/contract/test_deep_learning_runtime.py
```

의존성을 변경할 때는 `pyproject.toml`과 함께 `uv.lock`을 갱신하고 같은 변경 단위로 commit합니다.
커밋, PR, 테스트 및 문서화 규칙은 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 따릅니다.
중요한 구조 결정은 [`docs/adr`](docs/adr)에 ADR로 남깁니다.

## CLI and Dataset Acquisition

프로젝트 기능은 설치 가능한 `industrial-phm` 명령으로 노출합니다. 데이터 획득·local source
inspection·dataset-specific compatibility validation, feature characterization과 현재 구현된 XJTU experiment
workflow를 실제 책임 이름으로 노출하며, 필요가 확인되기 전에 빈 `train`/`evaluate` 명령을 미리 만들지
않습니다.

```bash
uv run industrial-phm doctor
uv run industrial-phm data list
uv run industrial-phm data status xjtu-sy
uv run industrial-phm data status ims-bearings
uv run industrial-phm data status ai4i-2020
```

자동 획득을 허용하는 공개 데이터셋은 사용자가 명시적으로 `fetch`를 실행할 때만 내려받습니다.
AI4I 2020은 UCI 공식 배포 ZIP을 `data/raw/ai4i-2020/` 아래에 보존합니다.

```bash
uv run industrial-phm data fetch ai4i-2020
uv run industrial-phm data verify ai4i-2020
```

IMS Bearings는 NASA PCoE 공식 ZIP endpoint를 registry에 등록합니다. `fetch`는 raw archive와 local
SHA-256 provenance를 보존하고, extracted source의 `validate`는 3개 test·9,464개 acquisition profile과
waveform compatibility를 검사합니다.

```bash
uv run industrial-phm data fetch ims-bearings
uv run industrial-phm data verify ims-bearings
```

XJTU-SY처럼 원 출처가 여러 cloud mirror를 제공하는 dataset은 `manual` provider로 등록합니다.
CLI는 공식 source를 안내하고 사용자가 확인한 local source를 validation input으로 받습니다.

원본 배포물 inventory와 압축 해제된 Adapter source의 의미는 구분합니다.

```bash
uv run industrial-phm data inspect xjtu-sy --source data/raw/xjtu-sy

uv run industrial-phm data validate xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
```

`data inspect`는 local inventory를 요약하고, `data validate`는 dataset source profile과 Adapter
compatibility를 검사합니다. 상세 준비 절차는 [`data/README.md`](data/README.md)를 참조합니다.

해제된 IMS prepared source는 NASA archive의 test/file/time/channel profile과 bearing별 canonical 변환
계약을 검사합니다.

```bash
uv run industrial-phm data validate ims-bearings \
  --source data/interim/ims-bearings/source
```

MIMII DUE prepared source는 development/evaluation directory grammar, filename metadata, 전체 clip count와
16 kHz mono PCM WAV header compatibility를 검사합니다.

```bash
uv run industrial-phm data validate mimii-due \
  --source data/interim/mimii-due/source
```

기본 raw data 위치는 `data/raw`이고 `INDUSTRIAL_PHM_DATA_DIR`로 변경할 수 있습니다. 데이터셋 선정 근거와
provenance 주의사항은 [`docs/research/dataset-selection.md`](docs/research/dataset-selection.md)를 참조합니다.

## Research Workflow

`notebooks/`는 실제 산업 데이터를 관찰하고 EDA·contract 검증·작은 PoC를 수행하는 exploratory-analysis
공간입니다. Notebook이나 interactive tool은 production pipeline의 두 번째 구현이나 실험 결과의 Source of Truth가
아니며, 반복 가능한 계산 로직은 `src/industrial_phm/`로 승격합니다.

프로젝트 환경은 lockfile 기준으로 준비하고 Jupyter는 현재 일회성 연구 도구로 실행합니다.

```bash
uv sync --locked
uv run --with jupyter jupyter lab
```

첫 inspection notebook으로 확인한 실제 XJTU-SY 구조와 time-axis 결론은
[`docs/research/xjtu-source-profile.md`](docs/research/xjtu-source-profile.md)에 승격했습니다. 반복되는
directory/schema 확인은 `data validate`로 production code에 이동했고, Notebook은 같은 validation을 다시
구현하지 않습니다. Notebook 운영 규칙과 현재 연구 진입점은 [`notebooks/README.md`](notebooks/README.md)를
참조합니다.

Version-controlled candidate를 development validation에 실행할 때는 code revision을 명시하고 결과 JSON을
생성합니다. XJTU 첫 baseline은 이후 reference comparison, finalized configuration, one-shot holdout과
post-holdout cross-fold robustness까지 완료됐으며, 아래 `validate` 명령은 그 역사적 development workflow의
재현 가능한 진입점입니다.

```bash
uv run industrial-phm experiment validate xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \
  --output docs/research/results/xjtu-sy-iforest-fold-1-validation-v1.json \
  --code-revision "$(git rev-parse HEAD)"
```

Bearing별 Spearman ρ 하나만으로는 score trajectory의 형태를 알 수 없으므로, 필요할 때
`--score-trajectory-dir`로 acquisition별 anomaly score를 development diagnosis artifact로 함께 남깁니다. 이
flag는 model fit·validation scoring/evaluation·selection을 바꾸지 않고, 요청된 경우에만 `train`을 추가
in-sample scoring합니다. 이 development command 자체는 holdout을 scoring하지 않으며, fold-1 holdout은 별도
finalized execution에서 이미 1회 사용되어 소진됐습니다.

이미 기록된 XJTU finalized holdout과 IMS cross-test evidence는 read-only inspection으로 확인합니다. 두 schema는
각자의 numerical interpretation을 유지하면서 source cardinality, effective feature/model configuration,
population flow, capability와 declared code revision을 같은 stage 순서로 해석합니다. Schema reader가 생성하는
immutable `ExperimentInspection` read model과 text renderer를 분리하며, CLI는 이 capability의 첫
developer-facing presentation surface입니다.

```bash
uv run industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-iforest-fold-1-holdout-v1.json

uv run industrial-phm experiment inspect \
  docs/research/results/ims-bearings-iforest-single-channel-cross-test-v1.json
```

MIMII DUE의 first audio development path는 protocol-fixed sections 00–02만 사용하며, test label은 scoring path가
아니라 evaluator edge에서만 결합합니다. 실제 numerical evidence는 implementation이 merge된 clean `main`
revision에서 다음 명령으로 생성합니다.

```bash
uv run industrial-phm experiment mimii-development mimii-due \
  --source data/interim/mimii-due/source \
  --output docs/research/results/mimii-due-iforest-domain-shift-development-v1.json \
  --code-revision "$(git rev-parse HEAD)"
```

첫 numerical PHM baseline의 data partition은 모델 코드에서 임의로 만들지 않습니다.
[`docs/research/xjtu-experiment-protocol.md`](docs/research/xjtu-experiment-protocol.md)가 development/holdout-test
경계와 leakage 규칙을 설명하고, packaged split manifest가 실제 bearing-run assignment의 Source of Truth가 됩니다.

Acquisition-level vibration baseline은 `industrial_phm.features`의 versioned feature set으로 계산합니다. Feature를
상관계수 하나로 자동 선정하거나 test trajectory를 반복해서 보고 튜닝하지 않고,
[`docs/research/xjtu-feature-characterization.md`](docs/research/xjtu-feature-characterization.md)에 따라
lifecycle·condition·channel·redundancy를 분석합니다. Characterization을 완성한 뒤에야 interactive analysis를
시작한다고 가정하지 않고, 현재 artifacts를 먼저 탐색하면서 실제로 반복되는 분석 요구를 reusable code로
승격합니다.

## Repository Layout

```text
.
├── .github/                # CI 및 협업 템플릿
├── assets/                 # canonical PNG 아키텍처 자산
├── docs/
│   ├── architecture/       # 시스템 구조와 설계 원칙
│   ├── product/            # 사용자 역할과 결과 UX 기준
│   ├── research/           # 데이터셋·benchmark·experiment protocol 조사
│   ├── terminology.md      # 연구·실험·PHM 공통 용어 기준
│   └── adr/                # Architecture Decision Records
├── notebooks/              # EDA·contract 검증·작은 PoC용 exploratory analysis
├── src/industrial_phm/
│   ├── contracts/          # 도메인 중립 데이터 계약
│   ├── adapters/           # 설비/데이터셋별 변환 경계
│   ├── data/               # dataset manifest·acquisition·validation
│   ├── experiments/        # experiment contract, split/config와 dataset-specific execution
│   ├── features/           # stateless numerical feature extraction
│   ├── models/             # model-fitting input과 model implementation
│   ├── preprocessing/      # train-fitted feature scaling state
│   └── sequences/          # feature-row window construction과 source lineage
└── tests/
    ├── unit/
    └── contract/
```

필요해지기 전까지 빈 `models/`, `apps/`, `pipelines/` 등의 디렉터리를 미리 만들지 않습니다.
실제 기능 PR에서 책임과 경계를 검토한 뒤 추가합니다.

## Roadmap

### Completed

- repository/package/CI와 변경·테스트·문서 운영 기준선
- dataset registry와 명시적 fetch/verify/inspect/validate workflow
- `CanonicalTimeSeries`와 dataset별 `DomainAdapter` 책임 경계
- XJTU-SY와 IMS 실제 source profile, validator, Adapter를 통한 canonical conformance
- XJTU-SY condition-stratified 5-fold bearing-run split과 leakage contract
- `vibration-statistical-v1` feature, split-aware characterization artifact와 interactive analysis
- `fold-1/train` evidence에서 도출한 첫 model experiment candidate dimensions
- dataset-neutral `ExperimentConfig v1`과 XJTU `fold-1` Isolation Forest 4개 active candidate
- train provenance와 feature schema를 고정하는 identity/robust `PreprocessingState`
- dataset-neutral `ModelFitInput`/`ModelScoringInput`과 acquisition-complete XJTU fit/scoring 준비 경계
- 검증된 XJTU train feature vectors에서 preprocessing fit과 model-fit input을 함께 생성하는 실행 경로
- dataset-neutral Isolation Forest fit/scoring과 higher-is-more-anomalous `AnomalyScores`
- XJTU validation bearing별 acquisition-order Spearman ρ를 사용하는 model-independent development evaluator
- XJTU `fold-1 validation` candidate 실행과 reproducible result artifact
- selection과 분리된 train/validation acquisition별 anomaly-score trajectory development diagnosis
- complete train / reference / model-fit population을 분리하는 reference strategy 계약과 fold-1 H0/H1 비교
- 비교용 manifest와 분리해 정확히 하나의 configuration을 소유하는 fold-1 finalized experiment configuration
- selection·calibration 없이 finalized configuration 하나만 소비하는 `fold-1` holdout evaluation 실행 경로
- `fold-1` holdout test 1회 실행과 development 결과와의 대조 evidence
- folds 2~5 test partition을 한 번에 실행하는 post-holdout cross-fold robustness 경로와 evidence
- verified IMS source profile과 canonical mapping을 기준으로 확인한 feature 계층의 cross-dataset portability와 XJTU dataset-specific boundary 가정 구분
- IMS Set 2 train → Set 3 README-documented evaluation으로 고정한 single-channel cross-test experiment protocol v1
- PHM/ML 개발자가 source → feature → preprocessing → reference/sampling → model → scoring/evaluation lineage를
  effective configuration·population flow·provenance와 함께 검토하는 pipeline transparency UX baseline 및
  Experiment Overview / Pipeline Lineage / Evidence Explorer low-fidelity Developer Workbench 구조
- IMS Set 2 → Set 3 one-time cross-test 실행과 preregistered temporal-shape statistic 관찰 evidence 기록
- IMS Set 2 complete train에서 preprocessing/model fit 후 Set 3 README-documented scope만 scoring하는
  fixed single-channel cross-test execution contract와 developer-transparent result schema
- XJTU finalized holdout과 IMS cross-test의 공통 pipeline stage, dataset-specific 의미와 inspection 정보 gap 비교
- XJTU holdout과 IMS cross-test result를 schema별로 검증해 immutable `ExperimentInspection`으로 해석하는
  inspection capability와 첫 presentation surface인 `experiment inspect` CLI
- XJTU fold-1 train/validation의 retrospective development scope, sequence construction, reconstruction score와
  evidence 경계를 numerical execution 전에 고정한 LSTM Autoencoder protocol v1
- Python 3.14와 Linux/macOS CPU wheel에서 deterministic LSTM training primitive를 검증한 PyTorch 2.14
  `deep-learning` optional runtime
- source row lineage, contiguous sequence와 asset·partition boundary, length/stride와 right-edge alignment를 보존하는
  dataset-neutral sequence-window construction contract
- fold-1 complete train preprocessing, bearing별 early-third reference와 validation acquisition을 공통 sequence
  contract에 연결하고 3,246→1,084→1,021 및 2,818→2,797 population lineage를 검증하는 XJTU dataset-specific boundary
- complete train vectors에서 robust preprocessing state를 직접 fit하고 1,021 reference windows로 deterministic
  PyTorch LSTM Autoencoder를 학습하는 protocol-defined XJTU execution path와 final-epoch training provenance
- immutable sequence input과 reconstruction의 schema·window identity를 대조하고, robust-scaled feature space의
  feature별 시간축 MSE와 right-edge acquisition-aligned window score를 생성하는 reconstruction scoring contract
- LSTM validation score를 original full-run lifecycle thirds에 정렬하고 bearing별 Spearman ρ,
  late-vs-middle rank probability, feature residual mean과 equal-bearing summary를 계산하는 XJTU development evaluator
- preprocessing fitted state, sequence population, deterministic training provenance, reconstruction score semantics,
  acquisition-aligned score trajectory, per-window feature residual, evaluation과 capability를 보존하는 XJTU LSTM
  development result schema와 one-shot execution path
- XJTU LSTM development result의 raw trajectory에서 bearing-first aggregate를 다시 검증하고 Sequence Construction,
  model training, reconstruction scoring, evaluation과 capability를 immutable `ExperimentInspection`으로 해석하는
  reader
- clean `main` revision `6f0d9593...`에서 두 번의 deterministic execution으로 동일 SHA-256을 확인한
  [XJTU LSTM fold-1 train/validation retrospective evidence](docs/research/results/xjtu-sy-lstm-autoencoder-fold-1-development-v1.json)
- XJTU/IMS Isolation Forest의 Sequence Construction applicability와 LSTM window population을 같은 ordered stage로
  표시하고, 세 실제 result의 Overview/Lineage 및 detailed evidence availability를 검토하는 Developer Workbench
- 세 result reader에서 반복되는 inspection 책임의 최소 승격 범위 검토. 새 public type 없이 반복된 stage
  구성과 capability 검증만 module 내부 helper로 정리
- MIMII DUE Zenodo record·license·file checksum 검증, `mimii-due` manual manifest와 local inventory 기반
  source profile
- MIMII DUE prepared source의 directory/filename/count profile과 16 kHz mono PCM WAV header를 검증하는
  dataset-specific validator와 `data validate mimii-due` CLI
- MIMII DUE 16-bit PCM clip을 normalization 없이 `CanonicalTimeSeries`로 옮기고 clip label·domain·section·
  원문 attribute를 metadata에 보존하는 audio `DomainAdapter`와 cross-domain canonical conformance
- XJTU LSTM retrospective evidence를 정비 엔지니어 관점의 Evidence Summary / Trend & Observations /
  Limits & Provenance로 재배치하고 anomaly evidence를 diagnosis·maintenance priority·RUL로 승격하지 않는
  role-specific Maintenance Evidence Review low-fidelity UX baseline
- MIMII DUE sections 00–02 development와 sections 03–05 external evaluation을 분리하고 label leakage,
  `audio-logmel-statistical-v1`, section-level Isolation Forest, AUC/pAUC와 one-shot ground-truth access를
  numerical result 전에 고정한 [experiment protocol v1](docs/research/mimii-due-experiment-protocol.md)
- protocol-defined 16 kHz/10-second PCM clip을 64-band log-mel frame statistic의 128-feature vector로 축약하는
  `audio-logmel-statistical-v1` representation과 observation ID로 labels를 late-bind하는 dataset-neutral
  binary AUC/pAUC evaluator
- 하나의 packaged MIMII development base configuration을 15개 machine type × section model identity로
  결정적으로 resolve하고, complete source/target normal train population에서 robust preprocessing과
  all-train `clip-uniform-v1` model input을 만들며 test label을 읽지 않는 scoring-input boundary
- MIMII dev source를 section 단위로 streaming해 15개 fixed Isolation Forest를 fit/score하고, evaluator edge에서
  labels를 late-bind해 30 machine/section/domain AUC·pAUC strata와 harmonic summaries를 생성하는
  `mimii-due-domain-shift-development-result-v1` execution/result contract와 CLI
- MIMII development result의 15 section population/preprocessing, 30 source/target AUC·pAUC strata,
  harmonic aggregate, DCASE non-official flag와 capability boundary를 재검증해 공통 Source → Evaluation →
  Provenance inspection read model로 해석하는 `experiment inspect` reader
- MIMII numerical artifact가 packaged dataset manifest의 version/provider/source URL/DOI/license identity를
  `source_scope.dataset_record`에 보존하고 inspection이 같은 manifest와 재대조하는 source-record provenance

### Current

1. frozen protocol에 따른 sections 00–02 MIMII development numerical evidence
   - [authoritative execution runbook](docs/research/mimii-due-development-execution-runbook.md)의 순서대로 실행
   - prepared source를 `data validate mimii-due`로 다시 확인
   - clean `main` revision에서 `experiment mimii-development` 실행
   - CLI가 declared `--code-revision` = current Git HEAD 및 tracked working tree clean 상태를 실행 전에 검증
   - 같은 revision/configuration의 deterministic rerun으로 result artifact 재현성 확인
   - 30 machine/section/domain AUC·pAUC와 source/target harmonic summary를 capability boundary 안에서 해석
   - authoritative numerical artifact와 code revision, dataset record provenance를 `docs/research/results/`에 기록

### Next

1. frozen protocol에 따른 sections 00–02 MIMII development numerical evidence
2. development review 후 configuration을 external evaluation에 freeze하거나 명시적인 protocol v2로 전환
3. freeze 후 evaluation test audio를 먼저 score하고 ground truth를 나중에 결합하는 sections 03–05 external evidence
4. 네 번째 result schema가 생긴 뒤 inspection public abstraction 필요성을 재검토
5. 첫 private/field source에서 quality, identity, event/censoring과 external-source boundary를 검증
6. event/onset/censoring 근거가 확보된 경우에만 Health Indicator/RUL 연구 범위를 재검토

### Later

- API와 역할 기반 dashboard
- 구조화된 PHM 결과와 정비 지식을 사용하는 Generative AI/RAG
- release/deployment 요구가 생긴 뒤 container·SBOM·attestation 검토

## Governance

- 공통 용어: [`docs/terminology.md`](docs/terminology.md)
- 변경 이력: [`CHANGELOG.md`](CHANGELOG.md)
- 기여 및 커밋/PR 규칙: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 보안 정책: [`SECURITY.md`](SECURITY.md)
- Architecture decisions: [`docs/adr`](docs/adr)
- 라이선스: [`Apache License 2.0`](LICENSE)

프로젝트 소스 코드는 Apache License 2.0으로 배포합니다. 데이터셋, 사전학습 모델, 제3자 코드 및 자산은
각 원저작자의 라이선스와 이용조건을 별도로 따르며, 도입 시 provenance와 호환성을 검토합니다.
