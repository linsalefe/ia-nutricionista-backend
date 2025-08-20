# app/services/lina_context.py
from typing import Optional, Tuple, Dict, Any, List, Literal
import os

# DB
try:
    import psycopg2
    import psycopg2.extras
except ImportError as e:
    raise RuntimeError("psycopg2 não encontrado. Adicione 'psycopg2-binary' ao requirements.txt") from e

SexType = Literal["M", "F"]
GoalType = Literal["lose", "maintain", "gain"]
ALLOWED_ACTIVITY = {1.2, 1.375, 1.55, 1.725, 1.9}

# ---------- DB helpers ----------
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

# ---------- Nutrition rules ----------
def _map_objetivo_to_goal_type(obj: Optional[str]) -> GoalType:
    s = (obj or "").strip().lower()
    if any(k in s for k in ["perder", "emagrec", "déficit", "deficit", "cut"]):
        return "lose"
    if any(k in s for k in ["ganhar", "massa", "hipertrof", "bulk"]):
        return "gain"
    return "maintain"

def _bmr_mifflin(sex: SexType, age: int, height_cm: float, weight_kg: float) -> float:
    if sex == "M":
        return 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
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

def _round5(x: float) -> float:
    return float(int(round(x / 5.0)) * 5)

def _compute_targets(profile: Dict[str, Any]) -> Dict[str, Any]:
    sex: SexType = profile["sex"]
    age = int(profile["age"])
    height_cm = float(profile["height_cm"])
    weight = float(profile["current_weight"])
    activity = float(profile["activity_level"])
    goal: GoalType = profile["goal_type"]

    bmr = _bmr_mifflin(sex, age, height_cm, weight)
    tdee = bmr * activity

    if goal == "lose":
        kcal = tdee * 0.85
    elif goal == "gain":
        kcal = tdee * 1.10
    else:
        kcal = tdee

    min_kcal = 1200.0 if sex == "F" else 1400.0
    warnings: List[str] = []
    blocked = False
    if kcal < min_kcal and not bool(profile.get("confirm_low_calorie")):
        warnings.append(f"Kcal calculada ({int(kcal)} kcal) abaixo do mínimo seguro ({int(min_kcal)} kcal).")
        blocked = True
        kcal = min_kcal

    protein_weight = _adjusted_weight_if_obese(weight, height_cm)
    protein_g = 1.8 * protein_weight
    fat_g = 0.8 * weight
    p_cal = protein_g * 4.0
    f_cal = fat_g * 9.0
    carbs_g = max(0.0, (kcal - (p_cal + f_cal)) / 4.0)

    return {
        "bmr": round(bmr, 0),
        "tdee": _round5(tdee),
        "targets": {
            "kcal": _round5(kcal),
            "protein_g": round(protein_g, 0),
            "fat_g": round(fat_g, 0),
            "carbs_g": round(carbs_g, 0),
        },
        "warnings": warnings,
        "blocked": blocked,
    }

# ---------- Profile loader ----------
def _load_profile(username: str) -> Dict[str, Any]:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT sex, age, height_cm, current_weight, activity_level, goal_type,
                   pace_kg_per_week, restrictions, confirm_low_calorie, objetivo
            FROM public.users
            WHERE username = %s
        """, (username,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Usuário não encontrado")

        sex_norm: Optional[SexType] = None
        if isinstance(row["sex"], str) and row["sex"].strip().upper() in ("M","F"):
            sex_norm = row["sex"].strip().upper()  # type: ignore

        restrictions = row.get("restrictions") or []
        if not isinstance(restrictions, list):
            restrictions = []

        goal_type: GoalType = (row.get("goal_type") or _map_objetivo_to_goal_type(row.get("objetivo")))  # type: ignore

        profile = {
            "sex": sex_norm,
            "age": int(row["age"] or 0),
            "height_cm": float(row["height_cm"] or 0.0),
            "current_weight": float(row["current_weight"] or 0.0),
            "activity_level": float(row["activity_level"] or 1.2),
            "goal_type": goal_type,
            "pace_kg_per_week": float(row["pace_kg_per_week"]) if row["pace_kg_per_week"] is not None else None,
            "restrictions": [str(x) for x in restrictions],
            "confirm_low_calorie": bool(row["confirm_low_calorie"]),
        }
        return profile

# ---------- Public API ----------
def build_lina_system_prompt(username: str) -> Tuple[str, Dict[str, Any]]:
    """
    Retorna (system_prompt_str, context_dict).
    Lança ValueError se perfil mínimo estiver ausente (sex/age/height/current_weight/activity/goal).
    """
    profile = _load_profile(username)

    # validação mínima para metas
    if not profile["sex"] or profile["age"] <= 0 or profile["height_cm"] <= 0 or profile["current_weight"] <= 0:
        # prompt sem metas, pedindo para completar perfil
        sys = f"""Você é a Lina, assistente nutricional da NutriFlow.
O usuário {username} ainda não completou o perfil mínimo (sexo, idade, altura, peso).
Seja acolhedora e peça esses dados de forma objetiva para calcular metas diárias.

Ao responder:
- Use português-BR, direto ao ponto e educado.
- Foque em coletar dados: sexo (M/F), idade (anos), altura (cm), peso (kg), nível de atividade (1.2, 1.375, 1.55, 1.725 ou 1.9) e objetivo (perder, manter, ganhar).
- Após coletar, confirme e diga que vai calcular metas."""
        return sys, {"profile": profile, "targets": None}

    # perfil completo -> calcular metas
    targets = _compute_targets(profile)

    # formatação
    restr = ", ".join(profile["restrictions"]) if profile["restrictions"] else "sem restrições informadas"
    goal_map = {"lose":"Perder", "maintain":"Manter", "gain":"Ganhar"}
    goal_pt = goal_map.get(profile["goal_type"], "Manter")

    sys = f"""Você é a Lina, assistente nutricional da NutriFlow.
Contexto do usuário:
- Nome de usuário: {username}
- Sexo: {profile['sex']}
- Idade: {profile['age']} anos
- Altura: {profile['height_cm']} cm
- Peso atual: {profile['current_weight']} kg
- Nível de atividade: {profile['activity_level']}
- Objetivo: {goal_pt}
- Ritmo (kg/sem): {profile['pace_kg_per_week'] or 'não informado'}
- Restrições: {restr}

Metas do dia (derivadas das RNs):
- BMR: {targets['bmr']} kcal   •   TDEE: {targets['tdee']} kcal
- Calorias: {int(targets['targets']['kcal'])} kcal
- Proteínas: {int(targets['targets']['protein_g'])} g
- Gorduras: {int(targets['targets']['fat_g'])} g
- Carboidratos: {int(targets['targets']['carbs_g'])} g
{"- Aviso: " + "; ".join(targets["warnings"]) if targets["warnings"] else ""}

Instruções de resposta:
- Use tom positivo, direto e prático, sem julgamento.
- Sempre que o usuário enviar uma refeição (texto ou foto), estime macros e atualize o status em relação às metas do dia.
- Se o usuário estiver perto de extrapolar (>5%) ou de não bater a meta, alerte com educação e sugira ajustes específicos.
- Evite assuntos fora de nutrição.
"""
    return sys, {"profile": profile, "targets": targets}
