# 0010. Recover lost OPC UA sessions with a fresh worker, not asyncua's in-client reconnect

Status: Accepted

## Context

v1 persistent acquisition은 transport/session/subscription 복구를 asyncua 2.0.1(`auto_reconnect=True`)에
맡기고, application은 connection epoch와 evidence만 소유했습니다. Subscription iterator queue가 넘치면
`OverflowPolicy.DISCONNECT` hook에서 `notify_transport_lost()`를 호출해 asyncua 재연결을 유도했습니다.

Phase 10 AI-Hub replay로 재현 가능한 fault harness(source/collector SIGSTOP, publish ledger 대조)를
돌린 결과, 이 경로에서 두 가지 실패가 결정적으로 재현됐습니다.

1. **Overflow 후 영구 disconnected.** 30초 source stall 뒤 재연결 순간 1,173건 burst가 queue(128)를
   넘었고, hook이 거부된 notification마다(1,019회) `notify_transport_lost()`를 호출했습니다. 재연결
   마무리와 겹친 뒤 asyncua client는 `client is disconnected`만 반복하며 다시 연결하지 않았고, worker의
   session evidence는 CONNECTED로 남았습니다. Phase 10 첫 날 11분 수집 정지와 같은 현상입니다.
2. **Session 재활성화 후 subscription 불일치.** 180초 stall 뒤 asyncua가 기존 session을 재활성화하면서
   새 subscription(80)을 만들고 기존 것(79)의 mapping을 버렸습니다. Server는 79로 계속 publish했고
   client는 `Received data for unknown subscription 79`로 모두 버렸습니다. CONNECTED 상태에서 데이터가
   무기한 유실됩니다.

Publish ledger 대조 기준 두 실패 모두 재시작 전까지 delivered 0이었습니다. 반면 client 측 20초
stall(collector SIGSTOP)은 같은 session이 유지되어 유실 0건이었습니다.

## Decision

- asyncua가 연결 상실을 알리면(`RECONNECTING`) worker는 `RECONNECT_WAIT` evidence를 남기고
  `OpcUaSessionLostError`로 종료합니다. 같은 wakeup에서 이미 dequeue된 notification은 이 session에
  도착한 것이므로 먼저 spool에 기록한 뒤 종료합니다. Connector close가 asyncua supervisor와 client를
  정리합니다.
- Subscription queue overflow hook은 asyncua client state를 건드리지 않고 worker에 한 번만 신호합니다.
  Worker는 overflow evidence를 기록한 뒤 `OpcUaSubscriptionOverflowError`로 종료합니다.
- Collection service가 종료된 worker를 새 client·session·subscription과 새 durable connection epoch로
  다시 시작합니다. 연속 실패는 1, 2, 4 … 최대 30초 backoff하고, 60초 이상 동작한 뒤의 실패는
  backoff를 처음부터 다시 시작합니다. 이 값은 `CollectionServicePolicy.restart_backoff_*`가 유일하게
  소유합니다. `OpcUaPersistentSessionPolicy.reconnect_*`는 worker가 버리는 asyncua 내부 재시도에만
  해당합니다.
- Window coordinator 실패는 OPC UA session 문제가 아니므로 worker를 재시작하지 않습니다. Session은 계속
  spool로 수집하고, coordinator만 durable cursor에서 같은 backoff로 재시작합니다.
- Subscription queue 기본값을 128에서 4096으로 올립니다. 정상 35 channel × 1 Hz 운전의 high
  watermark는 약 33이고, 30초 source stall 뒤 burst(1,007건, 최대 depth 914)는 overflow 없이 2.2초에
  처리되었습니다.
- 계측: `received_at`은 consumer dequeue 시각이 아니라 asyncua가 notification을 queue에 넣은 시각입니다
  (asyncua 2.0.1 `Subscription._deliver` 감싸기; 없으면 dequeue 시각으로 fallback). Collector의
  `--pipeline-metrics`는 queue depth, arrival→dequeue, spool accept, event-loop 동기 telemetry, event-loop
  lag, history commit, window cycle을 10초 단위 JSONL로 남기는 opt-in 진단입니다.

## Consequences

- asyncua의 session 재활성화·republish로 복구할 수 있었던 일부 notification은 포기합니다. 손실 경계는
  **source/연결 중단 시간 + restart backoff + 상실 시점에 이전 session client queue에 남아 아직 dequeue되지
  않은 notification**입니다(queue를 drain하지 않음). CONNECTED 상태의 무기한 silent loss나 영구
  disconnected는 생기지 않으며, 상실 구간은 publish ledger audit과 worker failure evidence로 드러납니다.
- `--pipeline-metrics` reporter가 실패해도 수집은 계속되고, collector log에 경고가 남습니다. Fault harness는
  최근 metrics record의 존재를 판정 전제 조건으로 확인해야 합니다.
- Replay flag(`Republish`)는 fresh session에서는 발생하지 않습니다. 기존 replay evidence 계약은 유지하지만
  in-client 재연결 경로의 epoch 증가 시나리오는 worker 재시작 epoch 계약으로 대체됩니다.
- asyncua private API(`_deliver`, `_event_queue`)는 진단·도착 시각에만 쓰고, 없으면 기능이 꺼질 뿐
  수집은 계속됩니다. asyncua 버전을 올릴 때 이 결정과 harness를 다시 검증합니다.
