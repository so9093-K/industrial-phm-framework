# PHM Industry Direction and Research Context (2025–2026)

상태: product/research direction reference  
범위: 공개 연구·표준·산업 사례를 현재 `industrial-phm-framework`의 roadmap 판단에 연결하는 배경 문서

이 문서는 특정 model family를 채택하기 위한 benchmark 문서가 아닙니다. 최근 PHM/Predictive Maintenance의
연구·산업 흐름을 정리하고, 현재 project가 무엇을 우선하고 무엇을 아직 우선하지 않는지 설명합니다.

## 1. Accuracy-only에서 trustworthy prognostics로

2025년 *Mechanical Systems and Signal Processing*의 data-driven prognostics review는 RUL prediction을 평가할 때
point accuracy뿐 아니라 다음 네 특성을 함께 봐야 한다고 정리합니다.

- uncertainty
- robustness
- interpretability
- feasibility

이는 현재 project의 evidence-first 방향과 직접 연결됩니다.

현재 적용:

- target/split/evaluation semantics를 model보다 먼저 고정
- point metric과 capability boundary를 versioned evidence에 함께 기록
- uncertainty calibration 근거가 없으면 interval을 만들지 않음
- public retrospective benchmark를 field validation으로 표현하지 않음
- presentation/GenAI가 numerical evidence의 의미를 넓히지 않음

Reference:

- Salinas-Camus, Goebel, Eleftheroglou, “A comprehensive review and evaluation framework for
  data-driven prognostics: Uncertainty, robustness, interpretability, and feasibility,”
  *Mechanical Systems and Signal Processing*, 237, 113015, 2025.
  https://doi.org/10.1016/j.ymssp.2025.113015

## 2. Domain shift와 generalization

실제 rotating machinery deployment에서는 training과 deployment의 operating condition, asset, site 또는 sensor
distribution이 달라지는 문제가 핵심입니다.

2025년 *Advanced Engineering Informatics*의 rotating-machinery domain-generalization survey는 distribution shift가
real-world fault diagnosis의 주요 장애물이며, target-domain data를 미리 사용할 수 없는 상황에서 domain
generalization이 중요한 연구 축이라고 설명합니다.

현재 project에서의 대응은 새 DG model을 바로 추가하는 것이 아니라 먼저 **shift를 evidence로 드러내는 것**입니다.

- XJTU-SY: primary vibration development / prognostics evidence
- IMS: 다른 bearing source에서 fixed cross-test portability evidence
- MIMII DUE: acoustic development/external domain-shift evidence
- source/dataset-specific assumption을 Domain Adapter와 protocol boundary에 유지

향후 domain adaptation/generalization method는 private/field source에서 실제 shift pattern과 failure mode가 확인된
뒤 baseline 대비 필요성이 입증될 때 추가하는 것이 현재 방향입니다.

References:

- Xiao et al., “Domain generalization for rotating machinery fault diagnosis: A survey,”
  *Advanced Engineering Informatics*, 64, 103063, 2025.
  https://doi.org/10.1016/j.aei.2024.103063
- Shang et al., “Domain generalization for rotating machinery real-time remaining useful life prediction
  via multi-domain orthogonal degradation feature exploration,”
  *Mechanical Systems and Signal Processing*, 223, 111924, 2025.
  https://doi.org/10.1016/j.ymssp.2024.111924

## 3. Human-in-the-loop explainability

Predictive maintenance에서 설명은 feature attribution 그림 하나로 끝나지 않습니다.
정비 담당자가 어떤 evidence와 limitation을 보고 판단할 수 있는지, 그리고 AI 결과를 실제 decision process에서
어떻게 검토하는지가 중요합니다.

2025년 Human-in-the-Loop XAI systematic review는 predictive maintenance AI의 adoption에서 transparency와 trust,
interactive human involvement를 중요한 문제로 다룹니다.

현재 project에서의 대응:

- Analysis Explorer가 결과 → supporting evidence → pipeline/provenance 순서로 drill-down 제공
- threshold/RUL/diagnosis 의미를 UI에서 명시적으로 분리
- unsupported capability를 숨기지 않고 표시
- deterministic report가 같은 read model을 사용
- 실제 maintenance action은 자동 실행하지 않음

Reference:

- Amaliah, Tjahjono, Palade, “Human-in-the-Loop XAI for Predictive Maintenance,”
  *Electronics*, 14(17), 3384, 2025.
  https://doi.org/10.3390/electronics14173384

## 4. LLM / GenAI는 PHM copilot 방향으로 이동 중

PHM Society 2025는 “1000 Days+ of ChatGPT: Adoption of LLMs in PHM” 패널과
“Boosting Prognostics and Health Management with LLM Assistants” tutorial을 운영했습니다.
최근 PHM 연구는 LLM을 PHM numerical model 자체보다 practitioner support, technical knowledge retrieval,
troubleshooting, maintenance recommendation workflow의 copilot으로 사용하는 방향을 적극적으로 탐색하고 있습니다.

2024년 PHM Society 논문에서도 LLM agent를 PHM alert 이후 maintenance recommendation workflow를 보조하는
in-the-loop copilot으로 제안합니다.

현재 project의 `GenAI after PHM` 원칙은 이 방향과 맞지만 더 보수적입니다.

현재 허용:

- validated structured evidence 설명
- evidence-scoped Q&A
- target/provenance/capability limitation 전달

현재 금지:

- raw sensor에서 독립적으로 PHM 수치 생성
- RUL 재계산/보정/외삽
- unsupported confidence/prediction interval 생성
- validated failure threshold 없이 alarm/failure state 생성
- field evidence 없이 maintenance deadline을 운영 사실처럼 제시

References:

- PHM Society 2025 Panel Sessions:
  https://phm2025.phmsociety.org/panel-sessions/
- PHM Society 2025 Tutorials:
  https://phm2025.phmsociety.org/tutorials/
- Lukens et al., “Large Language Model Agents as Prognostics and Health Management Copilots,”
  PHM Society Annual Conference 2024.
  https://doi.org/10.36001/phmconf.2024.v16i1.3906

## 5. Industrial foundation models는 watch area, 현재 우선순위는 아님

2025년 intelligent-manufacturing literature에서는 Industrial Foundation Models(IFMs)가 빠르게 독립 연구 영역으로
성장했습니다. Review literature는 industrial domain/task models, fine-tuning, prompt engineering, RAG와 제조
lifecycle application을 주요 축으로 다룹니다.

PHM Society 2025에도 LLM을 time-series pre-trained model로 활용하려는 연구가 나타났습니다. 다만 industrial
PHM의 데이터 scarcity, cross-domain validity, calibration과 deployment provenance 문제가 foundation model을
도입한다고 자동으로 해결되는 것은 아닙니다.

현재 project decision:

```text
public benchmark
  -> field/private source
  -> observed domain shift / diagnostic gap
  -> uncertainty and operational requirements
  -> only then evaluate SSL / foundation-model approaches
```

Foundation model을 architecture goal 자체로 두지 않습니다.

References:

- Zhao et al., “Industrial Foundation Models (IFMs) for intelligent manufacturing: A systematic review,”
  *Journal of Manufacturing Systems*, 82, 420–448, 2025.
  https://doi.org/10.1016/j.jmsy.2025.06.011
- Minami, Ji, Lee, “LLMs as Pre-trained Models for Time-Series Applications in PHM,”
  PHM Society Annual Conference 2025.
  https://doi.org/10.36001/phmconf.2025.v17i1.4376

## 6. Industrial examples: model보다 maintenance workflow integration

상용 predictive-maintenance 사례는 모델 자체보다 sensor/asset context와 maintenance workflow 연결을 강조합니다.

### Siemens

Siemens는 2025년 Industrial Copilot을 Senseye Predictive Maintenance와 확장하면서 repair, prevention,
prediction, optimization까지 maintenance cycle을 지원하는 방향을 공개했습니다.

이 사례가 project에 주는 시사점:

- GenAI는 isolated chatbot보다 maintenance context와 연결될 때 가치가 커짐
- predictive output과 repair/maintenance workflow는 별도의 responsibility boundary가 필요
- 현재 project에서 work-order action을 서둘러 만들지 않고 evidence layer를 먼저 닫는 결정이 타당함

Source:

- Siemens, “Siemens expands Industrial Copilot with New generative AI-powered Maintenance Offering,”
  24 March 2025.
  https://press.siemens.com/global/en/pressrelease/siemens-expands-industrial-copilot-new-generative-ai-powered-maintenance-offering

### IBM Maximo

IBM Maximo Condition Insight는 time-series, meter readings, alerts뿐 아니라 work orders와 FMEA 같은
maintenance context를 함께 해석해 asset condition, trend와 corrective action을 설명하는 방향을 제시합니다.

이 사례가 project에 주는 시사점:

- 실제 decision support에는 sensor model output만으로 부족함
- asset history, failure mode knowledge, maintenance event identity가 필요
- future GenAI/RAG는 이런 operational context가 준비된 이후에 확장해야 함

Source:

- IBM, “IBM introduces Maximo Condition Insight: Actionable Asset Performance Management with AI.”
  https://www.ibm.com/new/announcements/maximo-condition-insight

### Rolls-Royce

Rolls-Royce의 Blue Data Thread와 eMRO integration은 engine configuration과 maintenance data를 지속적으로
연결하고 predictive maintenance, digital-twin-based maintenance forecasting과 운영 schedule을 통합하는 사례입니다.

이 사례가 project에 주는 시사점:

- field PHM은 model prediction보다 asset configuration / maintenance history / system integration이 중요
- live inference를 시작할 때 experiment artifact와 다른 operational identity/provenance contract가 필요
- CMMS/EAM/MRO integration은 numerical PHM 검증 이후의 별도 product layer로 보는 것이 적절함

Sources:

- Rolls-Royce, “Investing in our digital services capability,” 2025.
  https://www.rolls-royce.com/media/our-stories/discover/2025/investing-in-our-digital-services-capability
- Rolls-Royce, “Digital Platforms.”
  https://www.rolls-royce.com/innovation/digital/digital-platforms.aspx

> 위 vendor 사례는 독립적인 comparative benchmark가 아니라 각 회사가 공개한 product/customer direction의
> 예시입니다. 이 문서는 수치 성능 우위를 주장하기 위해 사용하지 않습니다.

## 7. Relevant standards

최근 machine-system condition monitoring/prognostics의 공통 개념과 process를 다루는 ISO 표준도 2025년에
새 edition이 발행되었습니다.

### ISO 13381-1:2025

**Condition monitoring and diagnostics of machine systems — Prognostics — Part 1:
General guidelines and requirements**

Prognosis process의 개발·적용, 필요한 data/characteristics/process/behaviour와 공통 prognostics concepts에 대한
guidance와 requirements를 제공합니다.

https://www.iso.org/standard/88029.html

### ISO 13379-1:2025

**Condition monitoring and diagnostics of machine systems — Data interpretation and diagnostics techniques —
Part 1: General guidelines**

Condition monitoring/diagnostics의 common concepts, technical characteristics, system development와 diagnostic
approach selection guidance를 제공합니다.

https://www.iso.org/standard/88027.html

이 project는 현재 ISO conformity/certification을 주장하지 않습니다. 위 표준은 terminology와 responsibility
design을 검토할 때 참고하는 external reference입니다.

## 8. Project direction

최근 흐름과 현재 evidence gap을 함께 보면, project roadmap의 우선순위는 다음과 같습니다.

### Current

1. XJTU frozen RUL held-out numerical benchmark 실행
2. evidence lifecycle과 user-facing interpretation boundary 완결

### Near term

1. local/general input boundary
2. private/field source
3. domain shift와 source/data-quality evidence
4. fault semantics가 있는 diagnostics
5. uncertainty/calibration

### Operational phase

1. live inference identity/time/data-quality contract
2. asset history / maintenance event model
3. human approval boundary
4. CMMS/EAM/work-order integration
5. deployment monitoring / drift

### Research candidates after evidence exists

- domain adaptation / domain generalization
- self-supervised representation learning
- industrial/time-series foundation models
- physics/reliability-informed modeling
- maintenance knowledge retrieval
- constrained/causal agent assistance

핵심 원칙은 **novel model을 먼저 선택하지 않고, 실제 evidence gap이 확인된 뒤 method를 선택하는 것**입니다.
