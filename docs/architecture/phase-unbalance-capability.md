# Three-phase unbalance capability (`three-phase-unbalance-v1`)

첫 label-free 전력 분석 capability입니다. Asset History의 확정된 상전압·상전류만으로 동작하며 provider
annotation(AI-Hub label)을 읽지 않습니다. 결과는 **서술적 전력 품질 측정값**이며 고장, 설비 건강 상태,
alarm, 정비 권고가 아닙니다.

## 정의

한 timestamp의 불평형률은 세 상 값의 평균에서 가장 크게 벗어난 편차를 평균으로 나눈 백분율입니다.

```text
unbalance % = max(|X_R − X̄|, |X_S − X̄|, |X_T − X̄|) / X̄ × 100,   X̄ = (X_R + X_S + X_T) / 3
```

전압은 **상전압** 기준입니다. 선간전압 기준 정의(NEMA MG1 LVUR)는 R/S/T상선간전압 channel과 선간 pair의
대응이 확정되지 않아 사용하지 않습니다(`aihub-239-semantics-v2`에서 unresolved). 두 정의의 값은 서로
같지 않으므로 외부 기준값과 비교할 때 정의를 확인해야 합니다.

## 입력과 eligibility

- Asset History의 한 source·측정점에서 요청 구간 `[start_at, end_at)`을 **고정된 DuckLake snapshot**으로 읽습니다. Source에 여러 측정점이 있으면 `measurement_point_id`를 명시하지 않은 분석은 fail-closed합니다.
- 입력 channel은 이름이 아니라 **bound meaning(semantic role)**으로 고릅니다. 같은 snapshot·구간·측정점에서
  `phase voltage`/V와 `phase current`/A의 scope `phase R/S/T`에 각각 정확히 한 channel이 묶인 quantity만
  분석합니다(`resolve_phase_channels`). 예를 들어 AI-Hub `R상전압`과 현장 OPC UA `Voltage_L1`은 같은 규칙으로
  선택됩니다. 한 역할에 여러 channel이 있거나 한 channel이 여러 역할이면 모호하다고 실패하며,
  `PhaseUnbalanceConfig`에 channel을 명시해 override할 수 있습니다. 세 상이 모두 묶이지 않은 quantity는
  `unresolved`로 표시하고 두 quantity 모두 없으면 실패합니다. Evidence에는 quantity별 사용 channel과 선택
  방식(`semantic-role`/`explicit`/`unresolved`)이 남고, 기록된 설정은 실제 사용한 channel 이름을 담아 같은
  snapshot으로 그대로 재계산됩니다.
- 한 timestamp·측정점의 세 상이 모두 다음을 만족할 때만 sample이 됩니다. 아니면 첫 사유 하나로 제외하고
  사유별로 셉니다.

| 순서 | 제외 사유 | 조건 |
| --- | --- | --- |
| 1 | `incomplete-phases` | 세 상 중 일부 channel이 없음 |
| 2 | `unconfirmed-semantics` | semantic binding이 `phase voltage`/V 또는 `phase current`/A, scope `phase R/S/T`가 아님 |
| 3 | `conflicting-value` | 같은 timestamp에 서로 다른 값 |
| 4 | `non-good-source-quality` | protocol source quality가 Good이 아님(OPC UA) |
| 5 | `null-value` | 값이 null |
| 6 | `low-signal` | 세 상 평균이 전압 50 V 또는 전류 1 A 미만(정지·미부하) |

Semantics 조건 때문에 semantics-v2 예외 member, 이전 metadata(v1/v2) 적재, semantic binding이 없는 source의
관측은 자동으로 제외됩니다. 모든 제외가 source data quality를 뜻하지는 않습니다.
`null-value`, `conflicting-value`, `non-good-source-quality`만 `AnalysisRun.data_quality` warning으로
올리고, `unconfirmed-semantics`, `incomplete-phases`, `low-signal`은 capability input eligibility/exclusion
근거로만 남깁니다.

## Evidence

`PhaseUnbalanceEvidence`는 결과를 다시 계산하고 해석하는 데 필요한 것을 모두 담습니다.

- input reference: history snapshot ID, asset, 구간, channel 목록
- capability ID, algorithm version(`phase-unbalance-max-deviation-v2`), 설정값(channel, 신호 기준, bucket 수)
- 실제 사용한 semantic binding version 목록
- 전압·전류 각각의 평가 sample 수, 제외 사유별 수, median·p95·max와 max 시각, 시간 bucket별 sample 수·
  median·max. p95는 관측 범위 안에 머무는 inclusive empirical quantile로 계산합니다.
- 해석 경계 문구

`AnalysisRun`은 실행 시각, 관측 구간과 data-quality issue를 담습니다. 결과는
`JsonPhaseUnbalanceRepository`에 run 단위로 append되며 같은 run의 다른 내용 재기록은 거부합니다.

## 재현성

기록된 snapshot ID로 다시 실행하면 이후 같은 구간에 history가 추가되어도 같은 결과가 나옵니다
(`tests/integration/test_phase_unbalance_history.py`). 시각은 UTC로 정규화해 실행 환경의 timezone과 무관합니다.

## Finalized window 입력 (live)

[ADR-0008](../adr/0008-analyze-finalized-window-accepted-events.md)에 따라 live 분석은 finalized
`DurableObservationWindow`가 **accept한 event 집합**을 입력으로 씁니다(`run_phase_unbalance_on_window`). Window
구간으로 history를 다시 조회하지 않으므로 finalize 뒤 도착한 늦은 값은 입력에 들어가지 않습니다.

- Window event는 history와 같은 `ChannelObservation` 형태로 투영됩니다(`window_channel_observations`). 같은
  channel·event time에 값이 다른 delivery(예: 새 epoch의 replay)는 평균하지 않고 `conflicting`입니다.
- 의미는 각 event가 수집 시점에 가진 semantic snapshot에서 읽고, 같은 semantic role 규칙으로 channel을 고릅니다.
- Evidence의 입력 참조는 `WindowInputReference`입니다: window ID·구간·watermark·finalize 시각, accept/reject 수,
  missing channel, accept된 event의 delivery identity·channel·event time·값·status·semantic snapshot의 SHA-256
  (`window-accepted-events-v1`). 값은 float로 정규화해 JSON window 저장 전후 digest가 같습니다.
- 저장된 window로 다시 실행하면 같은 결과가 나옵니다. 저장소는 history snapshot 입력과 window 입력을 `kind`로
  구분해 기록하며, 이전 결과(`kind` 없음)는 history snapshot으로 읽습니다.
- Live runner의 중복 방지 identity는 input digest와 별개로
  `window + capability + algorithm version + analysis policy digest`를 사용합니다. Policy digest는 role 선택 전
  요청 설정(channel override, 저신호 기준, bucket 수)을 고정하므로 설정을 바꾼 의도적 재분석을 허용합니다.

## 실제 데이터 확인 (2026-09-29)

보일러 `SourceData_347`(device 5764) 전체 1,008,001건을 metadata v4로 적재하고 2021-01-15–02-06 UTC를
분석했습니다.

| 항목 | 전압 | 전류 |
| --- | --- | --- |
| 평가 sample | 28,800 | 7,286 |
| 제외 | 없음 | low-signal 21,514 (정지 구간) |
| median / p95 / max | 0.315% / 0.446% / 0.641% | 4.96% / 8.58% / 100% |

전류 100%는 한 상 전류가 0에 가까운 구간(단상 부하 또는 상 결손)에서 나오는 실제 값입니다. 분석 시간은
0.91초입니다. 입력 조회의 raw join을 equality key만 쓰도록 바꾸기 전에는 12.9초였고, 결과는 같습니다.

## 한계와 다음 단계

- 기준값·alarm·finding을 자동으로 만들지 않습니다. 사람이 Investigation에서 결과를 골라 review finding을
  만들면 `human-review-request-v1 / REVIEW_REQUIRED`로 기록되고 Maintenance Review로 이어집니다.
- Operations Asset Detail에서 실행·조회합니다([apps/README](../../apps/README.md)).
- OPC UA source: 등록 시 channel별 semantic binding을 두면 DataChange의 semantic snapshot이 spool, DuckLake
  raw evidence(`raw.opcua_data_change.semantic_binding_json`)까지 보존되고 FILE과 같은 eligibility로 분석
  입력이 됩니다. Binding이 없는 channel과 semantic column 도입 이전에 적재된 행은 `unconfirmed-semantics`입니다.
- 남은 연결: finalized window가 생길 때마다 한 번씩 분석하고 재시작 뒤에도 중복 기록하지 않는 runner와
  loopback OPC UA end-to-end 검증은 다음 단계입니다.
- AI-Hub label과의 비교는 research path에서만 합니다.
