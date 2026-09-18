from __future__ import annotations

import sys
from typing import Any

import pytest

torch = pytest.importorskip("torch", reason="install the deep-learning extra")
nn = torch.nn


class _CompatibilityAutoencoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = nn.LSTM(input_size=16, hidden_size=32, batch_first=True)
        self.decoder = nn.LSTM(input_size=32, hidden_size=32, batch_first=True)
        self.output = nn.Linear(32, 16)

    def forward(self, inputs: Any) -> Any:
        _, (hidden, _) = self.encoder(inputs)
        repeated_latent = hidden[-1].unsqueeze(1).repeat(1, inputs.shape[1], 1)
        decoded, _ = self.decoder(repeated_latent)
        return self.output(decoded)


def _run_seeded_update() -> tuple[float, tuple[Any, ...], Any]:
    torch.manual_seed(42)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)

    inputs = torch.randn(64, 8, 16, dtype=torch.float32, device="cpu")
    model = _CompatibilityAutoencoder().to(device="cpu", dtype=torch.float32)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=0.001,
        betas=(0.9, 0.999),
        eps=1e-8,
        weight_decay=0,
    )

    optimizer.zero_grad(set_to_none=True)
    reconstruction = model(inputs)
    loss = torch.mean((inputs - reconstruction) ** 2)
    assert torch.isfinite(loss)
    loss.backward()
    assert all(
        parameter.grad is not None and torch.isfinite(parameter.grad).all()
        for parameter in model.parameters()
    )
    gradient_norm = nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
    assert torch.isfinite(gradient_norm)
    optimizer.step()

    parameter_state = tuple(value.detach().clone() for value in model.state_dict().values())
    assert all(torch.isfinite(value).all() for value in parameter_state)
    return loss.item(), parameter_state, reconstruction.detach().clone()


def test_python_314_cpu_runtime_repeats_seeded_lstm_update_exactly() -> None:
    assert sys.version_info[:2] == (3, 14)
    assert torch.__version__.startswith("2.14.")

    original_deterministic_setting = torch.are_deterministic_algorithms_enabled()
    original_thread_count = torch.get_num_threads()
    try:
        loss_a, state_a, reconstruction_a = _run_seeded_update()
        loss_b, state_b, reconstruction_b = _run_seeded_update()
    finally:
        torch.use_deterministic_algorithms(original_deterministic_setting)
        torch.set_num_threads(original_thread_count)

    assert reconstruction_a.shape == (64, 8, 16)
    assert reconstruction_a.device.type == "cpu"
    assert reconstruction_a.dtype is torch.float32
    assert torch.isfinite(reconstruction_a).all()
    assert loss_a == loss_b
    assert torch.equal(reconstruction_a, reconstruction_b)
    assert all(torch.equal(left, right) for left, right in zip(state_a, state_b, strict=True))
