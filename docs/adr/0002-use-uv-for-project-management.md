# ADR-0002: Python project와 dependency 관리에 uv 사용

- Status: Accepted
- Date: 2026-09-14

## Context

Python 3.14를 기준으로 local/CI 환경을 재현하고 dependency resolution, lockfile, virtual environment,
build 명령을 일관되게 유지할 필요가 있습니다.

## Decision

`pyproject.toml`을 project metadata의 source of truth로 사용하고 uv를 project/dependency manager로
사용합니다. `uv.lock`은 재현 가능한 Python 3.14 환경에서 생성한 뒤 version control에 포함합니다.
bootstrap PR에서는 lockfile을 수작업으로 생성하지 않고 CI에서 dependency resolution을 검증합니다.
lockfile이 추가된 이후 CI는 `uv sync --locked`로 drift를 차단합니다.

초기 toolchain은 검토 시점의 최신 안정 계열인 uv `0.12.x`로 제한합니다. toolchain 범위를 변경할 때는
CI와 lockfile 재현성을 함께 검증합니다.

## Alternatives Considered

- pip + requirements files: 가능하지만 project metadata와 lock workflow가 분산됩니다.
- Poetry/PDM: 성숙한 대안이지만 현재 요구에서는 uv의 Python 관리와 lock workflow가 더 단순합니다.

## Consequences

- 개발자는 uv가 필요합니다.
- `uv.lock` 도입 이후 dependency 변경은 `pyproject.toml`과 lockfile을 함께 변경해야 합니다.
- workspace 기능은 사용하지 않습니다. 여러 독립 package가 실제 필요해질 때 별도 ADR로 검토합니다.
