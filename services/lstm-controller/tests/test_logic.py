"""Tests for lstm-controller logic layer."""

import numpy as np
import pytest
import torch

from app.logic import compute_lstm_step, make_lstm_features
from app.model import BoltShiftLSTM, ModelManager
from app.models import LstmControllerConfig


def _config(**overrides) -> LstmControllerConfig:
    defaults = dict(
        model_type="lstm",
        spot_to_coll_scale_x=50.0,
        spot_to_coll_scale_y=50.0,
        delta_clip_x=0.05,
        delta_clip_y=0.05,
        coll_x_min=-0.5,
        coll_x_max=0.5,
        coll_y_min=-0.5,
        coll_y_max=0.5,
        safety_threshold=0.5,
        safety_bias=0.01,
    )
    defaults.update(overrides)
    return LstmControllerConfig(**defaults)


class TestMakeLstmFeatures:
    def test_none_prev_step_uses_zeros(self) -> None:
        f = make_lstm_features(None, 0.1, -0.2)
        assert f.shape == (8,)
        assert f[:6].tolist() == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        assert f[6] == pytest.approx(0.1)
        assert f[7] == pytest.approx(-0.2)

    def test_extracts_prev_step_fields(self) -> None:
        prev_step = {
            "sim_after_position": {"spot_center_x": 0.02, "spot_center_y": -0.01},
            "command": {"coll_x": 0.003, "coll_y": -0.002},
            "sim_after_bolt": {"spot_center_x": 0.04, "spot_center_y": -0.02},
        }
        f = make_lstm_features(prev_step, 0.05, 0.01)
        assert f[0] == pytest.approx(0.02)
        assert f[1] == pytest.approx(-0.01)
        assert f[2] == pytest.approx(0.003)
        assert f[3] == pytest.approx(-0.002)
        assert f[4] == pytest.approx(0.04)
        assert f[5] == pytest.approx(-0.02)
        assert f[6] == pytest.approx(0.05)
        assert f[7] == pytest.approx(0.01)

    def test_missing_fields_default_to_zero(self) -> None:
        f = make_lstm_features({}, 0.0, 0.0)
        assert f[:6].tolist() == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


class TestBoltShiftLSTM:
    def test_forward_output_shape(self) -> None:
        model = BoltShiftLSTM(input_dim=8, hidden_dim=64, num_layers=2)
        x = torch.zeros(2, 5, 8)  # batch=2, seq_len=5
        preds, (h, c) = model(x)
        assert preds.shape == (2, 5, 2)
        assert h.shape == (2, 2, 64)  # (num_layers, batch, hidden)
        assert c.shape == (2, 2, 64)

    def test_step_output_shape(self) -> None:
        model = BoltShiftLSTM(input_dim=8, hidden_dim=64, num_layers=2)
        x = torch.zeros(1, 1, 8)
        pred, (h, c) = model.step(x)
        assert pred.shape == (1, 2)
        assert h.shape == (2, 1, 64)

    def test_hidden_state_propagates(self) -> None:
        model = BoltShiftLSTM(input_dim=8, hidden_dim=32, num_layers=1)
        model.eval()
        x = torch.randn(1, 1, 8)

        pred1, h_c1 = model.step(x, None)
        pred2, h_c2 = model.step(x, h_c1)
        # Second call with same input but different hidden state should give different output
        pred2_fresh, _ = model.step(x, None)
        assert not torch.allclose(pred2, pred2_fresh), "Hidden state should affect output"


class TestComputeLstmStep:
    def _make_manager_with_lstm(self) -> ModelManager:
        """Create a ModelManager holding an untrained BoltShiftLSTM."""
        mm = ModelManager(model_type="baseline_only")
        model = BoltShiftLSTM(input_dim=8, hidden_dim=32, num_layers=1)
        model.eval()
        mm._model = model
        mm._model_type = "lstm"
        return mm

    def test_baseline_only_model_type_returns_zero_residual(self) -> None:
        config = _config(model_type="baseline_only")
        features = np.zeros(8, dtype=np.float32)
        decision, new_hidden = compute_lstm_step(
            config=config,
            target_x=0.0, target_y=0.0,
            current_coll_x=0.0, current_coll_y=0.0,
            spot_pre_x=0.1, spot_pre_y=0.0,
            lstm_features=features,
            lstm_hidden_state=None,
            model_manager=None,
        )
        assert decision.lstm_residual_x == pytest.approx(0.0)
        assert decision.lstm_residual_y == pytest.approx(0.0)
        assert new_hidden is None

    def test_hidden_state_updated_on_lstm_inference(self) -> None:
        mm = self._make_manager_with_lstm()
        config = _config()
        features = np.zeros(8, dtype=np.float32)
        _, h1 = compute_lstm_step(
            config=config,
            target_x=0.0, target_y=0.0,
            current_coll_x=0.0, current_coll_y=0.0,
            spot_pre_x=0.05, spot_pre_y=0.0,
            lstm_features=features,
            lstm_hidden_state=None,
            model_manager=mm,
        )
        assert h1 is not None, "Hidden state should be updated after LSTM step"

    def test_convergence_check(self) -> None:
        config = _config(model_type="baseline_only")
        features = np.zeros(8, dtype=np.float32)
        # spot is essentially at target → converged
        decision, _ = compute_lstm_step(
            config=config,
            target_x=0.0, target_y=0.0,
            current_coll_x=0.0, current_coll_y=0.0,
            spot_pre_x=0.0001, spot_pre_y=0.0,
            lstm_features=features,
            lstm_hidden_state=None,
            model_manager=None,
        )
        # small error → small delta
        assert abs(decision.baseline_delta_x) < 1e-4

    def test_safety_trigger_suppresses_large_residual(self) -> None:
        mm = self._make_manager_with_lstm()
        # Force the LSTM to output a huge prediction by modifying fc bias
        import torch
        with torch.no_grad():
            mm._model.fc.bias.fill_(100.0)

        config = _config(safety_threshold=0.5, safety_bias=0.01)
        features = np.zeros(8, dtype=np.float32)
        decision, _ = compute_lstm_step(
            config=config,
            target_x=0.0, target_y=0.0,
            current_coll_x=0.0, current_coll_y=0.0,
            spot_pre_x=0.1, spot_pre_y=0.0,
            lstm_features=features,
            lstm_hidden_state=None,
            model_manager=mm,
        )
        assert decision.safety_triggered is True
        # Final should equal baseline when safety triggers
        assert decision.final_delta_x == pytest.approx(decision.baseline_delta_x, abs=1e-5)

    def test_delta_clipping(self) -> None:
        config = _config(model_type="baseline_only", delta_clip_x=0.05)
        features = np.zeros(8, dtype=np.float32)
        decision, _ = compute_lstm_step(
            config=config,
            target_x=0.0, target_y=0.0,
            current_coll_x=0.0, current_coll_y=0.0,
            spot_pre_x=100.0, spot_pre_y=0.0,  # huge error
            lstm_features=features,
            lstm_hidden_state=None,
            model_manager=None,
        )
        assert abs(decision.final_delta_x) <= 0.05
