# app/endpoints/webhook.py

import os
import hmac
import hashlib
import traceback
from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.db import grant_user_access, buscar_usuario  # Função correta

router = APIRouter(tags=["webhook"])

# Carrega segredos
DISRUPTY_WEBHOOK_SECRET = os.getenv("DISRUPTY_WEBHOOK_SECRET") or ""
SENDGRID_API_KEY        = os.getenv("SENDGRID_API_KEY") or ""
FROM_EMAIL              = os.getenv("FROM_EMAIL") or ""

if not DISRUPTY_WEBHOOK_SECRET:
    raise RuntimeError("❌ DISRUPTY_WEBHOOK_SECRET não definida")
if not SENDGRID_API_KEY or not FROM_EMAIL:
    raise RuntimeError("❌ SENDGRID_API_KEY ou FROM_EMAIL não definidos")

sg_client = SendGridAPIClient(SENDGRID_API_KEY)

async def send_access_email(to_email: str):
    try:
        msg = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject="Seu acesso NutriFlow foi liberado!",
            html_content=(
                "<p>Olá!</p>"
                "<p>Seu pagamento foi confirmado e seu acesso ao NutriFlow está liberado.</p>"
                "<p>Obrigado,<br/>Equipe NutriFlow</p>"
            )
        )
        resp = sg_client.send(msg)
        print(f"[SendGrid] status: {resp.status_code}", flush=True)
        print(f"[SendGrid] body: {resp.body}", flush=True)
    except Exception as e:
        print(f"[SendGrid] erro: {e}", flush=True)
        traceback.print_exc()

@router.post("/payment")
async def disrupty_payment_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_signature: str = Header(..., alias="X-Signature")
):
    try:
        body = await request.body()
        expected = hmac.new(
            DISRUPTY_WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_signature):
            print("[Webhook] assinatura inválida", flush=True)
            raise HTTPException(400, "Invalid signature")

        event = await request.json()
        print(f"[Webhook] evento: {event}", flush=True)
        if event.get("type") != "payment.success":
            print("[Webhook] evento ignorado", flush=True)
            return {"status": "ignored"}

        user_id = event["data"]["metadata"].get("user_id")
        if not user_id:
            print("[Webhook] user_id ausente", flush=True)
            raise HTTPException(400, "user_id não encontrado")

        await grant_user_access(user_id)

        user = buscar_usuario(user_id)
        if not user:
            print(f"[Webhook] usuário não existe: {user_id}", flush=True)
            raise HTTPException(404, "Usuário não existe")

        email = user.get("username")
        if not email:
            print(f"[Webhook] email ausente p/ usuário: {user_id}", flush=True)
            raise HTTPException(400, "Email do usuário não encontrado")

        background_tasks.add_task(send_access_email, email)
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Webhook] erro interno: {e}", flush=True)
        traceback.print_exc()
        raise HTTPException(500, "Internal server error")
