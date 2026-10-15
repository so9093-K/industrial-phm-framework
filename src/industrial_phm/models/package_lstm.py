"""Restore the research LSTM autoencoder from numeric state and score causal sequences."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any, cast

import numpy as np

from industrial_phm.models.package import EstimatorKind, ModelPackageError


def restore_lstm_estimator(
    kind: EstimatorKind, state: Mapping[str, Any]
) -> tuple[Callable[[np.ndarray], np.ndarray], Callable[[np.ndarray], np.ndarray] | None]:
    try:
        torch = import_module("torch")
    except ModuleNotFoundError as error:
        raise ModelPackageError("LSTM execution requires the deep-learning extra") from error
    try:
        if kind is not EstimatorKind.LSTM_AUTOENCODER:
            raise ValueError(f"unsupported LSTM estimator {kind.value}")
        implementation = import_module("industrial_phm.models.lstm_autoencoder")
        parameters = implementation._parse_parameters(state["model_parameters"])
        width = int(state["input_size"])
        if not 1 <= width <= 4096:
            raise ValueError("invalid LSTM feature width")
        with torch.random.fork_rng(devices=[]):
            module = implementation._build_module(torch, input_size=width, parameters=parameters)
        tensors = {
            name: torch.tensor(value, dtype=torch.float32, device="cpu")
            for name, value in state["weights"].items()
        }
        if not all(bool(torch.isfinite(t).all()) for t in tensors.values()):
            raise ValueError("non-finite LSTM weights")
        module.load_state_dict(tensors, strict=True)
        module.eval()
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise ModelPackageError(f"invalid numeric LSTM state: {error}") from error
    length = parameters.sequence_length

    def residuals(rows: np.ndarray) -> np.ndarray:
        if rows.ndim != 2 or rows.shape[1] != length * width:
            raise ModelPackageError("LSTM input must match sequence length and feature width")
        original_threads = torch.get_num_threads()
        original_determinism = torch.are_deterministic_algorithms_enabled()
        results = []
        try:
            torch.set_num_threads(1)
            torch.use_deterministic_algorithms(True)
            with torch.inference_mode():
                # One fixed-sized sequence per call makes results independent of batching.
                for row in rows:
                    inputs = torch.tensor(row.reshape(1, length, width), dtype=torch.float32)
                    if not bool(torch.isfinite(inputs).all()):
                        raise ModelPackageError("LSTM input is not finite in float32")
                    outputs = module(inputs)
                    if not bool(torch.isfinite(outputs).all()):
                        raise ModelPackageError("LSTM produced non-finite outputs")
                    error = inputs.numpy().astype(np.float64) - outputs.numpy().astype(np.float64)
                    results.append((error * error).mean(axis=1)[0] / width)
        finally:
            torch.use_deterministic_algorithms(original_determinism)
            torch.set_num_threads(original_threads)
        return cast(np.ndarray, np.asarray(results, dtype=np.float64))

    return lambda rows: residuals(rows).sum(axis=1), residuals
