# app/endpoints/webhook.py
from fastapi import APIRouter, Request, HTTPException, Header
import hmac
import hashlib
import os

from app.db import grant_user_access  # Função que garante acesso no DB

router = APIRouter(
    prefix="/api/webhook",
    tags=["webhook"],
)

DISRUPTY_WEBHOOK_SECRET = os.getenv("DISRUPTY_WEBHOOK_SECRET")
if not DISRUPTY_WEBHOOK_SECRET:
    raise RuntimeError("❌ DISRUPTY_WEBHOOK_SECRET não definida no .env")

@router.post("/payment")
async def disrupty_payment_webhook(
    request: Request,
    x_signature: str = Header(None, alias="X-Signature")
):
    body = await request.body()
    expected_sig = hmac.new(
        DISRUPTY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, x_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = await request.json()
    if event.get("type") == "payment.success":
        data = event.get("data", {})
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id não encontrado em metadata")

        await grant_user_access(user_id)

    return {"status": "ok"}
