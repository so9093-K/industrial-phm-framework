# XJTU-SY Interactive Feature Analysis Spike

상태: research tooling spike / development-data only

이 spike의 목적은 새로운 PHM 계산 계층을 만드는 것이 아니라, 이미 생성된
`vibration-statistical-v1` characterization artifacts를 연구자가 반복적으로 탐색할 때 필요한 최소
interaction을 검증하는 것입니다.

## Scope

현재 scope는 experiment protocol의 `fold-1/train`으로 고정합니다. UI는 generated feature table과 summary만
읽으며 raw waveform parsing, feature extraction, feature selection, preprocessing 또는 model fitting을 수행하지
않습니다. Holdout-test partition은 interactive development analysis에 노출하지 않습니다.

제공하는 interaction은 다음으로 제한합니다.

- operating condition 선택
- bearing run 선택
- feature 선택
- acquisition index / retrospective lifecycle fraction 전환
- bearing-run별 feature trajectory 비교

Retrospective lifecycle fraction은 각 run의 알려진 최종 acquisition count를 사용하는 사후 분석 축이며 online
model input이 아닙니다.

## Artifact boundary

`industrial_phm.experiments.xjtu_characterization_artifacts`는 characterization CSV/JSON의 schema와 scope가 서로
일치하는지 확인하는 작은 read-only loader입니다. 별도의 analysis framework가 아니며 새로운 통계, ranking 또는
experiment decision을 만들지 않습니다.

Interactive tool 내부에서 artifact parsing contract를 다시 구현하지 않습니다. 반대로 trajectory filtering이나
시각화처럼 아직 한 consumer에서만 필요한 동작을 production abstraction으로 미리 승격하지 않습니다.

## Run

프로젝트 dependency에는 marimo와 Matplotlib을 아직 추가하지 않습니다. Spike는 현재 검증 버전을 일회성 dependency로
실행합니다.

```bash
uv sync --locked
uv run --locked \
  --with marimo==0.24.2 \
  --with matplotlib==3.11.2 \
  marimo edit notebooks/01_xjtu_feature_analysis.py
```

기본 artifact directory는
`data/processed/xjtu-sy/vibration-statistical-v1-characterization`이며 UI에서 변경할 수 있습니다. 현재 spike는
그 directory의 `fold-1/train` v1 artifacts를 기대합니다.

## Adoption criteria

marimo를 research dependency로 채택하기 전에 최소한 다음을 실제 사용으로 확인합니다.

- Python 3.14에서 정적 검사와 실행이 안정적인가
- 새 process에서 같은 artifacts로 동일한 analysis scope를 재현할 수 있는가
- selector 변경이 stale output을 남기지 않는가
- 현재 XJTU feature-table 규모에서 interaction latency가 연구 흐름을 방해하지 않는가
- raw parsing/feature formulas/model logic이 UI로 복제되지 않는가
- holdout-test data가 development UI에 노출되지 않는가
- Git diff와 review가 기존 `.ipynb`보다 반복 workflow 유지에 실질적으로 유리한가

이 기준이 충족되고 반복 사용이 확인되면 `research` dependency group 도입을 별도 결정합니다. 그렇지 않으면 spike를
제거하고 Jupyter 기반 exploratory analysis를 유지할 수 있습니다. UI 선택 자체는 architecture contract가 아닙니다.
