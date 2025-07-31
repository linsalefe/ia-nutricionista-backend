from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from app.auth import get_current_user

router = APIRouter(tags=["dashboard"])


class LogItem(BaseModel):
    date: str
    weight: float


class DashboardMetricsOut(BaseModel):
    objective: Optional[str]
    height_cm: Optional[float]
    initial_weight: Optional[float]
    current_weight: Optional[float]
    weight_lost: Optional[float]
    bmi: Optional[float]
    history: List[LogItem]


@router.get("/metrics", response_model=DashboardMetricsOut)
def get_dashboard_metrics(
    period: Optional[str] = Query(None, description="e.g. '7d', '30d', '1y'"),
    current_user: dict = Depends(get_current_user),
):
    raw = current_user.get("weight_logs", []) or []
    logs = [
        {"recorded_at": datetime.fromisoformat(item["recorded_at"]), "weight": item["weight"]}
        for item in raw
    ]
    logs.sort(key=lambda x: x["recorded_at"])

    if period and logs:
        qty, unit = int(period[:-1]), period[-1]
        now = datetime.now()
        cutoff = now - (timedelta(days=qty) if unit=="d" else timedelta(days=qty*365))
        logs = [l for l in logs if l["recorded_at"] >= cutoff]

    history = [LogItem(date=l["recorded_at"].date().isoformat(), weight=l["weight"]) for l in logs]
    initial = current_user.get("initial_weight") or 0
    height = current_user.get("height_cm") or 0
    current_w = history[-1].weight if history else None
    lost = (initial - current_w) if (initial and current_w) else None
    bmi = (current_w / ((height/100)**2)) if (current_w and height) else None

    return DashboardMetricsOut(
        objective=current_user.get("objetivo"),
        height_cm=height,
        initial_weight=initial,
        current_weight=current_w,
        weight_lost=lost,
        bmi=bmi,
        history=history,
    )
