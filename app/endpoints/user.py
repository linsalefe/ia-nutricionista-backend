from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import uuid4

from app.auth import get_current_user, create_access_token, verify_password, hash_password
from app.db import buscar_usuario, salvar_usuario

router = APIRouter(tags=["user"])


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
    }
    salvar_usuario(user)
    return {"msg": "Usuário criado com sucesso"}


@router.post("/login", response_model=TokenOut)
def login(data: UserLogin):
    user = buscar_usuario(data.username)
    if not user or not verify_password(data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user["username"], "nome": user.get("nome")})
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
def get_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    user = current_user.copy()
    user.pop("password", None)
    return UserOut(
        id=user.get("id", user["username"]),
        username=user["username"],
        nome=user.get("nome"),
        objetivo=user.get("objetivo"),
        height_cm=user.get("height_cm"),
        initial_weight=user.get("initial_weight"),
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
    )
