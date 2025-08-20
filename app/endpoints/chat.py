# app/endpoints/chat.py
import os
import re
import json
from datetime import datetime, timezone, date
import openai
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from openai import OpenAI
from app.auth import get_current_username
from app.db import salvar_chat_message, buscar_chat_history, buscar_usuario
from app.services.lina_context import build_lina_system_prompt

# DB helpers (perfil + intake diário)
try:
    import psycopg2
    import psycopg2.extras
except ImportError as e:
    raise RuntimeError("psycopg2 não encontrado. Adicione 'psycopg2-binary' ao requirements.txt") from e

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

def _today_utc() -> date:
    return datetime.now(timezone.utc).date()

# OpenAI
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ ERRO: OPENAI_API_KEY não está definida no .env")
else:
    print(f"✅ OpenAI API Key encontrada: {api_key[:10]}...")
client = OpenAI(api_key=api_key)

router = APIRouter(tags=["chat"])

def get_lina_chat_prompt(username: str, nome: str | None = None) -> str:
    nome_exibicao = nome if nome else username
    return f"""Você é a Lina, assistente nutricional da NutriFlow. Você está conversando com {nome_exibicao} ({username}).

🎯 Sua missão: Ser a companheira nutricional de {nome_exibicao}, sempre positiva, encorajadora e prestativa.

💬 Como a Lina conversa:
- Se apresente como "Lina" na primeira interação
- Use o nome {nome_exibicao} de forma natural
- Seja amigável e motivadora
- Foque em nutrição e alimentação saudável
- Emojis com moderação
- Dicas práticas e personalizadas

⚠️ Importante:
- Nada de conselhos médicos específicos
- Sugira procurar profissional quando necessário
- Seja sempre positiva e motivadora
"""

class ChatSendPayload(BaseModel):
    message: str = Field(..., description="Texto que o usuário enviou")

class ChatResponse(BaseModel):
    response: str

class ChatHistoryResponse(BaseModel):
    history: list

# ---------- /perfil: parser e update ----------
_ALLOWED_ACTIVITY = {1.2, 1.375, 1.55, 1.725, 1.9}
_KEY_MAP = {
    "sex": "sex",
    "sexo": "sex",
    "age": "age",
    "idade": "age",
    "height": "height_cm",
    "altura": "height_cm",
    "height_cm": "height_cm",
    "weight": "current_weight",
    "peso": "current_weight",
    "current_weight": "current_weight",
    "activity": "activity_level",
    "atividade": "activity_level",
    "activity_level": "activity_level",
    "goal": "goal_type",
    "objetivo": "goal_type",
    "goal_type": "goal_type",
    "pace": "pace_kg_per_week",
    "ritmo": "pace_kg_per_week",
    "pace_kg_per_week": "pace_kg_per_week",
    "restrictions": "restrictions",
    "restricoes": "restrictions",
    "confirm_low_calorie": "confirm_low_calorie",
}

def _parse_perfil_cmd(text: str) -> dict:
    body = text.strip().split(None, 1)
    if len(body) < 2:
        return {}
    args = body[1]
    parts = re.findall(r'(\w+)\s*=\s*("[^"]+"|\'[^\']+\'|[^ \t]+)', args)
    out = {}
    for k, v in parts:
        k = k.strip().lower()
        v = v.strip().strip("'").strip('"')
        key = _KEY_MAP.get(k)
        if not key:
            continue
        if key in ("age",):
            try: out[key] = int(v)
            except: pass
        elif key in ("height_cm","current_weight","activity_level","pace_kg_per_week"):
            try: out[key] = float(v)
            except: pass
        elif key == "restrictions":
            out[key] = [s.strip() for s in v.split(",") if s.strip()]
        elif key == "confirm_low_calorie":
            out[key] = v.lower() in ("1","true","t","yes","sim","y")
        elif key == "goal_type":
            val = v.lower()
            if val in ("lose","maintain","gain"):
                out[key] = val
            elif val.startswith("perd"): out[key] = "lose"
            elif val.startswith("mant"): out[key] = "maintain"
            elif val.startswith("ganh") or "massa" in val: out[key] = "gain"
        elif key == "sex":
            up = v.upper()
            if up in ("M","F"): out[key] = up
        else:
            out[key] = v
    return out

def _validate_profile_patch(p: dict):
    if "age" in p and not (14 <= int(p["age"]) <= 100):
        raise HTTPException(422, "age deve estar entre 14 e 100.")
    if "height_cm" in p and not (120 <= float(p["height_cm"]) <= 230):
        raise HTTPException(422, "height_cm deve estar entre 120 e 230.")
    if "current_weight" in p and not (25 <= float(p["current_weight"]) <= 400):
        raise HTTPException(422, "current_weight deve estar entre 25 e 400.")
    if "activity_level" in p and float(p["activity_level"]) not in _ALLOWED_ACTIVITY:
        raise HTTPException(422, f"activity_level deve ser um de {sorted(_ALLOWED_ACTIVITY)}.")
    if "pace_kg_per_week" in p and not (0.10 <= float(p["pace_kg_per_week"]) <= 1.50):
        raise HTTPException(422, "pace_kg_per_week deve estar entre 0.10 e 1.50.")
    if "restrictions" in p and not all(isinstance(x, str) for x in p["restrictions"]):
        raise HTTPException(422, "restrictions deve ser lista de strings.")
    if "sex" in p and p["sex"] not in ("M","F"):
        raise HTTPException(422, "sex deve ser 'M' ou 'F'.")
    if "goal_type" in p and p["goal_type"] not in ("lose","maintain","gain"):
        raise HTTPException(422, "goal_type deve ser 'lose', 'maintain' ou 'gain'.")

def _patch_profile(username: str, p: dict):
    if not p:
        return
    fields, vals = [], []
    for k in ("sex","age","height_cm","current_weight","activity_level","goal_type","pace_kg_per_week","restrictions","confirm_low_calorie"):
        if k in p:
            if k == "restrictions":
                vals.append(psycopg2.extras.Json(p[k]))
            else:
                vals.append(p[k])
            fields.append(f"{k} = %s")
    if not fields:
        return
    vals.append(username)
    sql = f"UPDATE public.users SET {', '.join(fields)} WHERE username = %s"
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, vals)

# ---------- intake diário ----------
def _upsert_intake(username: str, kcal: float, p: float, c: float, f: float):
    """Soma nos contadores do dia (UTC)."""
    d = _today_utc()
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.daily_intake (username, day, kcal, protein_g, carbs_g, fat_g)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (username, day) DO UPDATE SET
              kcal = public.daily_intake.kcal + EXCLUDED.kcal,
              protein_g = public.daily_intake.protein_g + EXCLUDED.protein_g,
              carbs_g = public.daily_intake.carbs_g + EXCLUDED.carbs_g,
              fat_g = public.daily_intake.fat_g + EXCLUDED.fat_g,
              updated_at = now();
        """, (username, d, float(kcal or 0), float(p or 0), float(c or 0), float(f or 0)))

def _reset_intake(username: str):
    d = _today_utc()
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.daily_intake (username, day, kcal, protein_g, carbs_g, fat_g)
            VALUES (%s, %s, 0, 0, 0, 0)
            ON CONFLICT (username, day) DO UPDATE SET
              kcal = 0, protein_g = 0, carbs_g = 0, fat_g = 0, updated_at = now();
        """, (username, d))

def _get_intake(username: str) -> dict:
    d = _today_utc()
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT kcal, protein_g, carbs_g, fat_g
            FROM public.daily_intake
            WHERE username = %s AND day = %s
        """, (username, d))
        row = cur.fetchone()
        if not row:
            return {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
        return {
            "kcal": float(row[0] or 0),
            "protein_g": float(row[1] or 0),
            "carbs_g": float(row[2] or 0),
            "fat_g": float(row[3] or 0),
        }

def _format_status(cons: dict, targets_ctx: dict | None) -> str:
    # targets_ctx é o retorno do GET /api/nutrition/targets embutido no build_lina_system_prompt
    t = (targets_ctx or {}).get("targets") or {}
    trg = t.get("targets") or t  # compat ambas formas
    tkcal = float(trg.get("kcal") or 0)
    tp = float(trg.get("protein_g") or 0)
    tc = float(trg.get("carbs_g") or 0)
    tf = float(trg.get("fat_g") or 0)

    ck = int(round(cons.get("kcal", 0)))
    cp = int(round(cons.get("protein_g", 0)))
    cc = int(round(cons.get("carbs_g", 0)))
    cf = int(round(cons.get("fat_g", 0)))

    rk = int(round(max(0, tkcal - ck))) if tkcal else 0
    rp = int(round(max(0, tp - cp))) if tp else 0
    rc = int(round(max(0, tc - cc))) if tc else 0
    rf = int(round(max(0, tf - cf))) if tf else 0

    linhas = [
        "📊 **Status do dia (UTC)**",
        f"- **Calorias consumidas:** {ck} kcal",
        f"- **Calorias restantes:** {rk} kcal" if tkcal else "- **Calorias restantes:** (meta não definida)",
        f"- **Proteínas:** {cp} g" + (f" · restante {rp} g" if tp else " · (meta não definida)"),
        f"- **Gorduras:** {cf} g" + (f" · restante {rf} g" if tf else " · (meta não definida)"),
        f"- **Carboidratos:** {cc} g" + (f" · restante {rc} g" if tc else " · (meta não definida)"),
    ]
    return "\n".join(linhas)

# ---------- /refeicao (texto) ----------
_MEAL_JSON_INSTRUCTIONS = """Responda APENAS com um JSON válido, sem explicações.
Formato:
{
  "items": [{"nome": "string", "quantidade": "string"}],
  "totais": {"kcal": number, "protein_g": number, "carbs_g": number, "fat_g": number},
  "dica": "string curta"
}
Regras:
- Use estimativas conservadoras.
- Proteína/gordura/carboidrato em gramas; kcal em calorias.
- Se descrição for vaga, suponha porções comuns.
"""

def _analyze_meal_text(description: str) -> dict:
    resp = client.chat.completions.create(
        model=os.getenv("CHAT_MODEL_ANALYZE", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "Você é uma nutricionista que extrai macros de refeições em texto."},
            {"role": "user", "content": f"{_MEAL_JSON_INSTRUCTIONS}\nDescrição: {description}"},
        ],
        max_tokens=400,
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()
    try:
        if raw.startswith("```"):
            raw = raw.strip("`")
            idx = raw.find("{")
            raw = raw[idx:] if idx >= 0 else raw
        data = json.loads(raw)
        itens = data.get("items") or []
        totals = data.get("totais") or data.get("totals") or {}
        dica = data.get("dica") or ""
        return {
            "items": itens,
            "totais": {
                "kcal": float(totals.get("kcal") or 0),
                "protein_g": float(totals.get("protein_g") or totals.get("proteina_g") or 0),
                "carbs_g": float(totals.get("carbs_g") or totals.get("carboidratos_g") or 0),
                "fat_g": float(totals.get("fat_g") or totals.get("gorduras_g") or 0),
            },
            "dica": dica,
            "_raw": raw,
        }
    except Exception:
        return {
            "items": [],
            "totais": {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0},
            "dica": "",
            "_raw": raw,
        }

def _format_meal_reply(username: str, meal: dict, targets: dict | None, status_txt: str | None) -> str:
    itens = meal.get("items") or []
    t = meal.get("totais") or {}
    kcal = float(t.get("kcal") or 0)
    p = float(t.get("protein_g") or 0)
    c = float(t.get("carbs_g") or 0)
    f = float(t.get("fat_g") or 0)
    dica = meal.get("dica") or ""

    header = "🍽️ **Refeição registrada (texto)**\n\n"
    lista = ""
    if itens:
        lista = "Alimentos:\n" + "\n".join([f"- {i.get('nome','?')}: {i.get('quantidade','?')}" for i in itens]) + "\n\n"

    macros = f"""**Macros estimadas:**
- Calorias: {int(round(kcal))} kcal
- Proteínas: {int(round(p))} g
- Carboidratos: {int(round(c))} g
- Gorduras: {int(round(f))} g
"""

    dica_txt = (f"\n💡 **Dica da Lina:** {dica}\n" if dica else "")
    bloco_status = f"\n\n{status_txt}\n" if status_txt else ""

    return header + lista + macros + bloco_status + dica_txt

# ---------- parser /consumo ----------
def _parse_consumo(text: str) -> tuple[float, float, float, float]:
    """
    Suporta:
      /consumo 1300
      /consumo kcal=700 p=50 c=80 f=20
    Retorna (kcal, p, c, f) — não negativos.
    """
    body = text.strip().split(None, 1)
    if len(body) == 1:
        return (0.0, 0.0, 0.0, 0.0)
    arg = body[1].strip()
    if re.fullmatch(r"[+]?\d+(\.\d+)?", arg):
        kcal = float(arg)
        return (max(0.0, kcal), 0.0, 0.0, 0.0)
    # pares chave=valor
    kcal = p = c = f = 0.0
    for k, v in re.findall(r'(\w+)\s*=\s*([+\-]?\d+(?:\.\d+)?)', arg):
        k = k.lower()
        val = max(0.0, float(v))
        if k in ("kcal","cal","calorias"): kcal = val
        elif k in ("p","prot","proteina","proteína","protein","protein_g"): p = val
        elif k in ("c","carb","carbo","carboidrato","carboidratos","carbs_g"): c = val
        elif k in ("f","fat","gordura","gorduras","fat_g"): f = val
    return (kcal, p, c, f)

# ---------- Endpoints ----------
@router.post("/send", response_model=ChatResponse)
def send_to_ai(payload: ChatSendPayload, username: str = Depends(get_current_username)):
    """
    Comandos:
      - /perfil ...               → atualiza perfil e retorna metas
      - /confirmar_kcal_baixa     → marcar confirm_low_calorie=true
      - /revogar_kcal_baixa       → marcar confirm_low_calorie=false
      - /refeicao <texto>         → analisa refeição e **soma** no dia
      - /consumo ...              → soma manual no dia (kcal e/ou macros)
      - /status                   → mostra consumido vs metas do dia
      - /limpar_dia               → zera consumos de hoje
    Caso contrário: conversa normal com a Lina (system prompt com profile+targets).
    """
    try:
        if not api_key:
            raise HTTPException(500, "OpenAI API key não configurada")

        user_data = buscar_usuario(username)
        nome = user_data.get("nome") if user_data else None
        txt = payload.message.strip()
        low_cmd = txt.lower()

        # --- /perfil ---
        if low_cmd.startswith("/perfil"):
            patch = _parse_perfil_cmd(txt)
            if not patch:
                msg = ("Uso: /perfil sex=M age=30 height=180 weight=92 activity=1.55 "
                       "goal=gain pace=0.5 restrictions=lactose,gluten confirm_low_calorie=true")
                salvar_chat_message(username, "user", payload.message, "text")
                salvar_chat_message(username, "bot", msg, "text")
                return ChatResponse(response=msg)

            _validate_profile_patch(patch)
            _patch_profile(username, patch)

            sys_prompt, ctx = build_lina_system_prompt(username)
            t = ctx.get("targets") or {}
            trg = t.get("targets") or {}
            resumo = (
                "Perfil atualizado com sucesso! ✅\n\n"
                f"Metas do dia:\n"
                f"- Calorias: {int(trg.get('kcal', 0))} kcal\n"
                f"- Proteínas: {int(trg.get('protein_g', 0))} g\n"
                f"- Gorduras: {int(trg.get('fat_g', 0))} g\n"
                f"- Carboidratos: {int(trg.get('carbs_g', 0))} g"
            )
            salvar_chat_message(username, "user", payload.message, "text")
            salvar_chat_message(username, "bot", resumo, "text")
            return ChatResponse(response=resumo)

        # --- confirmar / revogar kcal baixa ---
        if low_cmd.startswith("/confirmar_kcal_baixa") or low_cmd.startswith("/liberar_kcal_baixa") or low_cmd.startswith("/confirmar_deficit") or "liberar_deficit" in low_cmd:
            _patch_profile(username, {"confirm_low_calorie": True})
            msg = "Confirmação registrada ✅. Metas abaixo do mínimo podem ser usadas."
            salvar_chat_message(username, "user", payload.message, "text")
            salvar_chat_message(username, "bot", msg, "text")
            return ChatResponse(response=msg)

        if low_cmd.startswith("/revogar_kcal_baixa") or low_cmd.startswith("/revogar_deficit") or low_cmd.startswith("/bloquear_deficit"):
            _patch_profile(username, {"confirm_low_calorie": False})
            msg = "Confirmação revogada ✅. Vou respeitar os mínimos de segurança novamente."
            salvar_chat_message(username, "user", payload.message, "text")
            salvar_chat_message(username, "bot", msg, "text")
            return ChatResponse(response=msg)

        # --- /limpar_dia ---
        if low_cmd.startswith("/limpar_dia"):
            _reset_intake(username)
            sys_prompt, ctx = build_lina_system_prompt(username)
            status_txt = _format_status(_get_intake(username), ctx)
            msg = "Dia zerado ✅\n\n" + status_txt
            salvar_chat_message(username, "user", payload.message, "text")
            salvar_chat_message(username, "bot", msg, "text")
            return ChatResponse(response=msg)

        # --- /status ---
        if low_cmd.startswith("/status"):
            sys_prompt, ctx = build_lina_system_prompt(username)
            status_txt = _format_status(_get_intake(username), ctx)
            salvar_chat_message(username, "user", payload.message, "text")
            salvar_chat_message(username, "bot", status_txt, "text")
            return ChatResponse(response=status_txt)

        # --- /consumo ---
        if low_cmd.startswith("/consumo"):
            kcal, p, c, f = _parse_consumo(txt)
            if (kcal + p + c + f) <= 0:
                msg = "Uso: `/consumo 1300` ou `/consumo kcal=700 p=50 c=80 f=20`"
                salvar_chat_message(username, "user", payload.message, "text")
                salvar_chat_message(username, "bot", msg, "text")
                return ChatResponse(response=msg)

            _upsert_intake(username, kcal, p, c, f)
            sys_prompt, ctx = build_lina_system_prompt(username)
            status_txt = _format_status(_get_intake(username), ctx)
            msg = f"Consumo registrado ✅ (+{int(kcal)} kcal, +{int(p)}g P, +{int(c)}g C, +{int(f)}g G)\n\n{status_txt}"
            salvar_chat_message(username, "user", payload.message, "text")
            salvar_chat_message(username, "bot", msg, "text")
            return ChatResponse(response=msg)

        # --- /refeicao ---
        if low_cmd.startswith("/refeicao"):
            parts = txt.split(None, 1)
            if len(parts) < 2 or not parts[1].strip():
                msg = "Uso: /refeicao <descrição da refeição> (ex: '/refeicao 150g frango grelhado, 1 xíc. arroz, salada')."
                salvar_chat_message(username, "user", payload.message, "text")
                salvar_chat_message(username, "bot", msg, "text")
                return ChatResponse(response=msg)

            description = parts[1].strip()
            sys_prompt, ctx = build_lina_system_prompt(username)

            meal = _analyze_meal_text(description)
            t = meal.get("totais") or {}
            _upsert_intake(
                username,
                float(t.get("kcal") or 0),
                float(t.get("protein_g") or 0),
                float(t.get("carbs_g") or 0),
                float(t.get("fat_g") or 0),
            )
            status_txt = _format_status(_get_intake(username), ctx)
            reply = _format_meal_reply(username, meal, ctx.get("targets"), status_txt)

            salvar_chat_message(username, "user", payload.message, "text")
            salvar_chat_message(username, "bot", reply, "text")
            return ChatResponse(response=reply)

        # --- Conversa normal com a Lina ---
        try:
            sys_prompt, ctx = build_lina_system_prompt(username)
        except Exception:
            sys_prompt = get_lina_chat_prompt(username, nome)
            ctx = {"profile": None, "targets": None}

        history = buscar_chat_history(username, limit=8) or []
        messages: list[dict] = [{"role": "system", "content": sys_prompt}]
        for msg in history:
            if isinstance(msg, dict) and "role" in msg and "text" in msg:
                role = msg.get("role", "user")
                if role == "bot":
                    role = "assistant"
                content = msg.get("text", "")
                if content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": txt})

        model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=700,
            temperature=0.6,
        )
        content = (resp.choices[0].message.content or "").strip()

        salvar_chat_message(username, "user", txt, "text")
        salvar_chat_message(username, "bot", content, "text")
        return ChatResponse(response=content)

    except openai.AuthenticationError as e:
        raise HTTPException(502, "Erro de autenticação com OpenAI. Verifique a API key.") from e
    except openai.APIError as e:
        raise HTTPException(502, f"Erro da API OpenAI: {str(e)}") from e
    except Exception as e:
        import traceback
        print(f"❌ ERRO geral: {type(e).__name__}: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(502, f"Erro ao conectar com a IA: {str(e)}")

@router.get("/history", response_model=ChatHistoryResponse)
def get_chat_history(username: str = Depends(get_current_username)):
    try:
        history = buscar_chat_history(username, limit=50) or []
        formatted_history = []
        for msg in history:
            if isinstance(msg, dict):
                formatted_history.append({
                    "role": msg.get("role", "user"),
                    "text": msg.get("text", ""),
                    "type": msg.get("type", "text"),
                    "imageUrl": msg.get("imageUrl"),
                    "created_at": msg.get("created_at", "")
                })
        return ChatHistoryResponse(history=formatted_history)
    except Exception:
        return ChatHistoryResponse(history=[])

@router.post("/save")
def save_chat_message_endpoint(message_data: dict, username: str = Depends(get_current_username)):
    try:
        role = message_data.get("role", "user")
        text = message_data.get("text", "")
        message_type = message_data.get("type", "text")
        salvar_chat_message(username, role, text, message_type)
        return {"status": "success", "message": "Mensagem salva"}
    except Exception as e:
        raise HTTPException(500, f"Erro ao salvar mensagem: {e}")
