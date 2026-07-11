"""Async training job runner."""

from __future__ import annotations

import asyncio
import functools
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .clients import RecipeServiceClient
from .data import collect_training_data, collect_training_sequences, normalize_features
from .models import TrainRequest, TrainJobStatus, TrainMetrics, EpochLog
from .train import (
    TrainingConfig,
    train_model,
    train_lstm_sequences,
    save_model,
    load_feature_stats,
)

logger = logging.getLogger(__name__)


async def run_training_job(
    train_job_id: str,
    request: TrainRequest,
    jobs_dict: dict[str, TrainJobStatus],
    recipe_client: RecipeServiceClient,
) -> None:
    """Background training job that updates progress in jobs_dict.
    
    Args:
        train_job_id: Job identifier
        request: Training request
        jobs_dict: Shared dictionary for job status
        recipe_client: Client for recipe-service
    """
    try:
        # Initialize job status
        job = jobs_dict[train_job_id]
        job.status = "running"
        job.updated_at = _utc_now_iso()
        
        # Step 1: Collect training data from recipe-service
        logger.info(f"[{train_job_id}] Collecting training data from experiments: {request.experiment_ids}")
        
        experiments_data = []
        for exp_id in request.experiment_ids:
            exp = recipe_client.get_experiment(exp_id)
            if not exp:
                logger.warning(f"Experiment {exp_id} not found")
                continue
            
            trials = recipe_client.get_trials(exp_id)
            exp["trials"] = trials
            experiments_data.append(exp)
        
        if not experiments_data:
            raise ValueError("No valid experiments found")
        
        # Define get_trial_steps function for data collection
        def get_trial_steps(exp_id: str, trial_id: str) -> list[dict]:
            return recipe_client.get_steps(exp_id, trial_id)
        
        config = TrainingConfig(
            epochs=request.epochs,
            batch_size=request.batch_size,
            learning_rate=request.learning_rate,
            val_split=0.1,
            hidden_dim=request.hidden_dim,
            n_history=request.n_history,
            num_layers=request.num_layers,
            device="cpu",
        )

        if request.model_type == "lstm":
            # LSTM path: collect per-trial sequences
            sequences = collect_training_sequences(
                experiments_data,
                get_trial_steps,
                only_converged=request.only_converged,
            )
            if not sequences:
                raise ValueError("No training sequences collected for LSTM")

            # When warm-starting, reuse the previous checkpoint's normalization
            # stats: the warm-started weights only make sense under the input
            # scale they were trained with, and recomputing fresh stats from
            # (possibly differently distributed) new data would shift that
            # scale out from under them.
            stats = (
                load_feature_stats(request.init_from_model_path)
                if request.init_from_model_path
                else None
            )
            if stats is None:
                all_features = np.vstack([s[0] for s in sequences])
                stats = {
                    "mean": all_features.mean(axis=0),
                    "std": all_features.std(axis=0) + 1e-8,
                }

            logger.info(
                f"[{train_job_id}] LSTM training: {len(sequences)} sequences, "
                f"epochs={request.epochs}"
            )
            job.data_stats = {
                "experiment_count": len(experiments_data),
                "total_samples": len(sequences),
            }
            job.updated_at = _utc_now_iso()

            model, metrics = await _train_lstm_with_progress(
                sequences,
                config,
                stats,
                train_job_id,
                jobs_dict,
                init_from_model_path=request.init_from_model_path,
            )
        else:
            # MLP / baseline_only path (original)
            features, labels, groups = collect_training_data(
                experiments_data,
                get_trial_steps,
                n_history=request.n_history,
                only_converged=request.only_converged,
            )

            if len(features) == 0:
                raise ValueError("No training samples collected")

            logger.info(f"[{train_job_id}] Collected {len(features)} training samples")

            job.data_stats = {
                "experiment_count": len(experiments_data),
                "total_samples": len(features),
            }
            job.updated_at = _utc_now_iso()

            # Warm-start reuses the previous checkpoint's normalization stats
            # (see LSTM branch above for why); otherwise compute fresh stats.
            stats = (
                load_feature_stats(request.init_from_model_path)
                if request.init_from_model_path
                else None
            )
            if stats is not None:
                normalized_features = (features - stats["mean"]) / (stats["std"] + 1e-8)
            else:
                normalized_features, stats = normalize_features(features)

            logger.info(
                f"[{train_job_id}] Starting training: model_type={request.model_type}, "
                f"epochs={request.epochs}"
            )

            model, metrics = await _train_with_progress(
                normalized_features,
                labels,
                request.model_type,
                config,
                train_job_id,
                jobs_dict,
                init_from_model_path=request.init_from_model_path,
                groups=groups,
            )
        
        logger.info(f"[{train_job_id}] Training completed: final_loss={metrics['final_train_loss']:.6f}")
        
        # Step 4: Save model
        model_dir = Path("/app/models")
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / f"{train_job_id}.pt"
        
        n_samples = len(sequences) if request.model_type == "lstm" else len(features)
        save_model(
            model,
            model_path,
            model_type=request.model_type,
            config=config,
            feature_stats=stats,
            metadata={
                "train_job_id": train_job_id,
                "experiment_ids": request.experiment_ids,
                "n_samples": n_samples,
            },
            metrics=metrics,
        )
        
        logger.info(f"[{train_job_id}] Model saved to {model_path}")
        
        # Step 5: Update job status
        job.status = "completed"
        job.progress_rate = 1.0
        job.train_metrics = TrainMetrics(
            epoch_losses=metrics["epoch_losses"],
            final_train_loss=metrics["final_train_loss"],
            epochs=request.epochs,
        )
        job.promoted = True
        job.promoted_version = f"v_{train_job_id}"
        job.updated_at = _utc_now_iso()
        
        logger.info(f"[{train_job_id}] Job completed successfully")
        
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error(f"[{train_job_id}] Training failed: {exc}", exc_info=True)

        job = jobs_dict.get(train_job_id)
        if job:
            job.status = "failed"
            job.error_message = (
                f"{type(exc).__name__}: {exc}\n\n"
                f"--- パラメータ ---\n"
                f"model_type={request.model_type}\n"
                f"epochs={request.epochs}\n"
                f"hidden_dim={request.hidden_dim}\n"
                f"num_layers={request.num_layers}\n"
                f"n_history={request.n_history}\n"
                f"experiment_ids={request.experiment_ids}\n\n"
                f"--- Traceback ---\n{tb}"
            )
            job.updated_at = _utc_now_iso()


async def _train_with_progress(
    features,
    labels,
    model_type: str,
    config: TrainingConfig,
    train_job_id: str,
    jobs_dict: dict[str, TrainJobStatus],
    init_from_model_path: str | None = None,
    groups: np.ndarray | None = None,
):
    """Train model in a thread pool executor so the event loop stays unblocked.

    Running training synchronously inside an async function blocks the FastAPI
    event loop, which prevents the orchestrator's poll requests from being
    served and causes ReadTimeout.  run_in_executor moves the CPU-bound work
    to a separate thread.
    """
    loop = asyncio.get_event_loop()
    fn = functools.partial(
        train_model,
        features,
        labels,
        model_type=model_type,
        config=config,
        init_from_model_path=init_from_model_path,
        groups=groups,
    )
    model, metrics = await loop.run_in_executor(None, fn)

    job = jobs_dict[train_job_id]
    job.current_epoch = config.epochs
    job.progress_rate = 1.0
    job.last_loss = metrics["final_train_loss"]

    for epoch, loss in enumerate(metrics["epoch_losses"], start=1):
        job.epoch_logs.append(
            EpochLog(epoch=epoch, loss=loss, timestamp=_utc_now_iso())
        )

    return model, metrics


async def _train_lstm_with_progress(
    sequences,
    config: TrainingConfig,
    feature_stats: dict,
    train_job_id: str,
    jobs_dict: dict,
    init_from_model_path: str | None = None,
) -> tuple:
    """LSTM training in a thread pool executor (same reason as _train_with_progress)."""
    loop = asyncio.get_event_loop()
    fn = functools.partial(
        train_lstm_sequences,
        sequences,
        config,
        feature_stats,
        init_from_model_path=init_from_model_path,
    )
    model, metrics = await loop.run_in_executor(None, fn)

    job = jobs_dict[train_job_id]
    job.current_epoch = config.epochs
    job.progress_rate = 1.0
    job.last_loss = metrics["final_train_loss"]

    for epoch, loss in enumerate(metrics["epoch_losses"], start=1):
        job.epoch_logs.append(
            EpochLog(epoch=epoch, loss=loss, timestamp=_utc_now_iso())
        )

    return model, metrics


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
