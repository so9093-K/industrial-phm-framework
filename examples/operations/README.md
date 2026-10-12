# Operations bundled FILE demo

This folder contains one **synthetic CSV snapshot**, not an actual bearing
condition or evidence of a fault, alarm, remaining useful life or maintenance.

## Run the current supervised Web

On the supported local Linux Operations pilot:

```bash
uv sync --locked --extra operations
make up
```

Open the **`/web/` URL** reported by the Operations supervisor. This is the
packaged Web operator UI, not the retired marimo app. Stop with `make down`.
The default workspace is `artifacts/operations` and can be changed using
`make up WORKSPACE=<path>`.

## Register the bundled CSV without guessing measurement meaning

Open **데이터 연결 → CSV 데이터 등록**. Use **내 PC에서 CSV 선택** for
`examples/operations/demo-bearing-snapshot.csv` (under 1 MiB); an arbitrary
repository path outside the workspace is **not** a supported relative-path
registration. The source is synthetic, so the following values are demo
identities rather than real machine metadata:

| Field | Value |
| --- | --- |
| Source ID | `demo-bearing-snapshot` |
| Name | `Bundled demo bearing snapshot` |
| Asset ID | `demo-bearing-01` |
| Measurement point | `drive-end` |
| Signal columns | `vibration_x` |
| Timestamp column | `timestamp` |
| Phase bindings | leave empty (vibration example, not three-phase voltage/current) |

Choose **CSV 분석 전 점검** and read the returned validation and timestamp
evidence before **CSV 확인 후 소스 등록**. Registration alone does not
prove receipt, history commit, a successful analysis or asset health.

## Verify actual receipt, history, analysis and human review

1. In **데이터 연결**, activate the registered FILE source and explicitly
   request **receive**. Verify accepted receipt evidence, not just registration.
2. Run the explicit FILE history backfill where supported; in **설비 · 신호**
   confirm stored observations, channel identity and UTC provenance.
3. Run the **FILE statistical feature analysis** action separately. Verify the
   resulting saved AnalysisRun and Evidence ID under **분석 근거**. This example
   expects 32 recorded samples and eight statistical features, not a fault score.
4. Request human review of that **exact saved evidence**. Under **정비 검토**,
   enter a note, acknowledge and close as separate actions. Closing human review
   is **not proof that physical maintenance occurred**.

The older **Setup → Investigations → Maintenance** marimo page sequence no
longer exists. The current Web workflow is intentionally bounded; full
Investigation/Maintenance parity is outside the current pilot; see
[current support](../../docs/status.md).

A separate contract test verifies that the included CSV passes the data
validator and produces the expected feature identities. It does not substitute
for the live Chromium user journey.
