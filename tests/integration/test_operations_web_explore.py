"""Signal exploration routes over a real workspace: acquisition features and stored history."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from importlib.util import find_spec
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlencode

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace

RMS = "feature.Horizontal_vibration_signals.rms"
BASE = datetime(2026, 10, 14, tzinfo=UTC)


def _serve(root: Path):
    server = create_operations_web_read_server(root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path: str, **query: Any) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            url = path + ("?" + urlencode(query, doseq=True) if query else "")
            connection.request("GET", url, headers={"Host": f"127.0.0.1:{server.server_port}"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)

    return get, stop


def test_acquisition_ranges_are_compared_by_their_stored_features(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale, amplitude_unit="g")
    analyze(workspace)
    get, stop = _serve(workspace.root)
    try:
        status, sources = get("/api/v1/explore/sources", asset_id="bearing-a")
        assert status == 200 and sources["history"] is None
        acquisition = sources["acquisition"]
        assert (acquisition["first"], acquisition["last"], acquisition["count"]) == (1, 8, 8)
        assert {"key": RMS, "label": "수평 진동 RMS"} in acquisition["features"]
        assert [m["task"] for m in acquisition["models"]] == ["anomaly-score", "anomaly-score"]

        status, body = get(
            "/api/v1/explore/profile",
            asset_id="bearing-a",
            kind="acquisition",
            series=[RMS],
            a_from=1,
            a_to=4,
            b_from=5,
            b_to=8,
        )
        assert status == 200 and body["periods"] == {
            "a": {"from": 1, "to": 4},
            "b": {"from": 5, "to": 8},
        }
        (series,) = body["series"]
        a, b = series["periods"]["a"], series["periods"]["b"]
        assert (a["observation_count"], a["usable_count"], a["missing_count"]) == (4, 4, 0)
        assert b["quantiles"][2] > a["quantiles"][2]
        assert series["unit"] == "g"
        assert series["comparison"]["b_outside_a_band"] == 4
        assert series["comparison"]["b_outside_a_band_percent"] == 100
        # A unit alone does not say "current": no measurement below 1 A is counted.
        assert "low_current" not in a and "low_current" not in b
        assert sum(series["histogram"]["a"]) == 4 and sum(series["histogram"]["b"]) == 4
        assert str(tmp_path) not in json.dumps(body)

        ranges = {"a_from": 1, "a_to": 4, "b_from": 5, "b_to": 8}
        status, relation = get(
            "/api/v1/explore/relation",
            asset_id="bearing-a",
            kind="acquisition",
            x=RMS,
            y="feature.Horizontal_vibration_signals.peak_to_peak",
            **ranges,
        )
        assert status == 200 and relation["pairing"] == "same-acquisition"
        assert relation["x_unit"] == relation["y_unit"] == "g"
        assert [g["pair_count"] for g in relation["groups"]] == [4, 4]
        assert all(
            group["binding_id"] == acquisition["binding_id"]
            and group["source_id"] == acquisition["source_id"]
            and group["measurement_point_id"] is None
            for group in relation["groups"]
        )
        assert relation["groups"][1]["points"][0][0] == 5

        status, spectrum = get("/api/v1/explore/spectrum", asset_id="bearing-a", **ranges)
        assert status == 200 and spectrum["sampling_rate_hz"] == 1000
        assert spectrum["acquisitions"] == {"a": [1, 2, 3, 4], "b": [5, 6, 7, 8]}
        horizontal = spectrum["channels"][0]
        assert horizontal["unit"] == "g²/Hz"
        assert len(horizontal["a"]) == len(horizontal["b"]) == len(spectrum["frequencies"])
        # B carries six times the amplitude of A: about 15 dB more power in its strongest band.
        assert max(band["change_db"] for band in horizontal["band_changes"]) > 10
        # Six times the amplitude is about 36 times the energy; each range's shares add up to 1.
        assert 25 < horizontal["power_ratio"] < 50
        for name in ("a", "b"):
            assert sum(band[name] for band in horizontal["band_shares"]) == pytest.approx(1)

        assert get("/api/v1/explore/profile", asset_id="bearing-a", kind="acquisition")[0] == 400
        bad = {"a_from": 4, "a_to": 1, "b_from": 5, "b_to": 8}
        query = {"asset_id": "bearing-a", "kind": "acquisition", "series": [RMS], **bad}
        assert get("/api/v1/explore/profile", **query)[0] == 400
        history = {"a_from": BASE.isoformat(), "a_to": BASE.isoformat()}
        query = {"asset_id": "bearing-a", "kind": "history", "series": ["x"], **history}
        assert get("/api/v1/explore/profile", **query)[0] == 404
    finally:
        stop()


def test_stored_history_periods_are_compared_from_raw_observations(tmp_path: Path) -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    events = [
        FileBackfillEvent(
            raw_evidence_id=f"file:motor:{'b' * 64}:{index}",
            source_id="motor-file",
            asset_id="motor-01",
            channel_id="current",
            source_file="motor.csv",
            source_sha256="b" * 64,
            source_size_bytes=10,
            sample_index=index,
            event_at=BASE + timedelta(minutes=index),
            value=10.0 + (5.0 if index >= 30 else 0.0) + (index % 3) * 0.1,
            source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
        )
        for index in range(60)
    ]
    # The voltage mapping changes from V to kV halfway through the second period.
    events += [
        FileBackfillEvent(
            raw_evidence_id=f"file:motor:{'b' * 64}:v{index}",
            source_id="motor-file",
            asset_id="motor-01",
            channel_id="voltage",
            source_file="motor.csv",
            source_sha256="b" * 64,
            source_size_bytes=10,
            sample_index=100 + index,
            event_at=BASE + timedelta(minutes=index),
            value=(380.0 + index) / (1000 if index >= 45 else 1),
            source_metadata_json='{"binding":{"definition":{"unit":"%s"}}}'
            % ("kV" if index >= 45 else "V"),
        )
        for index in range(60)
    ]
    history.append_file_batch(tuple(events), batch_id="motor")
    get, stop = _serve(workspace.root)
    try:
        status, sources = get("/api/v1/explore/sources", asset_id="motor-01")
        assert status == 200 and sources["acquisition"] is None
        assert sources["history"]["channels"] == ["current", "voltage"]
        assert sources["history"]["measurement_count"] == 120
        middle = BASE + timedelta(minutes=30)
        status, body = get(
            "/api/v1/explore/profile",
            asset_id="motor-01",
            kind="history",
            series=["current"],
            a_from=BASE.isoformat(),
            a_to=middle.isoformat(),
            b_from=middle.isoformat(),
            b_to=(BASE + timedelta(hours=1)).isoformat(),
        )
        assert status == 200
        (series,) = body["series"]
        assert series["unit"] == "A" and series["source_id"] == "motor-file"
        a, b = series["periods"]["a"], series["periods"]["b"]
        assert (a["usable_count"], b["usable_count"]) == (30, 30)
        assert a["median_interval_seconds"] == 60 and a["largest_gap"]["seconds"] == 60
        assert series["comparison"]["median_change"] == pytest.approx(5.0)
        assert series["comparison"]["b_outside_a_band_percent"] == 100
        status, relation = get(
            "/api/v1/explore/relation",
            asset_id="motor-01",
            kind="history",
            x="current",
            y="voltage",
            a_from=BASE.isoformat(),
            a_to=middle.isoformat(),
            b_from=middle.isoformat(),
            b_to=(BASE + timedelta(hours=1)).isoformat(),
        )
        assert status == 200
        units = sorted((g["period"], g["y_unit"], g["pair_count"]) for g in relation["groups"])
        assert units == [("a", "V", 30), ("b", "V", 15), ("b", "kV", 15)]
        assert (
            get(
                "/api/v1/explore/spectrum", asset_id="motor-01", a_from=1, a_to=2, b_from=3, b_to=4
            )[0]
            == 404
        )
        # Model-free comparison uses the same stored evidence as signal exploration.
        status, departures = get(
            "/api/v1/explore/anomaly",
            asset_id="motor-01",
            series=["current"],
            baseline="first-30",
        )
        assert status == 200
        assert departures["meaning"] == "departures-from-a-chosen-baseline-not-fault-diagnosis"
        assert departures["asset_id"] == "motor-01"
        assert departures["series"] == ["current"]
        assert departures["baseline"]["name"] == "first-30"
        assert departures["channels"][0]["state"] == "scored"
        assert departures["units"]["current"] == "A"
        assert departures["interval_count"] > 0
        assert all(interval["channel"] == "current" for interval in departures["intervals"])
        missing_status, missing = get("/api/v1/explore/anomaly", asset_id="unknown-asset")
        assert missing_status == 404 and missing["error"] == "nothing_to_explore"
    finally:
        stop()


def test_assets_whose_record_ends_away_from_its_baseline_are_named_for_a_look(
    tmp_path: Path,
) -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )

    def events(
        asset: str, step: float, count: int = 60, at: int = 40
    ) -> tuple[FileBackfillEvent, ...]:
        return tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:{asset}:{'c' * 64}:{index}",
                source_id=f"{asset}-file",
                asset_id=asset,
                channel_id="current",
                source_file=f"{asset}.csv",
                source_sha256="c" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                value=10.0 + (step if index >= at else 0.0) + (index % 3) * 0.1,
                source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
            )
            for index in range(count)
        )

    # One pump's current steps up and stays there; the other never moves.
    history.append_file_batch(events("pump-moved", 5.0), batch_id="moved")
    history.append_file_batch(events("pump-steady", 0.0), batch_id="steady")
    # A record long enough that coarser buckets would average it differently from the screen.
    history.append_file_batch(events("pump-long", 0.4, 2400, 1800), batch_id="long")
    get, stop = _serve(workspace.root)
    try:
        status, body = get("/api/v1/explore/attention")
        assert status == 200 and body["baseline"] == "first-30"
        long_item, item = body["items"]
        assert long_item["asset_id"] == "pump-long"
        _, long_screen = get(
            "/api/v1/explore/anomaly", asset_id="pump-long", series="current", baseline="first-30"
        )
        assert long_screen["score"][-1][1] == long_item["distance"]
        assert item["asset_id"] == "pump-moved" and item["channel"] == "current"
        assert item["unit"] == "A" and item["direction"] == "up" and item["distance"] >= 3.5
        # The note says the range the end was judged against in amperes, not a multiple of it.
        assert item["usual"]["low"] < item["usual"]["high"]
        # "Since" is the start of the bucket the step falls in, in UTC.
        since = datetime.fromisoformat(item["since"])
        assert since.utcoffset() == timedelta(0)
        assert BASE + timedelta(minutes=39) <= since <= BASE + timedelta(minutes=40)
        # The 기준 구간 이탈 screen for that signal names the same distance and the same start.
        _, screen = get(
            "/api/v1/explore/anomaly", asset_id="pump-moved", series="current", baseline="first-30"
        )
        assert screen["score"][-1][1] == item["distance"]
        latest = max(screen["intervals"], key=lambda interval: interval["end"])
        assert datetime.fromisoformat(latest["start"]) == since
        # The same record asked again is answered from the stored check.
        assert get("/api/v1/explore/attention")[1] == body
        # A screen asks for one asset only; an asset that stays put has nothing to name.
        assert [
            row["asset_id"]
            for row in get("/api/v1/explore/attention", asset_id="pump-moved")[1]["items"]
        ] == ["pump-moved"]
        assert get("/api/v1/explore/attention", asset_id="pump-steady")[1]["items"] == []
        # A record that keeps growing (a live source) is not checked again on every read.
        history.append_file_batch(events("pump-moved", 5.0, 61, 40)[60:], batch_id="moved-one-more")
        (reused,) = get("/api/v1/explore/attention", asset_id="pump-moved")[1]["items"]
        assert reused["distance"] == item["distance"]
        # ...and it still names the record end it judged, not the newer one.
        assert reused["last_at"] == item["last_at"] == (BASE + timedelta(minutes=59)).isoformat()
    finally:
        stop()


def test_the_summary_names_what_the_record_held_even_when_it_ends_as_it_began(
    tmp_path: Path,
) -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    phase = '{"binding":{"definition":{"observed_property":"phase current","unit":"A"}}}'
    # A compressor runs near 60 A, stops (0 A) from minute 60 to 90, then runs as before.
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:comp:{'d' * 64}:{index}",
                source_id="comp-file",
                asset_id="comp-01",
                channel_id="R상전류",
                source_file="comp.csv",
                source_sha256="d" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                value=0.0 if 60 <= index < 90 else 60.0 + (index % 5) * 0.5,
                source_metadata_json=phase,
            )
            for index in range(120)
        ),
        batch_id="comp",
    )
    # T상전류 reads exactly 60 A until the stop, so its baseline has no spread at all.
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:comp:{'d' * 64}:t{index}",
                source_id="comp-file",
                asset_id="comp-01",
                channel_id="T상전류",
                source_file="comp.csv",
                source_sha256="d" * 64,
                source_size_bytes=10,
                sample_index=1000 + index,
                event_at=BASE + timedelta(minutes=index),
                value=0.0 if 60 <= index < 90 else 60.0,
                source_metadata_json=phase,
            )
            for index in range(120)
        ),
        batch_id="comp-t",
    )
    get, stop = _serve(workspace.root)
    try:
        # 관측 현황 asks whether the record ends away from its start: it does not.
        assert get("/api/v1/explore/attention", asset_id="comp-01")[1]["items"] == []
        # The summary asks what the record held: the stop, named as observed.
        status, found = get("/api/v1/explore/findings", asset_id="comp-01")
        assert status == 200
        assert found["meaning"] == "departures-from-the-first-30-percent-not-fault-diagnosis"
        assert [(row["label"], row["state"]) for row in found["signals"]] == [
            ("R상전류", "scored"),
            ("T상전류", "level-change"),
        ]
        assert found["judged"] == 2 and found["unchecked"] == 0
        # A constant baseline still exposes its level change and observed values.
        held = found["signals"][1]
        assert held["held"] == 60.0 and held["later"] == {"low": 0.0, "high": 60.0}
        assert found["interval_count"] >= 1 and found["bucket_seconds"] > 0
        stop_interval = found["intervals"][0]
        assert stop_interval["direction"] == "down" and stop_interval["value"] == 0.0
        assert stop_interval["unit"] == "A" and stop_interval["within"] == ["T상전류"]
        assert stop_interval["usual"]["low"] < 60 < stop_interval["usual"]["high"]
        start = datetime.fromisoformat(stop_interval["start"])
        assert BASE + timedelta(minutes=59) <= start <= BASE + timedelta(minutes=60)
        assert get("/api/v1/explore/findings", asset_id="comp-01")[1] == found
        assert get("/api/v1/explore/findings", asset_id="unknown")[1]["intervals"] == []
        # A declared current in A also counts, per period, the measurements below 1 A.
        middle = BASE + timedelta(minutes=60)
        status, body = get(
            "/api/v1/explore/profile",
            asset_id="comp-01",
            kind="history",
            series=["R상전류"],
            a_from=BASE.isoformat(),
            a_to=middle.isoformat(),
            b_from=middle.isoformat(),
            b_to=(BASE + timedelta(hours=2)).isoformat(),
        )
        assert status == 200
        (series,) = body["series"]
        assert series["periods"]["a"]["low_current"] == {"below": 1.0, "count": 0}
        assert series["periods"]["b"]["low_current"] == {"below": 1.0, "count": 30}
    finally:
        stop()


def test_all_signals_are_checked_even_when_nothing_could_be_judged(
    tmp_path: Path,
) -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    # Even the thirteenth signal is read; empty input is distinct from an unchecked signal.
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:empty:{'e' * 64}:{channel}:{index}",
                source_id="empty-file",
                asset_id="empty-01",
                channel_id=f"s{channel:02d}",
                source_file="empty.csv",
                source_sha256="e" * 64,
                source_size_bytes=10,
                sample_index=channel * 100 + index,
                event_at=BASE + timedelta(minutes=index),
                value=None,
            )
            for channel in range(13)
            for index in range(20)
        ),
        batch_id="empty",
    )
    get, stop = _serve(workspace.root)
    try:
        status, found = get("/api/v1/explore/findings", asset_id="empty-01")
        assert status == 200
        assert found["judged"] == 0 and found["intervals"] == []
        assert len(found["signals"]) == 13 and found["unchecked"] == 0
        assert {row["state"] for row in found["signals"]} == {"no-values"}
    finally:
        stop()


def test_a_steady_rise_is_a_finding_unless_the_source_declares_a_running_total(
    tmp_path: Path,
) -> None:
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    # Both rise in every step; only the energy register's name says it is a running total.
    rising = {"온도": lambda i: 40 + 0.2 * i, "누적전력량": lambda i: 1000.0 + 5 * i}
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:rise:{'a' * 64}:{channel}:{index}",
                source_id="rise-file",
                asset_id="rise-01",
                channel_id=channel,
                source_file="rise.csv",
                source_sha256="a" * 64,
                source_size_bytes=10,
                sample_index=offset * 100 + index,
                event_at=BASE + timedelta(minutes=index),
                value=value(index),
            )
            for offset, (channel, value) in enumerate(rising.items())
            for index in range(100)
        ),
        batch_id="rise",
    )
    get, stop = _serve(workspace.root)
    try:
        status, found = get("/api/v1/explore/findings", asset_id="rise-01")
        assert status == 200
        states = {row["channel"]: row for row in found["signals"]}
        assert states["온도"]["state"] != "cumulative"
        assert states["누적전력량"]["state"] == "cumulative"
        assert (states["누적전력량"]["first"], states["누적전력량"]["last"]) == (1000.0, 1495.0)
        assert [item["channel"] for item in found["intervals"]] == ["온도"]
    finally:
        stop()


def test_findings_cover_all_signals_and_compare_only_the_same_measurement_source(
    tmp_path: Path,
) -> None:
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    events = []
    for channel in range(35):
        for index in range(100):
            value = 1.0 + (index % 3) * 0.1
            if 40 <= index < 70 and channel >= 32:
                value = 40.0 if channel == 34 else 5.0
            events.append(
                FileBackfillEvent(
                    raw_evidence_id=f"file:all:{'f' * 64}:{channel}:{index}",
                    source_id="different" if channel == 33 else "shared",
                    asset_id="all-signals",
                    channel_id=f"signal-{channel:02}",
                    source_file="all.csv",
                    source_sha256="f" * 64,
                    source_size_bytes=10,
                    sample_index=channel * 100 + index,
                    event_at=BASE + timedelta(minutes=index),
                    value=value,
                )
            )
    history.append_file_batch(tuple(events), batch_id="all")
    get, stop = _serve(workspace.root)
    try:
        status, found = get("/api/v1/explore/findings", asset_id="all-signals")
        assert status == 200 and found["judged"] == 35 and found["unchecked"] == 0
        change = found["intervals"][0]
        assert change["channel"] == "signal-34" and change["reason"] == "sustained"
        assert change["reference_value"] == pytest.approx(1.1)
        assert change["typical_value"] == 40.0
        related = {row["channel"]: row["state"] for row in change["related"]}
        assert related["signal-32"] == "higher"
        assert "within" in related.values()
        assert "signal-33" not in related  # A different source is not a simultaneous comparison.
    finally:
        stop()


def test_a_change_on_an_electrical_asset_always_says_what_the_current_did() -> None:
    from industrial_phm.runtime.operations_web_explore import related

    def row(channel: str, current: bool = False) -> dict[str, object]:
        return {"channel": channel, "current_signal": current}

    # Compressor 1338 stopping: power factors fall furthest, the current falls less far.
    changed = [row("T상역률"), row("역률평균"), row("R상전류", current=True)]
    similar = [row("T상전압고조파")]
    assert [item["channel"] for item in related(changed, similar)] == [
        "T상역률",
        "역률평균",
        "T상전압고조파",
        "R상전류",
    ]
    # Without a current signal nothing is added.
    assert len(related(changed[:2], similar)) == 3


def test_adding_another_source_does_not_change_existing_findings(tmp_path: Path) -> None:
    from industrial_phm.runtime.operations_web_explore import record_findings

    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )

    def append(
        source: str, point: str | None, start: datetime, count: int, changing: bool | None
    ) -> None:
        history.append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:{source}:{point}:{'a' * 64}:{i}",
                    source_id=source,
                    asset_id="motor",
                    channel_id="temperature",
                    source_file=source + ".csv",
                    source_sha256="a" * 64,
                    source_size_bytes=10,
                    sample_index=i,
                    event_at=start + timedelta(minutes=i),
                    value=None if changing is None else float(100 if changing and i >= 60 else 0),
                    measurement_point_id=point,
                )
                for i in range(count)
            ),
            batch_id=f"{source}-{point}",
        )

    append("b", "bearing", BASE, 120, True)
    original = record_findings(workspace, "motor")["intervals"]
    assert len(original) == 1 and original[0]["kind"] == "level-change"
    # A far longer stable source must not coarsen B's grid, baseline or result identity.
    append("a", None, BASE - timedelta(days=5), 800, False)
    mixed = record_findings(workspace, "motor")
    assert mixed["intervals"] == original
    # Another point in the same source is a separate record, even with an identical channel.
    append("b", "motor", BASE + timedelta(days=1), 120, True)
    mixed = record_findings(workspace, "motor")
    assert {row["measurement_point_id"] for row in mixed["intervals"]} == {"bearing", "motor"}
    assert mixed["baseline"] is None
    get, stop = _serve(workspace.root)
    try:
        chosen = original[0]
        status, body = get(
            "/api/v1/explore/anomaly",
            asset_id="motor",
            series="temperature",
            record_key=chosen["key"],
        )
        assert status == 200 and body["record"]["measurement_point_id"] == "bearing"
        assert {key: body["baseline"][key] for key in ("from", "to")} == chosen["baseline"]
        assert body["intervals"][0]["start"] == chosen["start"]
        assert len(body["records"]) == 3
        # An empty record stays selectable but cannot mask usable records on the first visit.
        append("0-empty", None, BASE, 30, None)
        status, default = get("/api/v1/explore/anomaly", asset_id="motor", series="temperature")
        assert status == 200 and default["record"]["source_id"] != "0-empty"
        assert any(record["source_id"] == "0-empty" for record in default["records"])
    finally:
        stop()
