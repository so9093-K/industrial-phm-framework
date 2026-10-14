# PHM Web 기능 인수

원본 기록 재생을 감독형 Operations 노드와 실제 `local-main`으로 확인한 결과입니다. 현장 설비 수신이나
모델 정확도 검증은 아닙니다.

아래 화면·AI 응답은 표시된 코드에 고정된 이전 검증 기록입니다. 현재 기능과 지원 경계는
[지원 현황](../../../status.md)의 PHM 신호 비교·AI 질문과 Operations lifecycle 항목을 따릅니다.

## 문제별 확인 흐름·기록 선택 (2026-10-14)

화면 코드 `f3873f9`의 저장된 Bearing1_1 기록을 작업공간 복사본에서 390·1024·1440px Chromium으로
확인했습니다. Monitor에는 입력 규격 오류·모델 실행 불가를 시험하는 별도 pump-x·pump-y도 포함됩니다.
캡처 서버는 읽기 전용이며 상단 행동은 측정값 비교를 열고 질문 입력을 숨깁니다. RUL의 MAE는 평가 평균으로
설명하고 평가 대상·적용 범위로 연결합니다. 원본 캡처는 측정 특징의 버튼을 사용했습니다.
감독형 화면의 문제별 이동·질문·사람 검토와 자동 갱신 중 키보드 포커스는
브라우저 테스트로 따로 검사합니다. [코드·화면 해시와 범위](operator-actions/capture.json).

- [문제별 확인 행동 1440px](operator-actions/monitor-1440.png)
- [선택 결과의 의미 → 측정 신호 → 비교 1440px](operator-actions/anomaly-1440.png)
- [특징별 값·변화·구간 흐름 카드 390px](operator-actions/comparison-390.png)
- [기록 기반 RUL의 단위·평가 평균 오차·시점 선택 1024px](operator-actions/rul-1024.png)
- [RUL의 선택 특징과 관련 원본 채널 390px](operator-actions/rul-original-390.png)

실제 고장 원인·모델 성능이나 사람의 사용성 합격을 판정하는 캡처가 아닙니다. 이 화면 확인에서 AI를 새로
호출하지 않았으며 이전 AI 응답 품질 판정은 아래 각 실행 범위에 한정됩니다.

## 이전 두 시점의 신호 비교·AI 질문 (2026-10-14)

제품 코드 `a5df027`에서 선택 분석과 같은 모델의 이전 시점을 비교합니다. 측정 특징·모델 값은 AI 없이
표시하며 원본 신호를 바로 열 수 있습니다. AI 질문은 검토 메모와 분리하고, 비교 시점·질문·응답을 복원합니다.
원본 파형은 파일 SHA-256을 검증해 통계를 전달하며, 다른 모델은 같은 설비·소스·측정점·원본 입력일 때만 연결합니다.
전체 기간 분석이나 여러 턴의 대화 기능을 구현한 것은 아닙니다.

- 단위·계약 **1,177 passed**. 이후 의미 검사 추가와 최종 코드의 관련 단위·HTTP·브라우저 검사는 **48 passed**,
  비교 선택·질문 복원은 3개 화면 폭에서 **3 passed**입니다. [검사 로그](signal-comparison/).
- 베어링·공기압축기의 실제 저장 결과를 분리된 작업공간 복사본에서 390·1024·1440px로 확인했습니다.
  페이지 오류·문서 가로 넘침은 없었고 원본 입력을 열었습니다. [캡처 범위·코드](signal-comparison/capture.json).
- 실제 `local-main`의 초기 응답은 변화량을 현재 점수로 쓰거나 음수와 감소를 겹쳐 표현했습니다.
  [초기 응답·경고](signal-comparison/real-ai-initial.json). 전체 비교 입력은 유지하고 숫자 반복을 줄인 최종
  응답 3건에서도 **2건에 원인·추세 단정 경고**가 나왔습니다. 해당 원문은 기본으로 접고 관측 비교는 유지합니다.
  일부 표현을 검출하는 장치이며 임의 문장의 의미나 점수 기여도를 모두 검증하는 것은 아닙니다. [전달 입력·원문·경고](signal-comparison/real-ai.json).
  **AI 답변 품질과 사용자 사용성은 합격으로 판정하지 않았습니다.**

[베어링 신호 비교 390px](signal-comparison/xjtu-anomaly-390.png) ·
[RUL 비교 1440px](signal-comparison/xjtu-rul-1440.png) ·
[공기압축기 비교·응답 경고](signal-comparison/aihub-anomaly-1440.png).

아래는 이전 버전의 고정된 검증 기록입니다.

## 이전 운영자 화면·연결 흐름 (2026-10-14)

화면 코드 `5b302f5`의 실제 AI-Hub 저장 기록을 390·1024·1440px에서 확인했습니다.
등록된 연결을 먼저 보고 새 CSV 입력은 필요할 때 펼칩니다. 소스 카드는 수신·마지막 수신·측정 신호·다음 작업을
먼저 보여주고 설정·진단을 접습니다. 1회 수신·수집 요청·실제 연결 상태를 구분합니다.

모델 연결은 입력 대기→runner 처리→저장 결과로 이어집니다. 모델 후보의 늦은 응답은 다른 설비의 선택을 바꾸지
않으며, 전기 입력은 기존 단위·상 역할 해석을 재사용합니다. 1 MiB 초과 CSV도 저장된 그래프와 분석 지원 범위를
확인할 수 있습니다. AI는 값·단위·이전 변화의 의미를 2~3문장으로 설명하고 연구 평가 기록은 모델 상세에 둡니다.

- 화면·HTTP 전체 검사 **102 passed / 6 failed / 2 skipped** 후, 실패한 6개 항목을 모두 수정·재검사했습니다.
  기존 문구·접힌 설정 경로를 반영했고 시스템 진입의 초기 조회 경합도 수정했습니다.
  **전체 108개 기능 항목 통과**이며 단일 실행 108 PASS로 표기하지 않습니다. [원본 검사·재검사 로그](operator-ux/).
- 최종 CSV 등록·재로딩·대용량 안내 **3 passed**. 실제 Supervisor의 Web 모델 연결→자동 runner 결과도 검증했습니다.
- 원본 재생 **21/21 PASS**는 코드 `83636db`에서 실행했고, 이후 준비 개수 문구·CSV 접힘·시스템 진입 수정은 관련
  브라우저 재검사를 따릅니다. [실행 코드·기록](operator-ux/replay-evidence.json).
- 실제 `local-main`의 이상 점수·RUL 설명 각 1건은 수치·판정 표현 경고 없이 생성됐습니다.
  [선택 입력·응답](operator-ux/local-main.json). 모델 전반의 답변 품질 보증이 아닙니다.
- `app.js`를 1,770→366줄로 줄이고 소스·CSV/OPC UA 등록·분석 기록·시스템·격리 데모를 분리했습니다.
  연구 Explorer와 실행 안내는 `notebooks/`로 이동했습니다. 기능·기술 검증이며 **사용성 최종 인수는 별도**입니다.

[현재 연결 화면 1440px](operator-ux/connect-1440.png) · [1024px](operator-ux/connect-1024.png) ·
[390px](operator-ux/connect-390.png) · [모니터링](operator-ux/monitor-1440.png) · [이상 탐지](operator-ux/anomaly-1440.png).
[화면 코드·이미지 해시·범위](operator-ux/capture.json). #548 수집 용량과 #527 모델 성능은 독립 과제입니다.

아래는 각 이전 버전의 고정된 검증 기록입니다.

## 데이터 우선 모니터링·최초 CSV 진입

제품 코드 `5362a0e503005c5d6b89f7bc9d509d83696d099d`의 기능 검사입니다. 실제 AI-Hub 저장 이력이
모델 연결과 무관하게 기본으로 보이며, PHM 조회를 실패시켜도 측정값·그래프를 유지했습니다.
수집과 분석은 별도 문구, 원본 측정·프로젝트 수신은 별도 시각이며 한국어 표시의 기본 시간대는 KST입니다.

CSV는 미리보기→서버 점검→등록·수신 확인→Supervisor 이력 저장→동일 설비·출처·신호로 이동합니다.
같은 ID를 재사용할 때 파일 SHA-256·이름·측정 컬럼·시각·측정점·설정을 확인하고 다른 입력은 거부합니다.
브라우저 재로딩 후 같은 파일로 입력을 복원해 중복 등록 없이 저장을 확인했습니다. 작업 상태의 조회 실패와
중단은 저장 결과 미확정으로 구별합니다. 정상 종료는 현재 쓰기를 마치며 이후 새 쓰기는 받지 않습니다.
예시는 별도 작업공간에서만 열고 Web 쓰기를 차단합니다. 동봉된 합성 CSV는 실제 작업공간에 등록하지 않습니다.

- 화면·HTTP 전체 검사에서 98개가 통과했고, 접힌 관리 경로를 반영한 재검사 3개도 통과했습니다.
  총 **101개 기능 검사 통과, 기록 데이터 opt-in 2개 제외**입니다. 최초 실행의 기존 검사 로그와 재검사를 모두 보존합니다.
- 최종 데이터 진입·모델 독립 관측 **7 passed**, 원본 재생 **21/21 PASS**, 단위·계약 **1,164 passed**.
- 390·1024·1440px에서 실제 저장 신호를 캡처했고, PHM 조회 실패 중 측정 관찰을 확인했습니다.
  [이미지 해시·검사 범위](data-entry/capture.json), [원본 재생](data-entry/replay-evidence.json), [검사 로그](data-entry/).
- 기능·기술 검증이며 **사용자 사용성 인수와 현장 운영 준비를 완료했다고 선언하지 않습니다**.
  수집 용량(#548)과 모델 성능(#527, AI-Hub 평가 FAIL)은 독립 과제입니다.

| 현재 데이터 우선 화면 | 캡처 |
| --- | --- |
| 1440px 실제 AI-Hub 저장 이력 | [화면](data-entry/aihub-stored-default-1440.png) |
| 1024px | [화면](data-entry/aihub-stored-default-1024.png) |
| 390px | [화면](data-entry/aihub-stored-default-390.png) |
| PHM 조회 실패 중 측정 유지 | [화면](data-entry/aihub-model-read-failure-1440.png) |

아래는 이전 화면 구조의 기록입니다. 현재 기본 Monitor는 위 데이터 우선 화면을 따릅니다.

## 이전 설비·신호 화면과 추세 상세 (사용성 검토 중)

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
