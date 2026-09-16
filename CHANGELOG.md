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
- 사용자가 직접 획득한 local dataset file/directory의 규모를 확인하는 `data inspect` 흐름.
- XJTU-SY 실데이터 관찰과 Adapter/contract 검증을 위한 Jupyter-compatible `notebooks/` Research UX 기준선.
- Git에 포함되지 않는 `data/` local workspace와 XJTU-SY 공식 Google Drive mirror의 반자동 획득 가이드.
- 실제 XJTU-SY 15개 bearing run / 9,216 acquisition 구조에 근거한 acquisition 단위 `XjtuSyAdapter`.
- XJTU-SY local source profile과 regular waveform time-axis 결정을 기록한 research 문서 및 ADR-0005.
- XJTU-SY complete source profile, lifecycle sequence 및 representative/full waveform parsing을 자동 확인하는
  `industrial-phm data validate xjtu-sy` 흐름.
- XJTU-SY 첫 numerical baseline을 위한 condition-stratified 5-fold bearing-run split manifest와
  leakage-prevention experiment protocol.
- acquisition별 channel 통계와 provenance를 보존하는 versioned `vibration-statistical-v1` feature foundation.
- correlation 하나에 종속되지 않고 lifecycle·condition·redundancy·run imbalance를 함께 보는 XJTU feature /
  degradation characterization research protocol.
- 전체 XJTU `vibration-statistical-v1` feature table과 condition/run 통계, Pearson·Spearman redundancy,
  retrospective lifecycle thirds, run-length imbalance를 재현 가능하게 생성하는 automated characterization workflow.

### Changed

- `CanonicalTimeSeries`가 regular sampling rate를 제공하는 경우 explicit sample `timestamps` 없이도 waveform segment를 표현할 수 있도록 확장했습니다.
- 초기 수동 XJTU directory/schema 검증을 반복 가능한 production validator로 승격하고 Notebook은 같은 검증을
  재구현하지 않도록 research workflow를 정리했습니다.
- XJTU experiment protocol이 stateless feature extraction과 data-derived feature/reference selection을 구분하고,
  test trajectory를 이용한 post-hoc tuning도 leakage로 취급하도록 연구 경계를 명확히 했습니다.
- XJTU feature characterization에서 반복 계산·집계는 automated artifact workflow가 담당하고 Notebook은 실제
  결과의 시각적 비교와 사람의 experiment decision에 집중하도록 역할을 구분했습니다.

### Fixed

- `CanonicalTimeSeries`가 mutable sequence 입력을 내부에 그대로 보관해 생성 이후 검증된 정렬 불변조건이 깨질 수 있던 문제를 수정했습니다.
- dataset acquisition User-Agent가 package version과 별도로 `0.1`에 하드코딩되어 있던 중복 version 값을 제거했습니다.
- `data inspect`가 파일이 하나도 없는 local directory를 연구 가능한 dataset source처럼 성공 처리하던 동작을 수정했습니다.
