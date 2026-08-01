"""Health endpoint used by the frontend to confirm backend availability.

This endpoint reports process liveness only. It must not expose session state,
user-supplied text, workflow contents, or credential status.

`HealthResponse` is a transport-local shape that mirrors the frontend's
`BackendHealth` type. Domain contracts belong in `app.schemas`.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

router = APIRouter(tags=["health"])

# Process boot time — helps spot a zombie server that never picked up new code.
_STARTED_AT = (
    datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
)


class HealthResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: str
    started_at: str


@router.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(status="ok", started_at=_STARTED_AT)
