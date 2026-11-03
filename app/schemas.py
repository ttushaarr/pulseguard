from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, json_schema_extra={"example": "GitHub API"})
    url: str = Field(..., min_length=5, max_length=500, json_schema_extra={"example": "https://api.github.com"})
    method: str = Field(default="GET", json_schema_extra={"example": "GET"})
    interval_seconds: int = Field(default=30, ge=5, le=3600)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    expected_status: int = Field(default=200, ge=100, le=599)
    is_active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    interval_seconds: Optional[int] = None
    timeout_seconds: Optional[int] = None
    expected_status: Optional[int] = None
    is_active: Optional[bool] = None


class CheckResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    status_code: Optional[int]
    response_time_ms: Optional[float]
    is_up: bool
    error_message: Optional[str]
    checked_at: datetime


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    cause: str
    is_resolved: bool
    started_at: datetime
    resolved_at: Optional[datetime]


class ServiceDetail(ServiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    is_up: Optional[bool] = None
    last_checked_at: Optional[datetime] = None
    last_response_time_ms: Optional[float] = None
    uptime_percentage: float = 100.0


class SystemStats(BaseModel):
    total_services: int
    services_up: int
    services_down: int
    overall_uptime_pct: float
    avg_response_time_ms: float
    active_incidents: int
