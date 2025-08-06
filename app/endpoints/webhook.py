# app/endpoints/webhook.py

from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
import hmac
import hashlib
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.db import grant_user_access, buscar_usuario_by_id  # Funções do DB

router = APIRouter(tags=["webhook"])

# Carrega segredos e configurações do .env
DISRUPTY_WEBHOOK_SECRET = os.getenv("DISRUPTY_WEBHOOK_SECRET")
SENDGRID_API_KEY         = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL               = os.getenv("FROM_EMAIL")

if not DISRUPTY_WEBHOOK_SECRET:
    raise RuntimeError("❌ DISRUPTY_WEBHOOK_SECRET não definida no .env")
if not SENDGRID_API_KEY or not FROM_EMAIL:
    raise RuntimeError("❌ SENDGRID_API_KEY ou FROM_EMAIL não definidos no .env")

# Cliente SendGrid
sg_client = SendGridAPIClient(SENDGRID_API_KEY)

async def send_access_email(to_email: str):
    """
    Envia um e-mail via SendGrid notificando liberação de acesso.
    """
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject="Seu acesso NutriFlow foi liberado!",
        html_content=(
            "<p>Olá!</p>"
            "<p>Seu pagamento foi confirmado e seu acesso ao NutriFlow está liberado.</p>"
            "<p>Obrigado,<br/>Equipe NutriFlow</p>"
        )
    )
    sg_client.send(message)

@router.post("/payment")
async def disrupty_payment_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_signature: str = Header(..., alias="X-Signature")
):
    # 1) Valida assinatura HMAC
    body = await request.body()
    expected_sig = hmac.new(
        DISRUPTY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, x_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 2) Processa evento
    event = await request.json()
    if event.get("type") == "payment.success":
        user_id = event.get("data", {}).get("metadata", {}).get("user_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id não encontrado em metadata")

        # 3) Concede acesso no DB
        await grant_user_access(user_id)

        # 4) Busca usuário para pegar e-mail
        user = buscar_usuario_by_id(user_id)
        email = user.get("username")
        if email:
            # 5) Agenda envio de e-mail em background
            background_tasks.add_task(send_access_email, email)

    return {"status": "ok"}
