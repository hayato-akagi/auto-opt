from pydantic import BaseModel, Field


class PositionApplyRequest(BaseModel):
    coll_x: float = Field(..., description="Commanded X position in mm")
    coll_y: float = Field(..., description="Commanded Y position in mm")


class PositionApplyResponse(BaseModel):
    coll_x_shift: float = Field(..., description="Effective X shift in mm")
    coll_y_shift: float = Field(..., description="Effective Y shift in mm")


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
