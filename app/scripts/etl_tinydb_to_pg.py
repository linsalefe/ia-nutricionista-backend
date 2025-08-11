# app/scripts/etl_tinydb_to_pg.py
import os, json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

# usa os modelos/sessão já definidos no app
from app.db import session_scope, User, WeightLog, ChatMessage, MealAnalysis

# ajuste se quiser forçar admins
ADMIN_USERNAMES = {"lins", "linsalefe"}

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_JSON            = os.path.join(BASE_DIR, "db.json")
DB_BACKUP_JSON     = os.path.join(BASE_DIR, "db_backup.json")
CHAT_DB_JSON       = os.path.join(BASE_DIR, "chat_db.json")
CHAT_BACKUP_JSON   = os.path.join(BASE_DIR, "chat_backup.json")
MEALS_DB_JSON      = os.path.join(BASE_DIR, "meals_db.json")
MEALS_BACKUP_JSON  = os.path.join(BASE_DIR, "meals_backup.json")

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  Arquivo não encontrado: {path}")
        return None
    except json.JSONDecodeError:
        print(f"⚠️  JSON inválido: {path}")
        return None

def parse_dt(s: str) -> datetime:
    if not s:
        return datetime.utcnow()
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.utcnow()

def is_uuid(val) -> bool:
    try:
        UUID(str(val))
        return True
    except Exception:
        return False

def upsert_user_from_dict(d: dict) -> User:
    username = d.get("username")
    if not username:
        return None
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            u = User(username=username)
            # usa ID se existir e for UUID válido
            if d.get("id") and is_uuid(d["id"]):
                u.id = UUID(d["id"])
            db.add(u)
            db.flush()

        # campos
        pw = d.get("password") or d.get("password_hash")
        if pw: u.password_hash = pw
        u.nome           = d.get("nome", u.nome)
        u.objetivo       = d.get("objetivo", u.objetivo)
        u.height_cm      = d.get("height_cm", u.height_cm)
        u.initial_weight = d.get("initial_weight", u.initial_weight)
        u.avatar_url     = d.get("avatar_url", u.avatar_url)

        # flags
        if "has_access" in d: u.has_access = bool(d["has_access"])
        if "is_admin"  in d: u.is_admin  = bool(d["is_admin"])
        if username in ADMIN_USERNAMES: u.is_admin = True

        # weight_logs
        for item in (d.get("weight_logs") or []):
            try:
                wl = WeightLog(
                    user_id=u.id,
                    weight=float(item["weight"]),
                    recorded_at=parse_dt(item.get("recorded_at")),
                )
                db.add(wl)
            except Exception:
                continue
        return u

def import_users():
    print("== Importando usuários (db.json / db_backup.json)…")
    seen = set()

    # db.json (TinyDB) pode ter _default e/ou users[]
    data = load_json(DB_JSON) or {}
    if isinstance(data.get("_default"), dict):
        for k, v in data["_default"].items():
            u = upsert_user_from_dict(v or {})
            if u:
                seen.add(u.username)

    if isinstance(data.get("users"), list):
        for v in data["users"]:
            u = upsert_user_from_dict(v or {})
            if u:
                seen.add(u.username)

    # db_backup.json pode ter outra estrutura
    bkp = load_json(DB_BACKUP_JSON) or {}
    if isinstance(bkp.get("_default"), dict):
        for _, v in bkp["_default"].items():
            if isinstance(v, dict) and v.get("username"):
                u = upsert_user_from_dict(v)
                if u:
                    seen.add(u.username)

    print(f"✅ Usuários importados: {len(seen)}")

def import_chat_from_embedded():
    # alguns users têm chat_history dentro do próprio user (db.json)
    data = load_json(DB_JSON) or {}
    default = data.get("_default") or {}
    for _, v in default.items():
        username = (v or {}).get("username")
        if not username:
            continue
        for m in (v.get("chat_history") or []):
            with session_scope() as db:
                u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                if not u:
                    continue
                msg = ChatMessage(
                    user_id=u.id,
                    role=m.get("role") or "user",
                    text=m.get("text") or "",
                    type=m.get("type") or "text",
                    image_url=m.get("imageUrl"),
                    created_at=parse_dt(m.get("created_at")),
                )
                db.add(msg)

def import_chat_from_db_files():
    # chat_db.json (normalmente uma lista de mensagens) — pode estar vazio
    data = load_json(CHAT_DB_JSON)
    if isinstance(data, list):
        for m in data:
            username = m.get("username")
            if not username:
                continue
            with session_scope() as db:
                u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                if not u:
                    continue
                db.add(ChatMessage(
                    user_id=u.id,
                    role=m.get("role") or "user",
                    text=m.get("text") or "",
                    type=m.get("type") or "text",
                    image_url=m.get("imageUrl"),
                    created_at=parse_dt(m.get("created_at")),
                ))

    # chat_backup.json tem vários formatos
    bkp = load_json(CHAT_BACKUP_JSON)
    if isinstance(bkp, dict):
        # 1) _default com registros que possuem "username" e/ou "chat" (lista)
        if isinstance(bkp.get("_default"), dict):
            for _, node in bkp["_default"].items():
                if not isinstance(node, dict):
                    continue
                if "username" in node and "chat" in node and isinstance(node["chat"], list):
                    username = node["username"]
                    for m in node["chat"]:
                        with session_scope() as db:
                            u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                            if not u: 
                                continue
                            db.add(ChatMessage(
                                user_id=u.id,
                                role=m.get("role") or "user",
                                text=m.get("text") or "",
                                type=m.get("type") or "text",
                                created_at=parse_dt(m.get("created_at")),
                            ))
                # também há entradas simples com username/role/text
                if "username" in node and "text" in node:
                    username = node["username"]
                    with session_scope() as db:
                        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                        if not u: 
                            continue
                        db.add(ChatMessage(
                            user_id=u.id,
                            role=node.get("role") or "user",
                            text=node.get("text") or "",
                            type=node.get("type") or "text",
                            created_at=parse_dt(node.get("created_at")),
                        ))
        else:
            # estrutura solta (chaves numéricas com entries)
            for _, node in bkp.items():
                if isinstance(node, dict) and node.get("username") and node.get("text"):
                    username = node["username"]
                    with session_scope() as db:
                        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                        if not u:
                            continue
                        db.add(ChatMessage(
                            user_id=u.id,
                            role=node.get("role") or "user",
                            text=node.get("text") or "",
                            type=node.get("type") or "text",
                            created_at=parse_dt(node.get("created_at")),
                        ))

def import_meals():
    # meals_db.json
    for path in (MEALS_DB_JSON, MEALS_BACKUP_JSON):
        data = load_json(path)
        if isinstance(data, list):
            for r in data:
                username = r.get("usuario") or r.get("username")
                if not username:
                    continue
                with session_scope() as db:
                    u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                    if not u:
                        continue
                    db.add(MealAnalysis(
                        user_id=u.id,
                        analysis=r.get("analise") or {},
                        image_name=r.get("imagem_nome"),
                        created_at=parse_dt(r.get("data")),
                    ))

def main():
    print("🚚 Iniciando ETL TinyDB → PostgreSQL")
    import_users()
    import_chat_from_embedded()
    import_chat_from_db_files()
    import_meals()
    print("✅ ETL concluído.")

if __name__ == "__main__":
    main()
