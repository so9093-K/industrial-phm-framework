# ADR-0001: Python package에 src layout 사용

- Status: Accepted
- Date: 2026-09-14

## Context

프레임워크 코드는 notebook, scripts, tests 및 향후 서비스 코드에서 재사용됩니다. repository root가
우연히 import path로 동작하면 설치된 package와 작업 디렉터리의 source가 달라도 테스트가 통과할 수 있습니다.

## Decision

배포 가능한 Python package는 `src/industrial_phm` 아래에 둡니다. 테스트와 애플리케이션은 설치된
`industrial_phm` package를 import합니다.

## Alternatives Considered

- flat layout: 초기 파일 수는 줄지만 repository root에서의 accidental import 가능성이 높습니다.

## Consequences

- editable install 또는 `uv sync`가 일반 개발 흐름의 일부가 됩니다.
- package와 repository-level tooling의 경계가 명확해집니다.
