# Research Notebooks

`notebooks/`는 실제 산업 데이터를 관찰하고 가설을 빠르게 검증하기 위한 **exploratory analysis** 공간입니다.
프로덕션 pipeline의 두 번째 구현 경로나 새로운 Source of Truth를 만들기 위한 디렉터리가 아닙니다. 프로젝트
공통 용어는 [`../docs/terminology.md`](../docs/terminology.md)를 따릅니다.

## 역할

Notebook에서 수행하기 적합한 작업:

- 원천 데이터 구조와 품질 확인
- exploratory data analysis (EDA)와 시각적 sanity check
- canonical contract 적합성 검토
- preprocessing / feature / model 아이디어의 작은 PoC
- characterization result와 model output의 일회성 탐색

반복 사용하거나 재현 가능한 실험에 필요한 계산 로직은 `src/industrial_phm/`로 이동합니다. Interactive analysis가
반복적으로 필요해지면 Jupyter, marimo 같은 도구는 이 로직과 generated artifacts를 소비하는 interface로 사용하고,
도구 내부에 parser·feature formula·model implementation을 별도로 만들지 않습니다.

장기간 유지할 split과 experiment parameter는 manifest/config, architecture 결정은 ADR에 기록합니다.

## 실행

먼저 lockfile 기준 프로젝트 환경을 준비합니다.

```bash
uv sync --locked
```

Jupyter 자체는 현재 product/runtime dependency로 고정하지 않습니다. 프로젝트 환경 위에 일회성 연구 도구로
실행합니다.

```bash
uv run --with jupyter jupyter lab
```

이 방식에서는 notebook이 현재 checkout의 `industrial_phm` package를 그대로 import할 수 있습니다. XJTU-SY
interactive analysis에 반복 사용하는 dependency는 아래 `research` group과 `uv.lock`에 고정하며, 다른 일회성
도구는 project dependency로 자동 승격하지 않습니다.

## XJTU-SY local source

XJTU-SY는 현재 manual provider입니다. Notebook이 원격 mirror에서 직접 다운로드하거나 multipart archive를
해제하지 않습니다. 원본 획득·압축 해제·준비된 Adapter source 검증 절차는
[`data/README.md`](../data/README.md)를 따릅니다.

원본 배포물 inventory는 `data inspect`, 압축 해제된 signal dataset의 구조와 Adapter 호환성은
`data validate`가 담당합니다.

```bash
uv run industrial-phm data inspect xjtu-sy --source data/raw/xjtu-sy

uv run industrial-phm data validate xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets
```

Notebook에서 개인 absolute path를 파일에 저장하지 않도록 `INDUSTRIAL_PHM_XJTU_SOURCE` 환경 변수를 사용할 수
있습니다. 실제 waveform EDA에서는 압축 해제된 Adapter source root를 지정합니다.

```bash
export INDUSTRIAL_PHM_XJTU_SOURCE="data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets"
uv run --with jupyter jupyter lab
```

## Feature characterization artifacts

`vibration-statistical-v1`의 반복 가능한 feature 계산과 기초 집계를 Notebook 셀에서 다시 구현하지 않습니다.
첫 numerical baseline의 development fold는 `fold-1`이며, characterization은 이 development scope에서 실행합니다.

```bash
uv run industrial-phm feature characterize xjtu-sy \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \
  --output-dir data/processed/xjtu-sy/vibration-statistical-v1-characterization \
  --fold-id fold-1 \
  --partition train
```

`fold-1`은 fold 간 결과 비교로 선택한 것이 아니라 development와 holdout test의 경계를 고정하기 위한 절차적
선택입니다. Experiment configuration finalization 전에는 다른 fold를 추가 development data로 열지 않습니다.
`--partition`은 `train` 또는 `validation`만 허용하며 test partition은 이 characterization workflow에서 의도적으로
열지 않습니다. 다른 fold는 `fold-1` holdout test 이후 cross-fold robustness analysis에서 사용합니다.

생성되는 CSV는 선택한 partition의 acquisition provenance와 feature 값을 보존하고, JSON summary는 condition/run
통계, Pearson·Spearman correlation, run-length imbalance, retrospective lifecycle thirds를 포함합니다. 이 artifact는
자동 feature selection 결과가 아니며 reference-data rule, normalization, sampling/weighting policy는 여전히
experiment decision입니다.

현재 artifact로 먼저 interactive feature analysis를 시작할 수 있습니다. 실제 사용 중 반복적으로 필요한
trajectory, condition/channel comparison, bearing overlay 또는 추가 통계가 확인되면 reusable analysis 또는
characterization code로 승격합니다. Characterization을 완성한 뒤에야 interactive analysis를 시작해야 한다고
가정하지 않습니다.

## Interactive feature analysis

`01_xjtu_feature_analysis.py`는 generated characterization artifacts를 소비하는 marimo 기반 research-tooling
interface입니다. 현재 `fold-1/train` development scope만 대상으로 하며 raw waveform, feature formula, model logic 또는
holdout-test data를 UI에서 다시 다루지 않습니다.

marimo와 Matplotlib은 production runtime과 분리된 `research` dependency group으로 실행합니다.

```bash
uv sync --locked --group research
uv run --locked --group research marimo edit notebooks/01_xjtu_feature_analysis.py
```

이 interface는 typed characterization loader를 통해 generated artifact만 읽습니다. Raw parsing, feature 계산,
feature selection, preprocessing과 model fitting은 notebook 책임이 아닙니다. 현재 도구는 Python 3.14 strict check와
실제 `fold-1/train` HTML execution을 반복 통과했고 source 형식이 일반 code review와 CI에 적합해 research group으로
채택했습니다. 이 선택은 XJTU interactive analysis의 tooling 결정이며 canonical Research UX나 architecture
contract가 아닙니다.

## 운영 규칙

1. Notebook은 exploratory analysis와 PoC용이며 production Source of Truth가 아닙니다.
2. dataset source/version/license는 packaged dataset manifest가 소유합니다.
3. Notebook 안에 별도 download/acquisition 구현을 만들지 않고 기존 CLI와 `industrial_phm.data`를 사용합니다.
4. raw dataset, credential, token, 개인 absolute path는 commit하지 않습니다.
5. 두 곳 이상에서 반복되는 parser/preprocessing/model 계산은 `src/industrial_phm/`로 승격할 후보로 봅니다.
6. 공식 split, threshold, metric, experiment configuration은 Notebook 셀 상태가 아니라 version-controlled
   contract로 남깁니다.
7. architecture/contract 변경 결론은 Notebook에만 남기지 않고 docs/ADR 또는 적절한 contract 문서로 이동합니다.
8. 대형 table, binary object, 중복 plot output은 commit하지 않습니다. 작은 핵심 결과만 연구 기록으로 남길 수
   있습니다.
9. production validator를 Notebook에서 다시 구현하지 않습니다.
10. 가능한 한 위에서 아래로 새 kernel에서 다시 실행해도 같은 의미의 결과가 나오는 형태를 유지합니다.

## 현재 Notebook

- `00_xjtu_source_inspection.ipynb`: 초기 XJTU-SY local source 조사와 contract 질문을 남긴 inspection notebook.
- `01_xjtu_feature_analysis.py`: generated `fold-1/train` characterization artifacts를 탐색하는 marimo interface.

초기 수동 구조 검사는 `data validate`로 승격했으므로 같은 directory/schema 검증을 새 Notebook에서 반복하지
않습니다. Interactive analysis는 split-aware characterization artifacts와 production API를 소비하고, 실제
사용에서 확인된 분석 요구만 reusable code로 승격하는 방향으로 진행합니다.
