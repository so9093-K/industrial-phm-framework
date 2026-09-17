# Research Notebooks

`notebooks/`는 실제 산업 데이터를 관찰하고 가설을 빠르게 검증하기 위한 **Research UX** 공간입니다.
프로덕션 pipeline의 두 번째 구현 경로나 새로운 Source of Truth를 만들기 위한 디렉터리가 아닙니다.

## 역할

Notebook에서 수행하기 적합한 작업:

- 원천 데이터 구조와 품질 확인
- EDA와 시각적 sanity check
- canonical contract 적합성 검토
- preprocessing / feature / model 아이디어의 작은 PoC
- 모델 출력과 evidence 형태 탐색

반복 사용하거나 재현 가능한 실험에 필요한 로직은 `src/industrial_phm/`로 이동합니다. 장기간 유지할 split,
threshold, metric, architecture 결정은 각각 experiment/research 문서나 ADR에 기록합니다.

## 실행

먼저 lockfile 기준 프로젝트 환경을 준비합니다.

```bash
uv sync --locked
```

Jupyter 자체는 현재 product/runtime dependency로 고정하지 않습니다. 프로젝트 환경 위에 일회성 도구로 실행합니다.

```bash
uv run --with jupyter jupyter lab
```

이 방식에서는 notebook이 현재 checkout의 `industrial_phm` package를 그대로 import할 수 있습니다. 실제 XJTU-SY
EDA에서 NumPy, SciPy, Polars 등 반복 가능한 연구 dependency가 필요하다고 확인되면 별도 dependency group과
`uv.lock`에 함께 고정합니다.

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

## Feature characterization artifact

`vibration-statistical-v1`의 반복 가능한 feature 계산과 기초 집계를 Notebook 셀에서 다시 구현하지 않습니다.
Characterization은 반드시 version-controlled reference split의 development partition을 명시해 실행합니다.

```bash
uv run python scripts/xjtu_feature_characterization.py \
  --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \
  --output-dir data/processed/xjtu-sy/vibration-statistical-v1-characterization \
  --fold-id fold-1 \
  --partition train
```

`fold-1`은 명령 예시일 뿐 특정 fold가 더 우수하다는 의미가 아닙니다. 사용할 fold는 결과를 보기 전에 고정하고
기록합니다. `--partition`은 `train` 또는 `validation`만 허용하며 test partition은 이 characterization workflow에서
의도적으로 열지 않습니다.

생성되는 CSV는 선택한 partition의 acquisition provenance와 feature 값을 보존하고, JSON summary는
condition/run 통계, Pearson·Spearman correlation, run-length imbalance, retrospective lifecycle thirds를
포함합니다. 이 artifact는 자동 feature selection 결과가 아니며 normal reference, normalization,
sampling/weighting policy는 여전히 연구 결정입니다.

첫 development artifact를 확인한 뒤 필요한 visualization interaction이 분명해지면 얇은 Feature Observatory
Notebook을 추가합니다. Notebook은 이 artifact와 production API를 소비하며 raw waveform parser나 feature formula를
복제하지 않고, feature decision을 위해 test bearing을 열어보지 않습니다.

## 운영 규칙

1. Notebook은 탐색·EDA·PoC용이며 production Source of Truth가 아닙니다.
2. dataset source/version/license는 packaged dataset manifest가 소유합니다.
3. Notebook 안에 별도 download/acquisition 구현을 만들지 않고 기존 CLI와 `industrial_phm.data`를 사용합니다.
4. raw dataset, credential, token, 개인 absolute path는 commit하지 않습니다.
5. 두 곳 이상에서 반복되는 parser/preprocessing/model 로직은 `src/industrial_phm/`로 승격할 후보로 봅니다.
6. 공식 split, threshold, metric은 Notebook 셀 상태가 아니라 version-controlled research/experiment contract로 남깁니다.
7. architecture/contract 변경 결론은 Notebook에만 남기지 않고 docs/ADR로 이동합니다.
8. 대형 table, binary object, 중복 plot output은 commit하지 않습니다. 작은 핵심 결과만 연구 기록으로 남길 수 있습니다.
9. production validator를 Notebook에서 다시 구현하지 않습니다.
10. 가능한 한 위에서 아래로 새 kernel에서 다시 실행해도 같은 의미의 결과가 나오는 형태를 유지합니다.

## 현재 Notebook

- `00_xjtu_source_inspection.ipynb`: 초기 XJTU-SY local source 조사와 contract 질문을 남긴 inspection notebook.

초기 수동 구조 검사는 `data validate`로 승격했으므로 같은 directory/schema 검증을 새 Notebook에서 반복하지
않습니다. 다음 Notebook은 split-aware automated characterization artifact의 실제 결과를 확인한 뒤 필요한 비교
UX를 근거로 추가합니다.
