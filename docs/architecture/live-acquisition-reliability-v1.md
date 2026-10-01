# Live Acquisition Reliability v1

## Local collector and concurrent history reads

실제 loopback OPC UA server, 별도 collector process, history query client를 함께 실행하는 검증은
`tests/contract/test_live_measurement_stack.py`가 소유합니다. Source restart/reconnect와 collector restart,
durable epoch 증가, FILE/live provenance, Stop Collection과 동시 조회를 작은 synthetic input으로 검증합니다.

DuckLake SQLite metadata의 attach/transaction이 겹치면 `database is locked`가 발생할 수 있어,
adapter는 resolved catalog 경로의 `.phm.lock`을 connection 생성 전 획득하고 close 이후 해제합니다.
대기 한도는 config의 `catalog_lock_timeout_seconds`(기본 10초)입니다. Timeout은 실패로 노출하고
spool writer의 기존 retry 정책을 따릅니다. Connection 생성/attach 실패도 잠금을 해제합니다.
이 보장은 협력하는 local adapter와 local filesystem에 한정되며, 외부 SQL client·분산 filesystem이나
복수 collector leader election을 포함하지 않습니다. 대용량 query가 writer를 지연시킬 수 있으므로
장기 운영의 처리량/retention/downsampling 검증은 별도 요구사항입니다.

참고: [DuckLake catalog 선택](https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database).

이 문서는 failure/restart/soak 검증 범위와 v1 runtime이 주장하는 신뢰성 경계를 고정합니다.
목표는 synthetic "exactly once"나 gap-free 보장을 만드는 것이 아니라, **어디까지 durable하고 어디서 loss가
가능한지, restart 후 어떤 identity/evidence를 복구하는지**를 executable test와 연결하는 것입니다.

## 1. v1 reliability claims

v1 reference runtime이 주장하는 범위는 다음과 같습니다.

- callback이 SQLite ingress spool transaction까지 도달한 뒤에는 collector process restart 후 복구할 수 있습니다.
- callback queue에만 있고 spool commit 전인 event는 durable하다고 주장하지 않습니다.
- 동일 local delivery identity의 동일 payload retry는 spool에서 idempotent합니다.
- 같은 local identity가 다른 payload로 재사용되면 conflict로 fail-fast합니다.
- OPC UA reconnect/replay는 새로운 factual delivery로 보존할 수 있으며 값/시각 similarity로 삭제하지 않습니다.
- DuckLake commit 전 실패하면 active spool batch는 ACK되지 않고 그대로 남습니다.
- DuckLake commit 후 spool ACK 전 crash가 나면 stable batch provenance로 기존 DuckLake snapshot을 복구한 뒤 ACK합니다.
- continuous history writer는 transient downstream exception을 같은 active batch로 재시도합니다.
- stable identity conflict와 spool invariant failure는 transient error로 숨기지 않고 fail-fast합니다.
- window coordinator는 durable raw history에서 deterministic rebuild할 수 있습니다.
- acquisition failure/telemetry는 source lifecycle이나 asset condition/health verdict로 자동 승격하지 않습니다.
- FILE backfill과 live OPC UA overlap은 provenance가 다르면 모두 보존합니다.

v1은 다음을 주장하지 않습니다.

- OPC UA server sequence 기준 gap-free delivery
- exactly-once physical measurement semantics
- spool commit 전 callback의 crash durability
- callback queue overflow 시 무손실
- 값/시각 heuristic 기반 cross-source deduplication
- acquisition failure에서 asset fault/health 자동 추론

## 2. deterministic scenario matrix

| Scenario | Executable evidence | Expected claim |
| --- | --- | --- |
| normal real OPC UA collection | `tests/contract/test_opcua_persistent_runtime.py::test_persistent_worker_collects_real_asyncua_datachange_to_durable_spool` | real asyncua DataChange가 durable spool까지 도달 |
| connection lost | `tests/integration/test_opcua_acquisition_worker.py::test_worker_ends_on_connection_loss_after_persisting_earlier_events` | 상실 전 event 보존, worker 종료 후 fresh session(ADR-0010), lifecycle ACTIVE 유지 |
| callback overflow | `test_worker_ends_with_explicit_overflow_so_a_fresh_session_restarts`, `tests/contract/test_opcua_persistent_runtime.py::test_queue_overflow_ends_the_worker_instead_of_wedging_the_client` | overflow evidence 기록 후 명시적 종료, client wedge 없음, gap-free claim 없음 |
| failed worker restart | `tests/integration/test_collection_control.py::test_collection_service_restarts_failed_workers_with_backoff` | 1·2·4…30초 backoff 재시작 |
| window coordinator failure | `test_window_failures_restart_only_the_coordinator_and_metrics_failure_is_reported` | OPC UA session 유지, coordinator만 backoff 재시작 |
| loss + in-flight notification | `tests/integration/test_opcua_acquisition_worker.py::test_notification_ready_with_connection_loss_is_persisted_before_the_worker_ends` | 이미 dequeue된 notification은 종료 전에 spool 기록 |
| concurrent spool reads | `tests/integration/test_acquisition_spool.py::test_backlog_reads_stay_consistent_while_events_are_accepted` | backlog 통계가 동시 accept와 섞이지 않음 |
| duplicate local retry | `tests/integration/test_acquisition_spool.py::test_duplicate_local_delivery_is_idempotent_but_conflict_is_rejected` | identical retry idempotent, conflicting payload fail-fast |
| spool capacity | `test_spool_capacity_is_bounded_without_rejecting_idempotent_retry` | capacity 초과는 explicit failure, 기존 durable row 유지 |
| collector restart | `test_worker_process_restart_reserves_new_connection_epoch` | durable epoch baseline 복구, identity reuse 방지 |
| history temporary failure | `tests/integration/test_history_writer.py::test_writer_keeps_stable_active_batch_when_history_fails` + reliability soak | active batch 미ACK 보존 후 동일 batch retry |
| commit → ACK crash | `tests/contract/test_spool_ducklake_writer.py::test_writer_recovers_ducklake_commit_after_ack_crash_without_duplicate` | 기존 snapshot recover 후 duplicate 없이 ACK |
| out-of-order / late / missing channel / future skew / unavailable timing | `tests/integration/test_window_coordinator.py::test_coordinator_rotates_windows_and_preserves_dispositions_across_rebuild` | timestamp overwrite 없이 disposition evidence 보존 |
| window buffer overflow | `test_coordinator_preserves_buffer_full_disposition` | BUFFER_FULL evidence 보존 |
| finalized window restart | `tests/contract/test_window_coordinator_ducklake.py::test_ducklake_history_rebuilds_same_finalized_windows_after_restart` | durable raw history에서 동일 finalized window rebuild |
| desired-state restart | `tests/integration/test_collection_control.py` | desired state는 durable, UI와 runtime owner 분리 |
| backfill + live overlap | `tests/contract/test_ducklake_runtime.py::test_ducklake_file_backfill_and_live_share_asset_history` | 같은 asset/time query, source provenance 보존 |
| no asset-health inference | reliability soak + source-health contracts | acquisition evidence가 asset verdict로 자동 승격되지 않음 |

## 3. bounded soak profile

`tests/contract/test_live_acquisition_reliability.py`는 빠르게 반복 가능한 bounded reference soak입니다.

CI reference profile:

- 192 durable OPC UA deliveries
- 2 collector epochs / simulated process restart
- one identical local-delivery retry
- one explicit replay delivery
- periodic out-of-order SourceTimestamp
- 24-event bounded DuckLake micro-batches
- first DuckLake append failure
- active-batch writer restart recovery
- full spool drain to DuckLake
- durable history count/identity verification
- observation-window rebuild verification
- telemetry restart/history consistency verification

이 profile은 장시간 production endurance benchmark가 아니라 **CI에서 deterministic하게 돌릴 수 있는 recovery
contract**입니다. 장시간 throughput/retention/compaction benchmark는 deployment hardware와 실제 sampling rate가
정해진 뒤 별도 performance profile로 측정합니다.

## 4. temporary downstream failure semantics

`write_next_spool_batch()`는 한 번의 commit attempt를 표현하므로 downstream failure를 caller에게 그대로
노출합니다. 반면 `run_spool_to_history_writer()`는 continuous runtime owner이며 다음 동작을 사용합니다.

```text
active spool batch
    ↓
DuckLake attempt
    ├─ success → ACK spool → next batch
    ├─ transient exception → keep active batch → poll delay → retry same batch
    └─ identity/spool invariant violation → fail fast
```

Retry 중 새 batch ID를 만들지 않습니다. 따라서 downstream 일시 장애가 active batch identity를 바꾸거나
spool ACK를 선행시키지 않습니다.

## 5. operational interpretation

Reliability evidence는 다음 의미를 서로 대체하지 않습니다.

```text
runtime failure / reconnect / overflow
    ≠ source lifecycle ERROR
    ≠ asset condition
    ≠ PHM finding
    ≠ maintenance verdict
```

운영 화면은 failure, queue/spool depth, latest history snapshot, watermark/disposition을 함께 보여줄 수 있지만,
그 정보를 설비 고장 판정으로 자동 승격하지 않습니다.
