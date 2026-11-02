# Operations Web

Svelte 5·TypeScript 웹 애플리케이션입니다. Python Operations의 동일 작업공간에 있는 실제 CSV·OPC UA·진동 획득 기록 및 분석 결과를 `/web/`에서 표시합니다. 정적 합성 쇼케이스나 별도 데모 런타임은 유지하지 않습니다.

## 실행과 빌드

프로젝트 루트에서 `make up`을 실행하면 현재 운영용 웹 자산을 준비합니다. 프런트엔드만 수정할 때:

```bash
npm ci --prefix frontend --no-audit --no-fund
npm run --prefix frontend check
npm test --prefix frontend
npm run --prefix frontend build
```

`npm run --prefix frontend build`는 `src/industrial_phm/apps/web_next/`에 웹 번들을 생성합니다. 서버는 빌드된 `asset-manifest.json`에 등록된 정적 파일만 제공합니다. 스냅샷 JSON 또는 별도 쇼케이스 모드는 없습니다.

## 화면과 데이터 근거

- **관측 현황**: 설비와 저장 기록, 분석 근거에 연결된 확인 항목
- **설비·신호**: 신호 탐색, 기간 비교, 특징 관계, 주파수 분석, 이상 징후, 상태 전망
- **운영 관리**: CSV·OPC UA 데이터 연결과 시스템 상태
- **선택 기능**: 분석 기록·사람 검토 및 AI 해설

서버에서 제공한 시각·출처·측정점·채널·단위·품질을 그대로 사용하고, 화면이 결과를 추정하거나 합성하지 않습니다. 사용자가 바꾼 설비·구간·기준에 맞는 분석 결과가 없는 경우 이전 결과를 현재 값처럼 재사용하지 않습니다.

## 개발 원칙

실제 데이터 기반 흐름과 오류 표시를 우선합니다. 화면 캡처·GIF·영상 생성 도구, 데모 전용 API, 합성 첫 실행 시나리오를 추가하지 않습니다. 화면 변경은 필요시 실제 실행 화면에서 직접 확인하고, 핵심 데이터 계약과 권한 처리는 Python 서버 테스트에서 보호합니다.

[데이터 기반 첫 사용](../docs/product/data-first-start.md) · [지원 범위](../docs/status.md) · [제품 설계](../docs/product/overview.md).
