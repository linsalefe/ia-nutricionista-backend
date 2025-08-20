# app/endpoints/chat.py
import os
import re
from datetime import datetime
import openai
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from openai import OpenAI
from app.auth import get_current_username
from app.db import salvar_chat_message, buscar_chat_history, buscar_usuario
from app.services.lina_context import build_lina_system_prompt

# DB helpers p/ atualização rápida do perfil via /perfil
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
    """
    Aceita formatos:
      /perfil sex=M age=30 height=180 weight=92 activity=1.55 goal=gain pace=0.5
      /perfil sexo=M idade=30 altura=180 peso=92 atividade=1.55 objetivo=ganhar
      /perfil restrictions=lactose,gluten confirm_low_calorie=true
    """
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
            # vírgula separada
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

# ---------- Endpoints ----------
@router.post("/send", response_model=ChatResponse)
def send_to_ai(payload: ChatSendPayload, username: str = Depends(get_current_username)):
    """
    Se começar com '/perfil ...', atualiza o perfil no ato e retorna metas.
    Senão, conversa com a Lina (com system prompt enriquecido por profile+targets).
    """
    try:
        if not api_key:
            raise HTTPException(500, "OpenAI API key não configurada")

        user_data = buscar_usuario(username)
        nome = user_data.get("nome") if user_data else None
        txt = payload.message.strip()

        # --- Comando /perfil ---
        if txt.lower().startswith("/perfil"):
            patch = _parse_perfil_cmd(txt)
            if not patch:
                msg = ("Uso: /perfil sex=M age=30 height=180 weight=92 activity=1.55 "
                       "goal=gain pace=0.5 restrictions=lactose,gluten confirm_low_calorie=true")
                salvar_chat_message(username, "user", payload.message, "text")
                salvar_chat_message(username, "bot", msg, "text")
                return ChatResponse(response=msg)

            _validate_profile_patch(patch)
            _patch_profile(username, patch)

            # Recalcular metas e responder
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
