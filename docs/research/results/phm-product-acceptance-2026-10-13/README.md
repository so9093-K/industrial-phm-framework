# PHM 기록 재생 및 Chromium 인수 (2026-10-13)

원본 기록 재생을 감독형 Operations 노드와 실제 `local-main`으로 확인한 결과입니다. 현장 설비 수신이나
모델 정확도 검증은 아닙니다.

## 설비·신호 화면과 추세 상세 (사용성 검토 중)

제품 코드 `b9ea855b90b0a98cb26aca40d7c5e346631e128a`의 화면입니다. 기본 화면에서 설비를 고르고
추세 상세로 이동한 뒤, 이전 기록 선택·재로딩·최신 기록 복귀·설비 목록 복귀까지 확인했습니다.
원본 기록과 기존 고정 모델 패키지를 사용했으며 현장 수신이나 모델 성능 검증이 아닙니다.

Bearing1_1의 기록 #122→#123에서 수평 진동 RMS는 4.339→7.268(67.5% 증가), LSTM 재구성 오차는
7.324→10.697(+3.373, 참고 기준 1.746)입니다. 각 값은 저장된 원본 통계와 모델 결과에서 읽었습니다.
신호 크기와 모델 오차는 별도 축으로 표시하며 선택 기록의 원본 파형을 바로 아래에 둡니다.
기록 공백과 거부 입력은 연결하지 않고, 기본 범위는 해당 모델의 선택 시점과 연속된 분석 기록입니다.
입력 특징·오차 분해, 검토·AI 설명, 패키지 정보는 보조 영역입니다.

사용자 확인에서는 앞선 화면이 ‘무엇을 봐야 할지 모르겠음’, ‘숫자는 보이지만 의미가 모호함’,
‘추세 상세가 여전히 복잡함’으로 평가됐습니다. 이 수정본의 **사용성 인수는 아직 미확정**입니다.
아래 자동 검증과 캡처를 사용성 합격이나 모델 성능 합격으로 해석하지 않습니다.

자동 기능 검사: Chromium·HTTP 통합 **42 passed / 0 skipped**, 원본 재생 **21/21 PASS**,
기본 화면 검사 **9/9**, 실제 클릭 경로 검사 **11/11**입니다. PHM 요약 HTTP p95는 29.095ms(37회)이며
기본 Monitor의 일반 갱신은 3초마다 요약 3개를 읽습니다. 선택 입력이 바뀌면 원본을, 입력·처리 상태가
바뀌면 최대 64개 저장 결과를 추가로 읽습니다. 이 갱신은 모델 재실행·이력 전체 읽기·AI 생성을 수행하지 않습니다.
[원본 재생 결과](asset-monitor/replay-evidence.json) · [재생 로그](asset-monitor/replay.log) ·
[브라우저 검사](asset-monitor/browser-tests.log)

[기본 화면 검사·측정값·이미지 해시](asset-monitor/observation-capture.json) ·
[실제 클릭 경로와 기록·설비 유지 검사](asset-monitor/detail-capture.json)

| 현재 화면 | 1440px | 1024px | 390px |
| --- | --- | --- | --- |
| 설비·신호 모니터링 | [화면](asset-monitor/observation-1440.png) | [화면](asset-monitor/observation-1024.png) | [화면](asset-monitor/observation-390.png) |
| 재구성 오차·선택 기록의 파형 | [화면](asset-monitor/detail-observation-1440.png) | [화면](asset-monitor/detail-observation-1024.png) | [화면](asset-monitor/detail-observation-390.png) |
| 공기압축기·동일 단위의 R/S/T | [화면](asset-monitor/detail-electrical-1440.png) | [화면](asset-monitor/detail-electrical-1024.png) | [화면](asset-monitor/detail-electrical-390.png) |

개편 전 기본·상세 화면 이미지는 아래 고정된 Git 링크로 이동했습니다. 원래 실행 JSON과 로그는
변경하지 않았습니다. 현재 캡처와 과거 기능 검사 기록을 구분합니다.

## 이전 Monitor의 지속 갱신 기능 인수

기본 `#monitor`를 먼저 열고 같은 감독형 노드에 XJTU-SY 원본 획득과 AI-Hub 공기압축기 원본 OPC UA 재생을
공급했습니다. 제품 코드는 `fd223ec`로 고정했으며 모델 패키지·가중치는 기존 인수의 고정 패키지를 재사용했습니다.
재학습이나 성능 판정은 수행하지 않았습니다.

- 두 설비·모델 5개의 새 입력과 분석 결과가 수동 새로고침 없이 반영됐습니다. 실제 재생 여정 **15/15 PASS**.
- 같은 노드의 검토 요청→확인→종료가 기본 Monitor에 자동 반영되고 재시작 후 종료 이력이 유지됐습니다.
  검토 여정 **4/4 PASS**, 모델 결과 변경 0. [검토 요청](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/monitor/review-requested-1440.png) ·
  [재시작 후 종료](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/monitor/review-persisted-1440.png). 브라우저/HTTP 통합 **39 passed / 0 skipped**,
  단위·계약 **1,164 passed**, Ruff·format·mypy·lockfile·wheel 빌드 통과.
- 실제 LSTM 준비, 분석기 일시 정지(SIGSTOP/CONT), 손상된 테스트 복사본 거부, 노드 중단·재시작 중 공급을
  기본 화면에서 확인했습니다. 원본 파일은 바꾸지 않았습니다. 이전 성공 결과와 최근 입력을 구별하며 중단 시
  이전 결과를 지우고 자동 복구했습니다. 이전 저장 결과 변경은 0건입니다.
- 실제 모델 5개 PHM 요약 HTTP 응답 p95는 35.499ms였습니다. 일반 조회는 3초 주기마다 HTTP 요청 3개입니다. 이력 전체 읽기·부하/불평형 재계산·AI 호출은 포함하지 않습니다.
- 링크는 정확한 모델·시점·원본 파형을 유지하고 재로딩 후에도 같은 입력을 엽니다. 1440·1024·390px에서
  문서 가로 넘침은 없었습니다. 부하·불평형 분석은 별도 수동 실행 영역으로 접혀 있습니다.
- PHM 요약의 응답 시간과 요청 기록은 아래 실행 JSON을 따릅니다. 합성 설비 50대·표시 모델 100개(전체 102개)의
  저장 결과 조회 10회 p95는 118.918ms, 응답 125,464 bytes였습니다. 실제 대규모 현장 성능 보증은 아닙니다.
  100개 초과 모델은 전체 수와 조회 범위를 표시합니다.

[실행 결과·로그](monitor/) · [다수 모델 조회 측정](monitor/scale.json)

| 기본 Monitor | 1440px | 1024px | 390px |
| --- | --- | --- | --- |
| 두 설비의 지속 관측 | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/monitor/monitor-1440.png) | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/monitor/monitor-1024.png) | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/monitor/monitor-390.png) |

[분석 대기](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/monitor/analysis-pending-1440.png) · [입력 거부와 이전 결과](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/monitor/input-refused-1440.png) ·
[노드 중단](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/monitor/node-outage-1440.png)

재현에는 이전 재생 인수에서 생성한 패키지 작업공간과 원본이 필요합니다. 새 출력 경로를 사용합니다.

```bash
uv run --locked --all-extras --all-groups --with playwright python -m tools.phm.acceptance_monitor \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \
  --archive data/raw/aihub/239/archives/training/raw/3.공기압축기.zip \
  --xjtu-workspace artifacts/acceptance/xjtu/ws --aihub-workspace artifacts/acceptance/aihub/ws \
  --output artifacts/acceptance/continuous-monitor
```

## 이상 탐지·RUL 상세 화면의 이전 인수

#549–#551이 반영된 제품 코드 `30beec1aa0aacd8c63c1f7e592392f05530388b3`로 다시 실행했습니다.
수치 계산·입력 특징·저장 스키마·Web API·3초 polling은 변경하지 않았습니다.

- 기존 Chromium 3개 파일과 390px/이전 RUL 결과 구분 검사를 포함해 **15 passed / 0 skipped**.
- XJTU-SY 원본 기록 재생 **28/28 PASS**, 저장 결과의 UX 검사 **65/65 PASS**.
- AI-Hub 239 원본 OPC UA 재생 **15/15 PASS**, UX 검사 **23/23 PASS**. R/S/T 세 상을
  전류(A)와 전압(V) 각각 한 축에서 비교하고, 축의 최소·최대값을 저장 특징과 대조했습니다.
- 1440×900, 1024×900, 390×844의 Chromium ko-KR 화면을 직접 캡처했습니다.
- 이상 점수·참고 기준, 기록 재생과 수신/분석 시각, RUL의 기록 종료점과 참고 MAE를 구분합니다.
- AI 설명은 기본으로 접혀 있고, 실제 Tab/Enter로 열 수 있습니다. 생성 요청 실패를 주입한 동안에도
  저장 점수를 조회하고 감독형 노드에서 검토 요청→확인→종료를 완료했습니다.
- 이 검사는 로컬 Chromium에 한정됩니다. 특정 스크린리더·다른 브라우저·현장 설비의 인증이 아닙니다.
  작은 화면의 SVG 축 글자는 축소되므로, 정밀 수치는 결과 카드와 선택한 입력 상세에서 확인합니다.

[실행 JSON](ux/)과 아래 고정 링크의 이미지는 당시 상세 화면의 기능 검사 기록입니다. 현재 화면은 위 설비·신호 화면과 추세 상세를 따릅니다. UX 개편 전 화면은 아래 고정된 Git 기록에서 확인합니다.
모델 성능 FAIL/미검증을 이 기능 인수 PASS로 대체하지 않습니다.

| 상세 화면 | 1440px | 1024px | 390px |
| --- | --- | --- | --- |
| XJTU LSTM 이상 | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/xjtu-lstm-lstm-autoencoder-v1-Bearing1_1-1440.png) | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/xjtu-lstm-lstm-autoencoder-v1-Bearing1_1-1024.png) | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/xjtu-lstm-lstm-autoencoder-v1-Bearing1_1-390.png) |
| XJTU LSTM RUL | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/xjtu-lstm-lstm-rul-v1-Bearing1_1-1440.png) | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/xjtu-lstm-lstm-rul-v1-Bearing1_1-1024.png) | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/xjtu-lstm-lstm-rul-v1-Bearing1_1-390.png) |

| AI-Hub 전기 이상 | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/aihub-aihub-1338-1440.png) | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/aihub-aihub-1338-1024.png) | [화면](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/aihub-aihub-1338-390.png) |

원본 입력 연결과 AI 실패 중 검토: [XJTU 파형](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/xjtu-selected-input-1440.png) ·
[AI 생성 실패](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/xjtu-ai-unavailable-review-1440.png) · [R/S/T와 원본 7채널](https://github.com/so9093-K/industrial-phm-framework/blob/585694dc0ecc3a17c2fb07f4b56c9713338f4f77/docs/research/results/phm-product-acceptance-2026-10-13/ux/aihub-selected-input-1440.png).
실측 p95는 [XJTU JSON](ux/xjtu-product.json)을 따릅니다. 공급→커밋은 모델별 0.643–1.005초,
커밋→화면 p95 3.025초입니다. 최대 화면 지연은 8.044초로, 모든 개별 지연이 5초 이하라는 뜻은 아닙니다.

AI-Hub 윈도우 확정→커밋 p95는 1.724초, 커밋→화면은 2.614초입니다. 전체 실행 명령·판정·이미지
해시는 [execution.json](ux/execution.json)과 [로그](ux/logs/)에서 확인합니다.

UX 재현은 아래 원본 재생 명령을 실행한 뒤 다음 명령으로 같은 감독형 작업공간을 다시 엽니다.

```bash
uv run --locked --all-extras --all-groups --with playwright python -m tools.phm.acceptance_ux \
  --workspace artifacts/acceptance/xjtu/ws --scenario xjtu --output artifacts/acceptance/xjtu/captures
uv run --locked --all-extras --all-groups --with playwright python -m tools.phm.acceptance_ux \
  --workspace artifacts/acceptance/aihub/ws --scenario aihub --output artifacts/acceptance/aihub/captures
```

## 이전 인수 기록

현재 기본·상세 화면은 위 `asset-monitor/`에 모았습니다. 이전 상세 화면의 JSON·로그는 `ux/`, 이미지는 고정된 Git 링크에 보존했습니다. 개편 전 캡처와 결함 수정 비교는
[이전 보고서](https://github.com/so9093-K/industrial-phm-framework/blob/30beec1aa0aacd8c63c1f7e592392f05530388b3/docs/research/results/phm-product-acceptance-2026-10-13/README.md)에 보존되어 있습니다.
이전 캡처를 현재 Web 인수처럼 보여주지 않으며, Git에서 같은 revision으로 다시 볼 수 있습니다.

원래 생성된 실행 JSON은 바꾸지 않았습니다.

| 시점 | 코드 | XJTU / AI-Hub | 원래 기록 |
| --- | --- | --- | --- |
| 1차 인수 | `cb00dbf` | 24/24 · 13/13 | [XJTU](initial-run/xjtu-evidence.json) · [AI-Hub](initial-run/aihub-evidence.json) |
| 입력 안내·AI 판정 경고 수정 후 | `bf6bf1b` | 28/28 · 15/15 | [XJTU](xjtu-evidence.json) · [AI-Hub](aihub-evidence.json) |
| UX 개편 후 | `30beec1` | 28/28 · 15/15 | [XJTU](ux/xjtu-product.json) · [AI-Hub](ux/aihub-product.json) |

1차 인수는 AI 설명의 숫자만 검사해 "정상 범위"라는 판정 표현을 놓쳤습니다. 이후 프롬프트의 판정 금지와
표현 경고를 더하고 다시 인수했습니다. 표현 검사는 목록 기반이어서 모든 판정 문장을 검출한다고 주장하지
않으며, AI 설명은 계속 사람 검토 대상입니다.

## 재생 인수 재현

원본과 기존 LSTM 패키지를 준비한 뒤 다음 명령을 실행합니다. 각 명령은 지정한 출력 디렉터리를 초기화하므로
보존할 결과와 다른 경로를 사용합니다. 원본 재생 인수 이후 위 UX 캡처 명령으로 같은 작업공간을 엽니다.

```bash
uv run --locked --all-extras --all-groups --with playwright python -m tools.phm.acceptance_xjtu \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets --lstm-models artifacts/phm-lstm/models \
  --output artifacts/acceptance/xjtu
uv run --locked --all-extras --all-groups --with playwright python -m tools.phm.acceptance_aihub \
  --archive data/raw/aihub/239/archives/training/raw/3.공기압축기.zip --output artifacts/acceptance/aihub
```

인수 지연은 [운영 추론 수용 프로토콜](../../operational-inference-acceptance-protocol.md)을 따릅니다.
화면 지연은 각 커밋 뒤 그 결과 또는 더 최신 결과가 보일 때까지의 시간입니다. 모든 개별 결과가 폴링 사이에
한 번씩 그려졌다는 뜻은 아닙니다. 두 사례 모두 `not_caught_up=0`입니다.

AI-Hub는 20배속 재생입니다. 수집 처리량을 초과하는 빠른 재생과 종료 전 알림 대기열 손실은
[ADR-0010](../../../adr/0010-application-owned-opcua-session-recovery.md)의 경계를 따릅니다.
끝난 재생의 마지막 열린 윈도우는 다음 관측 또는 재구독까지 확정되지 않을 수 있습니다.
모델 정확도는 별도 [AI-Hub 평가 v2](../aihub-239-electrical-anomaly-evaluation-v2.json)(FAIL)와 연구 프로토콜로
판정하며, 기능·화면 인수로 성능 합격을 주장하지 않습니다.
