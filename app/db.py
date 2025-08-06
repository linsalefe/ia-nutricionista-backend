# app/db.py

from tinydb import TinyDB, Query
import os
from datetime import datetime

# Definir caminhos dos bancos
DB_PATH       = os.path.join(os.path.dirname(__file__), '../db.json')
CHAT_DB_PATH  = os.path.join(os.path.dirname(__file__), '../chat_db.json')
MEALS_DB_PATH = os.path.join(os.path.dirname(__file__), '../meals_db.json')

# Inicializar bancos
db       = TinyDB(DB_PATH)
chat_db  = TinyDB(CHAT_DB_PATH)
meals_db = TinyDB(MEALS_DB_PATH)

User = Query()
Chat = Query()
Meal = Query()


def salvar_usuario(user: dict) -> None:
    """Salva ou atualiza um usuário no banco principal"""
    default_user = {
        "id":             user.get("id"),
        "username":       user["username"],
        "password":       user.get("password"),
        "nome":           user.get("nome"),
        "objetivo":       user.get("objetivo"),
        "height_cm":      user.get("height_cm"),
        "initial_weight": user.get("initial_weight"),
        "weight_logs":    user.get("weight_logs", []),
        "refeicoes":      user.get("refeicoes", []),
        "chat_history":   user.get("chat_history", []),
        "has_access":     user.get("has_access", False),
        "is_admin":       user.get("is_admin", False),
    }

    if db.search(User.username == user['username']):
        db.update(default_user, User.username == user['username'])
        print(f"✅ Usuário {user['username']} atualizado no banco")
    else:
        db.insert(default_user)
        print(f"✅ Usuário {user['username']} inserido no banco")


def buscar_usuario(username: str) -> dict | None:
    """Busca um usuário no banco principal"""
    result = db.search(User.username == username)
    if result:
        user = result[0]
        print(f"✅ Usuário {username} encontrado no banco")
        return user
    else:
        print(f"❌ Usuário {username} não encontrado")
        return None


def buscar_usuario_by_id(user_id: str) -> dict | None:
    """Busca um usuário pelo ID no banco principal"""
    result = db.search(User.id == user_id)
    if result:
        user = result[0]
        print(f"✅ Usuário ID {user_id} encontrado no banco")
        return user
    else:
        print(f"❌ Usuário ID {user_id} não encontrado")
        return None


async def grant_user_access(user_id: str) -> None:
    """
    Concede acesso ao usuário (seta has_access = True).
    """
    users = db.search(User.id == user_id)
    if not users:
        raise ValueError(f"Usuário '{user_id}' não encontrado no DB")
    db.update({"has_access": True}, User.id == user_id)
    print(f"✅ Acesso concedido ao usuário {user_id}")


def salvar_chat_message(username: str, role: str, text: str, msg_type: str = "text") -> None:
    """Salva uma mensagem de chat no banco separado"""
    chat_message = {
        "username":   username,
        "role":       role,
        "text":       text,
        "type":       msg_type,
        "created_at": datetime.now().isoformat()
    }
    chat_db.insert(chat_message)
    print(f"✅ Mensagem de chat salva para {username}")


def buscar_chat_history(username: str, limit: int = 10) -> list[dict]:
    """Busca histórico de chat de um usuário"""
    messages = chat_db.search(Chat.username == username)
    messages = sorted(messages, key=lambda x: x.get('created_at', ''), reverse=False)
    return messages[-limit:]


def salvar_meal_analysis(username: str, analise: dict, imagem_nome: str | None = None) -> None:
    """Salva análise de refeição no banco separado"""
    meal_data = {
        "usuario":     username,
        "analise":     analise,
        "imagem_nome": imagem_nome,
        "data":        datetime.now().isoformat()
    }
    meals_db.insert(meal_data)
    print(f"✅ Análise de refeição salva para {username}")


def buscar_meal_history(username: str, limit: int = 10) -> list[dict]:
    """Busca histórico de refeições de um usuário"""
    meals = meals_db.search(Meal.usuario == username)
    meals = sorted(meals, key=lambda x: x.get('data', ''), reverse=True)
    return meals[:limit]
