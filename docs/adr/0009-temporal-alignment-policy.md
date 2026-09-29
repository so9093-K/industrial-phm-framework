# 0009. Align multi-channel observations with an explicit, versioned temporal policy

Status: Accepted

## Context

다채널 분석(예: 3상 불평형)은 한 시각의 여러 channel 값을 함께 사용합니다. 현재 capability는 같은 source
timestamp의 값만 묶습니다(strict). OPC UA DataChange 구독은 sampling은 하지만 filter 조건(기본
STATUS_VALUE, 선택적 deadband)을 만족한 값만 알리므로, 안정적인 상은 notification이 드물고 strict
정렬의 coverage가 낮아집니다. Loopback E2E에서 상수 channel이 있는 window가 실제로 분석되지 않았습니다.

Notification이 없다는 사실은 "값이 그대로였다"를 뜻할 수도, deadband 안에서 바뀌었음을 뜻할 수도,
통신 문제를 뜻할 수도 있습니다. 이전 값을 유지(hold-last)하는 재구성은 산업 historian에서도 쓰는 방식이지만
(OPC UA HA의 Stepped, historian의 discrete history), 데이터의 의미와 source 계약에 따라 선택하는 정책이지
raw 데이터의 속성이 아닙니다. 전력품질처럼 동시성이 중요한 측정은 장비가 제공하는 동기·주기 측정값이
소프트웨어 재구성보다 우선입니다.

## Decision

- Raw acquisition은 어떤 보간·재구성도 하지 않습니다. DataChange, timestamps, status, 수신 시각을 그대로
  보존합니다(현재와 같음).
- **Temporal alignment는 protocol과 무관한 application 계층**(`industrial_phm.application.alignment`)입니다.
  입력은 공통 `ChannelObservation`, 출력은 정렬된 sample과 제외 사유입니다. OPC UA/asyncua 타입이나 새
  dependency를 쓰지 않으며, CSV·history·window 입력에 같은 정책을 재생할 수 있습니다.
- 정책은 versioned입니다.
  - `strict-v1`(기본): 모든 channel이 같은 timestamp에 관측된 시각만 sample입니다. 추정이 없습니다.
  - `bounded-previous-v1`: 어떤 channel이 관측된 시각 T를 기준으로, 다른 channel은 T 이전(또는 같은 시각)의
    마지막 관측을 `T − observed_at ≤ max_age`일 때만 사용합니다. 미래 관측은 쓰지 않습니다(causal).
    `max_age`와 그 근거(`basis`: 계측 갱신 주기, 장비 사양, calibration 결과 등)는 **명시적으로 요구**하며
    라이브러리 기본값이 없습니다. Transport timeout은 측정 유효 기간이 아닙니다.
- 재구성된 값은 원래 관측을 대신하지 않습니다. 각 sample 값은 원래 observation(시각·값·status·의미)과
  origin(`observed`/`carried`), age를 함께 가지며 raw evidence로 저장하지 않습니다.
- Capability는 필요한 정책을 요청할 뿐 cache나 protocol 상태를 직접 관리하지 않습니다. 정책은 evidence(정책
  version, max age, basis, carried 값 수, carry age 분포)와 분석 identity(policy digest)에 포함됩니다.
  기본 strict 정책은 기존 identity를 바꾸지 않습니다.
- ADR-0008은 유지됩니다. 정렬은 finalized window가 accept한 event에 결정적으로 적용되며, 정렬을 위해
  history를 재조회하지 않습니다.
- Window 시작 직전의 값(carry-in)은 현재 사용하지 않습니다. Window 첫 부분의 carried 정렬이 필요하면
  window coordinator가 finalize할 때 bounded carry-in state를 provenance와 함께 window에 고정하는 방식으로
  별도 변경에서 추가합니다(분석 시점 history 재조회 금지).

## Consequences

기본 동작과 기존 분석 identity는 변하지 않습니다. `bounded-previous-v1`은 coverage를 높이지만 deadband나
긴 무통신 구간에서는 실제 변화를 가릴 수 있으므로 source/device의 측정 계약이나 검증 결과가 있을 때만
사용해야 합니다. Source profile에 update 주기·trigger·deadband·timestamp 의미 같은 acquisition semantics를
기록하는 계약과, DataChange와 주기 grouped Read를 동시에 수집해 정책별 coverage·carry age·불평형 오차를
비교하는 calibration 실험이 후속 작업입니다. Nearest(비인과)와 주기 grid 정책은 offline 분석 필요가
확인될 때 추가합니다.
