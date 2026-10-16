# README와 아키텍처 시각 자료

## 구성도

- [`system-architecture.png`](system-architecture.png): README와 아키텍처 문서가 공유하는 대표 구성도.
  2026-10-16 사용자가 제공한 PNG 원본(1672×941)입니다. 현장 데이터 소스 → 데이터 파이프라인 →
  DuckLake → 분석 → Operations Web → 운영자 판단의 개념적 흐름과 AI 브리핑·운영 지원을 표현합니다.
- `model-training-evaluation.png`: 연구 경로의 모델 학습·평가 흐름 참조.
- `service-architecture.png`: 서비스 책임을 설명하는 참조 그림. 배포된 서비스 목록을 뜻하지 않습니다.

실행·저장 책임은 [아키텍처](../docs/architecture/overview.md), 기능별 지원 조건은
[현재 지원 상태](../docs/status.md)가 기준입니다. 입력·저장·분석 경계가 바뀌면 대표 구성도와 설명을 함께 갱신합니다.

## 화면 캡처

README의 화면은 **2026-10-16, Web 코드 `5550966`, ko-KR Chromium, 1440×1050**에서 촬영했습니다.

| 파일 | 화면과 조건 |
| --- | --- |
| [`screenshots/monitor-xjtu.png`](screenshots/monitor-xjtu.png) | 설비 개요. Bearing1_1의 진동 RMS·최근 기록과 IForest 이상 탐지 결과 |
| [`screenshots/outlook-xjtu.png`](screenshots/outlook-xjtu.png) | 같은 설비의 수평 진동 RMS 예측. 기준선 8·15는 캡처용 임의 입력값(화면 이름: 관리 상한·종료 기준), 기본 예측 설정 |

XJTU-SY Bearing1_1의 기존 원본 파형·모델 패키지를 읽고, 격리된 캡처용 작업공간에서
**Isolation Forest 한 모델을 연결해 진동 측정 #1–#123을 다시 분석**했습니다.
기존 운영 작업공간과 원본 측정·모델 파일은 변경하지 않았습니다. 합성값이나 문제 주입은 사용하지 않았습니다.

- 기록 재생 데이터를 조회하는 화면이며 현장 실시간 수신이 아닙니다.
- 운영 미실행 상태의 조회 화면입니다. 새 AI 답변·전망 저장·검토 쓰기 경로를 촬영한 것은 아닙니다.
- 기준선 8·15는 파형의 크기를 요약한 수평 진동 RMS에 적용했습니다. 이 화면이 읽는 특징 데이터에는 물리 단위가 등록돼 있지 않습니다.
  캡처를 위한 임의 입력값이며 실제 설비의 허용 진동값·고장 기준으로 검증되지 않았습니다.
- 화면은 표시 예시입니다. 모델 성능 합격·물리적 고장 시각·사용성 검증을 입증하지 않습니다.

캡처의 주요 화면 구조나 설명할 동작이 바뀌면 이미지를 다시 촬영하고 이 조건도 갱신합니다.
과거 연구·인수 화면은 [`docs/research/results/`](../docs/research/results/README.md)에서 별도로 관리합니다.
