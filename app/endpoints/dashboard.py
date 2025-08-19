# app/endpoints/dashboard.py

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import get_current_user
from app.db import session_scope, User, WeightLog

router = APIRouter(tags=["dashboard"])


class LogItem(BaseModel):
    date: str            # ISO-8601 (UTC)
    weight: float


class DashboardMetricsOut(BaseModel):
    objective: Optional[str] = None
    height_cm: Optional[float] = None
    initial_weight: Optional[float] = None
    current_weight: Optional[float] = None
    weight_lost: Optional[float] = None
    bmi: Optional[float] = None
    history: List[LogItem] = []


def _to_utc_iso(dt: datetime) -> str:
    """Converte datetime para ISO string UTC"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


@router.get("/metrics", response_model=DashboardMetricsOut)
def get_dashboard_metrics(
    period: Optional[str] = Query(None, description="Período: '7d', '30d', '1y'"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(401, "Não autenticado")

    username = current_user["username"]
    
    with session_scope() as db:
        # Busca o usuário
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        
        # Query base para logs
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
        
        # Busca logs ordenados por data
        logs = db.execute(query.order_by(WeightLog.recorded_at.asc())).scalars().all()
        
        # --- Métricas ---
        height_cm = user.height_cm
        initial_weight = user.initial_weight
        current_weight = logs[-1].weight if logs else None
        
        # Se não tem initial_weight definido, usa o primeiro log
        if initial_weight is None and logs:
            initial_weight = logs[0].weight
        
        def _bmi(w: Optional[float], h_cm: Optional[float]) -> Optional[float]:
            if not w or not h_cm or h_cm <= 0:
                return None
            h_m = h_cm / 100.0
            return round(w / (h_m * h_m), 2) if h_m > 0 else None
        
        bmi = _bmi(current_weight, height_cm)
        
        weight_lost: Optional[float] = None
        if initial_weight is not None and current_weight is not None:
            weight_lost = round(initial_weight - current_weight, 2)
        
        objective = user.objetivo  # campo objetivo na tabela User
        
        # Constrói histórico
        history: List[LogItem] = [
            LogItem(date=_to_utc_iso(log.recorded_at), weight=log.weight)
            for log in logs
        ]
        
        return DashboardMetricsOut(
            objective=objective,
            height_cm=height_cm,
            initial_weight=initial_weight,
            current_weight=current_weight,
            weight_lost=weight_lost,
            bmi=bmi,
            history=history,
        )