# industrial-phm-framework

**Evidence-first industrial PHM framework for anomaly analysis, prognostics, visualization, and bounded GenAI explanation.**

산업 센서 데이터를 재현 가능한 PHM(Prognostics and Health Management) evidence로 변환하고,
이상 변화와 RUL/prognostics 결과를 사용자 화면·report·생성형 AI 설명까지 연결하는 Python 기반 프레임워크입니다.

> **Status:** pre-alpha `0.0.1` · first end-to-end Analysis Application vertical slice complete ·
> XJTU RUL/prognostics v1 numerical held-out benchmark execution pending

이 프로젝트는 **데이터와 검증된 evidence가 지원하지 않는 capability를 주장하지 않습니다.**
LLM도 PHM 수치를 다시 계산하지 않고, numerical core가 만든 구조화된 evidence와 limitation만 설명합니다.

## Why this project

산업 PHM은 모델 정확도 하나로 끝나지 않습니다. 실제 적용에서는 source 차이, leakage, domain shift,
RUL target 의미, uncertainty, provenance, 사용자 해석과 운영 경계를 함께 관리해야 합니다.

이 저장소는 model zoo보다 다음 **evidence lifecycle**을 중심으로 설계합니다.

```text
industrial source
  -> source validation / Domain Adapter
  -> canonical data / feature / model
  -> model-independent evaluation
  -> versioned evidence artifact
  -> AnalysisView / ExperimentInspection
  -> Explorer / deterministic report / bounded GenAI
```

핵심 방향은 다음과 같습니다.

- **Domain boundary first** — 설비·dataset별 차이는 Adapter/source contract가 소유합니다.
- **Contract-driven core** — numerical core는 명시적 dataset-neutral contract에 의존합니다.
- **Model-independent evaluation** — 모델 구현과 평가 의미를 분리합니다.
- **Reproducible by default** — split, configuration, code revision, evidence provenance를 보존합니다.
- **Capability-aware** — 값이 없다고 0이나 추정값으로 채우지 않습니다.
- **GenAI after PHM** — LLM은 validated evidence를 설명하며 numerical source of truth가 아닙니다.
- **Grow by evidence** — 새로운 abstraction/model/platform은 실제 반복 요구가 확인될 때 추가합니다.

## What works today

| Capability | Status | Current evidence / boundary |
| --- | --- | --- |
| Dataset acquisition / validation | ✅ Implemented | XJTU-SY, IMS Bearings, MIMII DUE; AI4I fetch/verify |
| Canonical sensor contract | ✅ Implemented | dataset-specific Domain Adapters |
| Vibration anomaly analysis | ✅ Implemented | XJTU Isolation Forest + LSTM Autoencoder evidence |
| Cross-dataset portability | ✅ Implemented | XJTU → IMS fixed cross-test evidence |
| Acoustic domain-shift evaluation | ✅ Implemented | MIMII DUE development/external evidence |
| RUL point estimation | 🧪 Development evidence | XJTU age-only / Ridge / temporal LSTM |
| Frozen RUL held-out execution path | ✅ Implemented | runner, schema, lifecycle diagnostics, inspection runbook |
| Frozen RUL held-out numerical artifact | ⏳ Pending | prepared XJTU source에서 two-run deterministic execution 필요 |
| RUL prediction interval | — Not validated | v1에서 explicit unsupported |
| Validated physical failure threshold | — Not validated | recorded-end target을 physical failure time으로 승격하지 않음 |
| Fault diagnosis | — Not validated | fault semantics가 있는 적합한 source 필요 |
| Analysis Explorer | ✅ Implemented | anomaly + compatible attached prognostics evidence |
| Deterministic report export | ✅ Implemented | validated `AnalysisView` → Markdown |
| GenAI explanation / Q&A | ✅ Optional | bounded structured evidence only |
| Live inference / field deployment | — Not implemented | private/field source 단계에서 별도 operational contract 필요 |

## Reference evidence

공개 dataset은 단순 demo 목록이 아니라 서로 다른 PHM 질문을 검증하기 위해 사용합니다.

| Source | Role in this repository |
| --- | --- |
| **XJTU-SY** | run-to-failure vibration, anomaly trajectory, retrospective RUL/prognostics |
| **IMS Bearings** | 다른 bearing source에서 feature/model portability와 fixed cross-test 검증 |
| **MIMII DUE** | acoustic machine monitoring, label-blind scoring, domain shift / external evidence |
| **AI4I 2020** | dataset registry / acquisition / integrity workflow의 lightweight public example |

Dataset 선택 근거와 source provenance는
[`docs/research/dataset-selection.md`](docs/research/dataset-selection.md)를 참조합니다.

## Quickstart

### 1. Environment

검증 기준은 CPython `3.14.x` GIL-enabled build와 `uv.lock`입니다.

```bash
uv python install 3.14
uv sync --locked
uv run --locked industrial-phm doctor
```

### 2. Inspect existing evidence

Raw dataset 없이도 repository에 기록된 canonical evidence를 inspection read model로 확인할 수 있습니다.

```bash
uv run --locked industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-iforest-fold-1-holdout-v1.json

uv run --locked industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-rul-three-model-fold-1-validation-v1.json
```

### 3. Export a deterministic analysis report

```bash
uv run --locked industrial-phm analysis report \
  --anomaly docs/research/results/xjtu-sy-lstm-autoencoder-fold-1-development-v1.json \
  --asset Bearing1_2 \
  --prognostics docs/research/results/xjtu-sy-rul-three-model-fold-1-validation-v1.json \
  --output artifacts/reports/Bearing1_2.md
```

Report는 수치를 재계산하지 않고 validated read model을 렌더링합니다.
별도 prognostics artifact는 anomaly artifact와 dataset/split/fold/population scope가 compatible할 때만 attached evidence로 포함합니다.

### 4. Open the Analysis Explorer

```bash
uv sync --locked --group research
uv run --locked --group research marimo edit apps/analysis_explorer.py
```

Optional GenAI explanation은 `OPENAI_API_KEY`와 `INDUSTRIAL_PHM_GENAI_MODEL`이 있을 때만 활성화됩니다.
앱 경계와 artifact 선택 방법은 [`apps/README.md`](apps/README.md)에 정리합니다.

## Architecture

![System Architecture](assets/system-architecture.png)

현재 application의 중요한 dependency direction은 다음과 같습니다.

```text
source / adapter
  -> canonical data / features
  -> numerical model
  -> evaluation
  -> versioned evidence artifact
  -> inspection / analysis read model
  -> UI / report / GenAI
```

UI나 GenAI가 RUL target, metric, interval을 새로 계산하지 않습니다.
Experiment/anomaly/prognostics evidence는 capability-specific schema로 유지하며,
실제 operational output에서 반복 요구가 확인되기 전에는 universal `PHMResult`나 generic workflow engine을 만들지 않습니다.

상세 구조는 [`docs/architecture/overview.md`](docs/architecture/overview.md),
설계 원칙은 [`docs/architecture/principles.md`](docs/architecture/principles.md)를 따릅니다.

## Trust and evidence boundaries

이 프로젝트에서 **없음 / 미검증**은 정상적인 결과입니다.

- anomaly score를 자동으로 fault state, diagnosis, degradation state 또는 RUL로 승격하지 않습니다.
- RUL v1 target은 마지막 recorded acquisition까지 남은 `N-k` acquisition interval입니다.
- recorded-end target을 validated physical failure time으로 표현하지 않습니다.
- prediction interval은 calibration population, method, coverage/width evidence를 기록할 수 있을 때만 available로 선언합니다.
- 서로 다른 anomaly/prognostics artifact는 compatibility를 확인해도 하나의 execution으로 합치지 않습니다.
- 현재 artifact가 exact local source byte identity를 항상 기록하는 것은 아니므로 source-byte equality를 추정하지 않습니다.
- public retrospective benchmark 결과를 field validation이나 maintenance recommendation으로 표현하지 않습니다.
- GenAI는 raw sensor를 다시 분석하거나 RUL을 재계산·보정·clipping하지 않습니다.

Canonical numerical artifact와 사람이 읽는 summary/report의 역할은
[`docs/research/evidence-artifact-policy.md`](docs/research/evidence-artifact-policy.md)에 정리합니다.

## Current PHM direction

최근 PHM/Predictive Maintenance 연구와 산업 적용에서는 point accuracy뿐 아니라
**uncertainty, robustness under distribution shift, interpretability/human-in-the-loop, feasibility,
maintenance workflow integration**이 중요해지고 있습니다.

이 프로젝트는 그 흐름을 다음 순서로 반영합니다.

```text
model-centric PHM
  -> evidence-centric PHM        # current focus
  -> decision-support PHM        # field/private source + operational context 이후
```

LLM/copilot과 industrial foundation model도 빠르게 확장되고 있지만,
현재 우선순위는 더 큰 모델을 먼저 추가하는 것이 아니라 **field evidence, domain shift, uncertainty/calibration,
diagnostic semantics와 operational provenance를 먼저 검증하는 것**입니다.

2025–2026 연구 흐름, 관련 ISO 표준과 Siemens/IBM/Rolls-Royce 사례는
[`docs/research/phm-industry-direction.md`](docs/research/phm-industry-direction.md)에 별도로 정리합니다.

## Dataset workflow

모든 dataset을 자동 다운로드하거나 repository에 재배포하지 않습니다.
Provider/license/provenance에 따라 명시적인 fetch/inspect/validate 경계를 사용합니다.

```bash
uv run --locked industrial-phm data list
uv run --locked industrial-phm data status xjtu-sy
uv run --locked industrial-phm data status ims-bearings

uv run --locked industrial-phm data inspect xjtu-sy \
  --source data/raw/xjtu-sy

uv run --locked industrial-phm data validate xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
```

상세 준비 절차는 [`data/README.md`](data/README.md)를 참조합니다.

## RUL / Prognostics v1

현재 XJTU RUL v1은 protocol-frozen development evidence까지 구현되어 있습니다.

- target: `N-k`, unit = acquisition interval
- split: bearing-run boundary
- candidates: age-only, feature-Ridge, temporal LSTM
- validation selection: equal-bearing mean MAE rule
- validation-selected candidate: temporal LSTM
- operational primary method: none
- lifecycle diagnostics: early / middle / late thirds
- uncertainty interval: unsupported / not validated
- frozen held-out runner + result schema + inspection: implemented
- actual held-out numerical artifact: pending prepared-source execution

Held-out 실행 절차는
[`docs/research/xjtu-rul-benchmark-execution-runbook.md`](docs/research/xjtu-rul-benchmark-execution-runbook.md),
target/evaluation semantics는
[`docs/research/xjtu-rul-prognostics-protocol.md`](docs/research/xjtu-rul-prognostics-protocol.md)를 기준으로 합니다.

## Development

```bash
uv lock --check
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv build
```

Deep-learning runtime contract:

```bash
uv sync --locked --extra deep-learning
uv run --locked --extra deep-learning pytest tests/contract/test_deep_learning_runtime.py
```

CPython 3.14 free-threaded build와 다른 Python minor version은 현재 검증 범위가 아닙니다.
변경·테스트·문서화 규칙은 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 따릅니다.

## Repository layout

```text
.
├── apps/                    # Analysis Explorer
├── assets/                  # architecture diagrams
├── data/                    # local data layout / acquisition guidance
├── docs/
│   ├── architecture/        # system boundaries and ADR context
│   ├── product/             # user/result UX
│   ├── research/            # source profiles, protocols, runbooks, evidence policy
│   └── terminology.md
├── notebooks/               # exploratory analysis only
├── src/industrial_phm/
│   ├── adapters/            # dataset/domain boundary
│   ├── analysis/            # AnalysisView, composition, report
│   ├── commands/            # CLI command-family handlers
│   ├── contracts/           # canonical domain-neutral contracts
│   ├── data/                # manifests, acquisition, validation
│   ├── experiments/         # protocol/config/result execution and inspection
│   ├── features/            # numerical feature extraction
│   ├── genai/               # bounded evidence explanation
│   ├── models/              # model implementations
│   ├── preprocessing/       # train-fitted state
│   ├── prognostics/         # dataset-neutral RUL contracts/evaluation
│   └── sequences/           # source-aligned temporal windows
└── tests/
    ├── contract/
    └── unit/
```

## Roadmap

**Now**

1. Prepared XJTU source에서 frozen temporal LSTM held-out benchmark를 two-run deterministic procedure로 실행·검증
2. Canonical benchmark artifact를 versioned evidence로 승격하고 RUL v1 epic 마감

**Next**

1. CSV/WAV 등 local/general sensor input을 validation/Adapter boundary에 연결
2. 첫 private/field source에서 identity, data quality, event/censoring, provenance를 검증
3. fault semantics가 있는 source에서 diagnostics capability 검증
4. field evidence가 확보되면 uncertainty/calibration과 operational/live inference contract 확장

**Later, when evidence warrants it**

- maintenance history / CMMS / EAM context integration
- decision-support workflow and human approval boundary
- domain adaptation/generalization methods
- self-supervised / foundation-model approaches
- richer knowledge retrieval or agentic assistance

새 모델이나 platform은 roadmap 자체가 아니라 실제 evidence gap을 해결할 때 도입합니다.

## Documentation

| Topic | Owner |
| --- | --- |
| Architecture | [`docs/architecture/overview.md`](docs/architecture/overview.md) |
| Design principles | [`docs/architecture/principles.md`](docs/architecture/principles.md) |
| Operational / CLI boundaries | [`docs/architecture/operational-foundation.md`](docs/architecture/operational-foundation.md) |
| Product / result UX | [`docs/product/overview.md`](docs/product/overview.md) |
| Dataset preparation | [`data/README.md`](data/README.md) |
| Research protocols / runbooks | [`docs/research/README.md`](docs/research/README.md) |
| Evidence storage / review | [`docs/research/evidence-artifact-policy.md`](docs/research/evidence-artifact-policy.md) |
| Testing policy | [`docs/testing-policy.md`](docs/testing-policy.md) |
| Terminology | [`docs/terminology.md`](docs/terminology.md) |
| Contribution rules | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Change history | [`CHANGELOG.md`](CHANGELOG.md) |

## License and governance

프로젝트는 [MIT License](LICENSE)를 따릅니다.
Dataset의 원본 license/provenance는 project license와 별개이며 각 manifest와 dataset 문서를 따릅니다.

보안 정책은 [`SECURITY.md`](SECURITY.md),
중요한 구조 결정은 [`docs/adr/`](docs/adr/)에 기록합니다.
