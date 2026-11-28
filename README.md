# Industrial PHM Framework

**산업 설비 모니터링 및 상태 분석**

[시작하기](#시작하기) · [분석 예시](#분석-예시) · [데이터 준비](data/README.md)

## 개요

실측 데이터 연결 · 설비 상태 관측 · 변화 구간 조사 · 추세 전망

![설비 모니터링 화면. 베어링 진동과 공기압축기 전압·전류 추이에서 변화 구간이 색으로 표시됩니다.](assets/showcase/monitoring.png)

*저장 기록 재생 · 변화 시작점에서 상세 분석으로 이동*

## 주요 기능

- **데이터 연결** · CSV 파일 등록, OPC UA 수집, 저장 기록 조회
- **설비 모니터링** · 전력·진동 추이, 저장 기록 재생, 변화 구간 조사
- **상세 분석** · 기간 비교, 신호 관계, 진동 파형·주파수, 모델 이상 점수
- **상태 전망** · 신호 추세와 설정한 기준까지의 예상 시간
- **AI 질문 및 검토** · 선택한 변화와 분석 결과에 대한 질문, 판단·메모 기록

## 시작하기

**macOS:** Docker Desktop·Docker Compose·make가 필요합니다. **Linux:** uv·Python 3.14·Node.js 22.12+·npm·make가 필요합니다.

```bash
git clone https://github.com/so9093-K/industrial-phm-framework.git
cd industrial-phm-framework
make up
```

웹: http://127.0.0.1:2718/web/

시작 화면에서 **데이터 연결**로 이동하여 CSV를 등록하거나 OPC UA 소스를 연결합니다. 데이터를 준비한 뒤 관측·설비 분석·상태 전망으로 이동합니다.

```bash
make status
make logs
make down
```

macOS의 `make up`은 Linux 컨테이너를 사용하고, Linux의 기본 실행은 네이티브입니다. 데이터는 각각 Docker 볼륨 또는 `artifacts/operations` 작업공간에 저장합니다.

## 분석 예시

### 베어링 1-1 · 진동 분석

회전축을 받쳐 주는 부품인 베어링의 수명시험 기록

- **수평 진동** · 가로 방향 흔들림의 크기, 초기 **0.716 g** → 마지막 측정 **7.27 g**
- **주파수** · 흔들림의 초당 반복 횟수(Hz). **800–1,594 Hz** 대역의 수평 진동 에너지 비중 **17.5% → 63.5%**

![베어링 주파수 비교 화면. 초기와 변화 구간의 에너지 비중, 평균 스펙트럼과 측정별 주파수 지도.](assets/showcase/bearing-frequency.png)

[데이터 출처 · XJTU-SY 베어링 수명시험, Wang 외 (2020)](https://doi.org/10.1109/TR.2018.2882682)

### 공기압축기 1306 · 전압 비교

공정에 압축공기를 공급하는 설비의 운전 기록

- **비교 조건** · 운전 수준 차이의 영향을 줄이기 위해 전류가 약 **11 A**였던 때의 전압만 비교
- **R상 전압** · 세 전원선 중 한 상의 전압 중앙값, 초기 **222 V** → 변화 구간 **226 V**

![공기압축기 기간 비교 화면. 약 11 A로 운전할 때 초기와 변화 구간의 R상 전압 분포.](assets/showcase/compressor-load.png)

[데이터 출처 · AI-Hub 설비 에너지 패턴 및 고장 분석 센서](https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=239)

## 실제 공개 데이터로 분석

원본 데이터셋은 이 저장소에 재배포하지 않습니다. 각 제공자의 이용 조건에 따라 로컬에 준비하세요.

[데이터 안내](data/README.md)에 따라 `data/` 폴더에 준비한 기록은 웹의 **데이터 연결 › 공개 실측 데이터로 시작**에 나타나며, 하나를 골라 가져오면 같은 분석 화면에서 봅니다. `make up`은 이 폴더를 읽기 전용으로 연결합니다.

- **AI-Hub 239 설비 전력 기록:** 원천 JSON 하나가 설비 하나의 저장된 이력이 됩니다(공기압축기·보일러·압출기·펌프 등, 설비당 약 한 달). 원본 시각에 시간대가 없어 한국 표준시로 저장합니다.
- **XJTU-SY 베어링 진동 기록:** 모델 학습에 쓰지 않은 베어링의 실측 파형을 넣고 Isolation Forest를 연결합니다. 처음 가져올 때 모델을 학습용 베어링으로 한 번 준비합니다.

개발용으로 저장 기록을 Operations에 흘려 보내는 명령은 `industrial-phm demo xjtu`와 `industrial-phm demo aihub-boiler`입니다. 옵션은 `--help`로 확인합니다.

IMS 및 MIMII DUE 등 공개 데이터는 별도의 연구용 어댑터·결과와 함께 유지합니다.

## 기술 구성 및 제약

Python 3.14·DuckDB/DuckLake·SQLite·scikit-learn·Prophet·asyncua·Svelte/TypeScript 기반입니다. AI 해설에는 OpenAI 호환 모델 서버가 필요하며 나머지 분석은 AI 서버 없이 가능합니다.

이상 점수는 모델 기준에 따른 변화 지표입니다. 화면의 잔여수명(RUL)은 **사용자가 지정한 신호 종료 기준까지 걸리는 조건부 예상 시간**입니다.

현재는 **로컬 단일 사용자**를 대상으로 하며 원격 인증·TLS·다중 사용자 운영을 지원하지 않습니다. 현장 고장 진단·자동 정비 지시·장비 제어 기능으로 사용하지 마세요.

![시스템 아키텍처](assets/system-architecture.png)

## 문서

- [데이터 준비 및 출처](data/README.md)
- [아키텍처](docs/architecture/overview.md)
- [연구 자료 및 결과](docs/research/README.md)
- [기여 및 개발](CONTRIBUTING.md)

프로젝트 코드는 [Apache License 2.0](LICENSE)을 따릅니다. 외부 데이터셋·모델의 라이선스는 별도로 확인해야 합니다.
