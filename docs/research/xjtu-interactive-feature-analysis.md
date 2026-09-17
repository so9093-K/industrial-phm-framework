# XJTU-SY Interactive Feature Analysis Spike

이 문서는 generated XJTU-SY feature-characterization artifacts를 반복적으로 탐색하는 interactive analysis가
현재 연구 workflow에 실제로 필요한지, 그리고 marimo가 그 interface에 적합한지 검증하기 위한 작은 spike의
경계를 기록합니다. 프로젝트 공통 용어는 [`../terminology.md`](../terminology.md)를 따릅니다.

## 목적

현재 `fold-1/train` characterization은 feature table과 summary JSON을 재현 가능하게 생성하지만, 사용자가
feature·operating condition·bearing run을 바꿔가며 trajectory를 비교하려면 매번 ad-hoc plotting code가
필요합니다. 이 spike는 그 반복 interaction을 최소 UI로 옮겼을 때 실제 연구 효율과 재현성이 좋아지는지
확인합니다.

이 문서는 marimo를 canonical research interface로 채택하는 ADR이 아닙니다. Jupyter exploratory analysis도
계속 유지합니다.

## 입력과 책임 경계

Spike는 다음 generated development artifacts만 소비합니다.

- `vibration-statistical-v1-fold-1-train-features.csv`
- `xjtu-feature-characterization-summary-v1-fold-1-train.json`

Artifact parsing과 scope 검증은 `load_xjtu_feature_analysis()`가 담당합니다. marimo 파일은 다음 책임을 갖지
않습니다.

- raw XJTU waveform parsing
- feature extraction 또는 feature formula
- split assignment
- 새로운 characterization statistic 정의
- feature selection 결정
- experiment configuration
- model fitting/evaluation
- holdout test access

## 현재 interaction

`notebooks/01_xjtu_feature_analysis.py`에서 다음을 확인합니다.

- operating condition 선택
- bearing run 선택
- feature 선택
- acquisition index / retrospective lifecycle fraction 전환
- 선택 scope의 acquisition-level feature trajectory 비교

Channel은 현재 feature name에 포함되어 있지만 별도 analysis metadata contract가 없으므로, spike에서 feature-name
문자열을 파싱해 별도 channel selector를 만들지 않습니다. 실제 사용에서 channel 단위 탐색 요구가 반복되면
UI workaround가 아니라 feature/analysis metadata 경계에서 해결합니다.

## 해석 경계

Retrospective lifecycle fraction은 각 bearing run의 최종 acquisition count를 알고 난 뒤 계산합니다. 따라서
retrospective visualization에만 사용하며 online model input이나 fault-onset label로 해석하지 않습니다.

UI에서 선택한 상태 역시 experiment configuration이 아닙니다. 반복 관찰을 통해 feature/reference/preprocessing
후보를 만들 수는 있지만, downstream pipeline이 소비하는 결정은 별도 version-controlled configuration으로
정의해야 합니다.

## 검증 기준

Spike가 다음을 만족하는지 실제 `fold-1/train` artifacts로 확인합니다.

1. 새 kernel/process에서 generated artifacts만으로 동일한 view를 다시 만들 수 있다.
2. condition/bearing/feature 선택이 반응형으로 갱신되고 stale output을 남기지 않는다.
3. 3,246 acquisition 규모에서 trajectory interaction이 연구 사용에 충분히 빠르다.
4. holdout test artifact를 interactive development analysis로 열 수 없다.
5. marimo 파일을 제거해도 characterization/CLI/core pipeline은 영향을 받지 않는다.
6. raw parser, feature calculation 또는 experiment decision logic이 UI에 복제되지 않는다.
7. Git diff에서 interaction logic을 검토할 수 있다.
8. Python 3.14 환경에서 spike에 사용한 marimo/Matplotlib 조합이 실행된다.

## 후속 판단

실제 사용 후 아래 중 하나를 선택합니다.

- 반복 가치가 낮으면 spike를 experimental research file로만 유지하거나 제거한다.
- 반복 가치가 확인되면 research dependency group 및 marimo compatibility check 도입을 검토한다.
- Jupyter가 더 적합한 interaction은 Jupyter에 남긴다.
- 반복적으로 필요한 계산은 UI에 추가하지 않고 `src/industrial_phm/`의 reusable analysis/characterization code로
  승격한다.

UI framework 선택 자체보다 실제 analysis requirement와 계산 책임의 위치를 우선합니다.
