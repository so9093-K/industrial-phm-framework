from dataclasses import asdict

import pytest

from industrial_phm.application.measurement_semantics import MeasurementDefinition

EXTRUDER = "7fd3a50f1222a695fc440ef2d4e8f2b431dd419b2249b60a6bc0ab34d5472a17"
COMPRESSOR = "ffde668bfab1d669fa7dc649fdcc9aaee30305af61c732852377c10818043119"
UNPROFILED = "0" * 64


def test_unresolved_property_is_not_a_raw_channel_label():
    assert asdict(MeasurementDefinition()) == {
        "observed_property": None,
        "scope": None,
        "statistic": None,
        "unit": None,
        "unit_evidence": None,
    }
    definition = MeasurementDefinition(
        observed_property="active_power", unit="kW", unit_evidence="manual"
    )
    assert definition.observed_property == "active_power"
    with pytest.raises(ValueError, match="evidence"):
        MeasurementDefinition(unit="kW")
    with pytest.raises(ValueError, match="empty"):
        MeasurementDefinition(observed_property=" ")


def test_aihub_dictionary_confirms_only_items_where_document_and_data_agree():
    from industrial_phm.adapters.aihub_power_history import (
        AIHUB_239_SEMANTICS_V1,
        AIHUB_239_SEMANTICS_V2,
        channel_definition,
    )

    def definition(version, channel, member="7.압출기/SourceData_127.json"):
        return channel_definition(version, channel, archive_sha256=EXTRUDER, member=member)

    frequency = definition(AIHUB_239_SEMANTICS_V2, "주파수")
    assert (frequency.observed_property, frequency.unit) == ("frequency", "Hz")
    assert definition(AIHUB_239_SEMANTICS_V2, "전류평균").statistic == (
        "arithmetic mean of phases R, S and T"
    )
    # Power, power factor and energy contradict their documented scale (and
    # power "평균" is a three-phase sum); temperature has no independent check.
    for channel in ("유효전력평균", "R상유효전력", "역률평균", "누적전력량", "온도"):
        assert definition(AIHUB_239_SEMANTICS_V2, channel) == MeasurementDefinition()
    # v2 leaves a channel unresolved where its supporting relation fails in that
    # member; v1 is kept unchanged for exact retry of imports that used it.
    failing = "7.압출기/SourceData_130.json"
    assert definition(AIHUB_239_SEMANTICS_V2, "R상전류", failing) == MeasurementDefinition()
    assert definition(AIHUB_239_SEMANTICS_V1, "R상전류", failing).unit == "A"


def test_semantics_v3_applies_meaning_only_inside_its_profiled_archive_scope():
    from industrial_phm.adapters.aihub_power_history import (
        AIHUB_239_SEMANTICS_V2,
        AIHUB_239_SEMANTICS_V3,
        interpret_channel,
    )

    def interpret(channel, archive, member, version=AIHUB_239_SEMANTICS_V3):
        return interpret_channel(version, channel, archive_sha256=archive, member=member)

    confirmed = interpret("R상전류", COMPRESSOR, "3.공기압축기/SourceData_112.json")
    assert (confirmed.definition.unit, confirmed.unresolved_reason) == ("A", None)
    # v2 exceptions are carried into v3 unchanged.
    assert interpret("R상전류", EXTRUDER, "7.압출기/SourceData_130.json").definition.unit is None

    # Compressor members whose relation median falls outside its tolerance.
    line_mean = interpret("선간전압평균", COMPRESSOR, "3.공기압축기/SourceData_34.json")
    assert line_mean.definition == MeasurementDefinition()
    assert line_mean.unresolved_reason.startswith("aihub-239-semantics-v3 member exception")
    assert "median 1.726" in line_mean.unresolved_reason
    phase_voltage = interpret("R상전압", COMPRESSOR, "3.공기압축기/SourceData_34.json")
    assert phase_voltage.definition.unit == "V"
    for channel in ("R상전류", "전류평균", "선간전압평균"):
        member = "3.공기압축기/SourceData_135.json"
        assert interpret(channel, COMPRESSOR, member).definition == MeasurementDefinition()

    # An archive nobody profiled keeps raw values but no canonical meaning.
    unknown = interpret("R상전류", UNPROFILED, "3.공기압축기/SourceData_112.json")
    assert unknown.definition == MeasurementDefinition()
    assert unknown.unresolved_reason == (
        "archive sha256 is outside the aihub-239-semantics-v3 profiled evidence scope"
    )
    # Published v2 is never edited, so it still lacks the compressor exceptions.
    member = "3.공기압축기/SourceData_135.json"
    assert interpret("R상전류", COMPRESSOR, member, AIHUB_239_SEMANTICS_V2).definition.unit == "A"

    power = interpret("R상유효전력", COMPRESSOR, "3.공기압축기/SourceData_112.json")
    assert power.definition == MeasurementDefinition()
    assert power.unresolved_reason == (
        "no evidenced canonical definition is published for this ITEM_NAME in "
        "aihub-239-semantics-v3"
    )


def test_published_semantics_versions_are_immutable():
    from industrial_phm.adapters.aihub_power_history import (
        AIHUB_239_SEMANTICS_DIGESTS,
        semantics_dictionary_digest,
    )

    # Stored observations keep their version forever. Changing a dictionary payload
    # requires a new version and a new pinned digest, never an edit.
    assert AIHUB_239_SEMANTICS_DIGESTS == {
        "aihub-239-semantics-v1": (
            "a90327d6d885480ca7b044dc704fb95aa14677b8713f75a4d9401b80178a054d"
        ),
        "aihub-239-semantics-v2": (
            "4cc29be9d2fc98e7f4531e0504414a848329794ac049c78b3d097fda7da0db7c"
        ),
        "aihub-239-semantics-v3": (
            "2df8cf5bfaeab39f22396ab1dc849db23483c4c4676d8515139b6a10c4d130b1"
        ),
    }
    for version, digest in AIHUB_239_SEMANTICS_DIGESTS.items():
        assert semantics_dictionary_digest(version) == digest
