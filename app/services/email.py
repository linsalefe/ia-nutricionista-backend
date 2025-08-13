# app/services/email.py

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

def send_access_email(
    to: str, 
    name: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None
):
    """
    Envia email de acesso liberado
    Se subject e body não forem fornecidos, usa template padrão
    """
    
    # Configurações do email
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    email_user = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_PASSWORD")
    
    if not email_user or not email_password:
        print("❌ Configurações de email não encontradas")
        return
    
    # Template padrão se não fornecido
    if not subject:
        subject = "�� Bem-vindo ao NutriFlow!"
    
    if not body:
        body = f"""
Ol�� {name or 'Cliente'}!

Sua compra foi aprovada com sucesso! á��

Voc�� agora tem acesso completo êà plataforma NutriFlow.

�� Acesse agora: https://app-nutriflow.onrender.com/login

Seja bem-vindo �� famàília NutriFlow! ��

---
Equipe NutriFlow
        """
    
    try:
        # Criar mensagem
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = to
        msg['Subject'] = subject
        
        # Anexar corpo do email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Conectar e enviar
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
        
        print(f"��✅ Email enviado para {to}")
        
    except Exception as e:
        print(f"❌ Erro ao enviar email: {e}")
        raise
