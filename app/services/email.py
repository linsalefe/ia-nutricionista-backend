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
   """Envia email de acesso liberado"""
   
   smtp_server = os.getenv("SMTP_SERVER", "smtp.hostinger.com")
   smtp_port = int(os.getenv("SMTP_PORT", "587"))
   email_user = os.getenv("EMAIL_USER")
   email_password = os.getenv("EMAIL_PASSWORD")
   
   if not email_user or not email_password:
       print("Configuracoes de email nao encontradas")
       return
   
   if not subject:
       subject = "Bem-vindo ao NutriFlow!"
   
   if not body:
       body = f"Ola {name or 'Cliente'}!\n\nSua compra foi aprovada!\n\nAcesse: https://app-nutriflow.onrender.com/login\n\n---\nEquipe NutriFlow"
   
   try:
       msg = MIMEMultipart()
       msg['From'] = f"NutriFlow <{email_user}>"
       msg['To'] = to
       msg['Subject'] = subject
       
       msg.attach(MIMEText(body, 'plain', 'utf-8'))
       
       with smtplib.SMTP(smtp_server, smtp_port) as server:
           server.starttls()
           server.login(email_user, email_password)
           server.send_message(msg)
       
       print(f"Email enviado para {to}")
       
   except Exception as e:
       print(f"Erro ao enviar email: {e}")
       raise
