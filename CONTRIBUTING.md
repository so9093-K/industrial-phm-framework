# Contributing

Industrial PHM Framework는 실제 산업 측정 데이터의 수집·저장·분석·근거 확인을 개선하는 프로젝트입니다. 레거시 호환 계층, 합성 제품 시연, 캡처 영상, 중복 검증 체계를 새로 만들지 않습니다.

## 개발 환경

Python 3.14, uv, Node.js 22.12+ 및 npm을 사용합니다. 일반 제품 실행은 프로젝트 루트의 `make up`으로 시작합니다.

```bash
uv python install 3.14
uv sync --locked --extra operations --extra aihub
make frontend
```

## 빠른 확인

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
npm run --prefix frontend check
npm test --prefix frontend
npm run --prefix frontend build
```

기본 CI는 [테스트 정책](docs/testing-policy.md)의 작은 데이터 계약 집합만 실행합니다. 변경한 저장소·수집기·분석 기능의 관련 단위·통합 테스트를 직접 선택해 실행하고, 실제 산업 데이터가 있으면 재생해 확인합니다. 원본이 없어 실행하지 못한 항목은 미실행으로 기록합니다. 주간 전체 수용 테스트, 스크린샷 갱신, 합성 시연 재생성은 요구하지 않습니다.

## 변경 원칙

- 사용자에게 보이는 기능의 **현재 구현 하나**를 유지하고, 전환이 끝나면 옛 경로를 삭제합니다.
- CSV·OPC UA·XJTU-SY·AI-Hub의 실제 데이터 출처와 측정 의미를 보존합니다.
- 수치 근거가 없는 고장·잔여수명·정비 확정 표현을 사용하지 않습니다.
- 코드 제거 시 그 코드에만 필요한 테스트·설정·문서 참조도 함께 제거합니다.
- 데이터 무결성·실제 사용 경로·핵심 계약에 대한 회귀 보호는 유지합니다.
- 사용자 인터페이스는 실제 데이터로 직접 확인하며, 별도 제품 시연·촬영 도구를 추가하지 않습니다.

## 작업 기록

작업은 `main`이 아닌 브랜치에서 진행합니다. Conventional Commits 형태의 커밋과 변경 목적·설계 영향·검증 범위를 설명하는 단일 PR을 권장합니다. 작은 코드 변경에 별도 설계 문서나 ADR을 추가하지 않습니다.

- `README.md`: 사용자 진입점 및 기능 소개
- `docs/status.md`: 현재 지원 범위
- `docs/architecture/` 및 `docs/adr/`: 지속되는 설계 계약과 결정
- `docs/research/`: 원본 데이터 프로필·실험 방법·근거
- `CHANGELOG.md`: 변경 이력
- Issue/PR: 한 번의 작업 계획, 검토 내용 및 실행 결과

새 의존성이 필요하면 `pyproject.toml`을 갱신하고 `uv lock`으로 잠금 파일을 같은 변경에 포함합니다.
