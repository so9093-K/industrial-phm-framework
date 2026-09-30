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

프로젝트 CLI는 기능이 실제로 생길 때만 command를 추가합니다. 정확한 현재 command surface의
Source of Truth는 executable parser와 `industrial-phm --help`입니다. 이 architecture 문서는 command tree를
복사하지 않습니다. 지원되는 workflow의 상태는 [현재 지원 상태](../status.md), 실행 절차는 해당 subsystem
README를 참조합니다.

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
| 프로젝트 목적, 안정적인 진입점과 문서 navigation | root `README.md` |
| 현재 구현·지원·현장검증 상태 | `docs/status.md` |
| subsystem 실행 방법과 runtime 운영 규칙 | 해당 directory의 `README.md` |
| 계획된 작업과 milestone | GitHub Issue/PR |
| 검증된 dataset 관찰 사실 | dataset source profile |
| 반복 사용할 research protocol/method | 해당 subject의 research 문서 |
| secret/token/machine-specific path | environment/runtime configuration |
| 장기 구조 결정 | ADR |
| contract invariant | production code와 contract 문서 |
| 변경 이력 | `CHANGELOG.md` |
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

Isolation Forest만 사용하는 설치가 deep-learning stack을 함께 받지 않도록 sequence model runtime은
`deep-learning` optional dependency로 제공합니다. Reference execution에 사용하는 runtime·accelerator 선택과
호환성 경계는 [ADR-0006](../adr/0006-use-pytorch-cpu-reference-runtime.md)이 소유합니다.

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

## 7. UI and Operational Contracts Co-Evolve

운영 UI를 PHM result contract와 service boundary가 완성될 때까지 미루지 않습니다. 실제 field source와
사용자 surface를 연결하면서 필요한 operational read model/API를 함께 검증합니다. 반대로 UI가 experiment
artifact schema를 직접 해석하거나 numerical PHM 의미를 새로 만드는 것도 허용하지 않습니다.

현재 presentation 책임은 두 축으로 분리합니다.

- Analysis Explorer / Developer Workbench: version-controlled experiment evidence, pipeline, evaluation과 provenance 검토
- Operations surface: asset/source/measurement point의 관측 상태, data quality, operational finding/evidence 검토

첫 Operations slice는 관측 사실을 먼저 닫습니다. asset_id, source_id, optional measurement_point_id,
observation time range, channel/sample population과 data-quality state를 application read model로 전달하고,
anomaly/diagnosis/prognostics/maintenance 의미는 검증된 capability가 실제로 생길 때 별도 evidence로 붙입니다.

Asset-centric read model은 `AssetIdentity`, `ComponentIdentity`, `MeasurementPointIdentity`,
`ChannelIdentity`를 application contract로 분리합니다. Persisted source/operational schema의 exact version은
각 repository code가 소유합니다. Source/observation/analysis/finding이 실제로 보존하는 `asset_id`, optional
`measurement_point_id`, channel ID를 typed identity로 projection하며, source mapping에 없는 component
identity는 channel 이름이나 measurement-point 이름에서 추론하지 않습니다.

Operations Overview는 repository별 상태를 presentation cell에서 직접 재집계하지 않고
`build_operations_overview` application read model을 사용합니다. 이 projection은 이미 로드된 registered source,
lifecycle, latest receipt/freshness/connection-attempt evidence, AnalysisRun, OperationalFinding과 review event를
소비합니다. Source마다 기존 `assess_source_health`를 재사용해 data-flow dimension을 계산하고, current source
population의 누락/중복 linkage는 fail-fast합니다. Analysis/finding history는 durable historical fact이므로 현재
registry에 source가 남아 있어야 한다고 역으로 강제하지 않습니다. Overview는 source 상태를 asset health나
fleet risk로 승격하지 않습니다.

Attention Queue는 Overview가 이미 보존한 source data-flow와 human review evidence에, 현재 로드된
observation의 data-quality issue 및 명시적인 system-state read error를 결합하는 별도 application
projection으로 둡니다. 현재 category는 `SOURCE_ERROR`, `NO_RECEIPT`, `STALE`,
`DATA_QUALITY_ISSUE`, `REVIEW_REQUIRED`, `SYSTEM_STATE_ERROR`로 제한합니다. `OPEN` review는
`UNHANDLED`, acknowledgement 이후에도 종료되지 않은 review와 나머지 factual issue는 `ACTIVE`로
표현하며 risk/severity score를 만들지 않습니다. 동일 handling state 안에서는 evidence time 최신순으로
정렬하고, stale 발생 시각은 assessment time이 아니라 recorded observation time과 configured freshness
threshold가 만나는 시각을 사용합니다. Data Quality는 아직 fleet-wide durable latest state가 없으므로
현재 로드된 observation evidence만 queue에 포함하며 그 coverage를 UI에서 숨기지 않습니다.

Operations presentation은 application read model과 marimo widget 조립 사이에 pure presenter를 둡니다.
`industrial_phm.presentation`은 Attention Queue, source data-flow, observation, data-quality evidence를
Markdown representation으로만 변환하며 새로운 operational 의미를 계산하지 않습니다. 이 layer는
`marimo`를 import하지 않아 core package가 research UI dependency를 요구하지 않게 유지합니다.
Availability callout, button/state wiring과 interactive layout은 계속 `apps/operations.py`가 소유합니다.

Asset Detail은 current registry와 historical AnalysisRun/OperationalFinding을 같은 physical asset identity로
묶되, source가 registry에서 사라졌다는 이유로 historical asset evidence를 숨기지 않습니다. Asset inventory는
registered source, 현재 로드된 observation, AnalysisRun, OperationalFinding의 asset identity union으로
projection합니다. Detail은 source mapping/data-flow, loaded observation/data quality, analysis/finding/review를
asset scope로 모으지만 condition/fault/risk/RUL verdict를 만들지 않습니다.

Data Quality presentation은 standalone workflow를 만들지 않습니다. Source Detail은 현재 선택된 source와 일치하는
loaded `AssetObservationSummary`가 있을 때만 observation quality, source snapshot, declared validation policy를
contextual evidence로 표시합니다. Investigation은 실제 `AnalysisRun.data_quality`와 해당 run이 기록한 source
snapshot provenance를 표시하며 current observation quality를 analysis input quality로 대체하지 않습니다.
Asset Detail은 asset-scoped loaded observation의 같은 provenance를 함께 표시합니다. 이 세 surface 모두 quality
state를 asset health, diagnosis 또는 maintenance priority로 승격하지 않습니다.

Evidence Timeline은 서로 다른 clock fact를 하나의 timestamp로 합치지 않습니다. Source registration/lifecycle,
source observation, platform receipt, observation window, analysis execution/capability production, finding observation,
review action을 각각 versioned event kind/time basis로 표현합니다. Timezone-aware event만 chronological ordering에
참여하고 missing 또는 timezone-naive source/observation time은 `Time not comparable` evidence로 별도 보존합니다.

Persistent OPC UA runtime도 같은 clock ownership을 유지합니다. `OpcUaPersistentSessionEvidence`는 connection
epoch/reconnect attempt를 session state와 함께 기록하고, `OpcUaPersistentDataChangeEvent`는 bounded subscription의
registered DataChange evidence를 connection epoch 안의 local event index로 감쌉니다. 이 index는 server sequence가
아니며 gap-free/exactly-once evidence가 아닙니다. Event time은 SourceTimestamp를 우선하고 ServerTimestamp fallback은
explicit policy로만 허용합니다. Connector `received_at`과 future ingestion boundary의 `ingested_at`은 별도
platform timing fact로 보존하며 event time으로 대체하지 않습니다. Persistent session evidence contract 자체는 connection/reconnect 사실만 소유합니다. Credential/certificate
설정, durable event persistence와 watermark/window assembly는 각각 별도 connector/runtime/storage 책임으로
분리하며 session evidence 모델에 합치지 않습니다.

Durable observation/window reference boundary는 explicit window range와 caller-owned monotonic watermark를
사용합니다. `ObservationWindowBuffer`는 accepted event 수를 bounded하고 event를 in-order/out-of-order,
late, duplicate(local delivery identity 기준), timing unavailable, unexpected channel, outside-window,
future clock-skew, buffer-full로 구분합니다. Watermark가 window end에 도달한 뒤에만
`DurableObservationWindow`로 finalize하며 `JsonObservationWindowRepository`는 finalized window와
protocol/timing evidence를 current v1 schema로 저장합니다. Durable repository는 finalized window를 소유하고 partial in-memory assembly는 finalized-window persistence
contract에 포함하지 않습니다. COMPLETE는 expected channel coverage만 뜻하며 synchronization,
gap-free/exactly-once delivery, analysis readiness 또는 asset condition을 의미하지 않습니다.

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
