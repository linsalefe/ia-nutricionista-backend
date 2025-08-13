import os
import resend
from typing import Optional

resend.api_key = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("MAIL_FROM", "NutriFlow <no-reply@nutriflow.cloud>")
APP_URL = os.getenv("APP_URL", "https://app.nutriflow.cloud")

def send_access_email(to: str, name: Optional[str] = None) -> dict:
    if not resend.api_key:
        raise RuntimeError("RESEND_API_KEY not configured")

    first = (name or to.split("@")[0]).split(" ")[0]
    subject = "Seu acesso ao NutriFlow foi liberado"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;padding:24px">
      <h2 style="margin:0 0 12px;color:#0a0a0a">Ola, {first}!</h2>
      <p style="margin:0 0 12px;color:#333">Sua compra foi confirmada e seu acesso ao <b>NutriFlow</b> ja esta ativo.</p>
      <p style="margin:0 0 16px;color:#333">Clique abaixo para entrar:</p>
      <p><a href="{APP_URL}" style="background:#16a34a;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;display:inline-block">Acessar o app</a></p>
      <hr style="border:none;border-top:1px solid #eee;margin:20px 0" />
      <p style="font-size:12px;color:#666">Se nao foi voce, ignore este email.</p>
    </div>
    """
    return resend.Emails.send({
        "from": FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html,
    })
