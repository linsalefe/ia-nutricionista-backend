# app/endpoints/nutrition.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict, Any, Tuple
from app.auth import get_current_username
import os

try:
    import psycopg2
    import psycopg2.extras
except ImportError as e:
    raise RuntimeError("psycopg2 não encontrado. Adicione 'psycopg2-binary' ao requirements.txt") from e

router = APIRouter()

# --------- SCHEMAS ---------
GoalType = Literal["lose", "maintain", "gain"]
SexType = Literal["M", "F"]

ALLOWED_ACTIVITY = {1.2, 1.375, 1.55, 1.725, 1.9}

class NutritionProfileOut(BaseModel):
    # 🔧 Agora opcional para não quebrar GET /profile quando vazio no banco
    sex: Optional[SexType] = None
    age: int
    height_cm: float
    current_weight: float
    activity_level: float
    goal_type: GoalType
    pace_kg_per_week: Optional[float] = None
    restrictions: List[str] = Field(default_factory=list)
    confirm_low_calorie: bool

class NutritionProfileUpdate(BaseModel):
    sex: Optional[Literal["M","F","m","f"]] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    current_weight: Optional[float] = None
    activity_level: Optional[float] = None
    goal_type: Optional[Literal["lose","maintain","gain"]] = None
    pace_kg_per_week: Optional[float] = None
    restrictions: Optional[List[str]] = None
    confirm_low_calorie: Optional[bool] = None

class TargetsOut(BaseModel):
    bmr: float
    tdee: float
    targets: Dict[str, float]  # {kcal, protein_g, carbs_g, fat_g}
    warnings: List[str]
    blocked: bool

# --------- DB HELPERS ---------
def _dsn_from_env() -> dict:
    url = os.getenv("DATABASE_URL")
    if url:
        return {"dsn": url}
    return {
        "host": os.getenv("PGHOST") or os.getenv("DB_HOST") or "127.0.0.1",
        "port": int(os.getenv("PGPORT") or 5432),
        "dbname": os.getenv("PGDATABASE") or os.getenv("DB_NAME") or "nutriflow",
        "user": os.getenv("PGUSER") or os.getenv("DB_USER") or "nutriflow_user",
        "password": os.getenv("PGPASSWORD") or os.getenv("DB_PASSWORD") or None,
    }

def _get_conn():
    cfg = _dsn_from_env()
    if "dsn" in cfg:
        return psycopg2.connect(cfg["dsn"], sslmode=os.getenv("PGSSLMODE","prefer"))
    return psycopg2.connect(**cfg)

def _map_objetivo_to_goal_type(obj: Optional[str]) -> GoalType:
    s = (obj or "").strip().lower()
    if any(k in s for k in ["perder", "emagrec", "déficit", "deficit", "cut"]):
        return "lose"
    if any(k in s for k in ["ganhar", "massa", "hipertrof", "bulking"]):
        return "gain"
    return "maintain"

def _fetch_profile(username: str) -> NutritionProfileOut:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT sex, age, height_cm, current_weight, activity_level, goal_type,
                   pace_kg_per_week, restrictions, confirm_low_calorie, objetivo
            FROM public.users
            WHERE username = %s
            """,
            (username,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        # Normalizações e defaults seguros
        sex_raw = row["sex"]
        sex_norm: Optional[SexType] = None
        if isinstance(sex_raw, str) and sex_raw.strip():
            up = sex_raw.strip().upper()
            if up in ("M", "F"):
                sex_norm = up  # type: ignore[assignment]

        restrictions_db = row.get("restrictions")
        if isinstance(restrictions_db, list):
            restrictions = [str(x) for x in restrictions_db]
        else:
            restrictions = []

        # Se goal_type estiver vazio, inferimos a partir de 'objetivo' legível
        goal_type = row.get("goal_type") or _map_objetivo_to_goal_type(row.get("objetivo"))

        profile = NutritionProfileOut(
            sex=sex_norm,  # pode ser None aqui
            age=int(row["age"]) if row["age"] is not None else 0,
            height_cm=float(row["height_cm"]) if row["height_cm"] is not None else 0.0,
            current_weight=float(row["current_weight"]) if row["current_weight"] is not None else 0.0,
            activity_level=float(row["activity_level"]) if row["activity_level"] is not None else 1.2,
            goal_type=goal_type,  # garantido por _map_objetivo_to_goal_type
            pace_kg_per_week=float(row["pace_kg_per_week"]) if row["pace_kg_per_week"] is not None else None,
            restrictions=restrictions,
            confirm_low_calorie=bool(row["confirm_low_calorie"]),
        )
        return profile

def _validate_update(data: NutritionProfileUpdate) -> None:
    if data.age is not None and not (14 <= data.age <= 100):
        raise HTTPException(422, detail="age deve estar entre 14 e 100.")
    if data.height_cm is not None and not (120 <= data.height_cm <= 230):
        raise HTTPException(422, detail="height_cm deve estar entre 120 e 230.")
    if data.current_weight is not None and not (25 <= data.current_weight <= 400):
        raise HTTPException(422, detail="current_weight deve estar entre 25 e 400.")
    if data.activity_level is not None:
        try:
            lvl = float(data.activity_level)
        except:
            raise HTTPException(422, detail="activity_level inválido.")
        if lvl not in ALLOWED_ACTIVITY:
            raise HTTPException(422, detail=f"activity_level deve ser um de {sorted(ALLOWED_ACTIVITY)}.")
    if data.pace_kg_per_week is not None:
        if not (0.10 <= float(data.pace_kg_per_week) <= 1.50):
            raise HTTPException(422, detail="pace_kg_per_week deve estar entre 0.10 e 1.50.")
    if data.restrictions is not None:
        if not isinstance(data.restrictions, list) or not all(isinstance(x, str) for x in data.restrictions):
            raise HTTPException(422, detail="restrictions deve ser lista de strings.")

def _do_update(username: str, data: NutritionProfileUpdate) -> None:
    fields = []
    values = []
    if data.sex is not None:
        fields.append("sex = %s")
        values.append(data.sex.upper())
    if data.age is not None:
        fields.append("age = %s")
        values.append(int(data.age))
    if data.height_cm is not None:
        fields.append("height_cm = %s")
        values.append(float(data.height_cm))
    if data.current_weight is not None:
        fields.append("current_weight = %s")
        values.append(float(data.current_weight))
    if data.activity_level is not None:
        fields.append("activity_level = %s")
        values.append(float(data.activity_level))
    if data.goal_type is not None:
        fields.append("goal_type = %s")
        values.append(data.goal_type)
    if data.pace_kg_per_week is not None:
        fields.append("pace_kg_per_week = %s")
        values.append(float(data.pace_kg_per_week))
    if data.restrictions is not None:
        fields.append("restrictions = %s")
        values.append(psycopg2.extras.Json(data.restrictions))
    if data.confirm_low_calorie is not None:
        fields.append("confirm_low_calorie = %s")
        values.append(bool(data.confirm_low_calorie))

    if not fields:
        return

    values.append(username)
    sql = f"UPDATE public.users SET {', '.join(fields)} WHERE username = %s"

    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, values)
        if cur.rowcount == 0:
            raise HTTPException(404, detail="Usuário não encontrado.")

# --------- CÁLCULOS ---------
def _round5(x: float) -> float:
    return float(int(round(x / 5.0)) * 5)

def _bmr_mifflin(sex: SexType, age: int, height_cm: float, weight_kg: float) -> float:
    if sex == "M":
        return 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        return 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

def _adjusted_weight_if_obese(current_weight: float, height_cm: float) -> float:
    h = max(height_cm, 1.0) / 100.0
    ibw = 25.0 * (h ** 2)
    if ibw <= 0:
        return current_weight
    bmi = current_weight / (h ** 2) if h > 0 else 0
    if bmi >= 30.0:
        return ibw + 0.25 * (current_weight - ibw)
    return current_weight

def _compute_targets(profile: NutritionProfileOut) -> Tuple[TargetsOut, Dict[str, Any]]:
    bmr = _bmr_mifflin(profile.sex or "M", profile.age, profile.height_cm, profile.current_weight)  # sex garantido no /targets
    tdee = bmr * float(profile.activity_level)

    if profile.goal_type == "lose":
        kcal = tdee * 0.85
    elif profile.goal_type == "gain":
        kcal = tdee * 1.10
    else:
        kcal = tdee

    min_kcal = 1200.0 if (profile.sex == "F") else 1400.0
    warnings: List[str] = []
    blocked = False

    if kcal < min_kcal:
        if not profile.confirm_low_calorie:
            warnings.append(f"Kcal calculada ({int(kcal)} kcal) abaixo do mínimo seguro ({int(min_kcal)} kcal). Necessária confirmação explícita.")
            blocked = True
            kcal = min_kcal
        else:
            warnings.append(f"Kcal abaixo do mínimo ({int(min_kcal)} kcal) mas liberada por confirmação explícita.")

    protein_weight = _adjusted_weight_if_obese(profile.current_weight, profile.height_cm)
    protein_g = 1.8 * protein_weight
    fat_g = 0.8 * profile.current_weight

    p_cal = protein_g * 4.0
    f_cal = fat_g * 9.0
    remaining = kcal - (p_cal + f_cal)
    carbs_g = max(0.0, remaining / 4.0)

    targets = {
        "kcal": _round5(kcal),
        "protein_g": round(protein_g, 0),
        "fat_g": round(fat_g, 0),
        "carbs_g": round(carbs_g, 0),
    }

    out = TargetsOut(
        bmr=round(bmr, 0),
        tdee=_round5(tdee),
        targets=targets,
        warnings=warnings,
        blocked=blocked,
    )
    debug = {
        "protein_weight_used": round(protein_weight, 2),
        "p_cal": round(p_cal, 1),
        "f_cal": round(f_cal, 1),
        "remaining_cal_for_carbs": round(remaining, 1),
        "min_kcal": min_kcal,
    }
    return out, debug

# --------- ROUTES ---------
@router.get("/profile", response_model=NutritionProfileOut)
def get_profile(username: str = Depends(get_current_username)):
    return _fetch_profile(username)

@router.put("/profile", response_model=NutritionProfileOut)
def put_profile(payload: NutritionProfileUpdate, username: str = Depends(get_current_username)):
    if payload.sex is not None:
        payload.sex = payload.sex.upper()  # type: ignore
    _validate_update(payload)
    _do_update(username, payload)
    return _fetch_profile(username)

@router.get("/targets", response_model=TargetsOut)
def get_targets(username: str = Depends(get_current_username)):
    profile = _fetch_profile(username)

    if not profile.sex or profile.sex not in ("M","F"):
        raise HTTPException(400, detail="Defina 'sex' como 'M' ou 'F' no perfil.")
    if profile.age <= 0 or profile.height_cm <= 0 or profile.current_weight <= 0:
        raise HTTPException(400, detail="Perfil incompleto: informe age, height_cm e current_weight.")
    if float(profile.activity_level) not in ALLOWED_ACTIVITY:
        raise HTTPException(400, detail=f"activity_level deve ser um de {sorted(ALLOWED_ACTIVITY)}.")
    if profile.goal_type not in ("lose","maintain","gain"):
        raise HTTPException(400, detail="goal_type deve ser 'lose', 'maintain' ou 'gain'.")

    out, _debug = _compute_targets(profile)
    return out
