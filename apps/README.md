# Applications

이 디렉터리는 repository-local interactive application의 **실행·개발 진입점**을 설명합니다.

현재 지원 capability와 제한은 [프로젝트 상태](../docs/status.md), 제품 정보 구조와 UX 의미는
[제품·UX 기준](../docs/product/overview.md), runtime/data ownership은
[architecture 문서](../docs/architecture/overview.md)를 authoritative source로 사용합니다.
이 문서는 화면별 현재 기능 목록을 중복해서 유지하지 않습니다.

## Operations — supervised Web

현재 운영자 제품은 패키지 내 Web 자산(`src/industrial_phm/apps/web_next/`에 빌드한 Svelte 번들)과
Python API로 `/web/`에서 실행합니다. `/web-next/`는 같은 화면으로 이동합니다.
소스 실행은 Node.js 22.12 이상·npm으로 화면을 빌드하며 설치된 wheel 실행은 Python만 필요합니다. 운영용 marimo 애플리케이션 및 `--ui marimo`는 제거했습니다.
연구용 marimo 화면은 `notebooks/`와 선택 설치 `research` group에서 별도로 관리합니다.

```bash
make up
make status
make logs
make down
```

macOS에서는 Docker Desktop의 Linux 컨테이너로 실행하며 호스트 Node·uv는 필요 없습니다.
작업공간은 `industrial-phm_workspace` Docker 볼륨에 보존됩니다. Linux에서도
`make container-up/status/logs/down`을 사용할 수 있습니다.
[컨테이너 실행·데이터 보관 안내](../docs/architecture/operations-container.md).

Linux 네이티브 실행의 기본 작업공간은 `artifacts/operations`이며 `WORKSPACE=<path>`로 변경합니다.
`make up`은 collection/analysis/Web를 하나의 Supervisor로 시작하므로,
이미 동일 작업공간에 수동으로 실행한 수집기·분석기와 병행하지 마세요.

아래 직접 Python 명령은 Linux 네이티브 실행용입니다.

```bash
uv sync --locked --extra operations
uv run --no-sync industrial-phm operations up artifacts/live
# 정지된 workspace의 수집/분석 재시작이 필요하지 않은 독립 UI/API 진단:
uv run --no-sync python -m industrial_phm.runtime.operations_web_preview \
  artifacts/live --port 8765
```

마지막 UI-only 명령은 **독립 Web preview**이며 Supervisor의 수집/분석 lifecycle을
소유하지 않습니다. 같은 workspace의 supervised Web가 작동 중이면 협조적 writer lease가
preview 쓰기를 차단합니다. 무인증 네트워크·다중 사용자 서비스가 아닙니다.

빈 작업공간의 첫 화면에서 `분석 체험하기` 또는 `CSV 파일로 시작`을 선택합니다.
체험에서는 합성 진동 기록을 두 모델로 실제 분석하고, 신호·분포·관계·주파수·검토를 순서대로 봅니다.
[체험의 데이터·학습·저장 범위](../docs/product/data-first-start.md#데이터-없는-첫-사용-베어링-분석-체험).
CSV 점검·등록·이력 저장과 FILE/OPC UA 소스 제어의 정확한 절차 및 동작 계약은
[Web 화면·컴포넌트 안내](../frontend/README.md)를 참고하세요.
저장 작업은 Supervisor가 소유하며, 상태 조회 실패는 저장 실패와 구별합니다.
현재 지원 범위·제한은 [프로젝트 상태](../docs/status.md)를 기준으로 합니다.

개별 OPC UA replay와 fault/recovery 실험은 [도구 안내](../tools/opcua/README.md)를
따르며, 연구 화면은 아래 Analysis Explorer 실행 지침을 따릅니다.

### Web 업무 화면 안내

현재 화면의 메뉴·탭·주소 계약과 데이터·분석 근거는
[Operations Web](../frontend/README.md)에서 유지하며, 사용 목적과 용어는
[제품 기준](../docs/product/overview.md) 및 [용어 기준](../docs/terminology.md)을 따릅니다.
운영 Web의 계산 결과는 서버 응답만 근거로 하고, URL은 사용자 선택을 보존합니다.
조건이 바뀌면 이전 계산 결과를 현재 근거로 표시하지 않습니다.

### 이상 탐지 모니터링 (XJTU-SY 기록 재생)

기록된 XJTU-SY 측정을 로컬 작업공간에 재생해 Isolation Forest·LSTM 오토인코더의 점수와 측정 근거를 확인합니다.
준비된 XJTU-SY 원본([데이터 안내](../data/README.md#xjtu-sy))이 있으면 한 명령으로 실행합니다.

```bash
uv run industrial-phm demo xjtu                       # 기본: artifacts/demo-xjtu, Bearing1_1, 포트 2718
uv run industrial-phm demo xjtu --bearing Bearing2_1  # 학습에 쓰지 않은 다른 베어링
uv run industrial-phm demo xjtu --until 100           # 측정 #100까지만: 진행 중인 설비로 상태 전망·RUL 보기
```

- 처음 실행할 때 두 모델을 fold-1 train 베어링으로 맞춰 작업공간 `models/`에 저장합니다(몇 분).
  다음 실행은 저장된 패키지를 다시 씁니다. 깨끗한 Git checkout이 아니면 `--code-revision`을 지정합니다.
- 재생 대상은 모델 학습에 쓰지 않은 베어링(`Bearing1_1/2_1/3_1`, `Bearing1_2/2_2/3_2`)만 받습니다.
- 측정을 넣은 뒤 Operations를 실행하므로, Web을 열면 두 모델의 점수가 채워지고 있습니다. 화면에는 "기록 재생 데이터"로 표시됩니다.
  `--until`로 멈춘 뒤 `operations phm replay-xjtu ... --start N+1`로 나머지를 이어서 넣을 수 있습니다.

기존 작업공간에 단계별로 연결할 때는 같은 명령을 나눠 실행합니다.

```bash
make up                                   # 첫 터미널: 수집·분석·Web Supervisor
# 다른 터미널
SRC=data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
uv run --no-sync industrial-phm operations phm package-xjtu artifacts/operations --source "$SRC"
uv run --no-sync industrial-phm operations phm package-xjtu-lstm artifacts/operations --source "$SRC"
uv run --no-sync industrial-phm operations phm bind artifacts/operations \
  --package <package ID> --source-id xjtu-sy-replay --asset-id Bearing1_1 --recorded-replay   # 모델마다
uv run --no-sync industrial-phm operations phm replay-xjtu artifacts/operations \
  --source "$SRC" --bearing Bearing1_1 --interval-seconds 1
```

- 분석 runner는 새 측정을 차례로 처리하고, 화면은 최신 수신·최신 분석 시각과 분석 대기 수를 함께 보여줍니다.
- 이상 점수의 기준은 학습 측정 점수의 99.5% 분위수이며 고장 확률이 아닙니다. 모델 학습 범위와 재현 기록은
  [운영 추론 수용 프로토콜](../docs/research/operational-inference-acceptance-protocol.md)에 있습니다.

## 연구 도구

저장된 연구 결과 탐색은 [notebooks의 Analysis Explorer](../notebooks/saved-analysis-explorer.md)에서 별도로 실행합니다. 운영 제품의 모델 연결·수신·설비 관측 경로와 분리합니다.
