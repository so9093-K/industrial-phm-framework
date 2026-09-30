# Live Acquisition & DuckLake Asset History v1

이 문서는 continuous source acquisition의 v1 책임 경계와 durability semantics를 정의합니다.
Persistent OPC UA/event-time contract와 bounded observation-window contract를 대체하지 않고, 두 경계
사이와 그 아래의 장기 실행 runtime과 historical data plane 책임을 정의합니다.

v1 reference profile의 목표는 distributed streaming platform을 만드는 것이 아니라, 한 공장/edge node에서
**source를 지속적으로 수집하고, process restart와 일시적 downstream failure를 견디며, Live와 Backfill을
동일한 Asset history로 조회할 수 있는 single-writer reference runtime**을 만드는 것입니다.

## 1. 기준 데이터 흐름

```text
PLC / Sensor / Historian / File
            │
            ▼
       Source Adapter
            │
            ▼
       Source Worker
            │
     bounded callback queue
            │
            ▼
    Durable Ingress Spool
       (local SQLite WAL)
            │
            ▼
     micro-batch writer
            │
            ▼
          DuckLake
   ┌────────┼───────────┐
   │        │           │
raw evidence  measurement history  derived windows
   └────────┴───────────┘
            │
            ▼
        Asset History
            │
       PHM Analysis
            │
    Finding / Review
            │
       Maintenance
```

Operations UI는 이 loop를 소유하지 않습니다. UI는 source configuration과 collection desired state를
변경하고 runtime/history evidence를 읽는 control/monitor surface입니다.

## 2. 책임 경계

### Control plane

Control plane은 사용자가 **무엇을 수집할지**를 정의합니다.

- registered source identity와 type
- endpoint/path 같은 non-secret connection configuration
- Asset / Measurement Point / Channel mapping
- source lifecycle과 collection desired state
- sampling/window/freshness 같은 explicit policy
- credential/certificate material을 직접 저장하지 않는 secret reference

등록되었다는 사실, lifecycle이 ACTIVE라는 사실, collection desired state가 RUNNING이라는 사실은 실제
network connection 성공이나 data flow를 의미하지 않습니다.

### Acquisition plane

Acquisition plane은 **현재 source에서 event를 받는 실행 책임**을 가집니다.

- protocol connection/session/subscription lifecycle
- bounded callback queue
- reconnect/recovery
- connection epoch와 local delivery index
- protocol value/status/timestamp/replay evidence 보존
- durable ingress append
- graceful stop/cancel

OPC UA에서는 transport/session/subscription recovery를 검증된 protocol runtime에 위임할 수 있는 경우 이를
우선 사용하고, 이 프로젝트는 `OpcUaPersistentSessionEvidence`와
`OpcUaPersistentDataChangeEvent` 같은 application-level evidence semantics를 소유합니다.

Source lifecycle과 runtime connection state는 서로 다른 상태입니다. 예를 들어 transient disconnect 동안에도
source는 administrative lifecycle에서 ACTIVE일 수 있고 runtime은 RECONNECT_WAIT일 수 있습니다.

### Durable ingress plane

Callback queue는 memory bound일 뿐 durability boundary가 아닙니다. v1에서 event가 continuous pipeline에
durably accepted되었다고 판단하는 최초 지점은 **local ingress spool transaction이 성공한 시점**입니다.

Reference implementation은 SQLite WAL을 사용합니다. Spool은 다음만 책임집니다.

- 아직 DuckLake에 commit되지 않은 delivery의 crash-safe 보존
- pending delivery의 deterministic restore
- micro-batch writer retry를 위한 stable local identity
- downstream commit 성공 후 acknowledgement
- bounded capacity와 explicit overflow/failure evidence

Spool은 historical database가 아니며 장기 보존, PHM query, window query를 책임지지 않습니다.

`ingested_at`은 이 durable-ingress acceptance와 함께 기록되는 platform timing fact입니다.
`SourceTimestamp`, `ServerTimestamp`, connector `received_at`을 대체하지 않으며 event time으로
자동 승격하지 않습니다.

### Historical data plane

DuckLake는 v1의 **historical PHM data plane / Asset history**입니다. DuckLake는 SQL catalog와 Parquet data
storage를 사용하며 committed transaction은 snapshot으로 기록됩니다.

v1은 DuckLake를 callback queue, message broker, retry queue 또는 WAL로 사용하지 않습니다. Event는 spool에서
bounded micro-batch로 읽어 하나의 logical transaction으로 commit합니다.

History에는 최소 두 의미 계층을 분리합니다.

1. **raw source evidence** — protocol/source-specific fact를 손실 없이 보존
2. **normalized measurement history** — Asset / Measurement Point / Channel과 event-time 기준의 공통 조회 surface

OPC UA raw evidence에는 value, Variant/StatusCode, SourceTimestamp, ServerTimestamp, received_at,
ingested_at, connection epoch, local event index와 replay fact가 포함됩니다. 이후 MQTT/Historian source가
추가되어도 source-specific raw representation을 억지로 하나의 universal protocol schema로 합치지 않습니다.

Normalized history는 source-specific evidence를 참조하며 적어도 다음 provenance를 유지합니다.

- source identity/type
- asset / measurement-point / channel identity
- event_at + event-time basis
- raw evidence identity
- ingestion mode: LIVE / BACKFILL / IMPORT / REPLAY equivalent

### Derived window / PHM plane

`DurableObservationWindow`는 historical truth 자체가 아니라 raw/measurement history에서 계산되는 derived
aggregate입니다. Window policy가 바뀌거나 runtime이 restart되어도 필요한 경우 durable raw history에서 다시
구성할 수 있어야 합니다.

`COMPLETE` 의미는 bounded observation-window contract와 동일하게 expected channel coverage일 뿐이며 synchronized snapshot, equal sampling,
gap-free/exactly-once delivery, analysis readiness 또는 asset health를 뜻하지 않습니다.

AnalysisRun은 장기적으로 다음 provenance를 참조할 수 있어야 합니다.

- DuckLake snapshot id
- input event/window time range
- asset/source selection
- algorithm/configuration identity
- code revision

이를 통해 Finding → AnalysisRun → 당시 Asset history snapshot → raw source evidence까지 추적 가능한 경로를
만드는 것을 목표로 합니다.

## 3. Delivery와 duplicate 의미

v1은 exactly-once delivery를 주장하지 않습니다.

```text
protocol delivery
    ↓
application-local delivery identity
    ↓
durable spool
    ↓
idempotent batch commit
    ↓
DuckLake history
```

OPC UA의 `(source_id, connection_epoch, event_index)`는 persistent OPC UA contract의 의미 그대로 platform-local delivery
identity입니다. Server sequence number나 physical measurement identity가 아니며 reconnect 후 replay가 새로운
epoch/index로 도착하면 값이 같다는 이유만으로 제거하지 않습니다.

Spool/writer retry는 같은 local delivery를 두 번 historical record로 승격하지 않도록 idempotent해야 하지만,
protocol replay 자체는 별도 factual evidence로 보존합니다.

## 4. Event time과 watermark

다음 clock을 계속 분리합니다.

```text
source_timestamp   # source-provided event fact
server_timestamp   # server-provided protocol fact
received_at        # connector callback receipt
ingested_at        # durable ingress acceptance
event_at           # explicit event-time policy가 선택한 time
watermark          # runtime progress policy
```

`event_at`과 watermark는 같은 개념이 아닙니다. Persistent OPC UA event-time contract의 SourceTimestamp
우선 정책과 explicit ServerTimestamp fallback을 유지하고, watermark 생성 정책은 continuous window
coordinator가 소유합니다.

Late/out-of-order/future clock-skew는 timestamp를 덮어써서 해결하지 않고 factual disposition/evidence로
남깁니다.

## 5. Live + Historical

제품의 최종 history 모델은 dataset upload와 live collection을 별도 세계로 두지 않습니다.

```text
Historian / CSV ──→ Backfill ─┐
                             ├─→ DuckLake Asset History
OPC UA / MQTT ───→ Live ─────┘
```

두 경로는 동일한 asset/time query surface로 합쳐지지만 provenance는 유지합니다. Backfill이 live보다 늦게
실행되었다고 해서 historical event의 event time을 ingestion time으로 바꾸지 않습니다.

Registered FILE reference backfill은 기존 Asset / Measurement Point / Channel mapping을 재사용하고,
explicit timezone-aware CSV timestamp만 SOURCE_TIMESTAMP event time으로 승격합니다. Sampling rate만 있는
상대시간 CSV에는 임의 absolute time을 만들지 않으며 backfill을 거부합니다.

FILE raw evidence는 source ID, file name, exact source SHA-256, sample index, channel ID를 조합한 stable
`raw_evidence_id`로 저장하고, 파일 snapshot별 stable batch ID를 사용합니다. 동일 snapshot 재실행은 DuckLake
batch commit provenance를 checkpoint로 복구하여 새 row를 만들지 않습니다. 별도 cursor DB를 truth로 두지 않기
때문에 crash/restart 시 이미 commit된 segment는 recovered되고 아직 commit되지 않은 segment만 이어집니다.

Live/backfill overlap과 duplicate 정책은 explicit input identity/provenance를 기준으로 정의합니다. 다른 file
snapshot이나 live delivery가 같은 `event_at`/value를 가지더라도 서로 다른 raw evidence이면 모두 보존합니다.
값/시각 similarity heuristic으로 source evidence를 삭제하지 않습니다. Backfill 완료 결과는 현재 DuckLake
snapshot ID와 half-open asset input range를 `HistoricalInputReference`로 제공해 baseline/analysis provenance에
기록할 수 있습니다.

## 6. DuckLake v1 deployment profile

v1 reference profile은 local-first입니다.

- DuckLake catalog: **SQLite** — collector, writer, Operations/analysis 같은 여러 local client로 성장할 수 있는
  경계를 염두에 둠
- DuckLake data storage: local filesystem Parquet
- history writer: single writer
- ingress spool: DuckLake catalog와 분리된 SQLite WAL database
- object storage/PostgreSQL catalog: 별도 deployment adapter concern

DuckLake의 catalog/data path와 spool database는 서로 다른 state path를 사용해야 합니다.

DuckLake의 작은 transaction을 event마다 생성하지 않습니다. Writer는 max events / max bytes / max interval 같은
명시적 policy로 micro-batch를 만들고 하나의 transaction으로 commit합니다. Small Parquet file 누적과 old
snapshot/file retention은 maintenance responsibility이며 CHECKPOINT/compaction/expiry 정책은 실제 데이터
규모와 evidence retention 요구를 측정한 뒤 명시합니다.

## 7. Operational evidence 의미

최소한 다음 의미를 서로 섞지 않습니다.

```text
source lifecycle
    ≠ runtime connection state
    ≠ acquisition/data-flow health
    ≠ data quality
    ≠ asset condition/health
    ≠ PHM finding severity
```

Continuous runtime telemetry는 control-plane registry와 bounded source-runtime repository에서 분리된
SQLite WAL latest-evidence store를 사용합니다. Collector, history writer, window coordinator가 source별
component row를 독립적으로 갱신해 서로의 최신 evidence를 덮어쓰지 않습니다.

Acquisition telemetry surface는 다음 factual evidence를 제공합니다.

- session: CONNECTING / CONNECTED / RECONNECT_WAIT / STOPPED, connected_since,
  last_disconnect_at, connection epoch, reconnect attempt index
- flow: worker-start 이후 accepted/replayed/bad-status event count, latest SourceTimestamp / received_at /
  ingested_at, lifetime-average event rate
- callback queue: configured maxsize와 overflow count
- spool: durable pending event/bytes, oldest pending age, active batch depth/bytes를 spool DB에서 직접 sample
- history writer: latest acknowledged batch/snapshot과 source event count
- window: latest watermark, active/finalized count와 disposition counts
- failure: latest runtime component failure evidence

asyncua iterator의 queue depth는 public/stable API로 노출되지 않으므로 private `_event_queue`에
의존하지 않습니다. 따라서 callback queue depth/high-watermark는 현재 명시적으로 uninstrumented(`None`)이고,
configured maxsize와 실제 overflow signal만 factual evidence로 기록합니다.

Telemetry 저장 실패는 spool/DuckLake/window data-plane truth를 rollback하지 않습니다. Runtime producer는
telemetry failure를 로그로 남기되 이미 durable하게 수용/commit된 데이터의 진행을 막지 않습니다. 또한 이
surface에는 synthetic `healthy: bool`을 두지 않으며 기존 `SourceHealthAssessment.connection_state`를
자동으로 덮어쓰지 않습니다. 이 정보는 설비가 고장났다는 판단으로 자동 승격하지 않습니다.

## 8. Restart semantics

### Collector crash

이미 spool transaction이 commit된 event는 restart 후 pending delivery로 복원합니다. Memory callback queue에만
존재하고 spool에 들어가지 못한 event는 durable하다고 주장하지 않습니다.

OPC UA의 platform-local delivery identity에 사용하는 connection epoch도 source별로 durable spool metadata에서
보존합니다. Worker 시작 시 last epoch를 baseline으로 읽고 successful connection마다 next epoch를 atomic reserve한
뒤 event index를 0부터 시작합니다. 따라서 process restart가 과거 `(source_id, connection_epoch, event_index)`
identity를 재사용하지 않습니다. Reservation 직후 crash로 epoch gap이 생길 수 있지만 gap은 server sequence loss를
뜻하지 않으며 identity reuse보다 안전한 local-generation semantics입니다.

### DuckLake writer failure

DuckLake transaction이 실패하면 batch의 spool delivery를 acknowledge하지 않습니다. Retry는 stable batch/local
delivery identity를 사용합니다. Writer는 max events / max bytes / max interval 중 하나가 충족될 때 micro-batch를
assign하고, DuckLake commit 성공 뒤에만 spool ACK를 수행합니다.

DuckLake commit 성공과 spool ACK 사이에서 process가 종료될 수 있으므로 batch identity 자체도 durable해야 합니다.
각 historical batch snapshot에는 `batch_id`, ingestion mode, event count, canonical event fingerprint를
`commit_extra_info` provenance로 기록합니다. Restart 후 같은 active spool batch가 보이면 이 provenance가
정확히 일치하는 기존 snapshot을 복구하고 새 historical row를 쓰지 않은 채 ACK를 완료합니다. 같은 batch ID에
다른 event set/provenance가 대응하면 fail-fast conflict입니다.

### Window coordinator crash

Window coordinator는 DuckLake raw OPC UA history를 `ingested_at → connection_epoch → event_index` 순서로
deterministic replay하고, fixed alignment window와 bounded-out-of-orderness watermark
`max(valid expected-channel event_at seen) - allowed_lateness`를 다시 계산합니다. Timing-unavailable,
future-skew, current source mapping에 없는 unexpected-channel event는 disposition evidence는 남기지만
watermark를 전진시키지 않습니다.

Finalized window의 `finalized_at`은 wall clock이 아니라 해당 watermark를 전진시킨 durable event의
`ingested_at`을 사용합니다. 따라서 process restart 후 in-memory buffer가 사라져도 같은 raw history에서
같은 finalized window evidence를 재구성해 repository에 idempotently 기록할 수 있습니다.

이미 close된 window에 뒤늦게 도착한 event는 `LATE` disposition evidence로 남기지만 persisted window를
사후 변경하지 않습니다. Finalized durable window는 재사용하고, 아직 finalize되지 않은 window state는 raw
history를 source of truth로 rebuild합니다. in-memory buffer 자체를 historical truth로 승격하지
않습니다.

### Operations UI restart

UI restart나 browser close는 collector stop을 의미하지 않습니다. Operations는 SQLite WAL
collection-control store에 desired state만 기록하고, 별도 `run-collection-service` process가
source별 persistent worker/window coordinator와 shared spool→DuckLake writer를 소유합니다.

`SourceLifecycle.ACTIVE`, `CollectionDesiredState.RUNNING`, observed session `CONNECTED`는 서로 다른
dimension입니다. Start Collection은 lifecycle을 바꾸지 않고 ACTIVE source에 RUNNING intent만 기록하며,
Stop Collection도 lifecycle을 유지한 채 STOPPED intent를 기록합니다. Runtime service가 없거나 중단되면
desired RUNNING과 observed STOPPED/Unavailable이 동시에 보일 수 있으며 UI는 이를 숨기지 않습니다.

Service는 STOP request로 source worker/window coordinator를 종료해도 shared history writer를 계속 유지해
이미 durable spool에 수용된 backlog를 DuckLake로 drain할 수 있습니다. Service process 자체가 종료될 때는
remaining sub-threshold spool data를 버리지 않고 durable state로 남깁니다. UI는 acquisition telemetry와 spool
snapshot을 다시 읽어 monitor를 구성하며 DuckLake를 직접 mutate하지 않습니다.

## 9. 비목표

이번 v1에서 다음을 선제 도입하지 않습니다.

- Kafka/Pulsar 같은 distributed message broker
- Flink/Spark Streaming 같은 distributed stream processor
- generic source/plugin framework
- exactly-once marketing claim
- universal raw protocol schema
- automatic asset-health inference
- multi-region/high-availability control plane
- remote PostgreSQL catalog/object storage production deployment

실제 scale, multi-writer, plant deployment requirement가 확인되면 현재 contract를 유지한 채 infrastructure
adapter를 교체합니다.

## 10. 참고

- DuckLake specification v1.0: https://ducklake.select/docs/stable/specification/introduction
- DuckLake transactions/snapshots: https://ducklake.select/docs/stable/duckdb/advanced_features/transactions
- DuckLake catalog choice: https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database
- DuckLake maintenance: https://ducklake.select/docs/stable/duckdb/maintenance/recommended_maintenance
- DuckLake checkpoint: https://ducklake.select/docs/stable/duckdb/maintenance/checkpoint

## 11. Reliability verification

Failure/restart semantics와 bounded CI soak의 executable evidence는
[`live-acquisition-reliability-v1.md`](live-acquisition-reliability-v1.md)에 고정합니다.

Continuous history writer는 transient downstream exception에서 active spool batch를 ACK하지 않고 동일 batch를
poll delay 후 재시도합니다. Stable identity conflict와 spool invariant violation은 retry 대상으로 숨기지 않고
fail-fast합니다. 따라서 temporary DuckLake failure는 collection service 전체를 즉시 종료시키는 정상 경로가
아니며, spool capacity가 남아 있는 동안 durable ingress와 downstream recovery 경계를 유지합니다.

