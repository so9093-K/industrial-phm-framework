from pathlib import Path


def test_systemd_reference_unit_preserves_supervisor_ownership() -> None:
    unit = Path("deploy/systemd/industrial-phm-operations.service.example").read_text(
        encoding="utf-8"
    )

    assert "validate deployment /var/lib/industrial-phm/plant-a" in unit
    assert "operations start /var/lib/industrial-phm/plant-a" in unit
    assert "Restart=on-failure" in unit
    assert "RestartSec=5s" in unit
    assert "StartLimitIntervalSec=60" in unit
    assert "StartLimitBurst=5" in unit
    assert "KillMode=mixed" in unit
    assert "TimeoutStopSec=60s" in unit
    assert "UMask=0077" in unit
    assert "NoNewPrivileges=yes" in unit
