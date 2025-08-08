# app/endpoints/weight_logs.py

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, confloat

from app.auth import get_current_user
from app.db import buscar_usuario, salvar_usuario

router = APIRouter(tags=["weight-logs"])


class WeightLogIn(BaseModel):
    weight: confloat(gt=0)  # kg > 0
    recorded_at: Optional[datetime] = None  # default: agora (UTC)


class WeightLogOut(BaseModel):
    weight: float
    recorded_at: str  # ISO-8601


@router.post("", response_model=WeightLogOut, status_code=201)
def create_weight_log(payload: WeightLogIn, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    user = buscar_usuario(username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    # horário padrão: agora (UTC)
    dt = payload.recorded_at or datetime.now(timezone.utc)
    log = {"weight": float(payload.weight), "recorded_at": dt.isoformat()}

    logs = (user.get("weight_logs") or []) + [log]
    user["weight_logs"] = logs

    # Define peso inicial caso ainda não exista
    if not user.get("initial_weight"):
        user["initial_weight"] = float(payload.weight)

    salvar_usuario(user)
    return WeightLogOut(weight=float(payload.weight), recorded_at=dt.isoformat())


@router.get("", response_model=List[WeightLogOut])
def list_weight_logs(
    period: Optional[str] = Query(
        None, description="Período: '7d', '30d', '1y' (dias/anos)."
    ),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = buscar_usuario(username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    raw_logs = user.get("weight_logs") or []

    # parse ISO (aceita com/sem timezone)
    parsed = []
    for l in raw_logs:
        ts = l.get("recorded_at")
        try:
            dt = datetime.fromisoformat(ts)
        except Exception:
            # fallback: trata 'Z'
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        parsed.append({"weight": float(l["weight"]), "recorded_at": dt})

    parsed.sort(key=lambda x: x["recorded_at"])

    if period:
        try:
            qty, unit = int(period[:-1]), period[-1]
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=qty if unit == "d" else qty * 365)
            parsed = [l for l in parsed if l["recorded_at"] >= cutoff]
        except Exception:
            # período inválido -> ignora filtro
            pass

    return [
        WeightLogOut(weight=l["weight"], recorded_at=l["recorded_at"].isoformat())
        for l in parsed
    ]
