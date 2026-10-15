# Industrial PHM Framework

산업 설비의 **측정 데이터 탐색, 다변량 시계열 이상 탐지와 측정값 예측**을 바탕으로,
운영자가 관측 데이터와 분석 근거를 확인하고 정비 판단을 검토할 수 있도록 돕는
Python 기반 PHM(Prognostics and Health Management) 프로젝트입니다.

수집한 데이터의 시각·품질·출처를 보존하고, 분석 결과를 기록하며,
**모델의 추정과 사람의 판단을 구분**합니다. 연구 결과를 실제 설비 고장 진단이나
검증된 정비 권고로 자동 해석하지 않습니다.

## 주요 시나리오

| 데이터 | 현재 제공하는 흐름 | 제한 |
| --- | --- | --- |
| **XJTU-SY 베어링** | 획득 기록 순차 재생 → Isolation Forest 및 선택적 LSTM Autoencoder 이상 점수 → 구간 비교·주파수 성분·Web 근거 확인 | 기록 재생 기반 |
| **AI-Hub 239 공기압축기** | 기록된 3상 전기 신호 수집·이력 → 5분 window PCA/IForest 이상 점수 → 공통 시간축 다변량 Web 근거 | 추론 기능은 있으나 운영 성능 평가 **FAIL** |

기능별 실제 지원 조건과 검증 수준은 [현재 지원 상태](docs/status.md)에서 확인할 수 있습니다.
연구 데이터와 재현 가능한 평가 결과는 실제 현장 설비 검증과 구별합니다.

저장된 분석 결과에는 선택적으로 로컬 `local-main` 생성형 AI 설명을 연결하고 사람의
검토를 기록할 수 있습니다. AI 서버가 없어도 결과 조회와 직접 검토는 계속됩니다.

## 빠른 시작

**Linux 로컬 단일 사용자** 환경에서 `make`와 [uv](https://docs.astral.sh/uv/)가 필요합니다.
첫 실행 시 Python 3.14와 잠긴 의존성을 설치하므로 네트워크 연결이 필요합니다.

```bash
make up
```

서비스는 현재 터미널에서 실행됩니다. 다른 터미널에서 준비 상태를 확인한 뒤
[http://127.0.0.1:2718/web/](http://127.0.0.1:2718/web/)에 접속합니다.

```bash
make status
make logs
make down
```

실행 중인 터미널에서 Ctrl-C로 멈춰도 정상 종료로 기록됩니다. `make down`은 이미 멈춰 있으면 마지막 종료 상태만
알려주고, 이전 실행이 비정상 종료돼 수집·분석·Web 프로세스가 남아 있으면 그 작업공간의 프로세스만 골라 정리합니다.
`make up`도 시작 전에 같은 정리를 하고, Web 포트를 다른 프로그램이 쓰고 있으면 시작하지 않고 알려줍니다.

기본 작업공간은 `artifacts/operations`입니다. 별도 작업공간은
`make up WORKSPACE=/absolute/path`처럼 지정합니다.
원본 데이터 없이 흐름을 확인하려면 별도 합성 작업공간을 사용하는 `make demo`를 실행할 수 있습니다.

XJTU-SY 모델 준비·바인딩·재생 명령은 [Operations 사용법](apps/README.md#이상-탐지-모니터링-xjtu-sy-기록-재생),
데이터셋 준비와 출처는 [데이터 안내](data/README.md)를 참고하세요.
AI-Hub 데이터를 연결하는 방법도 [애플리케이션 안내](apps/README.md)에서 확인할 수 있습니다.

## 시스템 구조

![설비 관측에서 사람의 운영·정비 판단까지 이어지는 구조](assets/system-architecture.svg)

**설비 데이터 → 수집·이력 저장 → 신호 탐색·이상 탐지·미래 예측 → 근거 조회 → 운영자 검토**

분석 결과는 원본 관측과 모델·데이터 출처에 연결됩니다.
지원되지 않는 데이터나 검증되지 않은 수명 정보는 임의로 만들어내지 않습니다.

## 문서

- [애플리케이션 사용법](apps/README.md) — Operations Web, XJTU-SY 재생, 연구 분석 화면
- [데이터 준비](data/README.md) — 공개 데이터셋과 입력 준비
- [현재 지원 상태](docs/status.md) — 구현 범위와 명시적 제한
- [아키텍처](docs/architecture/overview.md) — 시스템 구성 요소와 책임
- [연구 및 평가](docs/research/README.md) — 프로토콜과 결과
- [개발 참여](CONTRIBUTING.md) — 개발 환경과 기여 방법

## 라이선스

[Apache License 2.0](LICENSE). 데이터셋은 각 제공자의 사용 조건을 따릅니다.
