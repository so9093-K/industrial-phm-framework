# 0022. Retire pre-release persisted migration paths

Status: Accepted · 2026-10-25 개정

> 2026-10-25 개정: 같은 원칙을 남은 저장소 전체로 넓혔습니다. `JsonPhaseUnbalanceRepository`를 포함한 JSON 창·장부·결과
> 저장소, DuckLake 카탈로그의 열 추가·버전 이전 스냅샷 읽기, PHM 분석 SQLite v1→v2, AI 해설·전망 검토 SQLite의 열 추가,
> 불평형 결과의 예전 필드 기본값, AI-Hub 가져오기 v1~v4 이어받기와 OPC UA 배치의 버전 이전 지문 복구를 지웠습니다.
> 저장소는 현재 형식만 열고, 저장 형식이 바뀐 출시 전 작업공간은 새로 만듭니다.

## Context

The local Operations runtime now has one current workspace configuration schema,
`industrial-phm-operations-runtime-v2`, and one product result store for live three-phase
analysis, `phase-unbalance.sqlite`.

During productization we temporarily kept two migration surfaces:

- the Operations config loader accepted `industrial-phm-operations-runtime-v1` and
  `operations init` rewrote it to v2;
- a maintenance command copied legacy phase-unbalance JSON results into SQLite, and
  Operations surfaced a migration warning when only the old JSON file existed.

ADR-0021 intentionally left persisted schemas and the explicit phase-result migration command
unchanged while CLI/path compatibility was removed. The package is still `0.0.1` / Pre-Alpha
without a declared public compatibility baseline, and other pre-release persisted schemas such as
older source registry/runtime versions already fail closed rather than auto-migrate.

Keeping these migration paths now extends two product-era storage contracts and keeps migration-only
commands, UI diagnostics and tests in the current runtime.

## Decision

- Operations workspace configuration accepts only the current
  `industrial-phm-operations-runtime-v2` schema.
- Workspace initialization loads an existing current config; it does not rewrite v1 config.
- The `maintenance migrate-phase-unbalance-results` command and its JSON-to-SQLite migration
  helper are removed.
- Operations no longer emits a product migration warning merely because a sibling
  `phase-unbalance.json` file exists.
- `SqlitePhaseUnbalanceRepository` remains the canonical live/Operations result store.
- `JsonPhaseUnbalanceRepository` remains available for bounded offline histories and historical
  payload compatibility tests. Removing the product migration surface does not redefine or rewrite
  those historical artifacts.
- Persisted evidence identities, schema strings and historical CHANGELOG/ADR text remain unchanged.

This decision supersedes only ADR-0021's statement that the explicit phase-result migration command
is unchanged. ADR-0021 remains authoritative for CLI taxonomy and workspace-only app composition.

## Consequences

A pre-release workspace containing a v1 `config.toml` is rejected instead of upgraded in place.
A workspace that contains only the old phase-unbalance JSON result file is not adopted by the current
Operations runtime. Such private pre-release state must be converted with an earlier revision or
recreated before adopting this revision.

The current runtime has one config schema and one live three-phase result-store path, while historical
JSON evidence can still be read deliberately through the offline repository API.
