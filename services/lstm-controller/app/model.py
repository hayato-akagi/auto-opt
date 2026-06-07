"""LSTM model definition and ModelManager for lstm-controller.

The LSTM processes one step at a time and carries hidden state (h, c)
across steps within a single trial.  The hidden state is reset at the
start of each new trial, so trials remain independent.

Input per step: 8 dimensions
  [0:6]  previous-step observation: spot_before(x,y), delta(x,y), spot_after(x,y)
  [6:8]  current spot position: (x, y)

Output per step: 2 dimensions — predicted bolt_shift (x, y) in spot space (mm)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch
    import torch.nn as nn
except ImportError:  # pragma: no cover
    torch = None
    nn = None

logger = logging.getLogger(__name__)

LSTM_INPUT_DIM = 8   # 6 prev-step features + 2 current position
LSTM_OUTPUT_DIM = 2  # bolt_shift (x, y)


class BoltShiftLSTM(nn.Module):
    """LSTM for step-by-step bolt shift prediction.

    Processes one step feature vector per call and updates hidden state.
    """

    def __init__(
        self,
        input_dim: int = LSTM_INPUT_DIM,
        hidden_dim: int = 128,
        num_layers: int = 2,
        output_dim: int = LSTM_OUTPUT_DIM,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
        )
        self.fc = nn.Linear(hidden_dim, output_dim)

    def forward(
        self,
        x: torch.Tensor,
        h_c: tuple[torch.Tensor, torch.Tensor] | None = None,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        """Full-sequence forward pass (used during training).

        Args:
            x: (batch, seq_len, input_dim)
            h_c: initial (h_0, c_0) or None (zeros)

        Returns:
            predictions: (batch, seq_len, output_dim)
            (h_n, c_n): final hidden state
        """
        out, (h_n, c_n) = self.lstm(x, h_c)
        predictions = self.fc(out)
        return predictions, (h_n, c_n)

    def step(
        self,
        x: torch.Tensor,
        h_c: tuple[torch.Tensor, torch.Tensor] | None = None,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        """Single-step inference (used during control loop).

        Args:
            x: (1, 1, input_dim) — one step, batch=1
            h_c: previous hidden state or None

        Returns:
            prediction: (1, output_dim)
            (h_n, c_n): updated hidden state
        """
        out, (h_n, c_n) = self.lstm(x, h_c)   # out: (1, 1, hidden_dim)
        prediction = self.fc(out[:, 0, :])      # (1, output_dim)
        return prediction, (h_n, c_n)


class BaselineOnlyModel(nn.Module):
    """Fallback model that always outputs zero bolt shift."""

    def __init__(self):
        super().__init__()
        self.dummy = nn.Parameter(torch.zeros(1))

    def forward(self, x, h_c=None):
        return torch.zeros(x.shape[0], x.shape[1], LSTM_OUTPUT_DIM), None

    def step(self, x, h_c=None):
        return torch.zeros(1, LSTM_OUTPUT_DIM), None


class ModelManager:
    """Loads and manages an LSTM model for online step-wise inference."""

    def __init__(
        self,
        *,
        model_type: str = "baseline_only",
        model_version: str | None = None,
        model_path: Path | None = None,
        device: str = "cpu",
    ) -> None:
        self._model_type = model_type
        self._model_version = model_version
        self._device = device
        self._loaded_at = datetime.now(timezone.utc)
        self._model: nn.Module | None = None
        self._feature_mean: np.ndarray | None = None
        self._feature_std: np.ndarray | None = None
        self._metadata: dict[str, Any] = {}
        self._hidden_dim: int = 128
        self._num_layers: int = 2

        if model_path is not None:
            self.load_model(model_path)

    def load_model(self, model_path: Path) -> None:
        if torch is None:
            raise RuntimeError("PyTorch not available")
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        logger.info(f"Loading LSTM model from {model_path}")
        checkpoint = torch.load(model_path, map_location=self._device, weights_only=False)

        model_type = checkpoint.get("model_type", "lstm")
        hidden_dim = checkpoint.get("hidden_dim", 128)
        num_layers = checkpoint.get("num_layers", 2)

        if model_type == "baseline_only":
            model = BaselineOnlyModel()
        elif model_type == "lstm":
            model = BoltShiftLSTM(
                input_dim=LSTM_INPUT_DIM,
                hidden_dim=hidden_dim,
                num_layers=num_layers,
            )
        else:
            raise ValueError(f"lstm-controller cannot load model_type='{model_type}'")

        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(self._device)
        model.eval()

        self._model = model
        self._model_type = model_type
        self._hidden_dim = hidden_dim
        self._num_layers = num_layers
        self._feature_mean = checkpoint.get("feature_mean")
        self._feature_std = checkpoint.get("feature_std")
        self._metadata = checkpoint.get("metadata", {})
        self._loaded_at = datetime.now(timezone.utc)

        logger.info(
            f"LSTM model loaded: hidden_dim={hidden_dim}, num_layers={num_layers}"
        )

    def step(
        self,
        features: np.ndarray,
        h_c: tuple | None,
    ) -> tuple[np.ndarray, tuple | None]:
        """Run one-step LSTM inference.

        Args:
            features: (8,) raw feature vector for this step
            h_c: previous hidden state (h_n, c_n) or None (start of trial)

        Returns:
            bolt_shift: (2,) predicted bolt shift [x, y] in spot space (mm)
            new_h_c: updated hidden state to pass to the next step
        """
        if torch is None:
            raise RuntimeError("PyTorch not available")

        if self._model is None:
            return np.zeros(2, dtype=np.float32), None

        # Normalize
        if self._feature_mean is not None and self._feature_std is not None:
            features = (features - self._feature_mean) / (self._feature_std + 1e-8)

        x = torch.from_numpy(features.astype(np.float32)).reshape(1, 1, -1).to(self._device)

        with torch.no_grad():
            pred, new_h_c = self._model.step(x, h_c)

        return pred.squeeze().cpu().numpy(), new_h_c

    def status(self) -> dict[str, Any]:
        return {
            "loaded_version": self._model_version,
            "model_type": self._model_type,
            "loaded_at": self._loaded_at.isoformat(),
            "device": self._device,
            "model_loaded": self._model is not None,
        }

    def reload(
        self,
        *,
        model_type: str | None = None,
        model_version: str | None = None,
        model_path: Path | None = None,
    ) -> dict[str, Any]:
        if model_type is not None:
            self._model_type = model_type
        if model_version is not None:
            self._model_version = model_version
        if model_path is not None:
            self.load_model(model_path)
        return {"loaded_version": self._model_version, "model_type": self._model_type}
