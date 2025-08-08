# app/db.py

import os
from datetime import datetime
from typing import Any, Dict, Optional, List

from tinydb import TinyDB, Query

# ===== Paths dos bancos (absolutos) =====
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH       = os.path.join(BASE_DIR, "db.json")
CHAT_DB_PATH  = os.path.join(BASE_DIR, "chat_db.json")
MEALS_DB_PATH = os.path.join(BASE_DIR, "meals_db.json")

# ===== DBs =====
db       = TinyDB(DB_PATH)        # usuários (tabela padrão)
chat_db  = TinyDB(CHAT_DB_PATH)   # histórico de chat
meals_db = TinyDB(MEALS_DB_PATH)  # análises de refeição

User = Query()
Chat = Query()
Meal = Query()


def buscar_usuario(username: str) -> Optional[Dict[str, Any]]:
    """Busca um usuário pelo username."""
    return db.get(User.username == username)


def buscar_usuario_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Busca um usuário pelo ID."""
    return db.get(User.id == user_id)


def _defaults_para_insercao(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constrói um documento completo para INSERT (quando usuário ainda não existe).
    Mantém defaults para campos não enviados.
    """
    return {
        "id":              user.get("id"),
        "username":        user["username"],
        "password":        user.get("password"),
        "nome":            user.get("nome"),
        "objetivo":        user.get("objetivo"),
        "height_cm":       user.get("height_cm"),
        "initial_weight":  user.get("initial_weight"),
        "weight_logs":     user.get("weight_logs", []),
        "refeicoes":       user.get("refeicoes", []),
        "chat_history":    user.get("chat_history", []),
        "has_access":      user.get("has_access", False),
        "is_admin":        user.get("is_admin", False),
        "avatar_url":      user.get("avatar_url"),  # << mantém avatar se vier
    }


def salvar_usuario(user: Dict[str, Any]) -> None:
    """
    Upsert com MERGE:
    - Se existir: preserva o registro e atualiza apenas os campos enviados (None NÃO sobrescreve).
    - Se não existir: insere com defaults.
    """
    if "username" not in user:
        raise ValueError("salvar_usuario: campo 'username' é obrigatório")

    existente = db.get(User.username == user["username"])

    if existente:
        # Atualiza apenas chaves com valor não-None (para não apagar acidentalmente)
        atualizacoes = {k: v for k, v in user.items() if v is not None}
        # Merge
        merged = {**existente, **atualizacoes}
        db.update(merged, User.username == user["username"])
        print(f"✅ Usuário {user['username']} atualizado (merge) no banco")
    else:
        doc = _defaults_para_insercao(user)
        db.insert(doc)
        print(f"✅ Usuário {user['username']} inserido no banco")


async def grant_user_access(user_id: str) -> None:
    """Concede acesso ao usuário (has_access = True)."""
    if not db.get(User.id == user_id):
        raise ValueError(f"Usuário '{user_id}' não encontrado no DB")
    db.update({"has_access": True}, User.id == user_id)
    print(f"✅ Acesso concedido ao usuário {user_id}")


def salvar_chat_message(username: str, role: str, text: str, msg_type: str = "text") -> None:
    """Salva uma mensagem de chat."""
    chat_message = {
        "username":   username,
        "role":       role,
        "text":       text,
        "type":       msg_type,
        "created_at": datetime.now().isoformat(),
    }
    chat_db.insert(chat_message)
    print(f"✅ Mensagem de chat salva para {username}")


def buscar_chat_history(username: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Busca histórico de chat (mais antigas primeiro, limitado)."""
    messages = chat_db.search(Chat.username == username)
    messages.sort(key=lambda x: x.get("created_at", ""), reverse=False)
    return messages[-limit:]


def salvar_meal_analysis(username: str, analise: Dict[str, Any], imagem_nome: Optional[str] = None) -> None:
    """Salva análise de refeição."""
    meal_data = {
        "usuario":     username,
        "analise":     analise,
        "imagem_nome": imagem_nome,
        "data":        datetime.now().isoformat(),
    }
    meals_db.insert(meal_data)
    print(f"✅ Análise de refeição salva para {username}")


def buscar_meal_history(username: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Busca histórico de refeições (mais recentes primeiro)."""
    meals = meals_db.search(Meal.usuario == username)
    meals.sort(key=lambda x: x.get("data", ""), reverse=True)
    return meals[:limit]
