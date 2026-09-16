# Versioning Baseline

현재 개발 단계에서는 프로젝트 버전을 `0.0.1`로 유지합니다.

기능 추가, 문서 변경, 내부 구조 개선, 실험적 모델 추가만으로 package version을 올리지 않습니다. 개발 중인 변경은 `CHANGELOG.md`의 `Unreleased`에 누적합니다.

버전 변경은 다음과 같이 명시적인 release 결정을 했을 때만 수행합니다.

- 외부 사용자에게 배포할 release를 만들기로 한 경우
- package/API compatibility 기준선을 새로 선언하는 경우
- Git tag 및 release artifact를 함께 만들 필요가 있는 경우

즉 commit/PR 단위의 변화와 package version은 분리합니다. 이 문서는 `0.0.1`을 영구적으로 유지한다는 의미가 아니라, release event가 있기 전에는 임의로 bump하지 않는다는 운영 원칙을 정의합니다.
