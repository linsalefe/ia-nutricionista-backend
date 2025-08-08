# app/endpoints/meal.py
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import BaseModel, Field

from app.auth import SECRET_KEY, ALGORITHM
from app.db import meals_db, Meal  # TinyDB Table e Query

router = APIRouter(tags=["meal"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")


# -------- Auth helper --------
def get_current_username(token: str = Depends(oauth2_scheme)) -> str:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if not username:
            raise cred_exc
        return username
    except JWTError:
        raise cred_exc


# -------- Schemas --------
class MealIn(BaseModel):
    analise: str = Field(..., description="Texto da análise nutricional")
    imagem_nome: Optional[str] = Field(None, description="Nome do arquivo salvo em /uploads")


class MealOut(MealIn):
    id: str
    usuario: str
    data: str


# -------- Helpers --------
def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _gen_id(username: str) -> str:
    return f"{username}-{int(datetime.utcnow().timestamp() * 1000)}"


# -------- Rotas base (casam com /api/meal e /api/meals) --------
@router.get("", response_model=List[MealOut])
def list_meals(username: str = Depends(get_current_username)):
    """Lista refeições do usuário (mais recentes primeiro)"""
    rows = meals_db.search(Meal.usuario == username)
    rows.sort(key=lambda r: r.get("data", ""), reverse=True)
    return rows


@router.post("", response_model=MealOut, status_code=status.HTTP_201_CREATED)
def create_meal(body: MealIn, username: str = Depends(get_current_username)):
    """Cria uma refeição (mesmo comportamento de /save)"""
    doc = {
        "id": _gen_id(username),
        "usuario": username,
        "analise": body.analise,
        "imagem_nome": body.imagem_nome,
        "data": _now_iso(),
    }
    meals_db.insert(doc)
    return doc


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(meal_id: str, username: str = Depends(get_current_username)):
    """Remove uma refeição do usuário pelo id"""
    deleted = meals_db.remove((Meal.usuario == username) & (Meal.id == meal_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Refeição não encontrada")
    return


# -------- Rotas de compatibilidade --------
@router.post("/save", response_model=MealOut, status_code=status.HTTP_201_CREATED)
def save_meal(meal: MealIn, username: str = Depends(get_current_username)):
    """Compat: salva refeição (equivale ao POST base)"""
    return create_meal(meal, username)  # reaproveita lógica


@router.get("/history", response_model=List[MealOut])
def get_meal_history(username: str = Depends(get_current_username)):
    """Compat: histórico (equivale ao GET base)"""
    return list_meals(username)
