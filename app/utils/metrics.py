# app/utils/metrics.py

from typing import Optional

def compute_bmi(weight: float, height_cm: float) -> Optional[float]:
    """
    Calcula o IMC: peso (kg) / (altura em m)².
    Retorna None se peso ou altura não forem válidos (>0).
    """
    if not weight or not height_cm:
        return None
    h_m = height_cm / 100
    return weight / (h_m * h_m)

def compute_progress(initial: float, current: float) -> float:
    """
    Calcula percentual de perda de peso: 
    (initial - current) / initial * 100, entre 0 e 100.
    """
    if not initial:
        return 0.0
    pct = (initial - current) / initial * 100
    return max(0.0, min(pct, 100.0))
