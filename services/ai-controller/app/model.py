"""Model management for AI controller."""

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


# Must match trainer's architecture constants
DEFAULT_MAX_HISTORY_STEPS = 10
STEP_FEATURE_DIM = 6
CURRENT_FEATURE_DIM = 2


def compute_input_dim(max_history_steps: int) -> int:
    return max_history_steps * STEP_FEATURE_DIM + CURRENT_FEATURE_DIM


class BoltShiftMLP(nn.Module):
    """MLP for bolt shift prediction (must match trainer architecture).
    
    Architecture: Input -> Linear(hidden) -> ReLU -> Linear(hidden) -> ReLU
                  -> Linear(hidden//2) -> ReLU -> Linear(output)
    """
    
    def __init__(
        self,
        max_history_steps: int = DEFAULT_MAX_HISTORY_STEPS,
        hidden_dim: int = 128,
        output_dim: int = 2,
    ):
        super().__init__()
        input_dim = compute_input_dim(max_history_steps)
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, output_dim),
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class BaselineOnlyModel(nn.Module):
    """Dummy model that always outputs zero (baseline-only fallback)."""
    
    def __init__(self, output_dim: int = 2):
        super().__init__()
        self.dummy = nn.Parameter(torch.zeros(1))
        self.output_dim = output_dim
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.shape[0]
        return torch.zeros(batch_size, self.output_dim, device=x.device, dtype=x.dtype)


class ModelManager:
    """Manages loading and inference of bolt shift prediction models."""
    
    def __init__(
        self,
        *,
        model_type: str = "mlp",
        model_version: str | None = None,
        model_path: Path | None = None,
        device: str = "cpu",
    ) -> None:
        """Initialize model manager.
        
        Args:
            model_type: "mlp" or "baseline_only"
            model_version: Model version identifier
            model_path: Path to .pt model file (if loading from disk)
            device: "cpu" or "cuda"
        """
        self._model_type = model_type
        self._model_version = model_version
        self._device = device
        self._loaded_at = datetime.now(timezone.utc)
        
        self._model: nn.Module | None = None
        self._feature_mean: np.ndarray | None = None
        self._feature_std: np.ndarray | None = None
        self._metadata: dict[str, Any] = {}
        self._max_history_steps: int = DEFAULT_MAX_HISTORY_STEPS
        self._n_history: int = 1
        self._hidden_dim: int = 128
        
        # Load model if path provided
        if model_path is not None:
            self.load_model(model_path)
    
    def load_model(self, model_path: Path) -> None:
        """Load model from file.
        
        Args:
            model_path: Path to .pt model file
        """
        if torch is None:
            raise RuntimeError("PyTorch not available")
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        logger.info(f"Loading model from {model_path}")
        
        # Load checkpoint
        checkpoint = torch.load(model_path, map_location=self._device, weights_only=False)
        
        # Extract model config
        model_type = checkpoint.get("model_type", "mlp")
        hidden_dim = checkpoint.get("hidden_dim", 128)
        max_history_steps = checkpoint.get("max_history_steps", DEFAULT_MAX_HISTORY_STEPS)
        n_history = checkpoint.get("n_history", 1)
        
        # Create model architecture
        if model_type == "baseline_only":
            model = BaselineOnlyModel()
        elif model_type == "mlp":
            model = BoltShiftMLP(
                max_history_steps=max_history_steps,
                hidden_dim=hidden_dim,
            )
        else:
            raise ValueError(f"Unknown model_type: {model_type}")
        
        # Load weights
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(self._device)
        model.eval()
        
        # Store model and metadata
        self._model = model
        self._model_type = model_type
        self._max_history_steps = max_history_steps
        self._n_history = n_history
        self._hidden_dim = hidden_dim
        self._feature_mean = checkpoint.get("feature_mean")
        self._feature_std = checkpoint.get("feature_std")
        self._metadata = checkpoint.get("metadata", {})
        self._loaded_at = datetime.now(timezone.utc)
        
        logger.info(
            f"Model loaded: type={model_type}, hidden_dim={hidden_dim}, "
            f"max_history_steps={max_history_steps}, n_history={n_history}, device={self._device}"
        )
    
    def predict(self, features: np.ndarray) -> np.ndarray:
        """Run inference on input features.
        
        Args:
            features: (N, 8) array of input features (normalized or raw)
        
        Returns:
            predictions: (N, 2) array of [residual_x, residual_y] in mm (coll space)
        """
        if torch is None:
            raise RuntimeError("PyTorch not available")
        
        if self._model is None:
            # No model loaded - return zeros (baseline-only behavior)
            logger.warning("No model loaded, returning zero residuals")
            return np.zeros((features.shape[0], 2), dtype=np.float32)
        
        # Normalize features if stats available
        if self._feature_mean is not None and self._feature_std is not None:
            features = (features - self._feature_mean) / (self._feature_std + 1e-8)
        
        # Convert to tensor
        x = torch.from_numpy(features).float().to(self._device)
        
        # Inference
        with torch.no_grad():
            output = self._model(x)
        
        # Convert back to numpy
        predictions = output.cpu().numpy()
        
        return predictions
    
    @property
    def max_history_steps(self) -> int:
        return self._max_history_steps
    
    @property
    def n_history(self) -> int:
        return self._n_history
    
    def status(self) -> dict[str, str | None]:
        """Get current model status.
        
        Returns:
            Status dict with model info
        """
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
    ) -> dict[str, str | None]:
        """Reload model with new parameters.
        
        Args:
            model_type: New model type (optional)
            model_version: New version identifier (optional)
            model_path: Path to new model file (optional)
        
        Returns:
            Status dict
        """
        if model_type is not None:
            self._model_type = model_type
        
        if model_version is not None:
            self._model_version = model_version
        
        if model_path is not None:
            self.load_model(model_path)
        
        return {
            "loaded_version": self._model_version,
            "model_type": self._model_type,
        }

