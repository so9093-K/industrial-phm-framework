# ADR-0006: CPU reference deep-learning runtime으로 PyTorch 사용

- Status: Accepted
- Date: 2026-09-18

## Context

XJTU LSTM Autoencoder protocol v1은 Python 3.14에서 `[batch, 8, 16]` float32 sequence를 입력으로 사용하고,
hidden size 32인 encoder/decoder LSTM, Adam update와 global-norm gradient clipping을 CPU deterministic mode에서
실행하도록 고정합니다. Numerical implementation 전에 이 계약을 pre-built wheel, dependency lock, package extra와
CI에서 실제로 실행할 수 있는 runtime을 선택해야 합니다.

Runtime 선택은 canonical time-series와 sequence/window public contract의 representation을 결정하지 않습니다.
Native tensor는 model implementation 경계 안에서 사용하고 dataset edge와 공통 contract는 runtime에 독립적으로
유지합니다.

## Decision

Deep-learning model runtime으로 PyTorch 2.14 series를 사용합니다.

- `deep-learning` package extra가 PyTorch dependency를 소유합니다.
- uv project와 CI는 PyTorch 공식 CPU wheel index를 사용해 Linux에서 CUDA dependency가 포함되지 않도록 합니다.
- Reference execution은 CPU, float32, fixed seed와 `torch.use_deterministic_algorithms(True)`를 사용합니다.
- Runtime version, device, dtype, seed와 deterministic setting은 experiment artifact provenance에 기록합니다.
- Compatibility contract는 protocol과 같은 input shape의 encoder/decoder LSTM forward/backward, Adam update,
  gradient clipping과 same-runtime exact repeat를 검증합니다.

PyTorch 2.14 CPU wheel은 CPython 3.14.7/macOS arm64에서 위 contract를 실행했고, 같은 process에서 반복한 loss,
reconstruction과 updated parameter state가 일치했습니다. Linux x86_64 CPU wheel 설치와 같은 contract는 CI가
검증합니다.

## Alternatives Considered

- TensorFlow: 공식 pip compatibility 범위가 Python 3.13까지이므로 현재 Python 3.14 기준선과 맞지 않습니다.
- JAX: Linux x86_64와 macOS arm64 CPU wheel을 제공하지만 LSTM module과 optimizer를 위해 별도 neural-network
  layer를 함께 선택해야 합니다. 현재 protocol은 PyTorch의 built-in LSTM과 optimizer로 직접 표현됩니다.

## Consequences

- Isolation Forest와 data workflow 사용자는 `deep-learning` extra를 설치하지 않아도 됩니다.
- Repository lock은 macOS와 Linux 모두 CPU build를 사용하며 accelerator별 dependency graph를 추가하지 않습니다.
- Reproducibility 주장은 같은 PyTorch release, platform과 device의 reference execution 범위로 제한합니다. 서로 다른
  release, platform 또는 CPU/GPU 사이의 bitwise identity를 주장하지 않습니다.
- GPU execution 요구가 생기면 accelerator-specific wheel, deterministic behavior와 evidence comparability를 별도
  결정으로 검증합니다.
