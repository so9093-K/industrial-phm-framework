# Operations bundled demo

This directory contains a small deterministic synthetic CSV snapshot for exercising the
current **Operations** FILE-source workflow without downloading an external dataset.

The signal is product-demo data only. It does **not** represent a real bearing condition,
fault, anomaly, degradation trajectory, remaining useful life, alarm, or maintenance need.

## Register the bundled FILE source

Start the canonical Operations application:

```bash
uv sync --locked --group research
uv run --no-sync marimo run src/industrial_phm/apps/operations.py
```

Open **Setup → Data Sources → Add data source** and register a FILE snapshot with these
explicit values:

- Source ID: `demo-bearing-snapshot`
- Name: `Bundled demo bearing snapshot`
- Asset: `demo-bearing-01`
- Measurement point: `drive-end`
- File: `examples/operations/demo-bearing-snapshot.csv`
- Mode: snapshot
- Time column: `timestamp`
- Signal: `vibration_x`
- Sampling rate: `1 Hz`
- Sampling-rate tolerance: `0.01`
- Minimum samples: `16`

Use the FILE discovery/validation step before saving. The bundled contract test verifies the
same file and mapping: 32 samples, explicit UTC timestamps, and one vibration channel.

Saving the source registers configuration only. It does not create a fault/health state and
does not start a background analysis process.

## Exercise the Operations flow

1. Open **Assets**, select `demo-bearing-01`, and choose **Analysis**.
2. Select the registered FILE snapshot and run **Analyze FILE snapshot**.
3. Open **Investigations**. Select the vibration-feature group and then the exact analysis
   evidence inside that group.
4. Inspect the stored waveform statistics and evidence identity. These features are not an
   anomaly/fault verdict.
5. Choose **Request review** if you want to exercise the explicit human-review workflow.
6. Open **Maintenance** and add a note, acknowledge, then close the review item.

The workflow demonstrates registration, persisted analysis evidence, investigation and
human-review persistence only. It is not a predictive-maintenance model validation demo.
