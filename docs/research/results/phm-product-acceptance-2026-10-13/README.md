# PHM 제품 인수 결과 (2026-10-13)

두 검증 사례를 감독형 Operations 노드(`operations start`) 하나의 흐름으로 실행한 결과입니다.
기록 데이터 재생이며 현장 설비 수신이 아닙니다. 판정 기준은
[운영 추론 수용 프로토콜](../../operational-inference-acceptance-protocol.md)의 지연 한도를 따릅니다.
AI 설명은 실제 `local-main`(`http://127.0.0.1:9400/v1`), 브라우저는 Chromium 1440px ko-KR입니다.

## 두 번의 인수

인수는 두 번 실행했습니다. 1차 인수에서 제품 결함 3건을 찾아 고친 뒤, 고친 코드로 다시 실행했습니다.
**최종 판정은 최종 인수입니다.**

| | 제품 코드 | XJTU-SY | AI-Hub 239 | 증거 |
| --- | --- | --- | --- | --- |
| 1차 인수 | main `cb00dbf` (수정 전) | PASS 24/24 | PASS 13/13 | [initial-run/](initial-run/) |
| **최종 인수** | `bf6bf1b` = `cb00dbf` + #545 + #546 | **PASS 28/28** | **PASS 15/15** | [xjtu-evidence.json](xjtu-evidence.json) · [aihub-evidence.json](aihub-evidence.json) |

1차 AI-Hub의 PASS에는 한계가 있습니다. 당시 저장된 AI 설명에 "이 데이터는 정상 범위 내에 있음을
시사합니다"라는 상태 판정이 있었지만, 당시 점검은 숫자 근거만 검사해 통과했습니다. 최종 인수에는
다음 점검을 더했습니다.

- 설명에 상태 판정 표현이 있으면 화면에 경고가 표시되어야 함
- 설명 패널이 윈도우는 기록 시각으로, 획득은 순번으로 표시해야 함

최종 인수의 설명 3건(XJTU 이상 탐지·RUL, AI-Hub)에는 판정 표현과 근거 없는 숫자가 모두 없었습니다.

## 흐름

| 사례 | 흐름 |
| --- | --- |
| XJTU-SY Bearing1_1 (진동 이상 + RUL) | 패키지 생성 → 바인딩 4개(IForest·Ridge·LSTM-AE·LSTM-RUL) → 1초 간격 획득 공급 → 감독 중단 중 공급 → 재시작 → 공백 → 중복 → 비호환 입력·변조 패키지 → 화면 → AI 설명 → 검토 → 재시작 |
| AI-Hub 239 공기압축기 1338 (전기 이상) | 재생 원천 등록 → 보류 기간 PCA 패키지 → OPC UA 재생(원래 기록 시각, 20배속) → 감독 중단·재시작 → 화면 → AI 설명 → 검토 → 재시작 |

## 지연 (최종 인수, 프로토콜 한도 대비)

| 구간 | 한도 | XJTU-SY | AI-Hub |
| --- | --- | --- | --- |
| 획득 공급 → 결과 커밋 p95 | ≤ 2초 | IForest 0.810초 · Ridge 0.659초 · LSTM-AE 0.599초 · LSTM-RUL 0.680초 | — |
| 윈도우 확정 → 결과 커밋 p95 | ≤ 10초 | — | 1.738초 (47개) |
| 결과 커밋 → 화면 반영 p95 | ≤ 폴링 3초 + 2초 | 2.819초 (45개) | 2.664초 (46개) |

**화면 반영 지표의 뜻**: 화면은 3초마다 갱신되고 결과는 그보다 빨리 쌓일 수 있습니다. 그래서 각 커밋부터
**그 결과 또는 더 최신 결과**가 화면에 처음 보인 시각까지를 잽니다. 이는 화면의 최신성을 재는 지표이며,
모든 개별 결과가 화면에 한 번씩 그려졌다는 뜻이 아닙니다. 각 커밋 이후 화면이 그 결과 또는 더 최신
결과까지 갱신되지 못한 경우는 두 사례 모두 0건입니다(증거의 `not_caught_up`).

## 장애 주입 (최종 인수)

| 상황 | 결과 |
| --- | --- |
| 감독 중단 중 공급(XJTU 15개) | 재시작 후 15개 모두 처리, 바인딩별 결과 정확히 1개(68개) |
| 공백(XJTU 61번 누락) | LSTM 8개 버퍼를 다시 모음(준비 구간 1–7, 62–68). 그래프는 선을 끊어 표시 |
| 중복 공급(XJTU 1–10 재공급) | `delivered=0 already_present=10`, 결과 변화 없음 |
| 비호환 입력(다른 채널) | 화면에 "입력을 분석할 수 없습니다: channels differ from the package input: got ['x', 'y'], expected […]" |
| 변조된 패키지 | 화면에 "모델을 실행할 수 없습니다: model package payload digest mismatch", 결과 0개 |
| 수집 중단(AI-Hub 감독 중단 약 18초) | 중단 중 화면은 "PHM 분석 결과를 읽지 못했습니다"(마지막 결과를 현재처럼 보이지 않음). 공백은 기록 시각 01:52:57–01:59:03뿐이며 겹친 두 윈도우만 부분 윈도우, 빠진 윈도우 0 |
| 재시작 | 기존 결과·AI 설명·검토 기록 그대로. 결과 변경 0 |
| RUL 근거 없는 설비(AI-Hub) | RUL 화면이 "근거가 없는 설비에는 표시하지 않습니다"로 안내, 추정 없음 |

## 화면 (최종 인수)

| XJTU 이상 탐지 · 설명 · 검토 | XJTU RUL · 설명 · 검토 |
| --- | --- |
| ![XJTU 이상 탐지](xjtu-anomaly-reviewed.png) | ![XJTU RUL](xjtu-rul-reviewed.png) |

| AI-Hub 이상 탐지 · 설명 · 검토 | AI-Hub 재시작 후 |
| --- | --- |
| ![AI-Hub 이상 탐지](aihub-anomaly-reviewed.png) | ![AI-Hub 재시작 후](aihub-anomaly-after-restart.png) |

재시작 후 XJTU 화면: [이상 탐지](xjtu-anomaly-after-restart.png) · [RUL](xjtu-rul-after-restart.png)

## 1차 인수에서 찾은 결함과 수정

| 결함 | 수정 | 화면 |
| --- | --- | --- |
| 비호환 입력 거부가 들어온 채널만 보여주고 패키지 입력 규격·재학습 필요를 알리지 않음 | #545 (안내는 입력 규격 불일치 skip에만 표시) | [수정 후](fix-incompatible-input-guidance.png) |
| 설명 패널이 윈도우를 내부 정렬 키(`#1605241800000000`)로 표시 | #546 | [수정 전](fix-explanation-before.png) · [수정 후](fix-explanation-after.png) |
| local-main이 임계값 이하 점수를 "정상 범위"라고 판정(숫자 대조로는 잡히지 않음) | #546: 프롬프트 판정 금지 + 판정 표현 경고 | [수정 전](fix-explanation-before.png) · [수정 후](fix-explanation-after.png) |

수정 전 화면은 1차 인수의 실제 화면입니다. 수정 후 화면은 같은 작업공간에서 같은 설명 문장을 새 점검에
통과시킨 결과입니다.

## 한계와 관찰

- **수집 처리량**: 수집기는 값마다 스풀 커밋과 원격 측정 기록을 하며, 이번 환경에서 약 18값/초를
  처리했습니다. AI-Hub 실시간 입력(35값/분)에는 약 30배 여유가 있지만, 60배속 재생(35값/초)에서는
  클라이언트 대기열이 쌓였습니다. 정상 종료는 아직 꺼내지 않은 알림을 비우지 않으므로
  ([ADR-0010](../../../adr/0010-application-owned-opcua-session-recovery.md) 손실 경계) 60배속에서는
  중단 손실이 중단 시간보다 컸습니다. 그래서 인수는 20배속으로 실행했습니다(#548).
- **값이 바뀌지 않으면 윈도우가 닫히지 않음**: OPC UA는 값 변경 시에만 알리므로 설비가 멈춰 값이
  고정되면 마지막 윈도우는 다음 관측이 올 때까지 열려 있습니다(재구독 시 현재값으로 닫힘).
- **판정 표현 검사는 표현 목록 기반**입니다. 다른 표현의 판정은 놓칠 수 있어 설명 문장은 계속 사람 검토
  대상입니다.
- 결과의 정확도(이상 탐지 탐지율·RUL 오차)는 이 인수의 판정 대상이 아닙니다. 성능 판정은
  [AI-Hub 평가 v2](../aihub-239-electrical-anomaly-evaluation-v2.json)(FAIL)와 프로토콜 §2.2·§5를 따릅니다.

## 실행

```bash
uv run --locked --all-extras --all-groups --with playwright python -m tools.phm.acceptance_xjtu \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets --lstm-models artifacts/phm-lstm/models \
  --output artifacts/acceptance/xjtu
uv run --locked --all-extras --all-groups --with playwright python -m tools.phm.acceptance_aihub \
  --archive data/raw/aihub/239/archives/training/raw/3.공기압축기.zip --output artifacts/acceptance/aihub
```

## 이전 단계 화면

같은 화면 계약의 이전 단계 기록입니다(각 단계 PR 시점 코드).

- M3 AI-Hub 전기 이상 탐지(PCA 잔차 기여, 공통 시간축 원본 신호): [earlier-m3-electrical-anomaly.png](earlier-m3-electrical-anomaly.png)
- M4 LSTM 이상 탐지·RUL: [earlier-m4-lstm-anomaly.png](earlier-m4-lstm-anomaly.png) · [earlier-m4-lstm-rul.png](earlier-m4-lstm-rul.png)
