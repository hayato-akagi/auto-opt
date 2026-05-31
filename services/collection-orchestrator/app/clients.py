from __future__ import annotations

from typing import Any

import httpx


class ControllerClient:
	def __init__(
		self,
		*,
		simple_controller_url: str,
		ai_controller_url: str,
		timeout_sec: float,
	) -> None:
		self.simple_controller_url = simple_controller_url.rstrip("/")
		self.ai_controller_url = ai_controller_url.rstrip("/")
		self._client = httpx.AsyncClient(timeout=timeout_sec)

	async def close(self) -> None:
		await self._client.aclose()

	async def run_control(self, algorithm: str, payload: dict[str, Any]) -> dict[str, Any]:
		if algorithm == "simple-controller":
			base = self.simple_controller_url
		elif algorithm == "ai-controller":
			base = self.ai_controller_url
		else:
			raise ValueError(f"unsupported algorithm: {algorithm}")

		url = f"{base}/control/run"
		response = await self._client.post(url, json=payload)
		response.raise_for_status()
		body = response.json()
		if not isinstance(body, dict):
			raise ValueError("invalid response payload")
		return body


class TrainerClient:
	"""HTTP client for trainer service."""

	def __init__(self, *, trainer_url: str, timeout_sec: float) -> None:
		self.trainer_url = trainer_url.rstrip("/")
		self._client = httpx.AsyncClient(timeout=timeout_sec)

	async def close(self) -> None:
		await self._client.aclose()

	async def start_training(self, payload: dict[str, Any]) -> dict[str, Any]:
		response = await self._client.post(f"{self.trainer_url}/train", json=payload)
		response.raise_for_status()
		return response.json()

	async def get_job(self, train_job_id: str) -> dict[str, Any]:
		response = await self._client.get(f"{self.trainer_url}/train/{train_job_id}")
		response.raise_for_status()
		return response.json()


class RecipeClient:
	"""HTTP client for recipe-service (orchestrator side)."""

	def __init__(self, *, recipe_service_url: str, timeout_sec: float) -> None:
		self.recipe_service_url = recipe_service_url.rstrip("/")
		self._client = httpx.AsyncClient(timeout=timeout_sec)

	async def close(self) -> None:
		await self._client.aclose()

	async def get_experiment(self, experiment_id: str) -> dict[str, Any]:
		response = await self._client.get(
			f"{self.recipe_service_url}/experiments/{experiment_id}"
		)
		response.raise_for_status()
		return response.json()
