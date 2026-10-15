"""Persist explanations of immutable PHM results without modifying model outputs."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_range import range_analysis
from industrial_phm.application.phm_read import project_phm_bindings
from industrial_phm.application.phm_signal_comparison import (
    feature_comparison,
    feature_label,
    raw_signal_summary,
)
from industrial_phm.models.package import is_retired_package


class PhmExplanationStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS explanation(id TEXT PRIMARY KEY, binding_id TEXT, "
            "position INTEGER, analysis_run_id TEXT, package_id TEXT, context TEXT, "
            "model TEXT, owner TEXT, "
            "status TEXT, text TEXT, error TEXT, requested_at TEXT, "
            "finished_at TEXT, finding_id TEXT, warnings TEXT, answer TEXT)"
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(explanation)")}
        if "warnings" not in columns:  # stores created before numeric grounding checks
            connection.execute("ALTER TABLE explanation ADD COLUMN warnings TEXT")
        if "answer" not in columns:  # stores created before structured answers
            connection.execute("ALTER TABLE explanation ADD COLUMN answer TEXT")
        return connection

    def request(self, context: dict[str, Any], *, model: str, owner: str) -> str:
        identifier = "explanation-" + uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute(
                "SELECT COUNT(*) FROM explanation WHERE status = 'pending'"
            ).fetchone()[0]
            if pending >= 4:
                raise ValueError("explanation generation capacity reached")
            connection.execute(
                "INSERT INTO explanation(id, binding_id, position, analysis_run_id, package_id, "
                "context, model, owner, status, text, error, requested_at, finished_at, "
                "finding_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    context["binding_id"],
                    context["position"],
                    context["analysis_run_id"],
                    context["package_id"],
                    json.dumps(context, ensure_ascii=False, allow_nan=False),
                    model,
                    owner,
                    "pending",
                    "",
                    None,
                    datetime.now(UTC).isoformat(),
                    None,
                    None,
                ),
            )
        return identifier

    def finish(
        self,
        identifier: str,
        *,
        owner: str,
        text: str = "",
        error: str | None = None,
        answer: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE explanation SET status=?, text=?, error=?, finished_at=?, warnings=?, "
                "answer=? WHERE id=? AND owner=? AND status='pending'",
                (
                    "failed" if error else "complete",
                    text,
                    error,
                    datetime.now(UTC).isoformat(),
                    "[]",
                    None if answer is None else json.dumps(answer, ensure_ascii=False),
                    identifier,
                    owner,
                ),
            )

    def recover(self, owner: str) -> None:
        if not self.path.exists():
            return
        with self._connect() as connection:
            connection.execute(
                "UPDATE explanation SET status='failed', error='generation interrupted', "
                "finished_at=? WHERE status='pending' AND owner!=?",
                (datetime.now(UTC).isoformat(), owner),
            )

    def get(self, identifier: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM explanation WHERE id=?", (identifier,)
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data.pop("owner")
        data["context"] = json.loads(data["context"])
        data["warnings"] = json.loads(data["warnings"]) if data.get("warnings") else []
        data["answer"] = json.loads(data["answer"]) if data.get("answer") else None
        return data

    def list_for(self, binding_id: str, position: int) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._connect() as connection:
            ids = connection.execute(
                "SELECT id FROM explanation WHERE binding_id=? AND position=? "
                "ORDER BY requested_at DESC LIMIT 10",
                (binding_id, position),
            ).fetchall()
        return [data for (identifier,) in ids if (data := self.get(identifier)) is not None]

    def link_finding(self, identifier: str, finding_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE explanation SET finding_id=? WHERE id=?", (finding_id, identifier)
            )


def explanation_context(
    store: SqlitePhmAnalysisStore,
    models_root: Path,
    snapshots: SqliteAcquisitionSnapshotRepository,
    binding_id: str,
    position: int,
    *,
    compare_position: int | None = None,
    question: str = "이전 시점과 비교해 어떤 측정 신호가 함께 변했는지 설명해 주세요.",
    windows: SqliteObservationWindowRepository | None = None,
    include_signals: bool = True,
) -> dict[str, Any]:
    result = store.get_result(binding_id, position)
    if result is None or result.state is not StepState.ANALYZED:
        raise ValueError("only persisted analyzed PHM results can be explained")
    binding = next(b for b in store.list_bindings() if b.binding_id == binding_id)
    summaries = project_phm_bindings(store, models_root, snapshots)
    package = next(
        item["package"] for item in summaries["bindings"] if item["binding_id"] == binding_id
    )
    previous = (
        store.latest_result(binding_id, state=StepState.ANALYZED, before_position=position)
        if compare_position is None
        else store.get_result(binding_id, compare_position)
    )
    if compare_position is not None and (
        compare_position >= position or previous is None or previous.state is not StepState.ANALYZED
    ):
        raise ValueError("comparison must select an earlier analyzed result of the same binding")
    score, prior_score = (
        result.output.get("score"),
        None if previous is None else previous.output.get("score"),
    )
    comparison = None
    if isinstance(score, (int, float)) and isinstance(prior_score, (int, float)):
        comparison = {
            "previous_score": prior_score,
            "score_change": score - prior_score,
            "previous_position": previous.position if previous else None,
        }
    features = feature_comparison(result, previous)
    signal_comparison: dict[str, Any] = {
        "current_position": position,
        "previous_position": None if previous is None else previous.position,
        "previous_event_start": None
        if previous is None or previous.event_start is None
        else previous.event_start.isoformat(),
        "previous_output": None if previous is None else dict(previous.output),
        "features": features,
        "output_changes": {
            key: result.output[key] - previous.output[key]
            for key in ("score",)
            if previous is not None
            and isinstance(result.output.get(key), (int, float))
            and isinstance(previous.output.get(key), (int, float))
        },
        "original_current": None
        if not include_signals
        else raw_signal_summary(store, snapshots, windows, binding, result),
        "original_previous": None
        if previous is None or not include_signals
        else raw_signal_summary(store, snapshots, windows, binding, previous),
    }
    if previous is not None and include_signals:
        signal_comparison["range"] = range_analysis(
            store,
            binding_id,
            binding.step_kind,
            previous.position,
            position,
            [row["feature"] for row in features[:8]],
        )
    related = []
    for other in store.list_bindings()[:100]:
        if is_retired_package(models_root, other.package_id):
            continue
        if other.binding_id == binding_id or (
            other.asset_id,
            other.source_id,
            other.measurement_point_id,
            other.step_kind,
        ) != (binding.asset_id, binding.source_id, binding.measurement_point_id, binding.step_kind):
            continue
        matched = store.get_result(other.binding_id, position)
        if (
            matched is None
            or matched.state is not StepState.ANALYZED
            or (dict(matched.input_reference) != dict(result.input_reference))
        ):
            continue
        before = None if previous is None else store.get_result(other.binding_id, previous.position)
        if (
            before is not None
            and previous is not None
            and (
                before.state is not StepState.ANALYZED
                or dict(before.input_reference) != dict(previous.input_reference)
            )
        ):
            before = None
        related.append(
            {
                "binding_id": other.binding_id,
                "package_id": other.package_id,
                "output": dict(matched.output),
                "previous_output": None if before is None else dict(before.output),
            }
        )
    return {
        "schema_version": 1,
        "binding_id": binding_id,
        "position": position,
        "analysis_run_id": result.analysis_run_id,
        "package_id": binding.package_id,
        "asset_id": binding.asset_id,
        "source_id": binding.source_id,
        "measurement_point_id": binding.measurement_point_id,
        "recorded_replay": result.replay,
        "event_start": None if result.event_start is None else result.event_start.isoformat(),
        "processed_at": result.processed_at.isoformat(),
        "features": dict(result.features or {}),
        "output": dict(result.output),
        "comparison": comparison,
        "question": question,
        "signal_comparison": signal_comparison,
        "related_models": related[:8],
        "input_reference": dict(result.input_reference),
        "model": None
        if package is None
        else {k: package.get(k) for k in ("recipe_id", "output", "validation", "applicability")},
        "meaning": "stored model output; not fault diagnosis or physical failure date",
        "facts": explanation_facts(
            dict(result.output),
            None if package is None else package.get("validation"),
            asset_id=binding.asset_id,
            recorded_replay=result.replay,
        ),
    }


def operator_explanation_context(context: dict[str, Any]) -> dict[str, Any]:
    """Bounded operator input; the complete immutable context stays in the explanation store.

    Research acceptance and training conditions are available in model details, not requested
    as operator advice. No model output is changed here.
    """
    original = context.get("output") or {}
    output = {
        key: original[key]
        for key in (
            "task",
            "score",
            "threshold",
            "exceeds_threshold",
            "change_from_previous",
            "feature_contributions",
            "sequence_positions",
        )
        if key in original
    }
    signals = context.get("signal_comparison")
    if signals is not None:
        # A custom comparison is not the runner's immediately preceding result.
        # Keep that output unchanged in storage; omit its delta from this comparison.
        output.pop("change_from_previous", None)
    task = output.get("task")
    model = context.get("model") or {}
    recipe = str(model.get("recipe_id") or "")
    label = "재구성 오차" if "pca" in recipe or "autoencoder" in recipe else "이상 점수"
    facts = []
    if task == "anomaly-score":
        facts.append(
            f"{label} {_n(output.get('score'))}는 학습 기준과의 차이를 나타내며 "
            "높을수록 더 다릅니다."
        )
        facts.append(
            f"모델 기준 {_n(output.get('threshold'))} "
            f"{'초과' if output.get('exceeds_threshold') else '이하'}입니다. "
            "정상·고장 판정이 아닙니다."
        )
        if not output.get("feature_contributions"):
            facts.append("변수별 기여도가 없으므로 원인 신호를 추정하지 마세요.")
        else:
            facts.append("기여도는 모델 점수에 대한 잔차 기여이며 고장의 원인이 아닙니다.")
            ranked = sorted(
                output["feature_contributions"].items(), key=lambda item: item[1], reverse=True
            )[:3]
            facts.append(
                "선택 시점의 잔차 기여가 큰 순서: "
                + " → ".join(feature_label(name) for name, _ in ranked)
            )
    if isinstance(signals, dict):
        for row in signals.get("features", [])[:4]:
            if row["previous"] is not None:
                direction = "증가" if row["change"] > 0 else "감소" if row["change"] < 0 else "동일"
                facts.append(
                    f"두 시점 비교에서 {row['label']}: {direction}. "
                    "관측 차이이며 원인 판정은 아닙니다."
                )
        if "score" in signals.get("output_changes", {}):
            change = signals["output_changes"]["score"]
            facts.append(
                "선택 비교 시점 대비 모델 점수는 "
                + ("증가" if change > 0 else "감소" if change < 0 else "동일")
                + "입니다."
            )
    return {
        "asset_id": context.get("asset_id"),
        "recorded_replay": context.get("recorded_replay"),
        "event_start": context.get("event_start"),
        "output": output,
        "comparison": context.get("comparison"),
        "question": context.get("question"),
        "position": context.get("position"),
        "signal_comparison": signals,
        "related_models": [
            {
                **item,
                "output": {
                    key: value
                    for key, value in item["output"].items()
                    if key != "change_from_previous"
                },
                "previous_output": None
                if item.get("previous_output") is None
                else {
                    key: value
                    for key, value in item["previous_output"].items()
                    if key != "change_from_previous"
                },
            }
            for item in context.get("related_models", [])
        ],
        "value_label": label,
        "facts": facts,
    }


def _n(value: Any) -> str:
    """Readable stored number: 4 significant digits below 1, 2 decimals otherwise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, int):
        return str(value)
    return f"{value:.4g}" if abs(value) < 1 else f"{value:.2f}"


def explanation_facts(
    output: dict[str, Any],
    validation: Any,
    *,
    asset_id: str,
    recorded_replay: bool,
) -> list[str]:
    """Code-derived Korean statements the explanation must not reinterpret.

    A small local model misreads terse fields (for example "last-recorded-acquisition"),
    so every meaning and comparison is stated here from the stored values.
    """
    facts = [
        "기록 데이터 재생 결과입니다. 현재 현장에서 수신한 측정이 아닙니다."
        if recorded_replay
        else "재생으로 선언되지 않은 스트림의 결과입니다.",
    ]
    validation = validation if isinstance(validation, dict) else {}
    acceptance = validation.get("acceptance")
    facts.append(
        f"이 모델의 운영 합격 판정 기록: {acceptance}."
        if isinstance(acceptance, str)
        else (
            "이 모델 패키지에는 운영 합격 판정이 기록되어 있지 않습니다. "
            "합격·불합격을 언급하지 마세요."
        )
    )
    task = output.get("task")
    if task == "anomaly-score":
        score, threshold = output.get("score"), output.get("threshold")
        facts.append(
            f"이상 점수 {_n(score)}는 학습 기준 데이터와 얼마나 다른지를 나타내며 "
            "높을수록 더 다릅니다. "
            "고장 확률이나 진단이 아닙니다."
        )
        facts.append(
            f"점수 {_n(score)}는 임계값 {_n(threshold)}"
            + (
                " 를 초과했습니다. 고장 판정이 아닙니다."
                if output.get("exceeds_threshold")
                else " 이하입니다. 임계값 이하는 '정상' 판정이 아닙니다."
            )
        )
        contributions = output.get("feature_contributions")
        if isinstance(contributions, dict) and contributions:
            top = sorted(contributions.items(), key=lambda item: item[1], reverse=True)[:3]
            facts.append(
                "점수에 가장 크게 기여한 입력 특징(모델 잔차 기준): "
                + ", ".join(f"{name}={_n(value)}" for name, value in top)
            )
        else:
            facts.append(
                "이 모델은 변수별 기여도를 제공하지 않습니다. 원인 변수를 추정하지 마세요."
            )
        semantics = validation.get("score_semantics")
        if isinstance(semantics, str):
            facts.append(f"점수 의미(패키지 기록): {semantics}")
        if validation.get("evidence_class"):
            facts.append(
                "패키지의 검증 근거는 연구 평가 기록이며, 설명에서 '성능이 확인되었다'고 "
                "일반화하지 마세요."
            )
    applicability = output.get("applicability")
    facts.append(
        {
            "inside": "입력이 모델의 학습 운전 조건 안에 있습니다.",
            "outside": "입력이 모델의 학습 운전 조건 밖에 있습니다. 결과를 일반화하지 마세요.",
        }.get(str(applicability), "학습 운전 조건과 비교할 근거가 없습니다.")
    )
    return facts
