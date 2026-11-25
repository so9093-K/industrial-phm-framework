# 0033. Retire the LSTM autoencoder and the PyTorch runtime

Status: Accepted (2026-11-25)

Supersedes: [ADR-0006](0006-use-pytorch-cpu-reference-runtime.md).
Amends: [ADR-0025](0025-run-versioned-model-packages-over-ordered-asset-steps.md)의 시퀀스 입력과 torch 가중치
읽기 규칙만 없앤다. 패키지 형식, 바인딩, 단계별 한 트랜잭션, 실패 시 적재하지 않는 규칙은 그대로 유효하다.

## Context

선택과 집중을 위한 결정이다. 이 제품의 가치는 실측 신호가 초기와 어떻게 달라졌는지를 그래프와 대화로
이해하고 판단하게 하는 데서 나온다. 이상 탐지 모델은 그 판단을 돕는 보조이고, 보조 모델을 여러 개
유지할수록 화면·대화·검증이 모델 사이의 차이를 설명하는 데 쓰인다.

LSTM 오토인코더는 XJTU-SY 베어링 기록 재생에서만 쓰였다. 작업공간에 저장된 Bearing1_1 결과를 보면
116회 중 55회 기준을 넘었고, 그중 30·34·36~43번째는 진동이 아직 초기 수준이던 측정이다. 같은 베어링에서
관제의 특이사항(초기 대비 RMS 변화)은 72~80번째 측정부터 잡았다.

이 모델 하나를 위해 다음을 유지해야 했다.

- PyTorch CPU 실행 환경과 전용 패키지 색인(ADR-0006). 운영 이미지가 PyTorch를 실었다.
- 모델 패키지의 시퀀스 입력, 단계 평가의 시퀀스 준비 상태와 '입력을 모으는 중' 모델 상태.
- 재구성 오차 점수, 별도 실험·평가·결과 검사, 그 결과만 그리던 분석 보고서.
- 환경마다 재학습 결과가 갈라져 따로 정한 판정 기준(operational inference acceptance protocol v3 §2.3·§5).

앞으로 이상 탐지는 Isolation Forest를 바로잡고(같은 운전 수준끼리 학습·판정) 점수에 크게 반영된 신호를
실측 그래프로 보여 주는 쪽에 집중한다.

## Decision

- LSTM 모델·패키지 복원·재구성 오차 점수, XJTU LSTM 실험·평가·결과 검사·운영 패키징, 시퀀스 창 구성,
  `experiment lstm-development`·`operations phm package-xjtu-lstm` 명령, LSTM 결과만 그리던 `analysis report`
  명령과 analysis 패키지, 진단(`doctor`)의 deep-learning 표시, 관련 테스트와 확인 도구를 삭제한다.
- `deep-learning` 추가 의존성(PyTorch)과 PyTorch CPU 색인을 없앤다. 운영 이미지에 PyTorch가 들어가지 않는다.
- 모델 패키지 형식에서 `lstm-autoencoder-v1` estimator와 입력의 `sequence_length`를 없앤다. 다른 패키지의
  매니페스트는 `sequence_length`를 기록하지 않았으므로 기존 패키지 ID는 바뀌지 않는다. 단계 평가의 시퀀스 준비
  상태, 결과의 `sequence_positions`, 모델 상태 `warmup`, AI 문맥의 입력 획득 수도 없앤다.
- 특징 기여(`feature_contributions`)는 PCA 잔차가 계속 제공하므로 남긴다.
- XJTU-SY 공개 데이터 가져오기와 `demo xjtu`는 Isolation Forest 하나만 준비하고 연결한다.
- 기존 작업공간에 남은 LSTM 패키지와 바인딩·결과는 지우지 않는다(출시 전 저장소는 옮기지 않는다, ADR-0022).
  패키지를 불러올 수 없으므로 실행하지 않는다. 다른 적재 실패와 같은 공통 규칙으로 다룬다.
  - 이상 점수 화면의 모델 목록에는 '실행할 수 없음'으로 보이고, 기본으로 열리지 않으며, 고르면 저장된 결과만
    보인다는 안내가 나온다.
  - 전망·데이터 기능 판단·AI 문맥은 지금 코드가 불러올 수 있는 패키지의 결과만 근거로 쓴다.
- 연구 프로토콜(`docs/research/xjtu-lstm-autoencoder-protocol.md`)과 결과 JSON
  (`xjtu-sy-lstm-autoencoder-fold-1-development-v1.json`)은 쓰는 코드가 없어 삭제한다. git 기록에 남는다.
  실험 결과 검사에서 늘 '해당 없음'이던 Sequence Construction 단계와, 실험 설정의 모델 계열 중 쓰지 않는
  `lstm-autoencoder`·`lstm-regression`·`ridge-regression`(ADR-0026 때 남은 값)도 없앤다.

## Consequences

- 설치와 운영 이미지가 가벼워지고, XJTU-SY 가져오기는 모델 하나만 학습한다.
- XJTU-SY 베어링의 이상 점수 화면과 AI 문맥에는 Isolation Forest만 보인다.
- 시퀀스 모델이 다시 필요하면 새 ADR과 새 estimator 이름으로 도입한다.
