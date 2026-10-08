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

## Web UX wireframe (design review only)

[Open the standalone Operations Web UX wireframe](web-ux-wireframe.html) in a local browser.
No Python environment, network connection, dataset download, or server is required.
The file includes its own CSS and JavaScript, so it can also be reviewed before the Web API
and frontend runtime are built.

This artifact is **not** the current Operations app and has no backend integration.
It never reads source files, connects to OPC UA, starts collection, creates an analysis,
saves a review, or produces a health/fault verdict. All example identities, timestamps,
values, receipt states, and chart points are illustrative.

The top-left navigation switches among **첫 실행 / 관측 현황 / 데이터 연결**.
The **예시 상태** selector switches between **샘플 관측 기록 / 데이터 없음 / 마지막 관측
지연 / 조회 실패 / 수신 확인됨**. Change the window width to compare 1024px and
1440px; check the native input labels, visible keyboard focus, field-level validation,
separated receive/quality/asset semantics, and non-connected chart gap.

For an authoritative **current implementation** use the above marimo demo. Product
behavior/UX requirements live in [the Product and UX Baseline](../../docs/product/overview.md),
and the proposed Web UI architecture is [ADR-0024](../../docs/adr/0024-separate-operations-web-ui-from-marimo.md).
The conceptual HTML file is retained only as a review example and should be replaced or
retired when an accepted Web frontend prototype has equivalent coverage.
