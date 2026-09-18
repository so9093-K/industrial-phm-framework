import sys

import pytest

torch = pytest.importorskip("torch", reason="install the deep-learning extra")


def test_python_314_pytorch_214_cpu_runtime_contract() -> None:
    assert sys.version_info[:2] == (3, 14)
    assert torch.__version__.startswith("2.14.")

    tensor = torch.zeros((1, 8, 16), dtype=torch.float32, device="cpu")
    assert tensor.shape == (1, 8, 16)
    assert tensor.device.type == "cpu"
    assert tensor.dtype is torch.float32
    assert torch.isfinite(tensor).all()

    original_deterministic_setting = torch.are_deterministic_algorithms_enabled()
    try:
        torch.use_deterministic_algorithms(True)
        assert torch.are_deterministic_algorithms_enabled()
    finally:
        torch.use_deterministic_algorithms(original_deterministic_setting)
