from __future__ import annotations

import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    recipe_service_url: str = Field(default="http://recipe-service:8002")
    downstream_timeout_sec: float = Field(default=10.0, gt=0.0)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            recipe_service_url=os.getenv("RECIPE_SERVICE_URL", "http://recipe-service:8002"),
            downstream_timeout_sec=float(os.getenv("DOWNSTREAM_TIMEOUT_SEC", "10.0")),
        )
