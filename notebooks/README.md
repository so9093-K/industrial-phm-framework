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

XJTU-SY는 현재 manual provider입니다. Notebook이 원격 mirror에서 직접 다운로드하지 않습니다. 공식 source에서
직접 획득한 뒤 먼저 CLI로 local source를 확인합니다. 프로젝트 내부 `data/raw/xjtu-sy`를 사용하는 방법과
공식 Google Drive mirror의 반자동 다운로드 절차는 [`data/README.md`](../data/README.md)를 참조합니다.

```bash
uv run industrial-phm data inspect xjtu-sy --source data/raw/xjtu-sy
```

Notebook에서는 개인 경로를 파일에 저장하지 않도록 `INDUSTRIAL_PHM_XJTU_SOURCE` 환경 변수를 사용할 수 있습니다.
설정하지 않으면 첫 inspection notebook은 `data/raw/xjtu-sy`를 기본 후보로 확인합니다.

```bash
export INDUSTRIAL_PHM_XJTU_SOURCE=/path/to/XJTU-SY
```

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

- `00_xjtu_source_inspection.ipynb`: XJTU-SY local source의 존재, inventory, 최상위 구조를 확인하고 다음 Adapter spike에서 검증할 질문을 기록합니다.

`01_eda`, `02_contract_spike` 같은 Notebook은 실제 XJTU-SY 파일 구조를 관찰한 뒤 필요한 내용이 구체화될 때 추가합니다.
빈 미래 Notebook을 미리 만들지 않습니다.
