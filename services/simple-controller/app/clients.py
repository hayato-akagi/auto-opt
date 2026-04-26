from __future__ import annotations

from typing import Any

import httpx

from .errors import DownstreamServiceError


class RecipeClient:
    def __init__(self, recipe_service_url: str, timeout_sec: float) -> None:
        self.recipe_service_url = recipe_service_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_sec)

    async def close(self) -> None:
        await self._client.aclose()

    async def create_trial(self, experiment_id: str, control: dict[str, Any]) -> dict[str, Any]:
        return await self._post_json(
            f"{self.recipe_service_url}/experiments/{experiment_id}/trials",
            {"mode": "control_loop", "control": control},
            "recipe-service",
        )

    async def execute_step(self, experiment_id: str, trial_id: str, coll_x: float, coll_y: float) -> dict[str, Any]:
        return await self._post_json(
            f"{self.recipe_service_url}/experiments/{experiment_id}/trials/{trial_id}/steps",
            {
                "coll_x": coll_x,
                "coll_y": coll_y,
                "options": {
                    "return_ray_hits": False,
                    "return_images": False,
                },
            },
            "recipe-service",
        )

    async def complete_trial(self, experiment_id: str, trial_id: str) -> dict[str, Any]:
        return await self._post_json(
            f"{self.recipe_service_url}/experiments/{experiment_id}/trials/{trial_id}/complete",
            {},
            "recipe-service",
        )

    async def _post_json(self, url: str, payload: dict[str, Any], downstream: str) -> dict[str, Any]:
        try:
            response = await self._client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise DownstreamServiceError(
                detail=f"timeout calling {downstream}",
                downstream=downstream,
                status_code=504,
            ) from exc
        except httpx.RequestError as exc:
            raise DownstreamServiceError(
                detail=f"failed to call {downstream}: {exc}",
                downstream=downstream,
                status_code=502,
            ) from exc

        if response.status_code >= 400:
            detail: str
            try:
                body = response.json()
                if isinstance(body, dict) and "detail" in body:
                    detail = str(body["detail"])
                else:
                    detail = response.text
            except ValueError:
                detail = response.text
            status = 404 if response.status_code == 404 else 502
            raise DownstreamServiceError(
                detail=f"{downstream} returned error: {detail}",
                downstream=downstream,
                status_code=status,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise DownstreamServiceError(
                detail=f"{downstream} returned non-json response",
                downstream=downstream,
                status_code=502,
            ) from exc

        if not isinstance(body, dict):
            raise DownstreamServiceError(
                detail=f"{downstream} returned invalid json payload",
                downstream=downstream,
                status_code=502,
            )

        return body
