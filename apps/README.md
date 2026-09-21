# Analysis Applications

`apps/`는 validated PHM analysis result를 실제 사용자 흐름으로 연결하는 presentation surface입니다.
Research notebook과 달리 새로운 parser, feature formula, model fitting 또는 evaluation을 구현하지 않습니다.
수치와 capability의 Source of Truth는 `src/industrial_phm/`와 version-controlled evidence artifact에 남습니다.

## PHM Analysis Explorer

`analysis_explorer.py`는 현재 XJTU LSTM retrospective evidence를 첫 concrete consumer로 사용합니다.

- Analysis Summary: 선택한 asset의 anomaly-evidence trajectory와 현재 capability
- Evidence: high-score observations와 feature residual evidence
- AI Explanation: bounded structured evidence 기반 생성형 AI 설명과 analysis-scoped Q&A
- Analysis Details: 기존 `ExperimentInspection` pipeline/provenance drill-down

현재 result에는 validated threshold가 없으므로 normal/fault state나 anomaly interval을 생성하지 않습니다.
RUL 역시 현재 artifact가 지원하지 않으며, 향후 RUL capability가 구현되면 같은 analysis surface에 추가합니다.

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

### Generative AI explanation

AI 설명은 optional runtime 기능입니다. API credential이나 model을 코드/설정 파일에 저장하지 않고 실행 환경에서
명시적으로 제공합니다.

```bash
export OPENAI_API_KEY="..."
export INDUSTRIAL_PHM_GENAI_MODEL="<enabled-model-id>"

uv run --locked --group research marimo edit apps/analysis_explorer.py
```

AI 탭에서 질문을 입력하고 **Generate AI explanation**을 눌렀을 때만 외부 API를 호출합니다. 초기 화면 로드,
asset 선택, graph/evidence 탐색과 CI HTML export는 API 요청을 만들지 않습니다.

전송 context는 raw waveform이나 전체 score trajectory가 아니라 선택 asset의 bounded structured evidence입니다.

- top recorded anomaly scores
- aggregate feature residual evidence
- score semantics
- available / unsupported capability
- Source / Model / Evaluation / Provenance facts

Responses API 요청은 `store=false`로 실행합니다. 생성형 AI 출력은 PHM numerical result가 아니며, unsupported
diagnosis, alarm/state, maintenance priority, health indicator 또는 RUL을 새 capability처럼 만들지 않습니다.

## 운영 원칙

1. 앱은 numerical evidence를 재계산하지 않습니다.
2. 앱을 위해 별도 result database나 duplicated model state를 만들지 않습니다.
3. capability가 없는 값을 UI convenience를 위해 추정하지 않습니다.
4. pipeline/provenance transparency는 사용자 결과의 drill-down으로 제공합니다.
5. 반복되는 presentation-independent 요구가 생기면 `industrial_phm.analysis`로 승격합니다.
