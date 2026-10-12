"""Build the packaged read-only research catalog from canonical committed evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from industrial_phm.experiments.result_inspection import (
    ExperimentResultInspectionError,
    inspect_experiment_result,
)

_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = Path("src/industrial_phm/apps/web/research-results.json")
_TITLES = {
    "aihub-239-electrical-anomaly-evaluation-v2": "전기 다변량 이상 탐지 · 운영 승격 평가 FAIL",
    "ims-bearings-iforest-single-channel-cross-test-v1": "Isolation Forest · 단일 채널 교차 시험",
    "mimii-due-iforest-domain-shift-development-v1": "Isolation Forest · 도메인 변화 개발 평가",
    "mimii-due-iforest-domain-shift-external-result-v1": "Isolation Forest · 외부 평가",
    "mimii-due-iforest-domain-shift-external-score-v1": "Isolation Forest · 외부 점수 기록",
    "xjtu-sy-iforest-cross-fold-robustness-v1": "Isolation Forest · 폴드 간 강건성 평가",
    "xjtu-sy-iforest-fold-1-holdout-v1": "Isolation Forest · 보류 데이터 평가",
    "xjtu-sy-iforest-fold-1-reference-comparison-v1": "Isolation Forest · 참조 모델 비교",
    "xjtu-sy-iforest-fold-1-validation-v1": "Isolation Forest · 검증 평가",
    "xjtu-sy-lstm-autoencoder-fold-1-development-v1": "LSTM Autoencoder · 개발 평가",
    "xjtu-sy-rul-lstm-fold-1-benchmark-v1": "RUL · LSTM 벤치마크",
    "xjtu-sy-rul-three-model-fold-1-validation-v1": "RUL · 3개 모델 검증 비교",
}


def build_catalog(root: Path) -> dict[str, object]:
    """Derive summaries; never turn research evaluations into workspace observations."""
    items: list[dict[str, object]] = []
    for path in sorted((root / "docs/research/results").glob("*.json")):
        relative = path.relative_to(root).as_posix()
        inspection: dict[str, object] | None
        try:
            result = inspect_experiment_result(path)
        except ExperimentResultInspectionError as error:
            if not str(error).startswith("unsupported experiment result schema_id"):
                raise
            inspection = None
        else:
            inspection = asdict(result)
            # Replace checkout paths in the serialized presentation only.
            inspection["stages"] = [
                {
                    **asdict(stage),
                    "facts": [
                        {
                            "label": fact.label,
                            "value": relative if fact.label == "Artifact" else fact.value,
                        }
                        for fact in stage.facts
                    ],
                }
                for stage in result.stages
            ]
        dataset = (
            "XJTU-SY"
            if path.name.startswith("xjtu-sy-")
            else "IMS Bearings"
            if path.name.startswith("ims-bearings-")
            else "AI-Hub 239"
            if path.name.startswith("aihub-239-")
            else "MIMII DUE"
        )
        items.append(
            {
                "id": path.stem,
                "title": _TITLES.get(path.stem, path.stem),
                "dataset": dataset,
                "artifact_path": relative,
                "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "artifact_bytes": path.stat().st_size,
                "source_url": "https://github.com/so9093-K/industrial-phm-framework/blob/"
                "main/" + relative,
                "inspection": inspection,
                "raw_data_status": "not-bundled-local-availability-unverified",
            }
        )
    return {
        "schema_version": 1,
        "meaning": "research-evaluation-not-workspace-data",
        "items": items,
    }


def catalog_text(root: Path) -> str:
    return json.dumps(build_catalog(root), ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if the packaged summary is stale"
    )
    args = parser.parse_args()
    expected = catalog_text(_ROOT)
    output = _ROOT / _OUTPUT
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != expected:
            print("Research catalog is stale; run python -m tools.research_catalog")
            return 1
        print("Research catalog matches canonical result artifacts")
    else:
        output.write_text(expected, encoding="utf-8")
        print(f"Generated {_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
