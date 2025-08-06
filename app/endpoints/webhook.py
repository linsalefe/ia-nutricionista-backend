# app/endpoints/webhook.py

import os
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
import resend

from app.db import grant_user_access, buscar_usuario, salvar_usuario

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

async def send_welcome_email(to_email: str, customer_name: str):
    """
    Envia email de boas-vindas com credenciais de acesso.
    """
    try:
        params = {
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": "Bem-vindo ao NutriFlow! Seus dados de acesso",
            "html": (
                f"<p>Olá <strong>{customer_name}</strong>!</p>"
                "<p>Seu pagamento foi confirmado e sua conta NutriFlow está ativa! 🎉</p>"
                "<p><strong>Seus dados de acesso:</strong></p>"
                "<ul>"
                f"<li><strong>Email:</strong> {to_email}</li>"
                "<li><strong>Senha:</strong> nutriflow123</li>"
                "</ul>"
                f'<p><a href="https://app-nutriflow.onrender.com/login" style="background: #4CAF50; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px;">🚀 Acessar NutriFlow</a></p>'
                "<p><em>Recomendamos alterar sua senha no primeiro acesso.</em></p>"
                "<p>Obrigado,<br/>Equipe NutriFlow</p>"
            )
        }
        
        email = resend.Emails.send(params)
        print(f"[Resend] Email de boas-vindas enviado: {email}", flush=True)
        
    except Exception as e:
        print(f"[Resend] Erro ao enviar email de boas-vindas: {e}", flush=True)

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
        # Extrair dados do cliente do Disrupty
        customer_data = event.get("data", {}).get("customer", {})
        customer_email = customer_data.get("email")
        customer_name = customer_data.get("name")
        
        if not customer_email:
            print("❌ Email do cliente não encontrado no webhook")
            return {"status": "email_not_found"}

        # 3) Busca ou cria usuário
        user = buscar_usuario(customer_email)
        
        if not user:
            # Cria novo usuário
            print(f"🆕 Criando novo usuário: {customer_email}")
            from app.auth import hash_password
            from uuid import uuid4
            
            new_user = {
                "id": str(uuid4()),
                "username": customer_email,
                "password": hash_password("nutriflow123"),  # senha padrão
                "nome": customer_name,
                "objetivo": "Perder peso",
                "height_cm": None,
                "initial_weight": None,
                "weight_logs": [],
                "refeicoes": [],
                "has_access": True,  # Já liberado
                "is_admin": False,
            }
            salvar_usuario(new_user)
            user = new_user
        else:
            # Usuário já existe, só libera acesso
            print(f"👤 Usuário existente: {customer_email}")
            try:
                await grant_user_access(user.get("id"))
            except Exception as e:
                print(f"❌ Erro ao conceder acesso: {e}")
                return {"status": "error", "message": str(e)}

        # 4) Envia email com credenciais
        background_tasks.add_task(send_welcome_email, customer_email, customer_name)

    return {"status": "ok"}