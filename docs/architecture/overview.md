# Architecture Overview

이 문서는 `industrial-phm-framework`의 현재 reference architecture를 설명합니다.
특정 설비나 특정 데이터셋을 구조 자체에 고정하지 않고 책임과 데이터 흐름을 기준으로 유지합니다.

아키텍처 그림은 장식보다 다음 질문에 빠르게 답하는 것을 우선합니다.

1. 데이터셋별 차이는 어디에서 끝나는가?
2. 어떤 부분이 공통 PHM 기능으로 재사용되는가?
3. 모델 출력은 어떤 근거와 함께 평가되는가?
4. Dashboard와 GenAI는 무엇을 source of truth로 소비하는가?
5. 실제 정비 조치는 어디에서 사람이 승인하는가?

## 1. 시스템 아키텍처

![시스템 아키텍처](../../assets/system-architecture.svg)

원천 산업 설비 데이터는 Domain Adapter에서 공통 데이터 계약으로 변환됩니다. 이후 PHM 계층은
도메인별 파일 형식이나 컬럼 이름이 아니라 공통 계약을 기준으로 전처리·이상 탐지·건전성 평가·예후 분석을
구성합니다. 모델은 가능한 경우 수치 출력과 함께 모델별 explanation/evidence를 생성하며, 독립 evaluation은
동일 split과 기준으로 성능·불확실성·적용 범위를 검증합니다.

최종 서비스 경계는 구조화된 `PHMResult`입니다. Dashboard와 생성형 AI는 모델 구현을 직접 참조하지 않고
이 결과 계약을 소비합니다.

## 2. 모델 학습 및 평가

![모델 학습 및 평가](../../assets/model-training-evaluation.svg)

모델 학습과 평가는 분리합니다. 데이터 분할은 자산·Run 단위를 기본으로 하여 같은 자산의 시간 구간이
train/test에 섞이는 leakage를 피합니다. scaler, threshold, feature fitting처럼 데이터로부터 학습되는
전처리 상태 역시 train 범위 안에서만 결정합니다.

Isolation Forest와 LSTM Autoencoder는 reference implementation이며 core 자체를 정의하지 않습니다. 모델은
교체 가능해야 하고 동일 split과 동일 evaluator에서 비교합니다. anomaly와 prognostics metric은 dataset capability가
지원하는 경우에만 적용합니다. XAI도 하나의 공통 알고리즘을 강제하지 않고 모델 특성에 맞는 설명 근거를
`PHMResult`로 전달할 수 있게 설계합니다.

## 3. 서비스 아키텍처

![서비스 아키텍처](../../assets/service-architecture.svg)

학습된 모델은 전처리·threshold·provenance와 함께 artifact 경계를 이루고, 공통 inference pipeline을 통해
구조화된 `PHMResult`를 생성합니다. 결과에는 상태/점수뿐 아니라 가능한 경우 evidence, explanation,
uncertainty와 provenance를 포함합니다.

Dashboard와 생성형 AI는 서로를 거치지 않고 같은 결과 계약을 독립적으로 소비합니다. 생성형 AI는 상태 해석,
가능 원인 정리, 정비 권고 초안을 담당하지만 PHM 수치를 다시 계산하는 source of truth가 되지 않습니다.
실제 work order나 설비 제어 같은 실행 조치는 사람의 승인 경계를 통과합니다.

## 아키텍처 자산 Source of Truth

세 아키텍처 그림은 `assets/*.svg`가 canonical source입니다. PNG/WebP 복제본을 병행 관리하지 않으며,
CI에서 SVG 구조와 README/architecture 문서 참조를 검증합니다.

그림을 수정할 때는 정보량을 늘리는 것보다 핵심 경계와 흐름이 한눈에 보이는지를 우선합니다. 본문에 이미
설명할 수 있는 세부 구현은 그림에 반복하지 않고, 작은 글씨를 늘려 모든 내용을 한 장에 넣는 방식은 피합니다.
