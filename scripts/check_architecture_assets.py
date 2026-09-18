"""Validate canonical architecture SVG assets and their documentation references."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]

ASSETS = (
    ROOT / "assets/system-architecture.svg",
    ROOT / "assets/model-training-evaluation.svg",
    ROOT / "assets/service-architecture.svg",
)

REFERENCES = {
    ROOT / "README.md": ("assets/system-architecture.svg",),
    ROOT / "docs/architecture/overview.md": (
        "../../assets/system-architecture.svg",
        "../../assets/model-training-evaluation.svg",
        "../../assets/service-architecture.svg",
    ),
}


def _parse_view_box(value: str) -> tuple[float, float, float, float]:
    parts = value.replace(",", " ").split()
    if len(parts) != 4:
        raise ValueError(f"viewBox must contain four numbers: {value!r}")
    x, y, width, height = (float(part) for part in parts)
    if width <= 0 or height <= 0:
        raise ValueError(f"viewBox dimensions must be positive: {value!r}")
    return x, y, width, height


def validate_asset(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"missing architecture asset: {path.relative_to(ROOT)}")

    root = ElementTree.parse(path).getroot()
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError(f"not an SVG root: {path.relative_to(ROOT)}")

    view_box = root.attrib.get("viewBox")
    if view_box is None:
        raise ValueError(f"missing viewBox: {path.relative_to(ROOT)}")

    _parse_view_box(view_box)

    title = root.find("{http://www.w3.org/2000/svg}title")
    desc = root.find("{http://www.w3.org/2000/svg}desc")
    if title is None or not (title.text or "").strip():
        raise ValueError(f"missing accessible title: {path.relative_to(ROOT)}")
    if desc is None or not (desc.text or "").strip():
        raise ValueError(f"missing accessible description: {path.relative_to(ROOT)}")


def validate_references(path: Path, expected: tuple[str, ...]) -> None:
    content = path.read_text(encoding="utf-8")
    for reference in expected:
        if reference not in content:
            raise ValueError(f"missing asset reference {reference!r} in {path.relative_to(ROOT)}")


if __name__ == "__main__":
    for asset in ASSETS:
        validate_asset(asset)
    for document, references in REFERENCES.items():
        validate_references(document, references)
    print(f"validated {len(ASSETS)} architecture SVG assets")
