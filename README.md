# industrial-phm-framework

이기종 산업 설비 시계열 데이터를 공통 분석 구조로 연결하기 위한 모듈형 PHM
(Prognostics and Health Management) 프레임워크입니다.

설비·데이터셋별 차이는 Domain Adapter에 격리하고, 공통 데이터 계약을 기준으로
전처리, 상태 평가, 이상 탐지, prognostics, 평가 및 서비스 계층을 확장하는 것을 목표로 합니다.
생성형 AI는 PHM 모델의 예측을 대신하지 않고, 구조화된 분석 결과를 해석하고 정비 의사결정을
지원하는 상위 계층으로 통합합니다.

> 현재 상태: repository foundation / pre-alpha (`0.1.0`)

## Architecture

![System Architecture](assets/system-architecture.webp)

세부 다이어그램은 [`docs/architecture/overview.md`](docs/architecture/overview.md)에서 확인할 수 있습니다.

## Design Principles

- **Domain boundary first**: 원천 데이터 차이는 Domain Adapter가 흡수합니다.
- **Contract-driven core**: 공통 PHM 계층은 특정 데이터셋 형식이 아니라 명시적 데이터 계약에 의존합니다.
- **Model-independent evaluation**: 모델 구현과 평가 로직을 분리해 비교 실험의 재사용성을 유지합니다.
- **Reproducible by default**: 코드, 환경, 데이터 provenance, 모델 artifact를 추적 가능한 형태로 관리합니다.
- **GenAI after PHM**: LLM은 계산된 PHM 결과를 해석하며, 핵심 수치 산출의 source of truth가 되지 않습니다.
- **Grow by evidence**: workspace, plugin, MLOps 구성은 실제 확장 요구가 생긴 시점에 도입합니다.

## Python Compatibility

- CPython `3.14.x` (GIL-enabled build): 검증 대상
- CPython 3.14 free-threaded build: Python 자체에서는 공식 지원되지만 이 프로젝트에서는 아직 검증하지 않음
- 다른 Python minor version: 지원 범위에 포함하기 전에 CI 및 주요 ML dependency 호환성을 검증

프로젝트의 `requires-python`은 현재 `>=3.14,<3.15`로 제한합니다. 새 Python minor version을 암묵적으로
지원하지 않고, 검증 후 명시적으로 범위를 확장합니다.

## Development

[uv](https://docs.astral.sh/uv/)를 프로젝트 및 dependency 관리 도구로 사용합니다.

```bash
uv python install 3.14
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

커밋, PR, 테스트 및 문서화 규칙은 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 따릅니다.
중요한 구조 결정은 [`docs/adr`](docs/adr)에 ADR로 남깁니다.

## Repository Layout

```text
.
├── .github/                # CI 및 협업 템플릿
├── assets/                 # 아키텍처 다이어그램 등 정적 자산
├── docs/
│   ├── architecture/       # 시스템 구조와 설계 원칙
│   └── adr/                # Architecture Decision Records
├── src/industrial_phm/
│   ├── contracts/          # 도메인 중립 데이터 계약
│   └── adapters/           # 설비/데이터셋별 변환 경계
└── tests/
    ├── unit/
    └── contract/
```

필요해지기 전까지 빈 `models/`, `apps/`, `pipelines/` 등의 디렉터리를 미리 만들지 않습니다.
실제 기능 PR에서 책임과 경계를 검토한 뒤 추가합니다.

## Roadmap

1. 첫 산업 설비 데이터셋 선정과 provenance 문서화
2. 실제 Domain Adapter 및 공통 전처리 경계 검증
3. Isolation Forest baseline과 독립 평가 계층
4. LSTM Autoencoder 기반 시계열 이상 탐지
5. Health Index 및 데이터가 지원하는 경우 RUL prognostics
6. 두 번째 도메인으로 adapter/core 확장성 검증
7. inference API, dashboard, Generative AI/RAG 연계

## Governance

- 변경 이력: [`CHANGELOG.md`](CHANGELOG.md)
- 기여 및 커밋/PR 규칙: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 보안 정책: [`SECURITY.md`](SECURITY.md)
- Architecture decisions: [`docs/adr`](docs/adr)

현재 저장소는 private이며 공개 라이선스는 아직 결정하지 않았습니다. 외부 공개 전에 코드와 데이터셋,
모델, 제3자 자산의 라이선스를 각각 검토합니다.
