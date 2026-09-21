# Analysis Applications

`apps/`는 validated PHM analysis result를 실제 사용자 흐름으로 연결하는 presentation surface입니다.
Research notebook과 달리 새로운 parser, feature formula, model fitting 또는 evaluation을 구현하지 않습니다.
수치와 capability의 Source of Truth는 `src/industrial_phm/`와 version-controlled evidence artifact에 남습니다.

## PHM Analysis Explorer

`analysis_explorer.py`는 현재 XJTU LSTM retrospective evidence를 첫 concrete consumer로 사용합니다.

- Analysis Summary: 선택한 asset의 anomaly-evidence trajectory, descriptive review threshold와 score-exceedance interval
- Evidence: high-score observations와 feature residual evidence
- Analysis Details: 기존 `ExperimentInspection` pipeline/provenance drill-down

현재 result에는 validated State Detection threshold가 없습니다. 대신 Analysis Explorer는 earliest-third recorded
scored windows의 95th percentile을 **descriptive review threshold**로 계산해 score-exceedance interval을
시각적으로 표시합니다. 이 구간은 retrospective review를 위한 것이며 normal/fault state, alarm 또는 diagnosis가
아닙니다. RUL 역시 현재 artifact가 지원하지 않으며, 향후 RUL capability가 구현되면 같은 analysis surface에
추가합니다.

실행:

```bash
uv sync --locked --group research
uv run --locked --group research marimo edit apps/analysis_explorer.py
```

다른 compatible artifact를 지정할 때는 environment variable을 사용합니다.

```bash
INDUSTRIAL_PHM_ANALYSIS_ARTIFACT=path/to/result.json \
  uv run --locked --group research marimo edit apps/analysis_explorer.py
```

현재 loader가 지원하지 않는 schema는 화면에서 임의로 해석하지 않고 실패합니다.

## 운영 원칙

1. 앱은 numerical evidence를 재계산하지 않습니다.
2. 앱을 위해 별도 result database나 duplicated model state를 만들지 않습니다.
3. capability가 없는 값을 UI convenience를 위해 추정하지 않습니다.
4. pipeline/provenance transparency는 사용자 결과의 drill-down으로 제공합니다.
5. 반복되는 presentation-independent 요구가 생기면 `industrial_phm.analysis`로 승격합니다.
