import os
from uuid import uuid4
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import (
    get_current_user,
    create_access_token,
    verify_password,
    hash_password
)
from app.db import session_scope, User

router = APIRouter(tags=["user"])

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UPLOADS_ROOT = os.path.join(BASE_DIR, "uploads")
UPLOAD_DIR = os.path.join(UPLOADS_ROOT, "avatars")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================
# MODELS
# ============================
class UserSignup(BaseModel):
    username: str
    password: str = Field(..., min_length=6)
    nome: Optional[str] = None
    objetivo: Optional[str] = None
    height_cm: Optional[float] = None
    initial_weight: Optional[float] = None

class UserLogin(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserUpdateIn(BaseModel):
    # painel (legacy)
    nome: Optional[str] = None
    objetivo: Optional[str] = None
    height_cm: Optional[float] = None
    initial_weight: Optional[float] = None
    # chat/perfil
    sex: Optional[str] = Field(None, description="M ou F")
    age: Optional[int] = None
    current_weight: Optional[float] = None
    activity_level: Optional[float] = Field(None, description="1.2, 1.375, 1.55, 1.725, 1.9")
    goal_type: Optional[str] = Field(None, description="lose|maintain|gain")
    pace_kg_per_week: Optional[float] = None
    restrictions: Optional[List[str]] = None
    confirm_low_calorie: Optional[bool] = None

class PasswordUpdateIn(BaseModel):
    password: str = Field(..., min_length=6)

class UserOut(BaseModel):
    id: str
    username: str
    nome: Optional[str]
    objetivo: Optional[str]
    sex: Optional[str]
    age: Optional[int]
    height_cm: Optional[float]
    initial_weight: Optional[float]
    current_weight: Optional[float]
    activity_level: Optional[float]
    goal_type: Optional[str]
    pace_kg_per_week: Optional[float]
    restrictions: List[str] = []
    confirm_low_calorie: bool = False
    has_access: bool
    avatar_url: Optional[str] = None

# ============================
# HELPERS
# ============================
def _public_url_to_disk_path(url_or_path: str) -> Optional[str]:
    if not url_or_path:
        return None
    path = url_or_path
    if url_or_path.startswith(("http://", "https://")):
        path = urlparse(url_or_path).path
    if "/static/" in path:
        rel = path.split("/static/", 1)[-1]
    else:
        rel = path.lstrip("/")
    full = os.path.normpath(os.path.join(UPLOADS_ROOT, rel))
    if not full.startswith(UPLOADS_ROOT):
        return None
    return full

def _serialize_user_for_out(u: User, request: Optional[Request]) -> UserOut:
    avatar_abs = None
    if u.avatar_url:
        if u.avatar_url.startswith(("http://", "https://")):
            avatar_abs = u.avatar_url
        else:
            rel = u.avatar_url.split("/static/", 1)[-1] if "/static/" in u.avatar_url else u.avatar_url.lstrip("/")
            avatar_abs = str(request.url_for("static", path=rel)) if request else u.avatar_url

    return UserOut(
        id=str(u.id),
        username=u.username,
        nome=u.nome,
        objetivo=u.objetivo,
        sex=u.sex,
        age=u.age,
        height_cm=u.height_cm,
        initial_weight=u.initial_weight,
        current_weight=u.current_weight,
        activity_level=u.activity_level,
        goal_type=u.goal_type,
        pace_kg_per_week=u.pace_kg_per_week,
        restrictions=(u.restrictions or []),
        confirm_low_calorie=bool(u.confirm_low_calorie),
        has_access=u.has_access,
        avatar_url=avatar_abs
    )

# ============================
# ENDPOINTS
# ============================
@router.post("/signup", status_code=201)
def signup(data: UserSignup):
    with session_scope() as db:
        existing = db.execute(select(User).where(User.username == data.username)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Usuário já existe")
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
        if not user or not verify_password(data.password, user.password_hash or ""):
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
        u = db.execute(select(User).where(User.username == current_user["username"])).scalar_one_or_none()
        if not u:
            raise HTTPException(404, "Usuário não encontrado")
        return _serialize_user_for_out(u, request)

@router.patch("", response_model=UserOut)
def update_profile(
    payload: UserUpdateIn,
    current_user: Dict[str, Any] = Depends(get_current_user),
    request: Request = None
):
    updates = payload.dict(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    # validações rápidas
    if "sex" in updates and updates["sex"] not in (None, "M", "F"):
        raise HTTPException(422, "sex deve ser 'M' ou 'F'.")
    if "activity_level" in updates and updates["activity_level"] not in (None, 1.2, 1.375, 1.55, 1.725, 1.9):
        raise HTTPException(422, "activity_level deve ser um de 1.2, 1.375, 1.55, 1.725, 1.9.")
    if "goal_type" in updates and updates["goal_type"] not in (None, "lose", "maintain", "gain"):
        raise HTTPException(422, "goal_type deve ser 'lose', 'maintain' ou 'gain'.")
    if "restrictions" in updates and updates["restrictions"] is not None:
        if not isinstance(updates["restrictions"], list) or not all(isinstance(x, str) for x in updates["restrictions"]):
            raise HTTPException(422, "restrictions deve ser lista de strings.")

    with session_scope() as db:
        u = db.execute(select(User).where(User.username == current_user["username"])).scalar_one_or_none()
        if not u:
            raise HTTPException(404, "Usuário não encontrado")
        for field, value in updates.items():
            if hasattr(u, field):
                setattr(u, field, value)

    # pós-commit, responde com dados frescos (evita DetachedInstanceError)
    return get_profile(request, current_user)

@router.put("/password", status_code=204)
def update_password(
    data: PasswordUpdateIn,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == current_user["username"])).scalar_one_or_none()
        if not u:
            raise HTTPException(404, "Usuário não encontrado")
        u.password_hash = hash_password(data.password)

@router.post("/avatar")
def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    if file.content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        raise HTTPException(400, "Formato inválido. Use PNG/JPG/WEBP")

    with session_scope() as db:
        u = db.execute(select(User).where(User.username == current_user["username"])).scalar_one_or_none()
        if not u:
            raise HTTPException(404, "Usuário não encontrado")

        old_path = None
        if u.avatar_url:
            old_path = _public_url_to_disk_path(u.avatar_url)
        if old_path and os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass

        ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
        fname = f"{u.username}-{uuid4().hex}{ext}"
        fpath = os.path.join(UPLOAD_DIR, fname)

        with open(fpath, "wb") as f:
            f.write(file.file.read())

        public_url = str(request.url_for("static", path=f"avatars/{fname}"))
        u.avatar_url = public_url

        return {"ok": True, "avatar_url": public_url}
