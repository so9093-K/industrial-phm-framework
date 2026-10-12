"""A shipped research summary cannot drift from its canonical evidence."""

from pathlib import Path

from tools.research_catalog import catalog_text


def test_packaged_research_catalog_matches_canonical_evidence() -> None:
    root = Path(__file__).resolve().parents[2]
    packaged = root / "src/industrial_phm/apps/web/research-results.json"
    assert packaged.read_text(encoding="utf-8") == catalog_text(root)
