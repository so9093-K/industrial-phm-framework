# Changelog

이 프로젝트의 사용자 및 개발자에게 의미 있는 변경사항을 기록합니다. 형식은 Keep a Changelog의
분류 방식을 따릅니다.

개발 중 package version은 `0.0.1`로 유지하며 기능 PR이나 내부 구조 변경마다 버전을 올리지 않습니다.
릴리즈 가능한 public API와 배포 정책을 별도로 결정할 때 versioning 정책을 다시 검토합니다. 그 전까지
의미 있는 변경은 `[Unreleased]` 아래에 누적합니다.

## [Unreleased]

### Added

- Python 3.14 기반 `src` layout과 uv project foundation.
- 공통 `CanonicalTimeSeries` 데이터 계약.
- 구조적 `DomainAdapter` protocol과 contract test 기반.
- 초기 시스템, 모델 학습/평가, 서비스 아키텍처 문서.
- ADR, 기여 규칙, CI 및 품질 검증 체계.
- Apache License 2.0 라이선스 정책과 배포 메타데이터.
- Python 3.14 dependency lock을 통한 재현 가능한 개발 환경.
- `industrial-phm` CLI와 dataset manifest 기반 `data list/status/fetch/verify` acquisition 흐름.

### Fixed

- `CanonicalTimeSeries`가 mutable sequence 입력을 내부에 그대로 보관해 생성 이후 검증된 정렬 불변조건이 깨질 수 있던 문제를 수정했습니다.
