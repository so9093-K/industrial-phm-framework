"""A synthetic cooling-pump CSV as field loggers export it: one minute apart, no timezone.

Three days of current, motor temperature, vibration and pressure; a trend starts late on the
second day. Used to capture the CSV use case in assets/csv/. Not a real equipment record.

    uv run --no-sync python -m tools.assets.pump_csv OUT.csv
"""

from __future__ import annotations

import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path


def write(path: Path, *, days: int = 3, seed: int = 7) -> None:
    rng = random.Random(seed)
    start = datetime(2026, 10, 15)
    lines = ["timestamp,current_a,motor_temp_c,vibration_mm_s,pressure_bar"]
    for minute in range(days * 24 * 60):
        day = minute / 1440
        wear = max(0.0, day - 1.6)
        load = 1 + 0.08 * math.sin(2 * math.pi * (minute % 1440) / 1440)
        values = (
            12.0 * load + rng.gauss(0, 0.15) + 0.9 * wear,
            48 + 40 * (load - 1) + rng.gauss(0, 0.3) + 6.5 * wear**1.5,
            2.1 + rng.gauss(0, 0.08) + 1.8 * wear**2,
            4.2 + rng.gauss(0, 0.03) - 0.05 * wear,
        )
        at = (start + timedelta(minutes=minute)).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(at + "," + ",".join(f"{value:.3f}" for value in values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write(Path(sys.argv[1]))
