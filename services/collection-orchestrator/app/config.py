from __future__ import annotations

import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    simple_controller_url: str = Field(default="http://simple-controller:8003")
    ai_controller_url: str = Field(default="http://ai-controller:9006")
    adaptive_controller_url: str = Field(default="http://adaptive-controller:8010")
    lstm_controller_url: str = Field(default="http://lstm-controller:9012")
    trainer_url: str = Field(default="http://trainer:9005")
    recipe_service_url: str = Field(default="http://recipe-service:8002")
    downstream_timeout_sec: float = Field(default=30.0, gt=0.0)
    max_workers: int = Field(default=4, ge=1, le=32)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            simple_controller_url=os.getenv("SIMPLE_CONTROLLER_URL", "http://simple-controller:8003"),
            ai_controller_url=os.getenv("AI_CONTROLLER_URL", "http://ai-controller:9006"),
            adaptive_controller_url=os.getenv("ADAPTIVE_CONTROLLER_URL", "http://adaptive-controller:8010"),
            lstm_controller_url=os.getenv("LSTM_CONTROLLER_URL", "http://lstm-controller:9012"),
            trainer_url=os.getenv("TRAINER_URL", "http://trainer:9005"),
            recipe_service_url=os.getenv("RECIPE_SERVICE_URL", "http://recipe-service:8001"),
            downstream_timeout_sec=float(os.getenv("DOWNSTREAM_TIMEOUT_SEC", "30.0")),
            max_workers=int(os.getenv("MAX_WORKERS", "4")),
        )