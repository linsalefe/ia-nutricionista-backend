# app/scripts/import_meals_only.py
import os, json
from datetime import datetime
from sqlalchemy import select, func
from app.db import session_scope, User, MealAnalysis

# procura arquivos na raiz e em app/
HERE = os.path.abspath(os.path.dirname(__file__))      # app/scripts
APP_DIR = os.path.abspath(os.path.join(HERE, ".."))    # app
ROOT_DIR = os.path.abspath(os.path.join(HERE, "../.."))# raiz
SEARCH_DIRS = [ROOT_DIR, APP_DIR]

def find_path(filename: str) -> str | None:
    for base in SEARCH_DIRS:
        p = os.path.join(base, filename)
        if os.path.exists(p):
            return p
    return None

def load_json_any(*names):
    for n in names:
        p = find_path(n)
        if not p: 
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️  JSON inválido: {p}")
    print(f"⚠️  Arquivo não encontrado: {', '.join(names)}")
    return None

def parse_dt(s: str | None) -> datetime:
    if not s: 
        return datetime.utcnow()
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.utcnow()

def import_meals():
    total = 0
    data = load_json_any("meals_db.json") or []
    if not isinstance(data, list):
        data = []

    data_bkp = load_json_any("meals_backup.json") or []
    if isinstance(data_bkp, list):
        data.extend(data_bkp)

    with session_scope() as db:
        for r in data:
            username = r.get("usuario") or r.get("username")
            if not username:
                continue
            u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
            if not u:
                continue

            created_at = parse_dt(r.get("data"))
            image_name = r.get("imagem_nome")
            analysis = r.get("analise") or {}

            # dedup simples: mesmo user_id + created_at (+ image_name se houver)
            exists_q = select(func.count(MealAnalysis.id)).where(
                MealAnalysis.user_id == u.id,
                MealAnalysis.created_at == created_at,
            )
            if image_name:
                exists_q = exists_q.where(MealAnalysis.image_name == image_name)

            exists = db.execute(exists_q).scalar_one()
            if exists:
                continue

            db.add(MealAnalysis(
                user_id=u.id,
                analysis=analysis,
                image_name=image_name,
                created_at=created_at,
            ))
            total += 1

    print(f"✅ Refeições importadas: {total}")

if __name__ == "__main__":
    print("🍽️ Importando apenas refeições…")
    import_meals()
    print("✅ Concluído.")
