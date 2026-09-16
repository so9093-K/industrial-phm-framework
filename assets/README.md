# Architecture Assets

이 디렉터리의 SVG 파일은 README와 architecture 문서에서 직접 사용하는 canonical architecture source입니다.
별도의 PNG/WebP 복제본을 source of truth로 유지하지 않습니다.

## Canonical assets

- `system-architecture.svg`
- `model-training-evaluation.svg`
- `service-architecture.svg`

## Rules

- 외부 font/image dependency 없이 self-contained SVG로 유지합니다.
- 문서에는 위 SVG 경로를 직접 참조합니다.
- 동일 그림의 PNG/WebP를 수동으로 병행 관리하지 않습니다.
- 변경 시 `scripts/check_architecture_assets.py`로 XML 구조와 문서 참조를 검증합니다.
- 발표나 외부 문서에서 raster export가 필요하면 canonical SVG에서 생성하고 repository 기준선으로 다시 commit하지 않습니다.

이 방식은 과거 binary asset 손상과 SVG/PNG/WebP 간 source-of-truth drift가 반복된 문제를 줄이기 위한 것입니다.
