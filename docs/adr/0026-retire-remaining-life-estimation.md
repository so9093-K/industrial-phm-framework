# 0026. Retire remaining-life estimation

Status: Accepted (2026-10-15)

Amends: ADR-0025의 출력 작업(task) 중 `rul-estimate`만 폐기한다. 모델 패키지, 설비별 순서
step 분석, 바인딩·커서·재시작 계약은 그대로 유효하다.

## Context

잔여수명(RUL) 추정은 XJTU-SY 기록 재생에서 Ridge·LSTM 두 패키지로 제공됐다. 종료점은
데이터셋의 마지막 기록 획득이며 실제 고장 시각이나 남은 운전시간이 아니었다. 일반 사용자 CSV,
OPC UA 전기 신호, AI-Hub 239에는 수명 종료 근거가 없어 적용할 수 없었다. 그 결과 대부분의 설비에서
RUL은 "사용할 수 없음"으로만 보였고, 실험·평가·패키징·추론·화면·AI 답변 검사까지 별도 경로를
유지해야 했다.

사용자에게 더 쓸모 있는 것은 "앞으로 측정값이 어떻게 변할까"이며, 이는 수명 종료 근거 없이도
저장된 측정 이력으로 예측할 수 있다.

## Decision

- RUL 학습·평가·패키징 코드(Ridge·LSTM RUL 모델, XJTU RUL 실험·결과 검사, prognostics 패키지),
  운영 추론의 RUL 경로, RUL 화면·API 분기·AI 답변 분기, 관련 테스트를 삭제한다.
- 모델 패키지의 작업은 `anomaly-score` 하나만 남긴다. 매니페스트의 `unit`·`endpoint_semantics`는
  항상 `null`로 계속 기록해 기존 이상 탐지 패키지의 내용과 패키지 ID를 바꾸지 않는다.
- `rul-estimate`를 선언한 패키지는 불러오지 않는다. 기존 작업공간에 남은 RUL 패키지와 바인딩·결과는
  지우지 않고 그대로 두되, 실행·목록·연결 후보·AI 문맥에서 제외한다.
- 연구 결과 문서(`docs/research/results`의 RUL JSON, 프로토콜·실행 기록)는 기록으로 보존한다.
- 앞으로의 변화는 측정값 예측 기능으로 제공한다. 예측 결과를 고장 시각·남은 수명·정비 시점으로
  표현하지 않는다.

## Consequences

- 이상 탐지·신호 탐색·AI 질문은 영향이 없다. 설비 탭에서 `RUL`이 사라지고, 예전 `#rul` 주소는 개요로 연다.
- `operations phm package-xjtu`·`package-xjtu-lstm`은 이상 탐지 패키지만 만든다.
  `experiment rul-*` 명령과 분석 보고서의 `--prognostics` 옵션은 없어진다.
- 수명 종료가 기록된 데이터로 RUL이 다시 필요해지면 새 ADR과 새 작업 이름으로 도입한다.
