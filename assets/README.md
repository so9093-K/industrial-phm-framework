# 사용자 흐름과 아키텍처 시각 자료

실행 중인 제품을 Chromium으로 촬영했습니다. 그래프·숫자·AI 답변을 이미지에 합성하지 않았습니다.
사용 사례마다 입력·쓰기 조건을 구분하며, 시각·코드 버전·화면 해시는 각 `capture.json`에 기록합니다.
**설치 없는 체험과 CSV 등록**은 최신 화면을 실제 Chromium에서 재촬영했고,
설치 없는 체험은 정적 API 응답도 함께 갱신했습니다. 모델·변화 분석·OPC UA 캡처는
각각의 2026-10-21 촬영 조건과 코드 버전을 보존한 실행 사례이며, 최신 공통 진입
화면과 동일한 시점에 촬영했다고 주장하지 않습니다.
사람의 검토 판단은 촬영용 예시이며 실제 점검 지시나 정비 수행 기록이 아닙니다.

| 사용 사례 | 입력과 확인할 흐름 | 조건 |
| --- | --- | --- |
| [진동 모델 비교](#진동-모델-비교) | XJTU-SY → 두 모델 → 원본·변화·AI → 사람 판단·RUL | 실제 기록·학습 모델·AI 응답, 격리 작업공간 |
| [변화 분석](#변화-분석) | 진동 구간 선택 → 분포·특징 관계·주파수 비교 | 같은 실제 기록, 경과 시간·동일 축·계산 결과 |
| [CSV로 시작](#csv로-시작) | 파일·시간대·단위 등록 → 모델 없는 이탈 분석 → 전망·판단 | 합성 4개 신호, 운영 쓰기 |
| [실시간 수신](#실시간-수신) | OPC UA 연결 → 수신 현황 → 시간별 신호 | 별도 합성 3상 모터, 실제 로컬 OPC UA 통신 |
| [설치 없는 체험](#설치-없는-체험) | 관측 → 신호 → 이탈 → 비교 → 전망 → 검토 | 합성 기록의 실제 계산 결과, 서버 없는 읽기 전용 화면 |

## 구성도

[`system-architecture.png`](system-architecture.png)는 1672×941의 대표 구성도입니다.
[HTML 원본](source/system-architecture.html)을 [렌더러](../tools/assets/render_architecture.py)로 재생성합니다.
DuckLake의 시계열 측정 이력과 작업공간의 진동 파형·모델 결과·해설·검토 기록을 구분합니다.
운영자의 후속 업무는 판단·확인·검토 종료이며 실제 정비 실행·작업 지시 기능으로 표현하지 않습니다.

`model-training-evaluation.png`는 연구 경로의 학습·평가, `service-architecture.png`는 서비스 책임의
개념적 참조입니다. 배포 책임과 지원 조건은 [아키텍처](../docs/architecture/overview.md)와
[현재 지원 상태](../docs/status.md)가 기준입니다.

## 진동 모델 비교

학습에 쓰지 않은 XJTU-SY Bearing1_1의 #1–#100을 재생한 격리 작업공간입니다.
Isolation Forest와 LSTM 오토인코더는 fold-1 학습 베어링으로 맞춘 패키지를 사용했습니다.
ko-KR Chromium, 1440×1000이며 [촬영 조건](models/capture.json)에 실제 해설 생성 방식도 기록합니다.

| 파일 | 확인할 사용자 가치 |
| --- | --- |
| [관측 현황](models/01-attention.png) | 현재 계속되는 기준 초과 구간부터 확인 |
| [모델 비교](models/02-models.png) | 점수를 각 모델 기준 대비로 비교 |
| [원본 확인](models/03-measurement.png) | 측정 #100의 확인값·표본 수·파형과 초과 직전 #75 |
| [전후 변화](models/04-changes.png) | 같은 두 측정의 진동 특징·단위·변화율 |
| [AI 해설](models/05-explanation.png) | 동일한 측정에서 두 모델의 기준 판단이 어떻게 다른지 질문 |
| [검토 판단](models/06-review.png) | 언제부터·얼마나·AI·다른 모델과 예시 ‘추가 점검 필요’ 판단 |
| [상태 전망](models/07-outlook.png) | 수평 RMS(g)의 Prophet 전망과 관리 4 g·종료 6 g까지의 여유 |
| [GIF](models/walkthrough.gif) | 관측 → 모델 → 원본 → 변화 → 해설 → 판단 → 전망 |

원본 파형·학습 패키지는 저장소에 배포하지 않습니다. 측정 간격으로 경과 시간을 환산한 기록 재생이며,
원본에 없는 측정 시각을 만들지 않습니다. 기준은 촬영용 임의 입력으로 실제 고장·허용 진동 기준이 아닙니다.

## 변화 분석

위와 같은 Bearing1_1의 100회 측정입니다. 기록된 1분 간격으로 시작 후 경과 시간을 표시합니다.
기간 A는 0–74분(1–75번째), 기간 B는 75–99분(76–100번째)이며, A는 정상으로 검증된 구간이 아닙니다.
[촬영 조건](changes/capture.json)에 선택한 원본 범위·특징·간격을 남깁니다.

| 파일 | 확인할 사용자 가치 |
| --- | --- |
| [구간 선택](changes/01-periods.png) | 회차 대신 시작 후 몇 분으로 두 구간 선택 |
| [시간 추이](changes/02-time-trend.png) | 경과 시간에 따른 특징값과 A/B 구간 음영 |
| [두 기간 분포](changes/03-distribution.png) | 특징값 눈금·A/B 행·중앙값·가운데 50%·집계 |
| [특징 선택](changes/04-relation.png) | 수평·수직 RMS의 같은 측정끼리 관계 계산 |
| [산점도](changes/05-scatter.png) | 두 특징의 축 이름·값·같은 눈금과 상관 계수 |
| [주파수 비교](changes/06-spectrum.png) | Hz·세기 눈금·단위와 같은 축의 A/B 실선·점선 |
| [대역 변화](changes/07-frequency-change.png) | 다른 진동 채널의 주파수별 세기·B/A 변화 dB |
| [GIF](changes/walkthrough.gif) | 구간 선택 → 시간 추이 → 분포 → 특징 관계 → 주파수 |

주파수 분석은 각 구간에서 최대 8회의 원본 파형을 선택해 계산합니다. 각 점은 주파수 구간의 평균 세기입니다.
산점도의 가로축은 시간이 아닌 선택한 특징값입니다. 상관 관계·세기 변화는 고장 원인이나 결함 진단이 아닙니다.

## CSV로 시작

[합성 펌프 입력 생성기](../tools/assets/pump_csv.py)가 만든 3일·4,320행의 전류·모터 온도·진동·압력입니다.
시간대 없는 시각을 한국 표준시로 지정하고 이름·단위를 사람이 선언했습니다.
학습 모델을 연결하지 않아 기준 구간 이탈을 사용합니다. [촬영 조건·입력 해시](csv/capture.json).

| 파일 | 확인할 사용자 가치 |
| --- | --- |
| [파일 등록](csv/01-register.png) | 시각·시간대·열 선택·이름·단위·파일 요약 |
| [관측 현황](csv/02-attention.png) | 모델 없이도 변화가 큰 신호부터 안내 |
| [기준 구간 이탈](csv/03-departure.png) | 크게 달라진 시점과 정도·시간별 값 |
| [설비 요약](csv/04-summary.png) | 저장된 신호와 가능한 분석으로 이동 |
| [상태 전망](csv/05-outlook.png) | 진동(mm/s)의 실제 계산과 임의 기준 6·7까지의 여유 |
| [검토 기록](csv/06-review.png) | 예시 ‘계속 관찰’ 판단·이유·확인·종료와 재접속 후 유지 |
| [GIF](csv/walkthrough.gif) | 등록 → 이탈 확인 → 전망 → 사람 판단 |

신호의 변화는 생성한 추세이며 실제 손상이나 고장을 나타내지 않습니다. 이 사례에는 AI 해설을 넣지 않았습니다.

## 실시간 수신

제품의 ‘예시로 둘러보기’에서 시작한 로컬 OPC UA 서버와 별도 작업공간입니다.
합성 3상 모터의 실제 구독 수신·저장·조회 화면이며 현장 설비 연결로 제시하지 않습니다.
예시 화면은 읽기 전용이고 촬영 도구는 촬영 후 예시를 종료합니다. [촬영 조건](live/capture.json).

| 파일 | 확인할 사용자 가치 |
| --- | --- |
| [데이터 연결](live/01-connection.png) | OPC UA 연결과 수집 상태 |
| [관측 현황](live/02-monitor.png) | 최근 수신 시각과 설비 상태 |
| [측정 신호](live/03-signals.png) | 실제 들어온 전기 신호의 시간·출처·단위 |
| [GIF](live/walkthrough.gif) | 연결 → 수신 확인 → 신호 |

## 설치 없는 체험

현재 Svelte UI를 ko-KR Chromium, 1440×1100에서 촬영합니다.
PNG·GIF는 실제 화면, WebM은 브라우저 녹화이며 [캡처 이력·화면/영상 해시](showcase/capture.json)에
촬영 시각과 소스 커밋, 정적 API 스냅샷을 함께 기록합니다.
공통 '이상 징후' 선택 화면도 촬영하되, 준비된 상세 분석의 직접 링크는 유지합니다.

| 파일 | 확인할 사용자 가치 |
| --- | --- |
| [관측](showcase/01-observe.png) | 두 설비의 저장 기록과 다음 확인 대상 |
| [신호](showcase/02-signals.png) | 전류 변화·시각·출처·단위 |
| [분석 방법 선택](showcase/02a-choose-method.png) | 데이터 종류에 무관한 공통 이상 징후 질문과 방법 선택 |
| [기준 구간 이탈](showcase/03-anomaly.png) | 선택한 방법의 벗어난 구간·시점·정도 |
| [기간 비교](showcase/04-compare.png) | 앞뒤 기간의 분포·유효 측정·결측 |
| [전망](showcase/05-outlook.png) | 계산한 1시간 전망과 임의 기준 13 A·15 A |
| [검토](showcase/06-review.png) | 저장된 분석 근거와 예시 사람 검토 메모 |
| [GIF](showcase/walkthrough.gif) · [WebM](showcase/walkthrough.webm) | 여섯 단계의 실제 화면 흐름 |

외부 데이터·학습 모델·실제 AI 응답이 없는 합성 입력입니다. 쓰기는 비활성화되어 있습니다.
[체험 데이터·해석 범위·재생성 절차](../docs/product/product-showcase.md).

## 재촬영

Playwright Chromium과 잠금 파일의 연구용 Pillow가 필요합니다. 운영 데이터와 분리한 작업공간을 준비합니다.
모델 사례는 두 모델로 분석한 기록, CSV 사례는 빈 작업공간을 사용합니다.
AI 서버와 키는 제품의 정상 설정으로 제공하고 토큰·개인 경로를 촬영물에 넣지 않습니다.

```bash
uv sync --locked --extra operations --group research
uv pip install --python .venv/bin/python 'playwright==1.64.0'
uv run --no-sync playwright install chromium
make frontend
uv run --no-sync python -m tools.assets.render_architecture
uv run --no-sync python -m tools.assets.pump_csv /tmp/cooling-pump.csv
uv run --no-sync python -m tools.assets.capture_usecases models --base http://127.0.0.1:2742
uv run --no-sync python -m tools.assets.capture_usecases changes --base http://127.0.0.1:2742
uv run --no-sync python -m tools.assets.capture_usecases csv --base http://127.0.0.1:2741 --csv /tmp/cooling-pump.csv
uv run --no-sync python -m tools.assets.capture_usecases live --base http://127.0.0.1:2741
```

촬영 도구는 CSV 등록·검토 판단 기록과 예시 시작·종료를 실제로 실행합니다. 기존 운영 작업공간을 대상으로 실행하지 않습니다.
서버 없는 체험의 재생성은 위 체험 안내의 별도 절차를 사용합니다.
