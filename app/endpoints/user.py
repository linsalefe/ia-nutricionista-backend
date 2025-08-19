# app/endpoints/user.py

import os
from uuid import uuid4
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.auth import (
    get_current_user,
    create_access_token,
    verify_password,
    hash_password
)
from app.db import session_scope, User

# Router (prefixo vem do main.py)
router = APIRouter(tags=["user"])

# Diretório para uploads de avatar
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UPLOADS_ROOT = os.path.join(BASE_DIR, "uploads")
UPLOAD_DIR = os.path.join(UPLOADS_ROOT, "avatars")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================
# MODELS
# ============================

class UserSignup(BaseModel):
    username: str = Field(..., description="E-mail ou nome de usuário único")
    password: str = Field(..., min_length=6, description="Senha com no mínimo 6 caracteres")
    nome: Optional[str] = Field(None, description="Nome completo")
    objetivo: Optional[str] = Field(None, description="Objetivo nutricional")
    height_cm: Optional[float] = Field(None, description="Altura em centímetros")
    initial_weight: Optional[float] = Field(None, description="Peso inicial em kg")


class UserLogin(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserUpdateIn(BaseModel):
    nome: Optional[str] = None
    objetivo: Optional[str] = None
    height_cm: Optional[float] = None
    initial_weight: Optional[float] = None


class PasswordUpdateIn(BaseModel):
    password: str = Field(..., min_length=6, description="Nova senha (mín. 6)")


class UserOut(BaseModel):
    id: str
    username: str
    nome: Optional[str]
    objetivo: Optional[str]
    height_cm: Optional[float]
    initial_weight: Optional[float]
    has_access: bool
    avatar_url: Optional[str] = None


# ============================
# HELPERS
# ============================

def _public_url_to_disk_path(url_or_path: str) -> Optional[str]:
    """
    Converte uma URL/rota pública (/static/avatars/xxx) para o caminho no disco.
    Retorna None se não der pra mapear.
    """
    if not url_or_path:
        return None
    path = url_or_path
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        path = urlparse(url_or_path).path  # /static/avatars/xxx.png

    if "/static/" in path:
        rel = path.split("/static/", 1)[-1]  # avatars/xxx.png
    else:
        rel = path.lstrip("/")
    # Só permitimos acessar dentro de uploads
    full = os.path.normpath(os.path.join(UPLOADS_ROOT, rel))
    if not full.startswith(UPLOADS_ROOT):
        return None
    return full


def _user_to_dict(user: User) -> Dict[str, Any]:
    """Converte User do SQLAlchemy para dict (compatibilidade com auth)"""
    return {
        "id": str(user.id),
        "username": user.username,
        "password": user.password_hash,
        "password_hash": user.password_hash,
        "nome": user.nome,
        "objetivo": user.objetivo,
        "height_cm": user.height_cm,
        "initial_weight": user.initial_weight,
        "has_access": user.has_access,
        "is_admin": user.is_admin,
        "avatar_url": user.avatar_url,
    }


# ============================
# ENDPOINTS
# ============================

@router.post("/signup", status_code=201)
def signup(data: UserSignup):
    with session_scope() as db:
        # Verifica se usuário já existe
        existing = db.execute(select(User).where(User.username == data.username)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Usuário já existe")
        
        # Cria novo usuário
        hashed = hash_password(data.password)
        user = User(
            username=data.username,
            password_hash=hashed,
            nome=data.nome,
            objetivo=data.objetivo,
            height_cm=data.height_cm,
            initial_weight=data.initial_weight,
            has_access=False,
            is_admin=False,
            avatar_url=None
        )
        db.add(user)
        
    return {"msg": "Usuário criado com sucesso"}


@router.post("/login", response_model=TokenOut)
def login(data: UserLogin):
    with session_scope() as db:
        user = db.execute(select(User).where(User.username == data.username)).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciais inválidas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not verify_password(data.password, user.password_hash or ""):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciais inválidas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = create_access_token({"sub": user.username})
        return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
def get_profile(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    with session_scope() as db:
        user = db.execute(select(User).where(User.username == current_user["username"])).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        # normaliza avatar para URL absoluta
        avatar = user.avatar_url
        if avatar:
            if avatar.startswith("http://") or avatar.startswith("https://"):
                avatar_abs = avatar
            else:
                rel = avatar.split("/static/", 1)[-1] if "/static/" in avatar else avatar.lstrip("/")
                avatar_abs = str(request.url_for("static", path=rel))
        else:
            avatar_abs = None

        return UserOut(
            id=str(user.id),
            username=user.username,
            nome=user.nome,
            objetivo=user.objetivo,
            height_cm=user.height_cm,
            initial_weight=user.initial_weight,
            has_access=user.has_access,
            avatar_url=avatar_abs
        )


@router.patch("", response_model=UserOut)
def update_profile(
    payload: UserUpdateIn,
    current_user: Dict[str, Any] = Depends(get_current_user),
    request: Request = None
):
    updates = payload.dict(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")
    
    with session_scope() as db:
        user = db.execute(select(User).where(User.username == current_user["username"])).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        # Atualiza campos
        for field, value in updates.items():
            if hasattr(user, field):
                setattr(user, field, value)
    
    return get_profile(request, _user_to_dict(user))  # type: ignore


@router.put("/password", status_code=204)
def update_password(
    data: PasswordUpdateIn,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    with session_scope() as db:
        user = db.execute(select(User).where(User.username == current_user["username"])).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        user.password_hash = hash_password(data.password)


@router.post("/avatar")
def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    # valida formato
    if file.content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        raise HTTPException(400, "Formato inválido. Use PNG/JPG/WEBP")

    with session_scope() as db:
        user = db.execute(select(User).where(User.username == current_user["username"])).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        # apaga avatar antigo (se existir)
        old = user.avatar_url
        old_path = _public_url_to_disk_path(old) if old else None
        if old_path and os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass  # não bloqueia o fluxo

        # nome único
        ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
        fname = f"{user.username}-{uuid4().hex}{ext}"
        fpath = os.path.join(UPLOAD_DIR, fname)

        # grava no disco
        with open(fpath, "wb") as f:
            f.write(file.file.read())

        # URL pública absoluta via /static
        public_url = str(request.url_for("static", path=f"avatars/{fname}"))

        # persiste no usuário
        user.avatar_url = public_url

        return {"ok": True, "avatar_url": public_url}