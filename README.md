# industrial-phm-framework

**Evidence-first industrial PHM framework for anomaly analysis, prognostics, visualization, and bounded GenAI explanation.**

산업 센서 데이터를 검증 가능한 PHM(Prognostics and Health Management) evidence로 변환하고,
분석 결과를 Explorer, deterministic report, 생성형 AI 설명까지 연결하는 Python 기반 프레임워크입니다.

> **Status:** pre-alpha `0.0.1` · end-to-end Analysis Application vertical slice complete ·
> XJTU RUL v1 retrospective held-out benchmark recorded

**데이터와 검증된 evidence가 지원하지 않는 capability는 주장하지 않습니다.**
LLM도 PHM 수치를 다시 계산하지 않고 numerical core가 만든 structured evidence와 limitation만 설명합니다.

## What it does

| Capability | Status | Scope |
| --- | --- | --- |
| Source validation / canonicalization | ✅ | XJTU-SY, IMS Bearings, MIMII DUE, AI4I workflow |
| Vibration anomaly evidence | ✅ | XJTU Isolation Forest + LSTM Autoencoder |
| Cross-run / domain-shift evaluation | ✅ | IMS fixed cross-test, MIMII development/external evidence |
| Retrospective RUL evidence | ✅ | XJTU age-only / Ridge / temporal LSTM + frozen held-out benchmark |
| Explorer / report / GenAI explanation | ✅ | validated evidence only; GenAI is optional |
| Diagnosis / RUL uncertainty / field validation / live inference | — | not validated or not implemented |

현재 직접 사용자는 PHM/ML 개발자·연구자이며, 목표는 model zoo가 아니라
**재현 가능한 evidence lifecycle과 명시적인 capability boundary**를 만드는 것입니다.

## How it works

```text
industrial source
  -> validation / Domain Adapter
  -> canonical data / features
  -> numerical model
  -> model-independent evaluation
  -> versioned evidence artifact
  -> AnalysisView / ExperimentInspection
  -> Explorer / report / bounded GenAI
```

![System Architecture](assets/system-architecture.png)

핵심 원칙은 네 가지입니다.

- **Domain boundary first** — dataset·설비별 차이는 Adapter/source contract에 격리합니다.
- **Reproducible evidence** — split, configuration, code revision, evaluation과 provenance를 artifact에 보존합니다.
- **Capability-aware** — 지원되지 않는 결과를 0, 추정값, 임의 interval로 채우지 않습니다.
- **GenAI after PHM** — UI와 LLM은 numerical result를 재계산하거나 의미를 승격하지 않습니다.

상세 구조는 [Architecture](docs/architecture/overview.md),
설계 원칙은 [Design Principles](docs/architecture/principles.md)를 참조합니다.

## Quickstart

검증 기준은 CPython `3.14.x` GIL-enabled build와 repository의 `uv.lock`입니다.

### 1. Set up

```bash
uv python install 3.14
uv sync --locked
uv run --locked industrial-phm doctor
```

### 2. Inspect recorded evidence

Raw dataset 없이도 version-controlled evidence를 inspection read model로 검토할 수 있습니다.

```bash
uv run --locked industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-iforest-fold-1-holdout-v1.json

uv run --locked industrial-phm experiment inspect \
  docs/research/results/xjtu-sy-rul-lstm-fold-1-benchmark-v1.json
```

### 3. Open the Analysis Explorer

```bash
uv sync --locked --group research
uv run --locked --group research marimo edit apps/analysis_explorer.py
```

Optional GenAI explanation은 `OPENAI_API_KEY`와 `INDUSTRIAL_PHM_GENAI_MODEL`이 있을 때만 활성화됩니다.
앱 사용 범위는 [`apps/README.md`](apps/README.md)에 정리합니다.

Deterministic Markdown report도 같은 validated `AnalysisView`를 사용합니다.

```bash
uv run --locked industrial-phm analysis report \
  --anomaly docs/research/results/xjtu-sy-lstm-autoencoder-fold-1-development-v1.json \
  --asset Bearing1_2 \
  --output artifacts/reports/Bearing1_2.md
```

## Evidence and limits

공개 dataset은 단순 demo가 아니라 서로 다른 PHM 질문을 검증하기 위해 사용합니다.

| Source | Role |
| --- | --- |
| **XJTU-SY** | run-to-failure vibration, anomaly trajectory, retrospective RUL |
| **IMS Bearings** | Set 2 → Set 3 fixed cross-test portability evidence |
| **MIMII DUE** | acoustic anomaly scoring and domain-shift evidence |
| **AI4I 2020** | lightweight acquisition / registry / integrity workflow |

### RUL v1

XJTU RUL v1은 protocol-frozen development와 retrospective held-out benchmark evidence까지 기록되어 있습니다.

- target: 마지막 recorded acquisition까지 남은 `N-k` acquisition interval
- validation-selected method: temporal LSTM
- operational primary method: none
- held-out benchmark: Bearing1_1 / Bearing2_1 / Bearing3_1, 3,131 predictions
- equal-bearing mean MAE: **458.251 acquisition intervals**
- normalized MAE: **0.3313**
- prediction interval / uncertainty calibration: **not validated**
- validated physical failure threshold / field RUL validation: **not available**

Canonical benchmark:
[`xjtu-sy-rul-lstm-fold-1-benchmark-v1.json`](docs/research/results/xjtu-sy-rul-lstm-fold-1-benchmark-v1.json)

이 benchmark는 protocol-frozen **retrospective evidence**이며 pristine external validation이나 field validation이 아닙니다.
Target도 validated physical failure time을 의미하지 않습니다.

### Trust boundary

- anomaly score를 자동으로 fault state, diagnosis, degradation state 또는 RUL로 승격하지 않습니다.
- prediction interval은 calibration population과 coverage/width evidence가 있을 때만 capability로 선언합니다.
- 서로 다른 anomaly/prognostics artifact는 compatible해도 하나의 execution으로 합치지 않습니다.
- public benchmark evidence를 maintenance recommendation이나 operational answer로 표현하지 않습니다.
- GenAI는 raw sensor를 다시 분석하거나 RUL을 재계산·보정·clipping하지 않습니다.

세부 정책과 protocol:

- [Evidence Artifact Policy](docs/research/evidence-artifact-policy.md)
- [XJTU RUL Protocol](docs/research/xjtu-rul-prognostics-protocol.md)
- [RUL Benchmark Runbook](docs/research/xjtu-rul-benchmark-execution-runbook.md)
- [2025–2026 PHM Research & Industry Direction](docs/research/phm-industry-direction.md)

## Roadmap

| Horizon | Focus |
| --- | --- |
| **Now** | local/general sensor input, first private/field source, identity/data-quality/provenance |
| **Next** | diagnostics semantics, uncertainty/calibration, operational/live inference contract |
| **Later** | CMMS/EAM context, decision support, domain adaptation, SSL/foundation models, richer knowledge assistance |

새 모델이나 platform은 roadmap 자체가 아니라 **실제 evidence gap을 해결할 때** 도입합니다.

현재 방향은:

```text
model-centric PHM
  -> evidence-centric PHM        # current
  -> decision-support PHM        # after field/operational evidence
```

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

Deep-learning contract:

```bash
uv sync --locked --extra deep-learning
uv run --locked --extra deep-learning pytest tests/contract/test_deep_learning_runtime.py
```

CPython 3.14 free-threaded build와 다른 Python minor version은 현재 검증 범위가 아닙니다.

## Documentation

| Topic | Document |
| --- | --- |
| Product / result UX | [Product Overview](docs/product/overview.md) |
| Architecture | [Architecture Overview](docs/architecture/overview.md) |
| Operational / CLI boundary | [Operational Foundation](docs/architecture/operational-foundation.md) |
| Dataset preparation | [Data Guide](data/README.md) |
| Research protocols / runbooks | [Research Notes](docs/research/README.md) |
| Contribution / testing | [CONTRIBUTING](CONTRIBUTING.md) · [Testing Policy](docs/testing-policy.md) |

변경 이력은 [CHANGELOG](CHANGELOG.md), 공통 용어는 [Terminology](docs/terminology.md)를 참조합니다.

## License

[Apache License 2.0](LICENSE). Dataset license와 provenance는 project license와 별개이며
각 manifest와 dataset 문서를 따릅니다.
