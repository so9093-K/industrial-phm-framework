# Contributing

이 저장소는 코드뿐 아니라 **변경 의도와 설계 판단이 추적 가능한 history**를 유지하는 것을 목표로 합니다.
작은 규칙도 장기간 유지될 경우 프로젝트의 운영 자산이 되므로 commit과 PR의 의미 단위를 중요하게 봅니다.

## Development Setup

```bash
uv python install 3.14
uv sync
```

변경 제출 전:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

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
- `docs`: 문서만 변경
- `build`: packaging/dependency/build 변경
- `ci`: CI/CD 변경
- `chore`: 그 외 repository 유지보수
- `revert`: 이전 변경 되돌리기

### Preferred scopes

`repo`, `core`, `contract`, `adapter`, `data`, `feature`, `model`, `evaluation`, `pipeline`,
`artifact`, `api`, `dashboard`, `genai`, `docs`, `ci`, `release`

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

## Pull Requests

PR 제목도 같은 형식을 사용합니다.

```text
<type>(<scope>): <PR의 목적>
```

PR 본문에는 다음을 남깁니다.

- 목적과 문제 정의
- 주요 변경
- 설계 결정 및 고려한 대안
- 수행한 검증
- compatibility/API/data/artifact 영향
- 관련 ADR
- 의도적으로 제외한 후속 작업

PR은 여러 기능을 한 번에 묶는 release container가 아니라 **하나의 리뷰 가능한 변화 단위**가 되어야 합니다.

## ADR

장기간 영향을 주는 구조적 결정은 `docs/adr`에 기록합니다. 모든 구현 선택을 ADR로 만들지는 않습니다.
결정이 바뀌면 기존 Accepted ADR을 조용히 수정하지 않고 새 ADR에서 supersede합니다.

## CHANGELOG

`CHANGELOG.md`는 git log의 복사본이 아닙니다. 사용자가 알아야 할 기능, 호환성, 동작, 보안 또는 중요한
개발 계약의 변화만 기록합니다.

## Compatibility

새 Python minor version, free-threaded build, OS, accelerator 또는 model serialization format을 지원한다고
표기하기 전에 자동화된 검증을 추가합니다. 현재 기준은 GIL-enabled CPython 3.14입니다.
