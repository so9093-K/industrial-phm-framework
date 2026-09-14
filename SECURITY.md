# Security Policy

현재 프로젝트는 pre-alpha이며 private repository에서 개발 중입니다.

보안 관련 변경에서는 다음 원칙을 우선합니다.

- 신뢰하지 않는 pickle/joblib/model artifact를 자동으로 역직렬화하지 않습니다.
- dataset 또는 artifact provenance를 가능한 범위에서 검증합니다.
- credential, token, 개인 데이터와 산업 설비의 민감한 원본 데이터를 repository에 commit하지 않습니다.
- 생성형 AI 계층에 raw secret이나 불필요한 민감 데이터를 전달하지 않습니다.
- 향후 외부 배포 전 dependency, model serialization, API authentication 및 data handling threat model을 별도 검토합니다.

공개 security contact와 vulnerability disclosure 절차는 repository 공개 전에 추가합니다.
