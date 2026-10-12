"""Persist explanations of immutable PHM results without modifying model outputs."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_read import project_phm_bindings


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
            "finished_at TEXT, finding_id TEXT, warnings TEXT)"
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(explanation)")}
        if "warnings" not in columns:  # stores created before numeric grounding checks
            connection.execute("ALTER TABLE explanation ADD COLUMN warnings TEXT")
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
        warnings: list[str] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE explanation SET status=?, text=?, error=?, finished_at=?, warnings=? "
                "WHERE id=? AND owner=? AND status='pending'",
                (
                    "failed" if error else "complete",
                    text,
                    error,
                    datetime.now(UTC).isoformat(),
                    json.dumps(warnings or [], ensure_ascii=False),
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
) -> dict[str, Any]:
    result = store.get_result(binding_id, position)
    if result is None or result.state is not StepState.ANALYZED:
        raise ValueError("only persisted analyzed PHM results can be explained")
    binding = next(b for b in store.list_bindings() if b.binding_id == binding_id)
    summaries = project_phm_bindings(store, models_root, snapshots)
    package = next(
        item["package"] for item in summaries["bindings"] if item["binding_id"] == binding_id
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
            + (" 를 초과했습니다." if output.get("exceeds_threshold") else " 이하입니다.")
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
    elif task == "rul-estimate":
        estimate, unit = output.get("estimate"), output.get("unit")
        unit_text = "획득 간격" if unit == "acquisition-interval" else str(unit)
        facts.append(
            f"RUL 추정값 {_n(estimate)} {unit_text}는 데이터셋에서 마지막으로 기록된 획득까지 남은 "
            "간격의 추정입니다. 물리적 고장 시각이 아닙니다."
            if output.get("endpoint_semantics") == "last-recorded-acquisition"
            else (
                f"RUL 추정값 {_n(estimate)} {unit_text}의 종료점 의미: "
                f"{output.get('endpoint_semantics')}"
            )
        )
        if isinstance(estimate, (int, float)) and estimate < 0:
            facts.append(
                "추정값이 0보다 작습니다. 모델이 기록 종료점을 이미 지났다고 출력한 것이며, "
                "남은 수명이 음수라는 뜻이 아닙니다."
            )
        change = output.get("change_from_previous")
        if isinstance(change, (int, float)):
            facts.append(
                f"직전 추정 대비 변화는 {_n(change)} {unit_text}입니다. 획득 하나가 지날 때 "
                f"추정이 시간 경과와 일치하면 변화는 -1이므로, 이번 변화는 그보다 "
                f"{_n(abs(change + 1))} {unit_text} "
                + ("더 크게 감소했습니다." if change < -1 else "덜 감소했거나 증가했습니다.")
            )
        same = next(
            (
                item
                for item in validation.get("per_asset") or ()
                if isinstance(item, dict) and item.get("asset_id") == asset_id
            ),
            None,
        )
        if same is not None:
            facts.append(
                f"이 설비의 연구 검증 기록: MAE {_n(same.get('mean_absolute_error'))}, "
                f"편향 {_n(same.get('mean_signed_error'))} {unit_text}."
            )
        uncertainty = validation.get("uncertainty")
        if isinstance(uncertainty, str):
            facts.append(f"불확실성(패키지 기록): {uncertainty}. 신뢰구간을 만들지 마세요.")
    applicability = output.get("applicability")
    facts.append(
        {
            "inside": "입력이 모델의 학습 운전 조건 안에 있습니다.",
            "outside": "입력이 모델의 학습 운전 조건 밖에 있습니다. 결과를 일반화하지 마세요.",
        }.get(str(applicability), "학습 운전 조건과 비교할 근거가 없습니다.")
    )
    return facts
