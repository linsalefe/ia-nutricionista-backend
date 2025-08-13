from fastapi import APIRouter, Request
from app.services.email import send_access_email

router = APIRouter(tags=["webhook"])

@router.post("/kiwify")
async def kiwify_webhook(request: Request):
    payload = await request.json()
    buyer = payload.get("buyer") or {}
    email = (buyer.get("email") or payload.get("email") or "").strip()
    name = (buyer.get("name") or payload.get("name") or "").strip()

    status_text = " ".join([
        str(payload.get("status", "")),
        str(payload.get("payment_status", "")),
        str(payload.get("event", "")),
    ]).lower()

    approved = any(w in status_text for w in ["approved","aprovada","paid","pago","completed","concluida","concluída","succeeded","captured"])

    if not email:
        return {"ok": True, "skipped": "no_email"}

    if not approved:
        return {"ok": True, "skipped": "not_approved"}

    send_access_email(to=email, name=name or None)
    return {"ok": True}
