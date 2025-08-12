# app/endpoints/weight_logs.py

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, confloat

from app.auth import get_current_user
from app.db import buscar_usuario, salvar_usuario

router = APIRouter(tags=["weight-logs"])


class WeightLogIn(BaseModel):
    weight: confloat(gt=0)                 # kg > 0
    recorded_at: Optional[datetime] = None # se não vier, usa agora (UTC)


class WeightLogOut(BaseModel):
    weight: float
    recorded_at: str                        # ISO-8601 (sempre UTC)
    id: str


def _to_utc_iso(dt: datetime) -> str:
    """Garante datetime timezone-aware em UTC e retorna isoformat."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def _parse_iso(ts: str) -> datetime:
    """Aceita ISO com 'Z' ou '+00:00'."""
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@router.post("", response_model=WeightLogOut, status_code=201)
def create_weight_log(
    payload: WeightLogIn,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = buscar_usuario(username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    # horário padrão: agora (UTC)
    dt_iso = _to_utc_iso(payload.recorded_at or datetime.now(timezone.utc))

    # 👉 Sempre cria um NOVO registro (nunca sobrescreve)
    log = {
        "id": str(uuid4()),
        "weight": float(payload.weight),
        "recorded_at": dt_iso,
    }

    logs = list(user.get("weight_logs") or [])
    logs.append(log)
    # Mantém ordenado por data
    logs.sort(key=lambda x: _parse_iso(x["recorded_at"]))

    user["weight_logs"] = logs

    # Campos de conveniência
    if not user.get("initial_weight"):
        user["initial_weight"] = float(payload.weight)
    user["current_weight"] = float(payload.weight)

    salvar_usuario(user)
    return WeightLogOut(weight=log["weight"], recorded_at=log["recorded_at"], id=log["id"])


@router.get("", response_model=List[WeightLogOut])
def list_weight_logs(
    period: Optional[str] = Query(
        None, description="Período: '7d', '30d', '1y'."
    ),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = buscar_usuario(username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    raw_logs = list(user.get("weight_logs") or [])

    parsed = []
    for l in raw_logs:
        dt = _parse_iso(l["recorded_at"])
        parsed.append({"id": l.get("id", ""), "weight": float(l["weight"]), "recorded_at": dt})

    parsed.sort(key=lambda x: x["recorded_at"])

    if period:
        try:
            qty, unit = int(period[:-1]), period[-1]
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=qty if unit == "d" else qty * 365)
            parsed = [l for l in parsed if l["recorded_at"] >= cutoff]
        except Exception:
            pass  # período inválido -> não filtra

    return [
        WeightLogOut(
            id=(l["id"] or str(uuid4())),
            weight=l["weight"],
            recorded_at=_to_utc_iso(l["recorded_at"]),
        )
        for l in parsed
    ]
