# Contributing

이 저장소는 코드뿐 아니라 **변경 의도와 설계 판단이 추적 가능한 history**를 유지하는 것을 목표로 합니다.
작은 규칙도 장기간 유지될 경우 프로젝트의 운영 자산이 되므로 commit과 PR의 의미 단위를 중요하게 봅니다.

## Development Setup

```bash
uv python install 3.14
uv lock --check
uv sync --locked
```

변경 제출 전:

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv build
```

의존성을 추가·제거·변경할 때는 `pyproject.toml`을 수정한 뒤 `uv lock`으로 `uv.lock`을 갱신하고
두 파일을 같은 변경 단위로 commit합니다. 일반 개발과 CI에서는 lockfile을 암묵적으로 갱신하지 않습니다.

## Branches

`main`에 기능 변경을 직접 commit하지 않습니다.

권장 형식:

```text
chore/repository-foundation
feat/timeseries-contract
feat/domain-adapter
feat/isolation-forest
fix/early-detection-boundary
```

## Commit Messages

Conventional Commits의 구조를 따르되 제목과 본문은 기본적으로 한국어로 작성합니다.

```text
<type>(<scope>): <변경 목적 요약>

* 변경의 의미와 경계를 설명
* 중요한 실패 동작이나 호환성 변화 설명
* 테스트 또는 회귀 방지 조치 설명
```

### Types

- `feat`: 사용자/개발자 관점의 기능 추가
- `fix`: 잘못된 동작 수정
- `refactor`: 의도한 외부 동작을 유지하는 구조 개선
- `perf`: 성능 개선
- `test`: 테스트 및 회귀 검증 개선
- `research`: 재현 가능한 연구 실행, benchmark evidence, protocol freeze처럼 연구 근거를 기록하는 변경
- `docs`: 문서만 변경
- `build`: packaging/dependency/build 변경
- `ci`: CI/CD 변경
- `chore`: 그 외 repository 유지보수
- `revert`: 이전 변경 되돌리기

### Preferred scopes

`repo`, `core`, `contract`, `adapter`, `data`, `feature`, `model`, `evaluation`, `pipeline`,
`artifact`, `analysis`, `application`, `operations`, `connector`, `prognostics`, `api`, `dashboard`,
`genai`, `cli`, `apps`, `docs`, `ci`, `release`

새 scope를 만들기 전 기존 scope로 충분히 표현 가능한지 먼저 확인합니다.

### Example

```text
feat(contract): 공통 시계열 데이터 계약 정의

* 자산 식별자, timestamp, sensor channel과 sampling metadata를 포함하는 공통 계약 추가
* label과 RUL 부재를 명시적으로 표현해 task 지원 여부를 데이터 계약에서 구분
* Domain Adapter가 원천 데이터 구조를 downstream 계층으로 누출하지 않도록 경계 설정
* sample/channel 정렬 오류를 조기에 차단하는 계약 회귀 테스트 추가
```

좋은 commit은 파일 목록을 다시 말하기보다 **왜 변경했고 어떤 invariant를 지키는지** 남깁니다.
서로 독립적으로 되돌리거나 리뷰할 수 있는 변경은 별도 commit으로 분리합니다.

## Terminology

연구·실험·PHM 기능을 새로 이름 붙일 때는 [`docs/terminology.md`](docs/terminology.md)를 먼저 확인합니다.

- ISO condition-monitoring vocabulary나 널리 쓰이는 ML/software 용어가 있으면 프로젝트 고유 조어보다 우선합니다.
- 관찰된 model output에 검증되지 않은 PHM 의미를 선제적으로 부여하지 않습니다. 예를 들어 anomaly-model output을
  근거 없이 `degradation score`라고 부르지 않습니다.
- UI나 Notebook의 임시 이름을 architecture 계층 또는 Source of Truth 이름으로 승격하지 않습니다.
- 새로운 canonical term이 실제로 필요하면 기존 용어로 표현할 수 없는 이유를 PR에서 설명하고 terminology 문서와
  함께 검토합니다.

## Documentation

새 파일을 만들기 전에 기존 authoritative owner를 갱신할 수 있는지 먼저 확인합니다. 문서는 작업 단계나 PR마다
추가하지 않고, 변경 이후에도 유지되는 책임을 기준으로 나눕니다. Source-of-Truth mapping은
[`docs/architecture/operational-foundation.md`](docs/architecture/operational-foundation.md)의
`One Fact, One Authoritative Owner`를 따릅니다.

- Root `README.md`: 프로젝트 목적, 안정적인 사용자 진입점과 문서 navigation
- `docs/status.md`: 현재 구현·지원·대상 source validation 상태와 명시적 미지원 경계
- Subsystem `README.md`: 해당 디렉터리의 실행 방법, runtime path와 운영 규칙
- `docs/architecture`: 여러 기능에 걸쳐 유지되는 책임과 contract boundary. milestone/PR 진행 상황을 기록하지 않음
- `docs/adr`: 장기간 영향을 주는 구조 결정과 대안
- `docs/research`: dataset 선택, 검증된 source profile, 반복 사용할 protocol과 research method
- Manifest/config/code: 정확한 provenance, split, experiment parameter와 executable invariant
- `CHANGELOG.md`: 사용자·개발자가 알아야 할 동작/호환성 변화의 역사
- GitHub Issue/PR: 계획된 작업, milestone, 일회성 비교표, migration 과정과 review context

새 문서는 독립적인 장기 소유 책임이 있고 기존 문서나 executable Source of Truth에 합치면 책임이 섞일 때만
추가합니다. 새 문서를 추가하는 PR은 기존 owner로 충분하지 않은 이유와 갱신·폐기 조건을 설명합니다. 구현 직전의
임시 계획, widget state, 생성 artifact의 전체 수치와 commit history 요약을 별도 문서로 승격하지 않습니다.

현재 지원 여부를 README·Architecture·Product 문서에 다시 나열하지 않습니다. `docs/status.md`는 지원 경계가
바뀔 때만 갱신하고 미래 계획을 기록하지 않습니다. "다음 milestone", "후속 #123", "아직 구현되지 않음" 같은
작업 진행 문구는 contract 자체의 한계를 설명하는 경우가 아니면 Issue/PR에 둡니다. Architecture에는 issue/PR
번호 대신 변경 이후에도 유지되는 component 책임과 invariant를 기록합니다.

## Pull Requests

PR 제목도 같은 형식을 사용합니다.

```text
<type>(<scope>): <PR의 목적>
```

PR 본문은 변경에 필요한 맥락만 남깁니다. 기본 구조는 다음과 같습니다.

```text
## 목적
## 주요 변경
## 설계 결정
## 검증
## 관련 ADR
```

설계 결정이나 관련 ADR이 없는 작은 변경에서는 해당 섹션을 생략합니다. PR template을 채우기 위해
불필요한 영향 범위나 후속 작업 목록을 반복하지 않습니다. PR은 여러 기능을 한 번에 묶는 release
container가 아니라 **하나의 리뷰 가능한 변화 단위**가 되어야 합니다.

### Review and merge

현재 single-maintainer 개발 단계에서는 별도 reviewer approval을 필수 조건으로 두지 않습니다. 대신 PR author는
merge 전에 최신 `main` 기준 diff, 필수 CI, PR 제목과 문서/ADR/CHANGELOG 반영 필요 여부를 self-review합니다.
협업자가 늘어나거나 보호가 필요한 운영 경계가 생기면 required approval을 별도 repository rule로 강화합니다.

`main`의 history는 PR 단위 변경 의도를 읽을 수 있게 **squash merge를 기본값**으로 사용합니다. Branch 안에서는
구현·테스트·format·문서 동기화 과정을 incremental commit으로 자유롭게 남길 수 있지만, 그 작업 과정 전체를
`main`의 장기 history로 보존하지 않습니다. 서로 독립적으로 revert할 가치가 있는 변경이 둘 이상이면 micro
commit을 그대로 merge하기보다 PR을 분리합니다. Merge commit 또는 rebase merge가 필요한 예외는 PR 본문에
그 이유를 남깁니다.

### Stacked PRs

가능하면 각 PR은 현재 `main`에서 분기해 독립적으로 리뷰합니다. 선행 변경에 의존해 stacked PR을 사용하는
경우에는 중간 feature branch에 merge됐다는 사실을 `main` 통합으로 간주하지 않습니다.

선행 PR이 `main`에 merge된 뒤 후속 PR마다 다음을 다시 확인합니다.

1. base branch를 `main`으로 맞추고 필요하면 rebase 또는 새 branch로 변경을 옮깁니다.
2. `main...head` diff에 해당 PR의 의도한 변경만 남는지 확인합니다.
3. 최신 `main`을 기준으로 필수 CI를 다시 실행합니다.
4. 위 조건을 만족한 뒤에만 후속 PR을 merge합니다.

PR 상태의 `merged` 표시는 해당 PR의 base branch에 통합됐다는 뜻이며, base가 중간 feature branch라면
`main`에 포함됐다는 보장이 아닙니다.

## ADR

장기간 영향을 주는 구조적 결정은 `docs/adr`에 기록합니다. 모든 구현 선택을 ADR로 만들지는 않습니다.
결정이 바뀌면 기존 Accepted ADR을 조용히 수정하지 않고 새 ADR에서 supersede합니다.

## Release and CHANGELOG

`CHANGELOG.md`는 git log의 복사본이 아닙니다. 사용자가 알아야 할 기능, 호환성, 동작, 보안 또는 중요한
개발 계약의 변화만 기록합니다.

Package version의 authoritative owner는 `pyproject.toml`입니다. 기능·문서·실험 PR마다 version을 올리지 않고,
외부 배포나 public compatibility 기준선을 선언하는 release 변경에서 tag와 artifact 정책을 함께 검토합니다.

## Compatibility

새 Python minor version, free-threaded build, OS, accelerator 또는 model serialization format을 지원한다고
표기하기 전에 자동화된 검증을 추가합니다. 현재 기준은 GIL-enabled CPython 3.14입니다.
