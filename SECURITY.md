# Security Policy

현재 프로젝트는 공개 GitHub 저장소의 pre-alpha 로컬 제품입니다. 원격 인증·TLS·다중 사용자 운영은 지원하지 않습니다.

보안 관련 변경에서는 다음 원칙을 우선합니다.

- 신뢰하지 않는 pickle/joblib/model artifact를 자동으로 역직렬화하지 않습니다.
- dataset 또는 artifact provenance를 가능한 범위에서 검증합니다.
- credential, token, 개인 데이터와 산업 설비의 민감한 원본 데이터를 repository에 commit하지 않습니다.
- 생성형 AI 계층에 raw secret이나 불필요한 민감 데이터를 전달하지 않습니다.
- 향후 외부 배포 전 dependency, model serialization, API authentication 및 data handling threat model을 별도 검토합니다.

민감한 취약점이나 실제 산업 설비 데이터를 **공개 Issue에 올리지 마세요.**
GitHub 저장소의 Security 탭에서 비공개 취약점 신고 기능이 활성화되어 있다면 해당 기능을 사용하세요.
활성화되지 않았다면 비밀 없는 재현 정보만 공개 Issue로 공유하고, 자격 증명·원본 로그·데이터는 첨부하지 않습니다.
이 문서는 비공개 신고 기능이 현재 활성화돼 있다고 주장하지 않습니다.
