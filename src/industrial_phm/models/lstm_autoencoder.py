"""Dataset-neutral deterministic LSTM Autoencoder fitting and reconstruction."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

from industrial_phm.experiments.config import ExperimentConfig, ModelFamily
from industrial_phm.sequences import SequenceConstruction, SequenceWindowSpec

_MODEL_PARAMETER_NAMES = {
    "sequence_length",
    "hidden_size",
    "layer_count",
    "dropout",
    "loss",
    "optimizer",
    "learning_rate",
    "adam_beta1",
    "adam_beta2",
    "adam_epsilon",
    "weight_decay",
    "gradient_clip_norm",
    "batch_size",
    "epochs",
    "shuffle",
    "checkpoint",
    "numeric_precision",
    "device",
    "deterministic_algorithms",
}
_SAMPLING_POLICY_ID = "reference-window-uniform-v1"


class LstmAutoencoderError(ValueError):
    """Raised when LSTM configuration, windows, or numerical execution is invalid."""


@dataclass(frozen=True, slots=True)
class LstmAutoencoderTrainingProvenance:
    """Runtime and optimization facts produced by one completed model fit."""

    runtime: str
    runtime_version: str
    device: str
    numeric_precision: str
    deterministic_algorithms: bool
    random_seed: int
    sampling_policy_id: str
    fit_window_count: int
    parameter_count: int
    batch_size: int
    epochs: int
    epoch_losses: Sequence[float]

    def __post_init__(self) -> None:
        for field_name in (
            "runtime",
            "runtime_version",
            "device",
            "numeric_precision",
            "sampling_policy_id",
        ):
            _validate_text(getattr(self, field_name), field_name)
        if not isinstance(self.deterministic_algorithms, bool):
            raise LstmAutoencoderError("deterministic_algorithms must be a boolean")
        if (
            isinstance(self.random_seed, bool)
            or not isinstance(self.random_seed, int)
            or self.random_seed < 0
        ):
            raise LstmAutoencoderError("random_seed must be a non-negative integer")
        for field_name in ("fit_window_count", "parameter_count", "batch_size", "epochs"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise LstmAutoencoderError(f"{field_name} must be a positive integer")
        epoch_losses = _finite_values(self.epoch_losses, "epoch_losses")
        if len(epoch_losses) != self.epochs:
            raise LstmAutoencoderError("epoch_losses must contain one value per epoch")
        if any(loss < 0.0 for loss in epoch_losses):
            raise LstmAutoencoderError("epoch_losses must be non-negative")
        object.__setattr__(self, "epoch_losses", epoch_losses)

    @property
    def final_loss(self) -> float:
        """Return the fixed final-epoch training loss."""
        return self.epoch_losses[-1]


@dataclass(frozen=True, slots=True)
class SequenceReconstructions:
    """Model reconstructions aligned to immutable source window identities."""

    experiment_id: str
    feature_set_id: str
    feature_names: Sequence[str]
    spec: SequenceWindowSpec
    window_ids: Sequence[str]
    sequence_ids: Sequence[str]
    asset_ids: Sequence[str]
    partition_ids: Sequence[str]
    aligned_source_observation_ids: Sequence[str]
    values: Sequence[Sequence[Sequence[float]]]

    def __post_init__(self) -> None:
        _validate_text(self.experiment_id, "experiment_id")
        _validate_text(self.feature_set_id, "feature_set_id")
        feature_names = _validated_names(self.feature_names, "feature_names")
        if not isinstance(self.spec, SequenceWindowSpec):
            raise LstmAutoencoderError("spec must be a SequenceWindowSpec")

        identity_fields = (
            "window_ids",
            "sequence_ids",
            "asset_ids",
            "partition_ids",
            "aligned_source_observation_ids",
        )
        identities: dict[str, tuple[str, ...]] = {}
        for field_name in identity_fields:
            values = tuple(getattr(self, field_name))
            if not values:
                raise LstmAutoencoderError(f"{field_name} must contain at least one value")
            for value in values:
                _validate_text(value, field_name)
            identities[field_name] = values

        reconstruction_values = tuple(
            tuple(
                _finite_values(row, f"reconstruction window {window_index} row {row_index}")
                for row_index, row in enumerate(window)
            )
            for window_index, window in enumerate(self.values)
        )
        window_count = len(reconstruction_values)
        if not window_count:
            raise LstmAutoencoderError("reconstruction values must contain at least one window")
        if any(len(values) != window_count for values in identities.values()):
            raise LstmAutoencoderError(
                "reconstruction identities and values must contain the same window count"
            )
        if len(set(identities["aligned_source_observation_ids"])) != window_count:
            raise LstmAutoencoderError(
                "aligned_source_observation_ids must be unique within reconstructions"
            )
        for window_index, window in enumerate(reconstruction_values):
            if len(window) != self.spec.length:
                raise LstmAutoencoderError(
                    f"reconstruction window {window_index} must contain {self.spec.length} rows"
                )
            if any(len(row) != len(feature_names) for row in window):
                raise LstmAutoencoderError(
                    f"reconstruction window {window_index} feature width must be "
                    f"{len(feature_names)}"
                )

        object.__setattr__(self, "feature_names", feature_names)
        for field_name, values in identities.items():
            object.__setattr__(self, field_name, values)
        object.__setattr__(self, "values", reconstruction_values)

    @property
    def window_count(self) -> int:
        """Return the number of reconstructed windows."""
        return len(self.values)


@dataclass(frozen=True, slots=True)
class FittedLstmAutoencoder:
    """Final-epoch LSTM Autoencoder bound to its fit schema and runtime provenance."""

    experiment_id: str
    feature_set_id: str
    feature_names: Sequence[str]
    spec: SequenceWindowSpec
    hidden_size: int
    layer_count: int
    sampling_policy_id: str
    training: LstmAutoencoderTrainingProvenance
    _batch_size: int = field(repr=False)
    _module: Any = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_text(self.experiment_id, "experiment_id")
        _validate_text(self.feature_set_id, "feature_set_id")
        feature_names = _validated_names(self.feature_names, "feature_names")
        if not isinstance(self.spec, SequenceWindowSpec):
            raise LstmAutoencoderError("spec must be a SequenceWindowSpec")
        _positive_int(self.hidden_size, "hidden_size")
        _positive_int(self.layer_count, "layer_count")
        _validate_text(self.sampling_policy_id, "sampling_policy_id")
        if not isinstance(self.training, LstmAutoencoderTrainingProvenance):
            raise LstmAutoencoderError("training must be LstmAutoencoderTrainingProvenance")
        _positive_int(self._batch_size, "batch_size")
        if self.training.sampling_policy_id != self.sampling_policy_id:
            raise LstmAutoencoderError("training sampling_policy_id must match the fitted LSTM")
        if self.training.batch_size != self._batch_size:
            raise LstmAutoencoderError("training batch_size must match the fitted LSTM")
        object.__setattr__(self, "feature_names", feature_names)

    def reconstruct(self, construction: SequenceConstruction) -> SequenceReconstructions:
        """Reconstruct windows in source order without producing anomaly scores."""
        _validate_construction_context(
            construction,
            feature_set_id=self.feature_set_id,
            feature_names=self.feature_names,
            spec=self.spec,
        )
        torch = _require_torch()
        inputs = _construction_tensor(torch, construction)
        self._module.eval()
        reconstructed_batches: list[Any] = []
        original_deterministic_setting = torch.are_deterministic_algorithms_enabled()
        original_thread_count = torch.get_num_threads()
        try:
            torch.use_deterministic_algorithms(self.training.deterministic_algorithms)
            torch.set_num_threads(1)
            with torch.inference_mode():
                for start in range(0, construction.window_count, self._batch_size):
                    batch = inputs[start : start + self._batch_size]
                    reconstructed = self._module(batch)
                    if not bool(torch.isfinite(reconstructed).all()):
                        raise LstmAutoencoderError("LSTM reconstruction contains non-finite values")
                    reconstructed_batches.append(reconstructed)
        finally:
            torch.use_deterministic_algorithms(original_deterministic_setting)
            torch.set_num_threads(original_thread_count)
        values = torch.cat(reconstructed_batches, dim=0).to(device="cpu").tolist()
        return SequenceReconstructions(
            experiment_id=self.experiment_id,
            feature_set_id=self.feature_set_id,
            feature_names=self.feature_names,
            spec=self.spec,
            window_ids=tuple(window.window_id for window in construction.windows),
            sequence_ids=tuple(window.sequence_id for window in construction.windows),
            asset_ids=tuple(window.asset_id for window in construction.windows),
            partition_ids=tuple(window.partition_id for window in construction.windows),
            aligned_source_observation_ids=tuple(
                window.aligned_source_observation_id for window in construction.windows
            ),
            values=values,
        )


@dataclass(frozen=True, slots=True)
class _LstmAutoencoderParameters:
    sequence_length: int
    hidden_size: int
    layer_count: int
    dropout: float
    loss: str
    optimizer: str
    learning_rate: float
    adam_beta1: float
    adam_beta2: float
    adam_epsilon: float
    weight_decay: float
    gradient_clip_norm: float
    batch_size: int
    epochs: int
    shuffle: bool
    checkpoint: str
    numeric_precision: str
    device: str
    deterministic_algorithms: bool


def fit_lstm_autoencoder(
    config: ExperimentConfig,
    construction: SequenceConstruction,
) -> FittedLstmAutoencoder:
    """Fit the configured LSTM Autoencoder once over every reference window per epoch."""
    parameters = _parse_parameters(config.model_parameters)
    _validate_fit_context(config, construction, parameters)
    torch = _require_torch()
    inputs = _construction_tensor(torch, construction)

    original_deterministic_setting = torch.are_deterministic_algorithms_enabled()
    original_thread_count = torch.get_num_threads()
    try:
        torch.use_deterministic_algorithms(parameters.deterministic_algorithms)
        torch.set_num_threads(1)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(config.random_seed)
            module = _build_module(
                torch,
                input_size=len(construction.feature_names),
                parameters=parameters,
            ).to(device=parameters.device, dtype=torch.float32)
            optimizer = torch.optim.Adam(
                module.parameters(),
                lr=parameters.learning_rate,
                betas=(parameters.adam_beta1, parameters.adam_beta2),
                eps=parameters.adam_epsilon,
                weight_decay=parameters.weight_decay,
            )
            shuffle_generator = torch.Generator(device="cpu")
            shuffle_generator.manual_seed(config.random_seed)
            epoch_losses = _train(
                torch,
                module,
                optimizer,
                inputs,
                parameters=parameters,
                shuffle_generator=shuffle_generator,
            )
    finally:
        torch.use_deterministic_algorithms(original_deterministic_setting)
        torch.set_num_threads(original_thread_count)

    parameter_count = sum(parameter.numel() for parameter in module.parameters())
    training = LstmAutoencoderTrainingProvenance(
        runtime="pytorch",
        runtime_version=str(torch.__version__),
        device=parameters.device,
        numeric_precision=parameters.numeric_precision,
        deterministic_algorithms=parameters.deterministic_algorithms,
        random_seed=config.random_seed,
        sampling_policy_id=config.sampling_policy_id,
        fit_window_count=construction.window_count,
        parameter_count=parameter_count,
        batch_size=parameters.batch_size,
        epochs=parameters.epochs,
        epoch_losses=epoch_losses,
    )
    return FittedLstmAutoencoder(
        experiment_id=config.experiment_id,
        feature_set_id=construction.feature_set_id,
        feature_names=construction.feature_names,
        spec=construction.spec,
        hidden_size=parameters.hidden_size,
        layer_count=parameters.layer_count,
        sampling_policy_id=config.sampling_policy_id,
        training=training,
        _batch_size=parameters.batch_size,
        _module=module,
    )


def _train(
    torch: Any,
    module: Any,
    optimizer: Any,
    inputs: Any,
    *,
    parameters: _LstmAutoencoderParameters,
    shuffle_generator: Any,
) -> tuple[float, ...]:
    module.train()
    epoch_losses: list[float] = []
    window_count = int(inputs.shape[0])
    for _ in range(parameters.epochs):
        if parameters.shuffle:
            order = torch.randperm(window_count, generator=shuffle_generator)
        else:
            order = torch.arange(window_count)
        weighted_losses: list[float] = []
        for start in range(0, window_count, parameters.batch_size):
            indices = order[start : start + parameters.batch_size]
            batch = inputs[indices]
            optimizer.zero_grad(set_to_none=True)
            reconstruction = module(batch)
            if not bool(torch.isfinite(reconstruction).all()):
                raise LstmAutoencoderError(
                    "LSTM training reconstruction contains non-finite values"
                )
            loss = torch.mean((batch - reconstruction) ** 2)
            if not bool(torch.isfinite(loss)):
                raise LstmAutoencoderError("LSTM training loss is non-finite")
            loss.backward()
            for parameter in module.parameters():
                if parameter.grad is None or not bool(torch.isfinite(parameter.grad).all()):
                    raise LstmAutoencoderError("LSTM training gradient is missing or non-finite")
            gradient_norm = torch.nn.utils.clip_grad_norm_(
                module.parameters(),
                max_norm=parameters.gradient_clip_norm,
            )
            if not bool(torch.isfinite(gradient_norm)):
                raise LstmAutoencoderError("LSTM gradient norm is non-finite")
            optimizer.step()
            if any(not bool(torch.isfinite(parameter).all()) for parameter in module.parameters()):
                raise LstmAutoencoderError("LSTM parameter state contains non-finite values")
            weighted_losses.append(float(loss.detach().item()) * int(batch.shape[0]))
        epoch_losses.append(math.fsum(weighted_losses) / window_count)
    return tuple(epoch_losses)


def _build_module(
    torch: Any,
    *,
    input_size: int,
    parameters: _LstmAutoencoderParameters,
) -> Any:
    class _LstmAutoencoderModule(torch.nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            recurrent_dropout = parameters.dropout if parameters.layer_count > 1 else 0.0
            self.encoder = torch.nn.LSTM(
                input_size=input_size,
                hidden_size=parameters.hidden_size,
                num_layers=parameters.layer_count,
                dropout=recurrent_dropout,
                batch_first=True,
            )
            self.decoder = torch.nn.LSTM(
                input_size=parameters.hidden_size,
                hidden_size=parameters.hidden_size,
                num_layers=parameters.layer_count,
                dropout=recurrent_dropout,
                batch_first=True,
            )
            self.output = torch.nn.Linear(parameters.hidden_size, input_size)

        def forward(self, inputs: Any) -> Any:
            _, (hidden, _) = self.encoder(inputs)
            latent = hidden[-1]
            repeated_latent = latent.unsqueeze(1).repeat(1, inputs.shape[1], 1)
            decoded, _ = self.decoder(repeated_latent)
            return self.output(decoded)

    return _LstmAutoencoderModule()


def _validate_fit_context(
    config: ExperimentConfig,
    construction: SequenceConstruction,
    parameters: _LstmAutoencoderParameters,
) -> None:
    if config.model_family is not ModelFamily.LSTM_AUTOENCODER:
        raise LstmAutoencoderError("model_family must be lstm-autoencoder")
    if config.sampling_policy_id != _SAMPLING_POLICY_ID:
        raise LstmAutoencoderError(f"LSTM sampling_policy_id must be {_SAMPLING_POLICY_ID!r}")
    _validate_construction_context(
        construction,
        feature_set_id=config.feature_set_id,
        feature_names=config.selected_features,
        spec=None,
    )
    if construction.spec.length != parameters.sequence_length:
        raise LstmAutoencoderError("sequence construction length does not match the LSTM model")
    if any(window.partition_id != "train" for window in construction.windows):
        raise LstmAutoencoderError("LSTM model fit requires train reference windows")


def _validate_construction_context(
    construction: SequenceConstruction,
    *,
    feature_set_id: str,
    feature_names: Sequence[str],
    spec: SequenceWindowSpec | None,
) -> None:
    if not isinstance(construction, SequenceConstruction):
        raise LstmAutoencoderError("model input must be a SequenceConstruction")
    expected: list[tuple[str, object, object]] = [
        ("feature_set_id", construction.feature_set_id, feature_set_id),
        ("feature schema", tuple(construction.feature_names), tuple(feature_names)),
    ]
    if spec is not None:
        expected.append(("window spec", construction.spec, spec))
    for field_name, value, configured in expected:
        if value != configured:
            raise LstmAutoencoderError(
                f"sequence construction {field_name} does not match the LSTM model"
            )


def _construction_tensor(torch: Any, construction: SequenceConstruction) -> Any:
    values = tuple(window.values for window in construction.windows)
    tensor = torch.tensor(values, dtype=torch.float32, device="cpu")
    expected_shape = (
        construction.window_count,
        construction.spec.length,
        len(construction.feature_names),
    )
    if tuple(tensor.shape) != expected_shape:
        raise LstmAutoencoderError(
            f"LSTM input shape must be {expected_shape}, got {tuple(tensor.shape)}"
        )
    if not bool(torch.isfinite(tensor).all()):
        raise LstmAutoencoderError("LSTM input contains non-finite values")
    return tensor


def _parse_parameters(
    values: Mapping[str, str | int | float | bool],
) -> _LstmAutoencoderParameters:
    observed_names = set(values)
    if observed_names != _MODEL_PARAMETER_NAMES:
        missing = sorted(_MODEL_PARAMETER_NAMES - observed_names)
        unknown = sorted(observed_names - _MODEL_PARAMETER_NAMES)
        raise LstmAutoencoderError(
            "LSTM Autoencoder parameters do not match the supported contract; "
            f"missing={missing}, unknown={unknown}"
        )

    parameters = _LstmAutoencoderParameters(
        sequence_length=_positive_int(values["sequence_length"], "sequence_length"),
        hidden_size=_positive_int(values["hidden_size"], "hidden_size"),
        layer_count=_positive_int(values["layer_count"], "layer_count"),
        dropout=_bounded_float(values["dropout"], "dropout", minimum=0.0, maximum=1.0),
        loss=_exact_text(values["loss"], "loss", "mean-squared-error"),
        optimizer=_exact_text(values["optimizer"], "optimizer", "adam"),
        learning_rate=_positive_float(values["learning_rate"], "learning_rate"),
        adam_beta1=_bounded_float(values["adam_beta1"], "adam_beta1", 0.0, 1.0),
        adam_beta2=_bounded_float(values["adam_beta2"], "adam_beta2", 0.0, 1.0),
        adam_epsilon=_positive_float(values["adam_epsilon"], "adam_epsilon"),
        weight_decay=_non_negative_float(values["weight_decay"], "weight_decay"),
        gradient_clip_norm=_positive_float(values["gradient_clip_norm"], "gradient_clip_norm"),
        batch_size=_positive_int(values["batch_size"], "batch_size"),
        epochs=_positive_int(values["epochs"], "epochs"),
        shuffle=_boolean(values["shuffle"], "shuffle"),
        checkpoint=_exact_text(values["checkpoint"], "checkpoint", "final-epoch"),
        numeric_precision=_exact_text(values["numeric_precision"], "numeric_precision", "float32"),
        device=_exact_text(values["device"], "device", "cpu"),
        deterministic_algorithms=_boolean(
            values["deterministic_algorithms"], "deterministic_algorithms"
        ),
    )
    if parameters.layer_count == 1 and parameters.dropout != 0.0:
        raise LstmAutoencoderError("single-layer LSTM dropout must be zero")
    if not parameters.deterministic_algorithms:
        raise LstmAutoencoderError("reference LSTM execution requires deterministic algorithms")
    return parameters


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LstmAutoencoderError(f"LSTM {field_name} must be a positive integer")
    return value


def _positive_float(value: object, field_name: str) -> float:
    number = _numeric_float(value, field_name)
    if number <= 0.0:
        raise LstmAutoencoderError(f"LSTM {field_name} must be positive")
    return number


def _non_negative_float(value: object, field_name: str) -> float:
    number = _numeric_float(value, field_name)
    if number < 0.0:
        raise LstmAutoencoderError(f"LSTM {field_name} must be non-negative")
    return number


def _bounded_float(
    value: object,
    field_name: str,
    minimum: float,
    maximum: float,
) -> float:
    number = _numeric_float(value, field_name)
    if not minimum <= number < maximum:
        raise LstmAutoencoderError(f"LSTM {field_name} must fall in [{minimum}, {maximum})")
    return number


def _numeric_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LstmAutoencoderError(f"LSTM {field_name} must be numerical")
    number = float(value)
    if not math.isfinite(number):
        raise LstmAutoencoderError(f"LSTM {field_name} must be finite")
    return number


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise LstmAutoencoderError(f"LSTM {field_name} must be a boolean")
    return value


def _exact_text(value: object, field_name: str, expected: str) -> str:
    if value != expected:
        raise LstmAutoencoderError(f"LSTM {field_name} must be {expected!r}")
    return expected


def _validated_names(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result:
        raise LstmAutoencoderError(f"{field_name} must contain at least one value")
    for value in result:
        _validate_text(value, field_name)
    if len(result) != len(set(result)):
        raise LstmAutoencoderError(f"{field_name} must contain unique values")
    return result


def _finite_values(values: Sequence[float], field_name: str) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise LstmAutoencoderError(f"{field_name} must contain numerical values")
        number = float(value)
        if not math.isfinite(number):
            raise LstmAutoencoderError(f"{field_name} must contain finite values")
        result.append(number)
    return tuple(result)


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise LstmAutoencoderError(f"{field_name} must be a trimmed non-empty string")


def _require_torch() -> Any:
    try:
        return import_module("torch")
    except ModuleNotFoundError as error:  # pragma: no cover - exercised in base-only CI process.
        raise LstmAutoencoderError(
            "LSTM Autoencoder requires the project deep-learning extra"
        ) from error
