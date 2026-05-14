from __future__ import annotations

import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    recipe_service_url: str = Field(default="http://recipe-service:8002")
    model_store_url: str = Field(default="http://model-store:9009")
    downstream_timeout_sec: float = Field(default=10.0, gt=0.0)
    default_model_type: str = Field(default="baseline_only")
    default_model_version: str | None = Field(default=None)

    @classmethod
    def from_env(cls) -> "Settings":
        raw_version = os.getenv("DEFAULT_MODEL_VERSION")
        return cls(
            recipe_service_url=os.getenv("RECIPE_SERVICE_URL", "http://recipe-service:8002"),
            model_store_url=os.getenv("MODEL_STORE_URL", "http://model-store:9009"),
            downstream_timeout_sec=float(os.getenv("DOWNSTREAM_TIMEOUT_SEC", "10.0")),
            default_model_type=os.getenv("DEFAULT_MODEL_TYPE", "baseline_only"),
            default_model_version=raw_version.strip() if raw_version else None,
        )