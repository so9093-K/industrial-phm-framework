# Live Acquisition & DuckLake Asset History v1

이 문서는 continuous source acquisition을 제품의 주 입력 경로로 확장할 때의 v1 책임 경계와
durability semantics를 정의합니다. 현재 `#256`의 persistent OPC UA/event-time contract와 `#257`의
bounded observation-window contract를 대체하지 않고, 두 경계 사이와 그 아래에 실제 장기 실행 runtime과
historical data plane을 추가하는 기준입니다.

현재 단계의 목표는 distributed streaming platform을 만드는 것이 아니라, 한 공장/edge node에서
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

`COMPLETE` 의미는 #257과 동일하게 expected channel coverage일 뿐이며 synchronized snapshot, equal sampling,
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

OPC UA의 `(source_id, connection_epoch, event_index)`는 현재 #256 의미 그대로 platform-local delivery
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

`event_at`과 watermark는 같은 개념이 아닙니다. #256의 SourceTimestamp 우선 정책과 explicit
ServerTimestamp fallback을 유지하고, watermark 생성 정책은 #263 continuous window coordinator가 소유합니다.

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

Live/backfill overlap과 duplicate 정책은 explicit input identity/provenance를 기준으로 정의하며 값/시각이
비슷하다는 heuristic만으로 source evidence를 삭제하지 않습니다.

## 6. DuckLake v1 deployment profile

이번 milestone의 reference profile은 local-first입니다.

- DuckLake catalog: **SQLite** — collector, writer, Operations/analysis 같은 여러 local client로 성장할 수 있는
  경계를 염두에 둠
- DuckLake data storage: local filesystem Parquet
- history writer: single writer
- ingress spool: DuckLake catalog와 분리된 SQLite WAL database
- object storage/PostgreSQL catalog: 후속 deployment concern

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

Runtime telemetry는 connected/reconnecting/stopped, reconnect evidence, last source/received time, event rate,
callback queue depth/overflow, spool pending depth, last DuckLake batch/snapshot, window/watermark와
late/out-of-order/replayed counts를 다룰 수 있습니다.

이 정보는 설비가 고장났다는 판단으로 자동 승격하지 않습니다.

## 8. Restart semantics

### Collector crash

이미 spool transaction이 commit된 event는 restart 후 pending delivery로 복원합니다. Memory callback queue에만
존재하고 spool에 들어가지 못한 event는 durable하다고 주장하지 않습니다.

### DuckLake writer failure

DuckLake transaction이 실패하면 batch의 spool delivery를 acknowledge하지 않습니다. Retry는 stable batch/local
delivery identity를 사용합니다.

### Window coordinator crash

Finalized durable window는 재사용할 수 있고, 아직 finalize되지 않은 window state는 raw history를 source of
truth로 사용해 rebuild 가능한 방향을 유지합니다. #257의 in-memory buffer 자체를 historical truth로
승격하지 않습니다.

### Operations UI restart

UI restart나 browser close는 collector stop을 의미하지 않습니다. UI는 independent runtime state를 다시 읽습니다.

## 9. 이번 milestone 작업 순서

1. #258 — 이 architecture/product boundary를 고정
2. #259 — DuckLake asset-history persistence vertical slice
3. #260 — SQLite WAL durable acquisition spool
4. #261 — persistent OPC UA acquisition worker
5. #262 — spool → DuckLake micro-batch writer
6. #263 — continuous observation-window coordinator
7. #264 — live acquisition telemetry
8. #265 — Operations Start/Stop Collection + Live Monitor
9. #266 — historical backfill → same Asset history
10. #267 — reconnect/crash/replay/overflow/restart/soak 검증

#262가 끝나기 전에는 Operations의 Start Collection을 durable product capability로 표현하지 않습니다.

## 10. 비목표

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

## 11. 참고

- DuckLake specification v1.0: https://ducklake.select/docs/stable/specification/introduction
- DuckLake transactions/snapshots: https://ducklake.select/docs/stable/duckdb/advanced_features/transactions
- DuckLake catalog choice: https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database
- DuckLake maintenance: https://ducklake.select/docs/stable/duckdb/maintenance/recommended_maintenance
- DuckLake checkpoint: https://ducklake.select/docs/stable/duckdb/maintenance/checkpoint
