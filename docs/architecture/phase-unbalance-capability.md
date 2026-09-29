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
- 남은 연결: finalized live window를 입력으로 쓰는 runner는 다음 단계입니다. Live 분석은 window 종료 후
  같은 시간 범위를 history에서 다시 조회하지 않고 window가 accept한 event 집합을 입력 근거로 사용해야 합니다.
- AI-Hub label과의 비교는 research path에서만 합니다.
