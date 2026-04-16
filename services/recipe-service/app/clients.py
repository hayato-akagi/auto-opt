from __future__ import annotations

from typing import Any

import httpx

from .errors import DownstreamServiceError, DownstreamTimeoutError


class DownstreamClients:
    def __init__(
        self,
        optics_sim_kraken_url: str,
        optics_sim_simple_url: str,
        position_service_url: str,
        bolt_service_url: str,
        timeout_sec: float,
    ) -> None:
        self.optics_sim_kraken_url = optics_sim_kraken_url.rstrip("/")
        self.optics_sim_simple_url = optics_sim_simple_url.rstrip("/")
        self.position_service_url = position_service_url.rstrip("/")
        self.bolt_service_url = bolt_service_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_sec)

    async def close(self) -> None:
        await self._client.aclose()

    async def apply_position(self, coll_x: float, coll_y: float) -> dict[str, Any]:
        return await self._post_json(
            f"{self.position_service_url}/position/apply",
            {"coll_x": coll_x, "coll_y": coll_y},
            "position-service",
        )

    async def apply_bolt(
        self,
        x0: float,
        y0: float,
        bolt_model: dict[str, Any],
        random_seed: int | None,
    ) -> dict[str, Any]:
        return await self._post_json(
            f"{self.bolt_service_url}/bolt/apply",
            {
                "x0": x0,
                "y0": y0,
                "bolt_model": bolt_model,
                "random_seed": random_seed,
            },
            "bolt-service",
        )

    async def simulate(self, engine_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if engine_type == "Simple":
            url = f"{self.optics_sim_simple_url}/simulate"
            downstream = "optics-sim-simple"
        else:
            url = f"{self.optics_sim_kraken_url}/simulate"
            downstream = "optics-sim-kraken"
        
        return await self._post_json(url, payload, downstream)

    async def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        downstream: str,
    ) -> dict[str, Any]:
        try:
            response = await self._client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise DownstreamTimeoutError(
                detail=f"timeout calling {downstream}",
                downstream=downstream,
            ) from exc
        except httpx.RequestError as exc:
            raise DownstreamServiceError(
                detail=f"failed to call {downstream}: {exc}",
                downstream=downstream,
            ) from exc

        if response.status_code >= 400:
            raise DownstreamServiceError(
                detail=f"{downstream} returned error: {self._extract_detail(response)}",
                downstream=downstream,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise DownstreamServiceError(
                detail=f"{downstream} returned non-json response",
                downstream=downstream,
            ) from exc

        if not isinstance(body, dict):
            raise DownstreamServiceError(
                detail=f"{downstream} returned invalid json payload",
                downstream=downstream,
            )
        return body

    def _extract_detail(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict) and "detail" in payload:
                return str(payload["detail"])
        except ValueError:
            pass

        text = response.text.strip()
        if text:
            return text
        return f"status {response.status_code}"
