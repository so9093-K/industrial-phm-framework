# Operations Web

Svelte 5·TypeScript 웹 애플리케이션입니다. Python Operations의 동일 작업공간에 있는 실제 CSV·OPC UA·진동 획득 기록 및 분석 결과를 `/web/`에서 표시합니다. 정적 합성 쇼케이스나 별도 데모 런타임은 유지하지 않습니다.

## 실행과 빌드

프로젝트 루트에서 `make up`을 실행하면 현재 운영용 웹 자산을 준비합니다. 프런트엔드만 수정할 때:

```bash
npm ci --prefix frontend --no-audit --no-fund
npm run --prefix frontend check
npm run --prefix frontend build
```

`npm run --prefix frontend build`는 `src/industrial_phm/apps/web_next/`에 웹 번들을 생성합니다. 서버는 빌드된 `asset-manifest.json`에 등록된 정적 파일만 제공합니다. 스냅샷 JSON 또는 별도 쇼케이스 모드는 없습니다.

## 화면과 데이터 근거

- **모니터링**: 실제 최근 값·추이와 변화 발견, 과거 실측 기록의 빠른 재생
- **변화 조사**: 같은 시간축의 관련 신호, 운전 수준·진동·주파수 비교, 필요한 모델 분석과 조건부 전망
- **운영 관리**: CSV·OPC UA 데이터 연결과 시스템 상태
- **AI·판단**: 선택한 전력·진동 변화에 질문하고 답변을 판단 메모로 활용

서버에서 제공한 시각·출처·측정점·채널·단위·품질을 그대로 사용하고, 화면이 결과를 추정하거나 합성하지 않습니다. 사용자가 바꾼 설비·구간·기준에 맞는 분석 결과가 없는 경우 이전 결과를 현재 값처럼 재사용하지 않습니다.

## 개발 원칙

실제 데이터 기반 흐름과 오류 표시를 우선합니다. 화면 캡처·GIF·영상 생성 도구, 데모 전용 API, 합성 첫 실행 시나리오를 추가하지 않습니다. 화면 변경은 베어링·공기압축기의 실제 기록으로 직접 확인합니다. 문구·메뉴·배치를 고정하는 테스트와 별도 브라우저 자동화 환경은 유지하지 않습니다. 시각·단위·출처·선택한 측정이 결과에 맞게 연결되는 검사는 관련 로직을 바꿀 때만 실행합니다. 예: `node --experimental-strip-types --test frontend/src/measurement-links.test.ts`. 핵심 데이터 저장과 권한 처리는 Python 서버 테스트에서 보호합니다.
