# app/endpoints/meal.py
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete

from app.auth import get_current_user  # retorna dict com dados do usuário
from app.db import session_scope, User, MealAnalysis

router = APIRouter(tags=["meal"])


# ===== Schemas =====
class MealIn(BaseModel):
    analise: Dict[str, Any] = Field(..., description="Análise nutricional (objeto)")
    imagem_nome: Optional[str] = Field(None, description="Nome do arquivo salvo em /uploads")


class MealOut(MealIn):
    id: str
    usuario: str
    data: str


# ===== Helpers =====
def _require_username(current_user: dict) -> str:
    username = current_user.get("username") or current_user.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Usuário não autenticado")
    return username


def _meal_to_out(username: str, m: MealAnalysis) -> MealOut:
    return MealOut(
        id=str(m.id),
        usuario=username,
        analise=m.analysis or {},
        imagem_nome=m.image_name,
        data=m.created_at.isoformat(),
    )


# ===== Rotas =====
@router.get("", response_model=List[MealOut])
def list_meals(
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
):
    """Lista refeições do usuário (mais recentes primeiro)."""
    username = _require_username(current_user)
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            return []
        rows = (
            db.execute(
                select(MealAnalysis)
                .where(MealAnalysis.user_id == u.id)
                .order_by(MealAnalysis.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_meal_to_out(username, r) for r in rows]


@router.post("", response_model=MealOut, status_code=status.HTTP_201_CREATED)
def create_meal(
    body: MealIn,
    current_user: dict = Depends(get_current_user),
):
    """Cria uma refeição."""
    username = _require_username(current_user)
    now = datetime.utcnow()
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        meal = MealAnalysis(
            user_id=u.id,
            analysis=body.analise,
            image_name=body.imagem_nome,
            created_at=now,
        )
        db.add(meal)
        db.flush()  # garante ID
        return _meal_to_out(username, meal)


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(
    meal_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove uma refeição do usuário pelo ID (UUID)."""
    username = _require_username(current_user)
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        # deleta somente se pertencer ao usuário
        result = db.execute(
            delete(MealAnalysis).where(
                MealAnalysis.id == meal_id,
                MealAnalysis.user_id == u.id,
            )
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Refeição não encontrada")
        return


# ===== Rotas de compatibilidade =====
@router.post("/save", response_model=MealOut, status_code=status.HTTP_201_CREATED)
def save_meal(meal: MealIn, current_user: dict = Depends(get_current_user)):
    """Compat: salva refeição (equivale ao POST base)."""
    return create_meal(meal, current_user)


@router.get("/history", response_model=List[MealOut])
def get_meal_history(limit: int = 10, current_user: dict = Depends(get_current_user)):
    """Compat: histórico (equivale ao GET base)."""
    return list_meals(limit, current_user)
