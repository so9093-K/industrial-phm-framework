# Architecture Assets

이 디렉터리의 PNG 파일은 README와 architecture 문서에서 직접 사용하는 canonical architecture asset입니다.

## Canonical assets

- `system-architecture.png`
- `model-training-evaluation.png`
- `service-architecture.png`

## Rules

- 문서에는 위 PNG 경로를 직접 참조하고 그림의 책임과 흐름을 설명하는 대체 텍스트를 제공합니다.
- 같은 그림의 SVG/WebP 복제본을 repository에서 병행 관리하지 않습니다.
- 구조나 책임이 바뀌면 canonical PNG와 이를 설명하는 architecture 문서를 같은 변경 단위에서 갱신합니다.
- 변경 시 `scripts/check_architecture_assets.py`로 PNG 무결성·크기·문서 참조를 검증합니다.
- 원본 크기와 README 축소 렌더링에서 텍스트와 연결 관계를 함께 확인합니다.
