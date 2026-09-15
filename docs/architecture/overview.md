# Architecture Overview

이 문서는 `industrial-phm-framework`의 현재 reference architecture를 설명합니다.
특정 설비나 특정 데이터셋을 구조 자체에 고정하지 않고 책임과 데이터 흐름을 기준으로 유지합니다.

## 1. System Architecture

![System Architecture](../../assets/system-architecture.webp)

원천 산업 설비 데이터는 Domain Adapter에서 공통 데이터 계약으로 변환됩니다. 이후 PHM 계층은
도메인별 파일 형식이나 컬럼 이름이 아니라 공통 계약을 기준으로 분석·평가·서비스 흐름을 구성합니다.

## 2. Model Training and Evaluation

![Model Training and Evaluation](../../assets/model-training-evaluation.webp)

모델 학습과 평가는 분리합니다. Isolation Forest를 비교 기준으로 두고 LSTM Autoencoder와 동일한
평가 흐름에서 비교하며, 모델 구현과 평가 로직이 서로 직접 결합되지 않도록 유지합니다.

## 3. Service Architecture

![Service Architecture](../../assets/service-architecture.webp)

학습된 모델 아티팩트는 공통 추론 서비스를 통해 구조화된 PHM 결과를 생성합니다. Dashboard/API와
생성형 AI 계층은 이 결과를 소비하며, 생성형 AI는 상태 해석·설명·정비 권고를 담당합니다.
