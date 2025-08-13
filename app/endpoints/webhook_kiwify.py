from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import os, hmac, hashlib, json
from typing import Optional, Tuple
from datetime import datetime
import uuid

from app.services.email import send_access_email
from sqlalchemy import create_engine, MetaData, Table, update, select, insert

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
metadata = MetaData()
users = Table("users", metadata, autoload_with=engine)

router = APIRouter(tags=["webhook"])

def _is_approved(payload: dict) -> bool:
    txt = " ".join([
        str(payload.get("status", "")),
        str(payload.get("payment_status", "")),
        str(payload.get("event", "")),
    ]).lower()
    return any(w in txt for w in [
        "approved", "aprovada", "paid", "pago", "completed",
        "concluida", "concluída", "succeeded", "captured"
    ])

def _get_email_and_name(payload: dict) -> Tuple[Optional[str], Optional[str]]:
    buyer = payload.get("buyer") or {}
    email = (buyer.get("email") or payload.get("email") or "").strip().lower()
    name = (buyer.get("name") or payload.get("name") or "").strip()
    return (email or None, name or None)

def _find_user(conn, email: str):
    row = conn.execute(select(users).where(users.c.username == email)).fetchone()
    return row._mapping if row else None

def _ensure_access(email: str, name: Optional[str]) -> int:
    with engine.begin() as conn:
        row = _find_user(conn, email)
        if row:
            if not row.get("has_access", False):
                conn.execute(update(users).where(users.c.id == row["id"]).values(has_access=True))
            return 1
        values = {
            "id": uuid.uuid4(),
            "username": email,
            "has_access": True,
            "is_admin": False,
            "created_at": datetime.utcnow(),
        }
        if name and "nome" in users.c:
            values["nome"] = name
        try:
            conn.execute(insert(users).values(values))
            return 1
        except Exception:
            return 0

def _verify_signature(raw_body: bytes, got_sig: str | None) -> bool:
    token = os.getenv("KIWIFY_WEBHOOK_TOKEN") or ""
    if not token:
        return True  # sem token configurado, não bloqueia
    if not got_sig:
        return False
    expected = hmac.new(token.encode(), raw_body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(got_sig, expected)

@router.post("/kiwify")
async def kiwify_webhook(request: Request):
    raw = await request.body()
    sig = request.query_params.get("signature") or request.headers.get("X-Signature")
    if not _verify_signature(raw, sig):
        return JSONResponse({"ok": False, "error": "invalid_signature"}, status_code=401)

    payload = json.loads(raw or b"{}")
    email, name = _get_email_and_name(payload)
    if not email:
        return {"ok": True, "skipped": "no_email"}
    if not _is_approved(payload):
        return {"ok": True, "skipped": "not_approved"}

    updated = _ensure_access(email, name)
    try:
        send_access_email(to=email, name=name)
    except Exception:
        pass
    return {"ok": True, "updated": int(updated)}
