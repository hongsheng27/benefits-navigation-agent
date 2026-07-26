"""Health endpoint used by the frontend to confirm backend availability.

This endpoint reports process liveness only. It must not expose session state,
user-supplied text, workflow contents, or credential status.

`HealthResponse` is a transport-local shape that mirrors the frontend's
`BackendHealth` type. Domain contracts belong in `app.schemas`.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(status="ok")
