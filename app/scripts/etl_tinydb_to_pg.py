# app/scripts/etl_tinydb_to_pg.py
import os, json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from app.db import session_scope, User, WeightLog, ChatMessage, MealAnalysis

# ===== Locais candidatos (raiz do repo e pasta app/) =====
HERE = os.path.abspath(os.path.dirname(__file__))              # app/scripts
APP_DIR = os.path.abspath(os.path.join(HERE, ".."))            # app
ROOT_DIR = os.path.abspath(os.path.join(HERE, "../.."))        # raiz do projeto
SEARCH_DIRS = [ROOT_DIR, APP_DIR]

ADMIN_USERNAMES = {"lins", "linsalefe"}

def find_path(filename: str) -> str | None:
    for base in SEARCH_DIRS:
        p = os.path.join(base, filename)
        if os.path.exists(p):
            return p
    return None

def load_json_any(*filenames):
    for name in filenames:
        p = find_path(name)
        if not p:
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️  JSON inválido: {p}")
    # log amistoso se nenhum foi encontrado
    if filenames:
        print(f"⚠️  Arquivo não encontrado: { ' / '.join(filenames) }")
    return None

def parse_dt(s: str | None) -> datetime:
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

def upsert_user_from_dict(d: dict) -> str | None:
    """Cria/atualiza usuário e retorna o USERNAME (string) para evitar objetos detached."""
    username = d.get("username")
    if not username:
        return None
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            u = User(username=username)
            if d.get("id") and is_uuid(d["id"]):
                u.id = UUID(d["id"])
            db.add(u)
            db.flush()

        pw = d.get("password") or d.get("password_hash")
        if pw: u.password_hash = pw
        u.nome           = d.get("nome", u.nome)
        u.objetivo       = d.get("objetivo", u.objetivo)
        u.height_cm      = d.get("height_cm", u.height_cm)
        u.initial_weight = d.get("initial_weight", u.initial_weight)
        u.avatar_url     = d.get("avatar_url", u.avatar_url)

        if "has_access" in d: u.has_access = bool(d["has_access"])
        if "is_admin"  in d: u.is_admin  = bool(d["is_admin"])
        if username in ADMIN_USERNAMES: u.is_admin = True

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
    return username

def import_users():
    print("== Importando usuários (db.json / db_backup.json)…")
    seen = set()

    data = load_json_any("db.json")
    if isinstance(data, dict):
        if isinstance(data.get("_default"), dict):
            for _, v in data["_default"].items():
                name = upsert_user_from_dict(v or {})
                if name: seen.add(name)
        if isinstance(data.get("users"), list):
            for v in data["users"]:
                name = upsert_user_from_dict(v or {})
                if name: seen.add(name)

    bkp = load_json_any("db_backup.json")
    if isinstance(bkp, dict) and isinstance(bkp.get("_default"), dict):
        for _, v in bkp["_default"].items():
            if isinstance(v, dict) and v.get("username"):
                name = upsert_user_from_dict(v)
                if name: seen.add(name)

    print(f"✅ Usuários importados: {len(seen)}")

def import_chat_from_embedded():
    data = load_json_any("db.json") or {}
    default = data.get("_default") or {}
    for _, v in default.items():
        username = (v or {}).get("username")
        if not username:
            continue
        for m in (v.get("chat_history") or []):
            with session_scope() as db:
                u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                if not u: continue
                db.add(ChatMessage(
                    user_id=u.id,
                    role=m.get("role") or "user",
                    text=m.get("text") or "",
                    type=m.get("type") or "text",
                    image_url=m.get("imageUrl"),
                    created_at=parse_dt(m.get("created_at")),
                ))

def import_chat_from_db_files():
    data = load_json_any("chat_db.json")
    if isinstance(data, list):
        for m in data:
            username = m.get("username")
            if not username: continue
            with session_scope() as db:
                u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                if not u: continue
                db.add(ChatMessage(
                    user_id=u.id,
                    role=m.get("role") or "user",
                    text=m.get("text") or "",
                    type=m.get("type") or "text",
                    image_url=m.get("imageUrl"),
                    created_at=parse_dt(m.get("created_at")),
                ))

    bkp = load_json_any("chat_backup.json")
    if isinstance(bkp, dict):
        if isinstance(bkp.get("_default"), dict):
            for _, node in bkp["_default"].items():
                if not isinstance(node, dict):
                    continue
                if "username" in node and "chat" in node and isinstance(node["chat"], list):
                    username = node["username"]
                    for m in node["chat"]:
                        with session_scope() as db:
                            u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                            if not u: continue
                            db.add(ChatMessage(
                                user_id=u.id,
                                role=m.get("role") or "user",
                                text=m.get("text") or "",
                                type=m.get("type") or "text",
                                created_at=parse_dt(m.get("created_at")),
                            ))
                if "username" in node and "text" in node:
                    username = node["username"]
                    with session_scope() as db:
                        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                        if not u: continue
                        db.add(ChatMessage(
                            user_id=u.id,
                            role=node.get("role") or "user",
                            text=node.get("text") or "",
                            type=node.get("type") or "text",
                            created_at=parse_dt(node.get("created_at")),
                        ))
    elif isinstance(bkp, dict):
        for _, node in bkp.items():
            if isinstance(node, dict) and node.get("username") and node.get("text"):
                username = node.get("username")
                with session_scope() as db:
                    u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                    if not u: continue
                    db.add(ChatMessage(
                        user_id=u.id,
                        role=node.get("role") or "user",
                        text=node.get("text") or "",
                        type=node.get("type") or "text",
                        created_at=parse_dt(node.get("created_at")),
                    ))

def import_meals():
    for fname in ("meals_db.json", "meals_backup.json"):
        data = load_json_any(fname)
        if isinstance(data, list):
            for r in data:
                username = r.get("usuario") or r.get("username")
                if not username: continue
                with session_scope() as db:
                    u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
                    if not u: continue
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
