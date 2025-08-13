from fastapi import APIRouter, Request
import os
from typing import Optional, Tuple
from datetime import datetime
import uuid
import secrets
import string

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

def _generate_temp_password(length: int = 8) -> str:
    """Gera uma senha temporária segura"""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def _hash_password(password: str) -> str:
    """Hash da senha usando bcrypt"""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)

def _find_user(conn, email: str):
    """Procura usuário por username=email"""
    row = conn.execute(select(users).where(users.c.username == email)).fetchone()
    return row._mapping if row else None

def _ensure_access_with_password(email: str, name: Optional[str]) -> Tuple[int, Optional[str]]:
    """
    Garante acesso ao usuário e retorna (updated, senha_temporaria)
    Se usuário não existe, cria com senha temporária
    Se existe mas não tem acesso, libera acesso mas não altera senha
    """
    with engine.begin() as conn:
        row = _find_user(conn, email)
        
        if row:
            # Usuário existe
            if not row.get("has_access", False):
                # Libera acesso mas mantém senha existente
                conn.execute(
                    update(users)
                    .where(users.c.id == row["id"])
                    .values(has_access=True)
                )
                return (1, None)  # Sem nova senha
            return (1, None)  # Já tinha acesso
        
        # Usuário não existe -> criar com senha temporária
        temp_password = _generate_temp_password()
        hashed_password = _hash_password(temp_password)
        
        values = {
            "id": uuid.uuid4(),
            "username": email,
            "password_hash": hashed_password,
            "has_access": True,
            "is_admin": False,
            "created_at": datetime.utcnow(),
        }
        if name and "nome" in users.c:
            values["nome"] = name
        
        try:
            conn.execute(insert(users).values(values))
            return (1, temp_password)  # Nova senha gerada
        except Exception:
            return (0, None)

def send_welcome_email(email: str, name: Optional[str], temp_password: Optional[str]):
    """Envia email de boas-vindas com dados de acesso"""
    try:
        if temp_password:
            # Novo usuário - envia dados de login
            subject = "Bem-vindo ao NutriFlow! Seus dados de acesso"
            body = f"""
Ola {name or 'Cliente'}!

Sua compra foi aprovada com sucesso!

Aqui estao seus dados de acesso ao NutriFlow:

Email: {email}
Senha temporaria: {temp_password}

Acesse agora: https://app-nutriflow.onrender.com/login

IMPORTANTE: Por seguranca, altere sua senha no primeiro acesso em Configuracoes.

Seja bem-vindo a familia NutriFlow!

---
Equipe NutriFlow
            """
        else:
            # Usuário existente - só libera acesso
            subject = "Acesso liberado no NutriFlow!"
            body = f"""
Ola {name or 'Cliente'}!

Sua compra foi aprovada e seu acesso ao NutriFlow foi liberado!

Acesse com seu login habitual: https://app-nutriflow.onrender.com/login

Aproveite todos os recursos da plataforma!

---
Equipe NutriFlow
            """
        
        # Usar função send_access_email
        send_access_email(to=email, name=name, subject=subject, body=body)
        
    except Exception as e:
        print(f"Erro ao enviar email: {e}")

@router.post("/kiwify")
async def kiwify_webhook(request: Request):
    payload = await request.json()
    email, name = _get_email_and_name(payload)

    if not email:
        return {"ok": True, "skipped": "no_email"}

    if not _is_approved(payload):
        return {"ok": True, "skipped": "not_approved"}

    updated, temp_password = _ensure_access_with_password(email, name)
    
    # Envia email personalizado baseado se é novo usuário ou não
    send_welcome_email(email, name, temp_password)

    return {
        "ok": True, 
        "updated": int(updated),
        "new_user": temp_password is not None
    }
