"""Ask the configured local model about one stored comparison and print the checked answers.

For prompt or model changes: shows what a user would read and which checks fired, without
writing an explanation record.

    uv run --all-extras python tools/phm/answer_samples.py --workspace WS \\
        --binding anomaly-score-Bearing1_1 --position 69 --compare 1 \\
        --question "왜 점수가 올랐어?" --question "다음에 무엇을 보면 좋을까?"
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_explanation import explanation_context
from industrial_phm.genai.local_explanation import ExplanationProvider
from industrial_phm.genai.phm_answer import generate_grounded_answer
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

DEFAULT_QUESTIONS = (
    "이전 시점과 비교해 어떤 측정 신호가 함께 변했는지 설명해 주세요.",
    "왜 점수가 올랐어?",
    "RUL이 변한 구간과 함께 움직인 측정값은 뭐야?",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--position", type=int, required=True)
    parser.add_argument("--compare", type=int, required=True)
    parser.add_argument("--question", action="append")
    args = parser.parse_args()
    workspace = OperationsWorkspace(args.workspace.resolve())
    provider = ExplanationProvider(
        base_url=os.environ.get("INDUSTRIAL_PHM_GENAI_BASE_URL", "http://127.0.0.1:9400/v1"),
        model=os.environ.get("INDUSTRIAL_PHM_GENAI_MODEL", "local-main"),
        api_key=os.environ.get("INDUSTRIAL_PHM_GENAI_API_KEY"),
    )
    for question in args.question or DEFAULT_QUESTIONS:
        context = explanation_context(
            SqlitePhmAnalysisStore(workspace.phm_analysis_path),
            workspace.models_path,
            SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
            args.binding,
            args.position,
            compare_position=args.compare,
            question=question,
            windows=SqliteObservationWindowRepository(workspace.window_state_path),
        )
        started = time.monotonic()
        answer = generate_grounded_answer(context, provider)
        answer["question"] = question
        answer["seconds"] = round(time.monotonic() - started, 1)
        print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
