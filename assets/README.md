# Architecture Reference Diagrams

- `system-architecture.png` — 현재 대표 시스템 구조. 원본은 편집 가능한 `system-architecture.svg`이며
  PNG는 그 렌더링입니다. 내용을 바꿀 때는 SVG를 수정하고 PNG를 다시 렌더링합니다.
- `model-training-evaluation.png` — research path의 모델 학습·평가 흐름 reference
- `service-architecture.png` — 향후 서비스 책임을 설명하는 reference

대표 그림은 구현 부품이 아니라 책임 단계(설비·데이터 소스 → 수집·설비 이력 → PHM 분석·근거 → 운영·검토 →
사람의 판단)를 보여줍니다. 구현 구성 요소와 현재 구현 범위는
[architecture overview](../docs/architecture/overview.md)의 상세 runtime에서 확인합니다.

SVG를 PNG로 렌더링하는 예(Playwright Chromium, 2배 해상도):

```bash
uv run --no-sync python - <<'EOF'
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=2)
    page.goto(Path("assets/system-architecture.svg").resolve().as_uri())
    page.screenshot(path="assets/system-architecture.png")
EOF
```
