from pydantic import BaseModel, Field


class PositionApplyRequest(BaseModel):
    coll_x: float = Field(..., description="Commanded X position in mm")
    coll_y: float = Field(..., description="Commanded Y position in mm")


class PositionApplyResponse(BaseModel):
    actual_x: float = Field(..., description="Actual X position in mm")
    actual_y: float = Field(..., description="Actual Y position in mm")


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
