"""PyTorch MLP model definition and training loop."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
except ImportError:  # pragma: no cover
    torch = None
    nn = None
    optim = None
    DataLoader = None
    TensorDataset = None

logger = logging.getLogger(__name__)


# Default architecture constants (must match data.py)
DEFAULT_MAX_HISTORY_STEPS = 10
DEFAULT_STEP_FEATURE_DIM = 6
DEFAULT_CURRENT_FEATURE_DIM = 2


def compute_input_dim(max_history_steps: int) -> int:
    """Compute input dimension from max_history_steps."""
    return max_history_steps * DEFAULT_STEP_FEATURE_DIM + DEFAULT_CURRENT_FEATURE_DIM


@dataclass
class TrainingConfig:
    """Training hyperparameters."""
    epochs: int = 50
    batch_size: int = 32
    learning_rate: float = 1e-3
    val_split: float = 0.1
    hidden_dim: int = 128
    max_history_steps: int = DEFAULT_MAX_HISTORY_STEPS  # Model's input dim source
    n_history: int = 3  # Actual history steps used (1..max_history_steps)
    device: str = "cpu"


class BoltShiftMLP(nn.Module):
    """MLP for bolt shift prediction (residual correction).
    
    Architecture: Input -> Linear(hidden) -> ReLU -> Linear(hidden) -> ReLU
                  -> Linear(hidden/2) -> ReLU -> Linear(output)
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
        self.dummy = nn.Parameter(torch.zeros(1))  # Just to have parameters
        self.output_dim = output_dim
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.shape[0]
        return torch.zeros(batch_size, self.output_dim, device=x.device, dtype=x.dtype)


def create_model(model_type: str, config: TrainingConfig) -> nn.Module:
    """Create model based on type.
    
    Args:
        model_type: "mlp" or "baseline_only"
        config: Training configuration
        
    Returns:
        PyTorch model
    """
    if model_type == "baseline_only":
        return BaselineOnlyModel()
    elif model_type == "mlp":
        return BoltShiftMLP(
            max_history_steps=config.max_history_steps,
            hidden_dim=config.hidden_dim,
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type}")


def train_model(
    features: np.ndarray,
    labels: np.ndarray,
    model_type: str = "mlp",
    config: TrainingConfig | None = None,
    feature_stats: dict[str, np.ndarray] | None = None,
    init_from_model_path: Path | str | None = None,
) -> tuple[nn.Module, dict[str, Any]]:
    """Train bolt shift prediction model.
    
    Args:
        features: (N, 8) normalized feature array
        labels: (N, 2) label array (bolt shifts in mm)
        model_type: "mlp" or "baseline_only"
        config: Training configuration
        feature_stats: Normalization statistics (mean, std)
        
    Returns:
        model: Trained PyTorch model
        metrics: Training metrics dict
    """
    if torch is None:
        raise RuntimeError("PyTorch not available")
    
    if config is None:
        config = TrainingConfig()
    
    device = torch.device(config.device)
    
    # Split train/val
    n_samples = len(features)
    n_val = int(n_samples * config.val_split)
    n_train = n_samples - n_val
    
    indices = np.random.permutation(n_samples)
    train_idx = indices[:n_train]
    val_idx = indices[n_train:]
    
    X_train = torch.from_numpy(features[train_idx]).float().to(device)
    y_train = torch.from_numpy(labels[train_idx]).float().to(device)
    X_val = torch.from_numpy(features[val_idx]).float().to(device) if n_val > 0 else None
    y_val = torch.from_numpy(labels[val_idx]).float().to(device) if n_val > 0 else None
    
    # Create model
    model = create_model(model_type, config).to(device)

    # Warm-start: load weights from previous checkpoint if compatible
    if init_from_model_path and model_type == "mlp":
        try:
            ckpt = torch.load(init_from_model_path, map_location=device, weights_only=False)
            prev_hidden = ckpt.get("hidden_dim")
            prev_mhs = ckpt.get("max_history_steps")
            if prev_hidden == config.hidden_dim and prev_mhs == config.max_history_steps:
                model.load_state_dict(ckpt["model_state_dict"])
                logger.info(f"Warm-start: loaded weights from {init_from_model_path}")
            else:
                logger.warning(
                    f"Warm-start skipped: architecture mismatch "
                    f"(prev hidden={prev_hidden}, max_history={prev_mhs} vs "
                    f"new hidden={config.hidden_dim}, max_history={config.max_history_steps})"
                )
        except Exception as exc:
            logger.warning(f"Warm-start failed (continuing from scratch): {exc}")

    if model_type == "baseline_only":
        # No training needed for baseline-only
        logger.info("baseline_only model - no training performed")
        return model, {
            "epoch_losses": [],
            "val_losses": [],
            "final_train_loss": 0.0,
            "final_val_loss": 0.0,
        }
    
    # Training setup
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=config.learning_rate)
    
    train_dataset = TensorDataset(X_train, y_train)
    train_loader = DataLoader(train_dataset, batch_size=config.batch_size, shuffle=True)
    
    epoch_losses = []
    val_losses = []
    
    # Training loop
    for epoch in range(config.epochs):
        model.train()
        train_loss = 0.0
        n_batches = 0
        
        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()
            
            pred = model(batch_X)
            loss = criterion(pred, batch_y)
            
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            n_batches += 1
        
        avg_train_loss = train_loss / max(n_batches, 1)
        epoch_losses.append(avg_train_loss)
        
        # Validation
        if X_val is not None:
            model.eval()
            with torch.no_grad():
                val_pred = model(X_val)
                val_loss = criterion(val_pred, y_val).item()
                val_losses.append(val_loss)
        else:
            val_losses.append(0.0)
        
        if (epoch + 1) % 10 == 0 or epoch == 0:
            logger.info(f"Epoch {epoch+1}/{config.epochs} - train_loss: {avg_train_loss:.6f}, val_loss: {val_losses[-1]:.6f}")
    
    metrics = {
        "epoch_losses": epoch_losses,
        "val_losses": val_losses,
        "final_train_loss": epoch_losses[-1] if epoch_losses else 0.0,
        "final_val_loss": val_losses[-1] if val_losses else 0.0,
    }
    
    return model, metrics


def save_model(
    model: nn.Module,
    save_path: Path,
    model_type: str,
    config: TrainingConfig | None = None,
    feature_stats: dict[str, np.ndarray] | None = None,
    metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    """Save model to file.
    
    Args:
        model: PyTorch model
        save_path: Path to save .pt file
        model_type: "mlp" or "baseline_only"
        config: Training configuration (for architecture params)
        feature_stats: Normalization statistics
        metadata: Additional metadata
    """
    if torch is None:
        raise RuntimeError("PyTorch not available")
    
    save_dict = {
        "model_state_dict": model.state_dict(),
        "model_type": model_type,
    }
    
    if config is not None:
        save_dict["hidden_dim"] = config.hidden_dim
        save_dict["max_history_steps"] = config.max_history_steps
        save_dict["n_history"] = config.n_history
    
    if feature_stats is not None:
        save_dict["feature_mean"] = feature_stats.get("mean")
        save_dict["feature_std"] = feature_stats.get("std")
    
    if metadata is not None:
        save_dict["metadata"] = metadata

    if metrics is not None:
        save_dict["epoch_losses"] = metrics.get("epoch_losses", [])
        save_dict["val_losses"] = metrics.get("val_losses", [])
        save_dict["final_train_loss"] = metrics.get("final_train_loss")

    save_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(save_dict, save_path)
    logger.info(f"Model saved to {save_path}")


def load_model(load_path: Path, device: str = "cpu") -> tuple[nn.Module, dict[str, Any]]:
    """Load model from file.
    
    Args:
        load_path: Path to .pt file
        device: Device to load model on
        
    Returns:
        model: Loaded PyTorch model
        metadata: Dict containing model_type, feature_stats, etc.
    """
    if torch is None:
        raise RuntimeError("PyTorch not available")
    
    # PyTorch 2.6+ requires weights_only=False for non-tensor data
    checkpoint = torch.load(load_path, map_location=device, weights_only=False)
    
    model_type = checkpoint.get("model_type", "mlp")
    hidden_dim = checkpoint.get("hidden_dim", 128)
    max_history_steps = checkpoint.get("max_history_steps", DEFAULT_MAX_HISTORY_STEPS)
    n_history = checkpoint.get("n_history", 3)
    
    config = TrainingConfig(
        device=device,
        hidden_dim=hidden_dim,
        max_history_steps=max_history_steps,
        n_history=n_history,
    )
    model = create_model(model_type, config)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    
    metadata = {
        "model_type": model_type,
        "hidden_dim": hidden_dim,
        "max_history_steps": max_history_steps,
        "n_history": n_history,
        "feature_mean": checkpoint.get("feature_mean"),
        "feature_std": checkpoint.get("feature_std"),
        "metadata": checkpoint.get("metadata", {}),
        "epoch_losses": checkpoint.get("epoch_losses", []),
        "val_losses": checkpoint.get("val_losses", []),
        "final_train_loss": checkpoint.get("final_train_loss"),
    }
    
    logger.info(f"Model loaded from {load_path}")
    return model, metadata
