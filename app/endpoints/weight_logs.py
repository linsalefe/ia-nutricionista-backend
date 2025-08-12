# app/endpoints/weight_logs.py

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from pydantic import BaseModel, confloat

from app.auth import get_current_user
from app.db import buscar_usuario, salvar_usuario

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

def _parse_iso(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def _ensure_ids(user: dict) -> List[dict]:
    logs = list(user.get("weight_logs") or [])
    changed = False
    for l in logs:
        if not l.get("id"):
            l["id"] = str(uuid4())
            changed = True
    if changed:
        user["weight_logs"] = logs
        salvar_usuario(user)
    return logs

def _recompute_weights(user: dict) -> None:
    logs = list(user.get("weight_logs") or [])
    if not logs:
        user["current_weight"] = None
        salvar_usuario(user)
        return
    # ordena por data
    logs_sorted = sorted(logs, key=lambda x: _parse_iso(x["recorded_at"]))
    user["weight_logs"] = logs_sorted
    # inicial permanece se já existir; se não existir, usa o primeiro
    if user.get("initial_weight") is None:
        user["initial_weight"] = float(logs_sorted[0]["weight"])
    # current é o último
    user["current_weight"] = float(logs_sorted[-1]["weight"])
    salvar_usuario(user)

# --------- Endpoints ---------
@router.post("", response_model=WeightLogOut, status_code=201)
def create_weight_log(payload: WeightLogIn, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    user = buscar_usuario(username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    dt_iso = _to_utc_iso(payload.recorded_at or datetime.now(timezone.utc))
    log = {"id": str(uuid4()), "weight": float(payload.weight), "recorded_at": dt_iso}

    logs = list(user.get("weight_logs") or [])
    logs.append(log)
    user["weight_logs"] = logs

    if user.get("initial_weight") is None:
        user["initial_weight"] = float(payload.weight)

    _recompute_weights(user)
    return WeightLogOut(**log)

@router.get("", response_model=List[WeightLogOut])
def list_weight_logs(
    period: Optional[str] = Query(None, description="Período: '7d', '30d', '1y'."),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = buscar_usuario(username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    logs = _ensure_ids(user)
    parsed = []
    for l in logs:
        dt = _parse_iso(l["recorded_at"])
        parsed.append({"id": l["id"], "weight": float(l["weight"]), "recorded_at": dt})

    parsed.sort(key=lambda x: x["recorded_at"])

    if period:
        try:
            qty, unit = int(period[:-1]), period[-1].lower()
            now = datetime.now(timezone.utc)
            cutoff = now - (timedelta(days=qty) if unit == "d" else timedelta(days=qty * 365))
            parsed = [l for l in parsed if l["recorded_at"] >= cutoff]
        except Exception:
            pass

    return [
        WeightLogOut(id=l["id"], weight=l["weight"], recorded_at=_to_utc_iso(l["recorded_at"]))
        for l in parsed
    ]

@router.patch("/{log_id}", response_model=WeightLogOut)
def update_weight_log(
    log_id: str = Path(..., description="ID do registro de peso"),
    payload: WeightLogUpdate = ...,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = buscar_usuario(username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    logs = _ensure_ids(user)
    idx = next((i for i, l in enumerate(logs) if l.get("id") == log_id), None)
    if idx is None:
        raise HTTPException(404, "Registro não encontrado")

    if payload.weight is not None:
        logs[idx]["weight"] = float(payload.weight)
    if payload.recorded_at is not None:
        logs[idx]["recorded_at"] = _to_utc_iso(payload.recorded_at)

    user["weight_logs"] = logs
    _recompute_weights(user)

    updated = next(l for l in user["weight_logs"] if l["id"] == log_id)
    return WeightLogOut(id=updated["id"], weight=float(updated["weight"]), recorded_at=updated["recorded_at"])

@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weight_log(
    log_id: str = Path(..., description="ID do registro de peso"),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = buscar_usuario(username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    logs = _ensure_ids(user)
    new_logs = [l for l in logs if l.get("id") != log_id]
    if len(new_logs) == len(logs):
        raise HTTPException(404, "Registro não encontrado")

    user["weight_logs"] = new_logs
    _recompute_weights(user)
    return
