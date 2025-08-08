# app/endpoints/meal.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import BaseModel
from datetime import datetime

from app.auth import SECRET_KEY, ALGORITHM
from app.db import meals_db, Meal  # << usa o mesmo TinyDB central

router = APIRouter(tags=["meal"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")


def get_current_username(token: str = Depends(oauth2_scheme)) -> str:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise cred_exc
        return username
    except JWTError:
        raise cred_exc


class MealIn(BaseModel):
    analise: str
    imagem_nome: str | None = None


@router.post("/save")
def save_meal(meal: MealIn, username: str = Depends(get_current_username)):
    """Salva uma refeição/análise para o usuário logado"""
    try:
        doc = {
            "usuario": username,
            "analise": meal.analise,
            "imagem_nome": meal.imagem_nome,
            "data": datetime.utcnow().isoformat()
        }
        meals_db.insert(doc)
        return {"ok": True, "msg": "Refeição salva com sucesso!"}
    except Exception as e:
        raise HTTPException(500, f"Falha ao salvar refeição: {e}")


@router.get("/history")
def get_meal_history(username: str = Depends(get_current_username)):
    """Retorna o histórico do usuário (mais recentes primeiro)"""
    rows = meals_db.search(Meal.usuario == username)
    rows.sort(key=lambda r: r.get("data", ""), reverse=True)
    return rows
