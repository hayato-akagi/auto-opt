from pydantic import BaseModel
from typing import Any


class HealthResponse(BaseModel):
    status: str
