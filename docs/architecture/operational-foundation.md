# Operational Foundation

이 문서는 모델 구현 이전부터 유지해야 하는 실행·데이터·설정·패키징·사용자 경험의 운영 경계를 정의합니다.
목표는 기능을 미리 많이 만드는 것이 아니라, 같은 사실과 같은 동작이 여러 위치에 중복 정의되는 것을 막고
실제 요구가 생길 때 일관된 방향으로 확장하는 것입니다.

## 1. Execution Interfaces

프로젝트의 실행 인터페이스는 두 층으로 구분합니다.

- 개발 도구 실행: `uv`
- 프로젝트 기능 실행: 설치 가능한 `industrial-phm` CLI

개발 명령을 `Makefile`, `just`, shell script 등 여러 wrapper로 중복하지 않습니다. 현재 개발 기준선은
`uv lock --check`, `uv sync --locked`, Ruff, mypy, pytest, `uv build`입니다.

프로젝트 CLI는 기능이 실제로 생길 때만 command를 추가합니다. 현재 구현된 command tree는 다음과 같습니다.

```text
industrial-phm
├── doctor
├── data
│   ├── list
│   ├── status
│   ├── fetch
│   ├── verify
│   ├── inspect
│   └── validate
├── feature
│   └── characterize
└── experiment
    ├── validate
    ├── reference-compare
    ├── holdout
    ├── cross-fold
    └── cross-test
```

Python package의 CLI entry point는 표준 `[project.scripts]`를 사용합니다.

## 2. Dataset Acquisition Boundary

공개 연구 데이터셋의 획득은 Domain Adapter 책임과 분리합니다.

```text
Dataset Registry
      ↓
Acquisition Provider
fetch / cache / verify
      ↓
Raw Dataset
      ↓
Domain Adapter
      ↓
Canonical Contract
```

가능한 데이터셋은 명시적 `data fetch` 동작으로 자동화합니다. package 설치/import 시 대용량 데이터나
네트워크 리소스를 자동으로 내려받지 않습니다. 공급자가 로그인, 약관 수락, 수동 다운로드만 허용하는 경우
`manual` acquisition으로 표시하고 공식 위치와 검증 절차를 안내합니다.

다운로드 성공 여부만으로 데이터를 신뢰하지 않습니다. 가능한 경우 file size와 cryptographic checksum 또는
공급자가 제공하는 checksum을 검증하고, dataset source/version/license/citation을 manifest에 기록합니다.

## 3. One Fact, One Authoritative Owner

Single Source of Truth는 모든 설정을 하나의 파일에 넣는다는 의미가 아닙니다. 하나의 사실에는 하나의
권위 있는 소유자만 두고, 다른 코드와 문서는 그 사실을 복사하지 않고 참조합니다.

| 사실 | 권위 있는 위치 |
| --- | --- |
| package metadata와 의도된 dependency 범위 | `pyproject.toml` |
| 정확히 resolve된 개발 환경 | `uv.lock` |
| dataset source/version/license/file/hash | dataset manifest |
| asset/run split | split manifest |
| 실험 parameter | version-controlled experiment config |
| model artifact provenance | artifact manifest |
| 현재 capability와 project-level roadmap | root `README.md` |
| subsystem 실행 방법과 운영 규칙 | 해당 directory의 `README.md` |
| 검증된 dataset 관찰 사실 | dataset source profile |
| 반복 사용할 research protocol/method | 해당 subject의 research 문서 |
| secret/token/machine-specific path | environment/runtime configuration |
| 장기 구조 결정 | ADR |
| contract invariant | production code와 contract 문서 |
| 작업 과정과 일회성 비교 결과 | PR 본문 또는 generated artifact |

README나 발표 자료에 version, URL, threshold 같은 값을 불필요하게 복사하지 않습니다.
문서도 작업 단계마다 새 파일을 만드는 방식으로 확장하지 않습니다. 기존 owner의 책임 안에 들어가는 변화는 해당
문서를 갱신하고, 정확한 설정값과 실행 가능한 invariant는 manifest/config/code에 둡니다.

## 4. Configuration Boundary

하드코딩 제거를 목적으로 모든 값을 config로 이동하지 않습니다. 값의 성격에 따라 위치를 구분합니다.

- invariant: 코드에 둡니다. 예: sampling rate가 제공된 경우 양수여야 함.
- dataset provenance: dataset manifest에 둡니다.
- reproducible experiment input: version-controlled config에 둡니다.
- secret/local path/deployment value: environment 또는 runtime setting에 둡니다.
- user override: 명시적 CLI option으로 허용하되 effective configuration을 추적 가능하게 합니다.

복잡한 config composition이나 sweep 요구가 실제로 확인되기 전까지 별도 configuration framework를 도입하지
않습니다. 표준 라이브러리와 작은 typed structure로 충분한 범위는 단순하게 유지합니다.

## 5. Packaging and Dependency Boundary

현재 `pyproject.toml` + `uv.lock`을 개발 환경의 기준으로 유지합니다.

- `[project.dependencies]`: 설치된 package가 실제 runtime에 필요로 하는 dependency
- `[dependency-groups]`: 개발, 테스트, 문서, benchmark 같은 local workflow dependency
- `[project.optional-dependencies]`: 사용자에게 실제 선택 설치 기능을 제공할 필요가 생긴 경우에만 추가

`requirements.txt`를 `uv.lock`과 병행하는 두 번째 source of truth로 유지하지 않습니다. 외부 도구와의
상호운용이 필요할 경우 release/export 단계에서 `pylock.toml`, requirements, CycloneDX SBOM 등으로
생성합니다.

Python library 배포와 running service 배포도 분리합니다. library는 wheel/sdist가 기본이고, inference
service가 실제로 생긴 뒤 OCI container를 검토합니다.

## 6. Data Representation Boundary

Public contract와 storage/compute representation을 같은 것으로 취급하지 않습니다. 현재 canonical contract는
특정 DataFrame, array 또는 tensor library에 종속되지 않는 의미와 invariant를 우선합니다.

실제 workload가 요구할 때 representation을 선택합니다.

- raw/dense numerical signal은 signal processing과 모델이 요구하는 효율적인 array representation을 사용할 수 있습니다.
- inventory, feature/result table은 columnar 또는 tabular representation을 사용할 수 있습니다.
- deep/sequence model은 해당 모델 runtime의 native tensor를 사용할 수 있습니다.
- public canonical contract는 위 구현 선택을 호출자에게 강제하지 않습니다.

특정 tabular library나 tensor stack을 미래 기본값으로 미리 고정하지 않습니다. 실제 adapter, feature workflow,
model implementation 또는 규모 요구가 생기면 dependency와 representation을 그 consumer와 함께 도입하고
Python compatibility, memory/layout 비용과 serialization boundary를 검증합니다.

## 7. UX Before UI Implementation

Dashboard 구현은 PHM Result contract와 inference 경계가 안정된 뒤 진행하지만, 사용자가 어떤 정보를
소비하는지는 지금부터 설계합니다.

초기 역할은 다음 네 가지를 기준으로 검토합니다.

- 설비 관리자: 상태, 위험 설비, alert, fleet overview
- 정비 엔지니어: trend, score/threshold, supporting evidence, 정비 이력과 원인 가설
- 의사결정자: risk/urgency, maintenance priority, fleet-level summary
- PHM/ML 개발자·연구자: pipeline stage, effective configuration, population flow, evaluation semantics와 provenance

CLI 역시 현재 단계의 주요 사용자 인터페이스입니다. 실패 시 원인, 해결 방법, local state와 provenance를
명확히 보여주는 것을 GUI와 동일한 UX 문제로 취급합니다.

개발자용 pipeline transparency는 별도 orchestration framework를 추가하는 이유가 아닙니다. 기존
`CanonicalTimeSeries`, feature vector, `PreprocessingState`, `ModelFitInput`, `AnomalyScores`,
experiment result가 이미 소유한 사실을 사람이 단계별로 추적할 수 있게 보여주는 문제입니다. 표시를 위해 같은
configuration/population/provenance를 두 번째 상태 저장소에 복제하지 않습니다. 구체적인 information
architecture와 capability 표현은 [`../product/overview.md`](../product/overview.md)를 기준으로 합니다.

## 8. Validation Reuse

검증 로직은 테스트 전용으로 복제하지 않습니다.

```text
Production Validator
      ├── CLI
      ├── Adapter / Pipeline
      └── Tests
```

예를 들어 dataset checksum, artifact schema, split invariant는 production validator 하나가 source of truth가
되고 CLI와 테스트가 이를 재사용합니다.

## 9. Adoption Rule

새 도구는 최근 유행이나 미래 가능성만으로 도입하지 않습니다. 다음 중 하나가 실제로 확인될 때 도입합니다.

- 반복되는 수작업 때문에 재현성이 깨짐
- 두 군데 이상에서 같은 규칙을 중복 구현하게 됨
- 기존 boundary로 표현할 수 없는 두 번째 실제 사례가 등장함
- release/deployment 요구가 생김

이 원칙은 dataset tooling, MLOps, configuration framework, dashboard framework, RAG/vector database,
workspace/plugin architecture에 동일하게 적용합니다.

## References

- uv project dependencies: https://docs.astral.sh/uv/concepts/projects/dependencies/
- uv lock/export formats: https://docs.astral.sh/uv/concepts/projects/export/
- Python packaging dependency groups: https://packaging.python.org/en/latest/specifications/dependency-groups/
- Polars lazy API: https://docs.pola.rs/user-guide/concepts/lazy-api/
- Polars query optimizations: https://docs.pola.rs/user-guide/lazy/optimizations/
- scikit-learn dataframe support FAQ: https://scikit-learn.org/stable/faq.html
- pytest good integration practices: https://docs.pytest.org/en/stable/explanation/goodpractices.html
- ISO 9241-210 human-centred design overview: https://www.iso.org/standard/77520.html
