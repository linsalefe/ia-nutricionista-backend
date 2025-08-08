# app/endpoints/user.py

import os
from uuid import uuid4
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from pydantic import BaseModel, Field

from app.auth import (
    get_current_user,
    create_access_token,
    verify_password,
    hash_password
)
from app.db import buscar_usuario, salvar_usuario

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
# ENDPOINTS
# ============================

@router.post("/signup", status_code=201)
def signup(data: UserSignup):
    if buscar_usuario(data.username):
        raise HTTPException(status_code=400, detail="Usuário já existe")
    hashed = hash_password(data.password)
    user = {
        "id": str(uuid4()),
        "username": data.username,
        "password": hashed,
        "nome": data.nome,
        "objetivo": data.objetivo,
        "height_cm": data.height_cm,
        "initial_weight": data.initial_weight,
        "weight_logs": [],
        "refeicoes": [],
        "has_access": False,
        "is_admin": False,
        "avatar_url": None
    }
    salvar_usuario(user)
    return {"msg": "Usuário criado com sucesso"}


@router.post("/login", response_model=TokenOut)
def login(data: UserLogin):
    user = buscar_usuario(data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    stored = user.get("password") or user.get("password_hash")
    if not verify_password(data.password, stored or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user["username"]})
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
def get_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    return UserOut(
        id=current_user.get("id", current_user["username"]),
        username=current_user["username"],
        nome=current_user.get("nome"),
        objetivo=current_user.get("objetivo"),
        height_cm=current_user.get("height_cm"),
        initial_weight=current_user.get("initial_weight"),
        has_access=current_user.get("has_access", False),
        avatar_url=current_user.get("avatar_url")
    )


@router.patch("", response_model=UserOut)
def update_profile(
    payload: UserUpdateIn,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    updates = payload.dict(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")
    current_user.update(updates)
    salvar_usuario(current_user)
    return UserOut(
        id=current_user.get("id", current_user["username"]),
        username=current_user["username"],
        nome=current_user.get("nome"),
        objetivo=current_user.get("objetivo"),
        height_cm=current_user.get("height_cm"),
        initial_weight=current_user.get("initial_weight"),
        has_access=current_user.get("has_access", False),
        avatar_url=current_user.get("avatar_url")
    )


@router.post("/avatar")
def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    # validação simples
    if file.content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        raise HTTPException(400, "Formato inválido. Use PNG/JPG/WEBP")

    # nome único
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    fname = f"{current_user['username']}-{uuid4().hex}{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)

    # salvar no disco
    with open(fpath, "wb") as f:
        f.write(file.file.read())

    # URL ABSOLUTA usando a montagem /static (definida no main.py)
    # Ex.: https://seu-backend.com/static/avatars/arquivo.png
    public_url = str(request.url_for("static", path=f"avatars/{fname}"))

    # atualizar usuário
    current_user["avatar_url"] = public_url
    salvar_usuario(current_user)

    return {"ok": True, "avatar_url": public_url}
