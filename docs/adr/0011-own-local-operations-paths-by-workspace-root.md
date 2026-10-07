# 0011. Own local Operations paths by one workspace root

Status: Accepted

## Context

Phase 10의 local live stack은 replay source, independent collection service, window-analysis runner,
DuckLake history와 Operations UI를 별도 process/repository 경계로 검증했습니다. 이 분리는 collection,
analysis와 browser lifecycle을 서로 독립적으로 복구하고 관측하기 위해 필요합니다.

하지만 정상 실행 절차에서는 같은 runtime instance의 source registry, control state, spool, telemetry,
window state, analysis result/ledger, finding/review state와 DuckLake path를 CLI option과 환경변수로 반복
전달해야 합니다. 같은 topology가 demo tooling, subsystem README, Operations app default와 test setup에
복사되면서 사용자가 사실상 process와 repository wiring을 직접 소유하게 됐습니다.

이 문제는 state store를 하나로 합치거나 collector와 analysis runner를 같은 process로 합쳐서 해결할
문제가 아닙니다. 각 repository의 durability/evidence 책임과 process failure boundary는 유지하면서,
"한 local Operations instance가 어느 경로를 사용하는가"라는 사실의 authoritative owner가 필요합니다.

## Decision

- 하나의 local Operations instance는 `OperationsWorkspace(root)`로 식별합니다.
- workspace는 **non-secret local path layout만** 소유합니다. 개별 repository는 계속 자기 파일의 schema,
  durability와 contents에 대한 Source of Truth입니다.
- v1 workspace는 현재 AI-Hub/live demo에서 이미 사용하는 flat artifact layout을 기준으로 합니다.
  source registry는 `sources.json`, collection control은 `control.sqlite`, spool은 `spool.sqlite`,
  telemetry는 `telemetry.sqlite`, finalized windows는 `windows.sqlite`, analysis ledger는
  `window-analysis-ledger.sqlite`, DuckLake catalog/data는 `catalog.sqlite`와 `data/`처럼 root에서
  결정합니다.
- workspace projection 자체는 filesystem을 생성하거나 repository를 열지 않습니다. 초기화, migration,
  service construction과 lifecycle은 별도 runtime/application 책임입니다.
- collector와 analysis runner는 독립 process로 유지합니다. workspace는 process supervisor가 아닙니다.
- credential, certificate와 token 같은 secret은 workspace state/config/history evidence에 저장하지 않습니다.
- user-facing Operations path는 후속 변경에서 workspace root를 기본 입력으로 사용합니다. 개별 file-path
  override는 compatibility, diagnostics 또는 internal execution 경계로 제한합니다.
- `config.toml`과 `logs/` 위치도 workspace가 예약하지만, 이 ADR은 config schema나 logging backend를
  미리 고정하지 않습니다.

## Consequences

정상 사용자는 장기적으로 workspace root 하나로 local node를 선택할 수 있고, UI/CLI/demo가 같은 path
projection을 재사용할 수 있습니다. 여러 SQLite/JSON/DuckLake store는 그대로 유지되므로 기존 evidence와
failure isolation을 잃지 않습니다.

현재 Operations app default는 일부 이름과 history subdirectory가 이 layout과 다르므로 즉시 암묵적으로
이관하지 않습니다. 후속 product-runtime 변경에서 explicit compatibility/migration을 정의한 뒤 UI/CLI가
workspace를 소비하게 합니다.

이 결정은 distributed coordination, HA, container runtime, systemd, backup/retention 정책을 선택하지
않습니다. 해당 deployment 책임은 #346과 #318에서 이 workspace 계약 위에 추가합니다.

## Notes

- 2026-10-07: repository-local `operations up` front door는 config 도입 전 Operations가 만든 것으로
  식별 가능한 workspace만 현재 기본 runtime policy를 기록한 config로 명시적으로 adopt합니다. 알려지지 않은 top-level/runtime
  entry가 있으면 아무것도 변경하지 않고 거부합니다. 이는 path projection 자체에 side effect를 추가하지
  않고 lifecycle layer가 migration 판단을 소유한다는 이 ADR의 경계를 유지합니다.
