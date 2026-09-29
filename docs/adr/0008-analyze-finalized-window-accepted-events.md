# 0008. Analyze the finalized window's accepted events, not a history re-query

Status: Accepted

## Context

Live 수집은 OPC UA DataChange → durable spool → DuckLake history → window coordinator → finalized
`DurableObservationWindow`로 이어집니다. Window coordinator는 watermark가 window end에 도달한 뒤 window를
finalize하고, 그 뒤 도착한 event는 `late`로 거부하며 개수만 남깁니다. 그러나 같은 event는 spool을 거쳐
history에는 계속 추가될 수 있습니다.

따라서 finalized window의 `[window_start, window_end)`로 나중에 history를 다시 조회하면, window가 accept한
입력과 다른 event 집합(늦게 도착한 값, 다른 source의 replay)이 분석될 수 있습니다. 같은 window를 다시 분석한
결과가 조회 시점에 따라 달라지고, "무엇을 분석했는가"를 window evidence로 설명할 수 없게 됩니다.

과거 Asset History 분석은 고정된 DuckLake snapshot을 입력 근거로 삼습니다(`three-phase-unbalance-v1`).
Live 분석에도 같은 수준의 입력 고정이 필요합니다.

## Decision

- Live 분석의 **authoritative input은 finalized window가 accept한 event 집합**(`DurableObservationWindow.events`)
  입니다. Window 종료 후 같은 시간 범위로 history를 재조회해 입력을 만들지 않습니다.
- 입력 근거는 `WindowInputReference`로 기록합니다: window ID, source·asset·측정점, window 구간, 닫힐 때의
  watermark, finalize 시각, accept/reject 개수, configured channel coverage, 그리고 accept된 event의
  delivery identity·channel·event time·값·status·semantic snapshot을 canonical JSON으로 만든 SHA-256
  (`input_digest`). 같은 window의 입력이 바뀌면 digest가 달라집니다.
- 측정 의미는 각 event가 수집 시점에 가진 semantic binding snapshot에서 읽습니다. 현재 source 등록 상태로
  과거 event를 재해석하지 않습니다. Snapshot이 없는 event는 미확정입니다.
- Window는 history와 같은 `ChannelObservation`/`ChannelSemanticCandidate` 형태로 투영되고, capability는
  history 입력과 같은 core(semantic role 선택, eligibility, 통계)를 사용합니다. 입력 출처만 다릅니다.
- Late·duplicate·timing-unavailable 등 window가 거부한 event는 분석 입력이 아니며 reject 개수로만 남습니다.
  Window completeness(`COMPLETE`/`PARTIAL`)는 channel coverage이며 분석 가능 여부나 설비 상태가 아닙니다.
- Window 분석 결과는 입력과 분석 정책이 같으면 같아야 합니다. 중복 기록 identity는
  **window·capability·algorithm version·analysis policy digest**입니다. Analysis policy digest는 role 선택 전
  요청 설정(명시 channel override 여부, 전압/전류 저신호 기준, bucket 수)과 policy digest version을 canonical
  JSON으로 고정합니다. 따라서 threshold나 explicit channel 설정을 바꾼 재분석은 이전 결과/skip에 막히지
  않습니다. 같은 identity의 결과는 재시작 뒤에도 중복 기록되지 않아야 하며(runner의 책임), 기록된 결과는
  window evidence로 재계산됩니다.

## Consequences

Window가 finalize된 뒤 도착한 늦은 값은 그 window의 분석에 반영되지 않습니다. 이것은 입력 고정의 의도된
결과이며, 늦은 값은 window reject evidence와 history에서 확인할 수 있습니다. 늦은 값까지 반영하려면
별도의 재분석 정책(새 window 정의 또는 history snapshot 기반 분석)을 명시적으로 선택해야 합니다.

Window evidence(JSON repository)가 분석 재현의 근거가 되므로, window 저장소는 분석 결과보다 오래 보존되어야
합니다. Window의 event 목록은 bounded buffer로 제한되며, 제한을 넘은 event는 `buffer_full`로 거부됩니다.

Historical 분석과 live 분석은 입력 참조의 종류(`history snapshot` / `finalized window`)가 다르므로 evidence에
두 종류를 구분해 기록합니다. 같은 시간 구간에 대한 두 결과가 다를 수 있으며, 그 차이는 입력 참조로 설명합니다.
