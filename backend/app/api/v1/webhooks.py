"""/webhooks/{provider} inbound webhook receivers.

SPEC-BE-071 F10: no provider webhook is implemented, so the route answers 404
for every provider instead of accepting unauthenticated data. Restore a
provider only together with its signature verification (e.g. Meta's
X-Hub-Signature-256), then route the payload to workflow_engine/dispatcher.py.
"""
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/{provider}", status_code=status.HTTP_404_NOT_FOUND)
async def receive_webhook(provider: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "No webhook is enabled for this provider."})
