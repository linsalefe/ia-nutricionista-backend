# app/endpoints/dashboard.py

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user

router = APIRouter(tags=["dashboard"])


class LogItem(BaseModel):
    date: str   # ISO-8601 (UTC)
    weight: float


class DashboardMetricsOut(BaseModel):
    objective: Optional[str]
    height_cm: Optional[float]
    initial_weight: Optional[float]
    current_weight: Optional[float]
    weight_lost: Optional[float]
    bmi: Optional[float]
    history: List[LogItem]


def _parse_iso_to_utc(ts: str) -> datetime:
    """Aceita ISO com/sem timezone e retorna aware (UTC)."""
    if not ts:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        # trata sufixo 'Z'
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.get("/metrics", response_model=DashboardMetricsOut)
def get_dashboard_metrics(
    period: Optional[str] = Query(None, description="Período ex.: '7d', '30d', '1y'"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(401, "Não autenticado")

    # Coleta e normaliza logs
    raw_logs = current_user.get("weight_logs") or []
    parsed: List[Dict[str, Any]] = []
    for item in raw_logs:
        w = item.get("weight")
        ts = item.get("recorded_at") or item.get("date")
        if w is None or ts is None:
            continue
        try:
            dt = _parse_iso_to_utc(str(ts))
            parsed.append({"dt": dt, "weight": float(w)})
        except Exception:
            continue

    # Ordena por data
    parsed.sort(key=lambda x: x["dt"])

    # Filtro de período (UTC aware)
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
                cutoff = None
            if cutoff:
                parsed = [l for l in parsed if l["dt"] >= cutoff]
        except Exception:
            # período inválido -> ignora filtro
            pass

    # Métricas
    height_cm: Optional[float] = current_user.get("height_cm")
    initial_weight: Optional[float] = current_user.get("initial_weight")
    current_weight: Optional[float] = parsed[-1]["weight"] if parsed else None

    # Se não houver peso inicial salvo, usa o primeiro do histórico (sem mutar DB aqui)
    if initial_weight is None and parsed:
        initial_weight = parsed[0]["weight"]

    def _bmi(w: Optional[float], h_cm: Optional[float]) -> Optional[float]:
        if not w or not h_cm or h_cm <= 0:
            return None
        h_m = h_cm / 100.0
        if h_m <= 0:
            return None
        return round(w / (h_m * h_m), 2)

    bmi = _bmi(current_weight, height_cm)

    weight_lost: Optional[float] = None
    if initial_weight is not None and current_weight is not None:
        weight_lost = round(initial_weight - current_weight, 2)

    objective = current_user.get("objective") or current_user.get("objetivo")

    history: List[LogItem] = [
        LogItem(date=entry["dt"].isoformat(), weight=entry["weight"]) for entry in parsed
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
