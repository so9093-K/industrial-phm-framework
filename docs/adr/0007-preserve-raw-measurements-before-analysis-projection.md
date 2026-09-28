# 0007. Preserve raw measurements before analysis projection

Status: Accepted

## Context

AI-Hub 239의 보일러·압출기 Training raw ZIP을 전수 조사한 결과, null, 동일 timestamp/channel의
상이한 값, 채널 간 시각 차이가 존재합니다. 원본에는 단위와 timezone이 없고 source device 식별자를
물리 asset identity로 확정할 근거도 부족합니다. 기존 CanonicalTimeSeries는 공통 sample axis의
유한한 숫자 행렬이며, 이 계약을 raw ingestion에 강제하면 사실을 잃습니다.

## Decision

- ZIP 원본은 저장소 외부의 local data root에 유지하고 SHA-256/member/record index로 참조합니다.
  Streaming reader는 원본 시각 문자열, device/board 식별자, null, 중복을 그대로 노출합니다.
- 원본 읽기에는 asset/timezone binding이 필요하지 않습니다. Asset History 적재에는 명시적 binding을
  요구하고, identity/timezone 근거와 버전을 각 FILE evidence에 보존합니다. 개발용 grouping과
  timezone 가정은 source fact와 구분합니다. 애매하거나 존재하지 않는 DST 시각은 거부합니다.
- FileBackfillEvent는 nullable value와 optional source metadata JSON을 허용합니다. null은 0으로
  바꾸지 않으며 history에서 good numeric observation으로 표시하지 않습니다. 기존 카탈로그는
  nullable 변경과 metadata column 추가로 이전 row와 batch fingerprint를 보존합니다.
- MeasurementDefinition과 ChannelSemanticBinding은 identity와 의미를 분리합니다. 최초 AI-Hub
  binding은 ITEM_NAME만 보존하며 canonical property/phase/statistic/unit 확정은 후속 evidence에
  따릅니다. 단위가 알려졌다고 기록하려면 근거가 필요합니다. binding은 관측별로 고정하여 새 해석이
  과거 이력을 암묵적으로 재해석하지 않게 합니다.
- CanonicalTimeSeries의 finite rectangular 계약은 유지합니다. 정렬·제외·보간은 별도 분석 projection의
  명시적 책임이며, 이번 변경은 전력 PHM 분석이나 universal raw schema를 도입하지 않습니다.
- UI 조회는 단일 asset/channel과 half-open time range, point budget을 받습니다. 처음에는 downsampling
  대신 시간순 첫 관측을 제한하고 truncation을 표시합니다. 충돌은 limit 이전 전체 선택 범위에서
  source/measurement point/channel/time별로 판정하며 FILE/live 또는 서로 다른 source를 합쳐 제거하지 않습니다.

## Consequences

실제 데이터의 불완전성을 조회할 수 있지만, 이력은 곧 분석 입력이 아닙니다. 단위 미상이나 이름 해석 미완료는
정상적인 metadata 상태입니다. 샘플 cadence 차이는 그 자체로 오류가 아니며, 예상 주기가 없는 상태에서
관측 부재를 자동으로 missing sample로 판정하지 않습니다.

Importer는 batch 단위 commit과 exact rerun recovery를 제공합니다. 다른 범위/크기로 겹쳐 적재하면
기존 raw identity 충돌을 명시적으로 거부합니다. 배치 중 오류가 나면 앞서 commit된 배치는 남으며,
동일 설정으로 재실행해 복구할 수 있습니다. 임의 overlap merge나 mapping migration은 제공하지 않습니다.

장기 storage의 single-writer 제약은 유지합니다. Multi-process coordination과 대규모 trend downsampling은
실제 운영 규모와 배포 요구에 맞춰 별도로 검증해야 합니다.
