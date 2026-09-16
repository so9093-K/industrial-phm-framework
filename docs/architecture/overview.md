# Architecture Overview

이 문서는 `industrial-phm-framework`의 현재 reference architecture를 설명합니다.
특정 설비나 특정 데이터셋을 구조 자체에 고정하지 않고 책임과 데이터 흐름을 기준으로 유지합니다.

## 1. System Architecture

![System Architecture](../../assets/system-architecture.svg)

원천 산업 설비 데이터는 Domain Adapter에서 공통 데이터 계약으로 변환됩니다. 이후 PHM 계층은
도메인별 파일 형식이나 컬럼 이름이 아니라 공통 계약을 기준으로 전처리·이상 탐지·건전성 평가·예후 분석을
구성합니다. 모델 결과는 독립 evaluation을 거쳐 구조화된 PHM Result로 전달되며, 서비스와 생성형 AI는
이 결과 계약을 소비합니다.

## 2. Model Training and Evaluation

![Model Training and Evaluation](../../assets/model-training-evaluation.svg)

모델 학습과 평가는 분리합니다. 데이터 분할은 자산·Run 단위를 기본으로 하여 같은 자산의 시간 구간이
train/test에 섞이는 leakage를 피합니다. Isolation Forest와 LSTM Autoencoder는 reference implementation이며,
동일 split과 동일 evaluator에서 비교합니다. anomaly와 prognostics metric은 dataset capability가 지원하는 경우에만
적용합니다.

## 3. Service Architecture

![Service Architecture](../../assets/service-architecture.svg)

학습된 모델은 전처리·threshold·provenance와 함께 artifact 경계를 이루고, 공통 inference pipeline을 통해
구조화된 PHM Result를 생성합니다. Dashboard와 생성형 AI는 모델 구현을 직접 참조하지 않고 같은 결과 계약을
소비합니다. 생성형 AI는 상태 해석·가능 원인 정리·정비 권고 초안을 담당하며 PHM 수치를 다시 계산하는
source of truth가 되지 않습니다.

## Asset Source of Truth

세 아키텍처 그림은 `assets/*.svg`가 canonical source입니다. PNG/WebP 복제본을 병행 관리하지 않으며,
CI에서 SVG 구조와 README/architecture 문서 참조를 검증합니다.
