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

의존성을 변경할 때는 `pyproject.toml`과 함께 `uv.lock`을 갱신하고 같은 변경 단위로 commit합니다.
커밋, PR, 테스트 및 문서화 규칙은 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 따릅니다.
중요한 구조 결정은 [`docs/adr`](docs/adr)에 ADR로 남깁니다.

## CLI and Dataset Acquisition

프로젝트 기능은 설치 가능한 `industrial-phm` 명령으로 노출합니다. 현재는 데이터 획득·local source
inspection·dataset-specific compatibility validation까지 구현하며, 모델 기능이 생기기 전에 빈
`train`/`evaluate` 명령을 미리 만들지 않습니다.

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
│   ├── experiments/        # version-controlled experiment split/config/protocol inputs
│   ├── features/           # stateless numerical feature extraction
│   ├── models/             # model-fitting input과 model implementation
│   └── preprocessing/      # train-fitted feature scaling state
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

### Current

1. bearing-first, model-independent development evaluator 방법론 확정과 구현

### Next

1. `fold-1 validation`과 experiment configuration finalization
2. finalized configuration의 `fold-1` holdout test evaluation
3. cross-fold robustness analysis
4. IMS에서 같은 feature/preprocessing/model/evaluation interface의 cross-dataset portability 확인
5. LSTM Autoencoder, reconstruction evidence, Health Indicator 연구
6. 데이터가 정당하게 지원하는 경우 RUL prognostics
7. MIMII DUE를 통한 cross-domain evaluation
8. 실제 여러 모델 출력에 근거한 PHM result/artifact/inference contract

### Later

- 첫 private/field source가 확보되면 access policy, quality, provenance, event/censoring, external-source boundary 검증
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
