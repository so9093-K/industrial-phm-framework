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

프로젝트 CLI는 기능이 실제로 생길 때만 command를 추가합니다. 장기 namespace는 다음을 기준으로 하되
빈 command tree를 미리 구현하지 않습니다.

```text
industrial-phm
├── data
│   ├── list
│   ├── fetch
│   ├── verify
│   ├── status
│   └── inspect
├── train
├── evaluate
├── infer
├── artifact
├── report
└── doctor
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
| secret/token/machine-specific path | environment/runtime configuration |
| 장기 구조 결정 | ADR |
| contract invariant | production code와 contract 문서 |

README나 발표 자료에 version, URL, threshold 같은 값을 불필요하게 복사하지 않습니다.

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

DataFrame library 하나를 전체 PHM 데이터 구조로 사용하지 않습니다. 데이터의 역할에 따라 표현을 분리합니다.

- dataset inventory, metadata, lifecycle observation, feature/result table: **Polars를 우선 검토**
- dense numerical signal과 signal processing: NumPy/SciPy 계열 배열
- sequence/deep model input: PyTorch Tensor 등 해당 모델의 native tensor
- public canonical contract: 특정 DataFrame library에 종속되지 않는 명시적 계약

Polars를 tabular processing의 우선 후보로 두는 이유는 CSV/Parquet 같은 columnar source를 `scan_*`으로 읽고
lazy query optimization, predicate/projection pushdown, streaming execution을 사용할 수 있기 때문입니다. 특히
여러 asset/run의 feature table이나 lifecycle observation을 필터링·집계하는 단계와 잘 맞습니다.

다만 `Polars가 pandas보다 빠르다`는 이유만으로 raw waveform이나 모델 tensor까지 DataFrame으로 감싸지
않습니다. scikit-learn estimator 내부도 일반적으로 NumPy/SciPy 같은 homogeneous representation으로 변환하므로
모델 경계에서는 불필요한 DataFrame 의존을 피합니다.

현재는 실제 adapter/preprocessing이 Polars를 요구하기 전까지 runtime dependency에 추가하지 않습니다. 첫
실데이터 pipeline에서 tabular processing 요구가 확인되면 Polars를 도입하고 정확한 버전과 Python 3.14 호환성을
CI에서 검증합니다.

## 7. UX Before UI Implementation

Dashboard 구현은 PHM Result contract와 inference 경계가 안정된 뒤 진행하지만, 사용자가 어떤 정보를
소비하는지는 지금부터 설계합니다.

초기 역할은 다음 세 가지를 기준으로 검토합니다.

- 설비 관리자: 상태, 위험 설비, alert, fleet overview
- 정비 엔지니어: trend, score/threshold, supporting evidence, 정비 이력과 원인 가설
- 의사결정자: risk/urgency, maintenance priority, fleet-level summary

CLI 역시 현재 단계의 주요 사용자 인터페이스입니다. 실패 시 원인, 해결 방법, local state와 provenance를
명확히 보여주는 것을 GUI와 동일한 UX 문제로 취급합니다.

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
