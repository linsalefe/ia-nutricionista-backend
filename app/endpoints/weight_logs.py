# app/endpoints/weight_logs.py

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from pydantic import BaseModel, confloat
from sqlalchemy import select, update, delete

from app.auth import get_current_user
from app.db import session_scope, User, WeightLog

router = APIRouter(tags=["weight-logs"])

# --------- Schemas ---------
class WeightLogIn(BaseModel):
    weight: confloat(gt=0)
    recorded_at: Optional[datetime] = None  # default: agora (UTC)

class WeightLogUpdate(BaseModel):
    weight: Optional[confloat(gt=0)] = None
    recorded_at: Optional[datetime] = None

class WeightLogOut(BaseModel):
    id: str
    weight: float
    recorded_at: str  # ISO-8601 (UTC)

# --------- Helpers ---------
def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()

def _update_user_weights(db, user_id: str) -> None:
    """Atualiza initial_weight e current_weight do usuário baseado nos logs"""
    logs = db.execute(
        select(WeightLog)
        .where(WeightLog.user_id == user_id)
        .order_by(WeightLog.recorded_at.asc())
    ).scalars().all()
    
    if not logs:
        # Se não tem logs, limpa os pesos
        db.execute(
            update(User)
            .where(User.id == user_id)
            .values(initial_weight=None)
        )
        return
    
    first_weight = logs[0].weight
    last_weight = logs[-1].weight
    
    # Busca o usuário para verificar se já tem initial_weight
    user = db.execute(select(User).where(User.id == user_id)).scalar_one()
    
    updates = {}
    if user.initial_weight is None:
        updates["initial_weight"] = first_weight
    
    # Sempre atualiza o peso atual
    # Note: removemos current_weight da tabela User pois será calculado dinamicamente
    
    if updates:
        db.execute(update(User).where(User.id == user_id).values(**updates))

# --------- Endpoints ---------
@router.post("", response_model=WeightLogOut, status_code=201)
def create_weight_log(payload: WeightLogIn, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    
    with session_scope() as db:
        # Busca o usuário
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        # Cria o log
        recorded_at = payload.recorded_at or datetime.now(timezone.utc)
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        
        log = WeightLog(
            user_id=user.id,
            weight=float(payload.weight),
            recorded_at=recorded_at
        )
        db.add(log)
        db.flush()  # Para pegar o ID gerado
        
        # Atualiza pesos do usuário
        _update_user_weights(db, user.id)
        
        return WeightLogOut(
            id=str(log.id),
            weight=log.weight,
            recorded_at=_to_utc_iso(log.recorded_at)
        )

@router.get("", response_model=List[WeightLogOut])
def list_weight_logs(
    period: Optional[str] = Query(None, description="Período: '7d', '30d', '1y'."),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    
    with session_scope() as db:
        # Busca o usuário
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        # Query base
        query = select(WeightLog).where(WeightLog.user_id == user.id)
        
        # Filtro por período
        if period:
            try:
                qty = int(period[:-1])
                unit = period[-1].lower()
                now = datetime.now(timezone.utc)
                if unit == "d":
                    cutoff = now - timedelta(days=qty)
                elif unit == "y":
                    cutoff = now - timedelta(days=qty * 365)
                else:
                    cutoff = now - timedelta(days=qty)  # default para dias
                
                query = query.where(WeightLog.recorded_at >= cutoff)
            except Exception:
                pass  # período inválido -> não filtra
        
        # Executa e ordena
        logs = db.execute(query.order_by(WeightLog.recorded_at.asc())).scalars().all()
        
        return [
            WeightLogOut(
                id=str(log.id),
                weight=log.weight,
                recorded_at=_to_utc_iso(log.recorded_at)
            )
            for log in logs
        ]

@router.patch("/{log_id}", response_model=WeightLogOut)
def update_weight_log(
    log_id: str = Path(..., description="ID do registro de peso"),
    payload: WeightLogUpdate = ...,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    
    with session_scope() as db:
        # Busca o usuário
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        # Busca o log
        log = db.execute(
            select(WeightLog)
            .where(WeightLog.id == log_id, WeightLog.user_id == user.id)
        ).scalar_one_or_none()
        
        if not log:
            raise HTTPException(404, "Registro não encontrado")
        
        # Atualiza campos
        if payload.weight is not None:
            log.weight = float(payload.weight)
        
        if payload.recorded_at is not None:
            recorded_at = payload.recorded_at
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
            log.recorded_at = recorded_at
        
        # Atualiza pesos do usuário
        _update_user_weights(db, user.id)
        
        return WeightLogOut(
            id=str(log.id),
            weight=log.weight,
            recorded_at=_to_utc_iso(log.recorded_at)
        )

@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weight_log(
    log_id: str = Path(..., description="ID do registro de peso"),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    
    with session_scope() as db:
        # Busca o usuário
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        # Verifica se o log existe e pertence ao usuário
        log = db.execute(
            select(WeightLog)
            .where(WeightLog.id == log_id, WeightLog.user_id == user.id)
        ).scalar_one_or_none()
        
        if not log:
            raise HTTPException(404, "Registro não encontrado")
        
        # Remove o log
        db.execute(delete(WeightLog).where(WeightLog.id == log_id))
        
        # Atualiza pesos do usuário
        _update_user_weights(db, user.id)
        
        return