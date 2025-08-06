# app/endpoints/webhook.py

import os
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
import resend

from app.db import grant_user_access, buscar_usuario_by_id

router = APIRouter(tags=["webhook"])

# Carrega segredos do .env
DISRUPTY_WEBHOOK_SECRET = os.getenv("DISRUPTY_WEBHOOK_SECRET")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@nutriflow.cloud")  # email padrão

if not DISRUPTY_WEBHOOK_SECRET:
    raise RuntimeError("❌ DISRUPTY_WEBHOOK_SECRET não definida no .env")
if not RESEND_API_KEY:
    raise RuntimeError("❌ RESEND_API_KEY não definida no .env")

# Configura o Resend
resend.api_key = RESEND_API_KEY

async def send_access_email(to_email: str):
    """
    Envia um e-mail via Resend notificando liberação de acesso.
    """
    try:
        params = {
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": "Seu acesso NutriFlow foi liberado!",
            "html": (
                "<p>Olá!</p>"
                "<p>Seu pagamento foi confirmado e seu acesso ao NutriFlow está liberado.</p>"
                "<p>Obrigado,<br/>Equipe NutriFlow</p>"
            )
        }
        
        email = resend.Emails.send(params)
        print(f"[Resend] Email enviado: {email}", flush=True)
        
    except Exception as e:
        print(f"[Resend] Erro ao enviar email: {e}", flush=True)

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

    # 2) Processa evento JSON
    event = await request.json()
    if event.get("type") == "payment.success":
        user_id = event.get("data", {}).get("metadata", {}).get("user_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id não encontrado em metadata")

        # 3) Concede acesso no DB
        await grant_user_access(user_id)

        # 4) Busca usuário para pegar e-mail
        user = buscar_usuario_by_id(user_id)
        if user:
            email = user.get("username")  # username é o email
            if email:
                # 5) Agenda envio de e-mail em background
                background_tasks.add_task(send_access_email, email)

    return {"status": "ok"}