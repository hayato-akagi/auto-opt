"""HTTP clients for recipe-service, model-store, and controller services."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RecipeServiceClient:
    """Client for recipe-service API."""
    
    def __init__(self, base_url: str = "http://recipe-service:8002"):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.Client | None = None
    
    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client
    
    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
    
    def get_experiments(self) -> list[dict[str, Any]]:
        """Get all experiments.
        
        Returns:
            List of experiment dicts
        """
        try:
            client = self._get_client()
            response = client.get(f"{self.base_url}/experiments")
            response.raise_for_status()
            data = response.json()
            return data.get("experiments", [])
        except Exception as e:
            logger.error(f"Failed to get experiments: {e}")
            return []
    
    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Get experiment details.
        
        Args:
            experiment_id: Experiment ID
            
        Returns:
            Experiment dict or None
        """
        try:
            client = self._get_client()
            response = client.get(f"{self.base_url}/experiments/{experiment_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get experiment {experiment_id}: {e}")
            return None
    
    def get_trials(self, experiment_id: str) -> list[dict[str, Any]]:
        """Get trials for an experiment.
        
        Args:
            experiment_id: Experiment ID
            
        Returns:
            List of trial dicts
        """
        try:
            client = self._get_client()
            response = client.get(f"{self.base_url}/experiments/{experiment_id}/trials")
            response.raise_for_status()
            data = response.json()
            return data.get("trials", [])
        except Exception as e:
            logger.error(f"Failed to get trials for {experiment_id}: {e}")
            return []
    
    def get_steps(self, experiment_id: str, trial_id: str) -> list[dict[str, Any]]:
        """Get steps for a trial.
        
        Args:
            experiment_id: Experiment ID
            trial_id: Trial ID
            
        Returns:
            List of step dicts
        """
        try:
            client = self._get_client()
            response = client.get(
                f"{self.base_url}/experiments/{experiment_id}/trials/{trial_id}/steps"
            )
            response.raise_for_status()
            data = response.json()
            return data.get("steps", [])
        except Exception as e:
            logger.error(f"Failed to get steps for {experiment_id}/{trial_id}: {e}")
            return []
    
    def get_step_detail(
        self, experiment_id: str, trial_id: str, step_index: int
    ) -> dict[str, Any] | None:
        """Get detailed step data.
        
        Args:
            experiment_id: Experiment ID
            trial_id: Trial ID
            step_index: Step index
            
        Returns:
            Step dict or None
        """
        try:
            client = self._get_client()
            response = client.get(
                f"{self.base_url}/experiments/{experiment_id}/trials/{trial_id}/steps/{step_index}"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get step {experiment_id}/{trial_id}/{step_index}: {e}")
            return None


class ModelStoreClient:
    """Client for model-store API."""
    
    def __init__(self, base_url: str = "http://model-store:8009"):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.Client | None = None
    
    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client
    
    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
    
    def register_model(
        self,
        model_version: str,
        model_type: str,
        model_data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Register a trained model.
        
        Args:
            model_version: Model version identifier
            model_type: "mlp" or "baseline_only"
            model_data: Binary model file content
            metadata: Optional metadata
            
        Returns:
            Response dict or None
        """
        try:
            client = self._get_client()
            files = {"file": ("model.pt", model_data, "application/octet-stream")}
            data = {
                "model_version": model_version,
                "model_type": model_type,
            }
            if metadata:
                data["metadata"] = str(metadata)
            
            response = client.post(f"{self.base_url}/models", files=files, data=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to register model {model_version}: {e}")
            return None
    
    def promote_model(self, model_version: str) -> dict[str, Any] | None:
        """Promote a model to current.
        
        Args:
            model_version: Model version to promote
            
        Returns:
            Response dict or None
        """
        try:
            client = self._get_client()
            response = client.post(f"{self.base_url}/models/{model_version}/promote")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to promote model {model_version}: {e}")
            return None
