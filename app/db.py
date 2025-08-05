# app/db.py

from tinydb import TinyDB, Query
import os
from datetime import datetime

# Definir caminhos dos bancos
DB_PATH = os.path.join(os.path.dirname(__file__), '../db.json')
CHAT_DB_PATH = os.path.join(os.path.dirname(__file__), '../chat_db.json')
MEALS_DB_PATH = os.path.join(os.path.dirname(__file__), '../meals_db.json')

# Inicializar bancos
db = TinyDB(DB_PATH)
chat_db = TinyDB(CHAT_DB_PATH)
meals_db = TinyDB(MEALS_DB_PATH)

User = Query()
Chat = Query()
Meal = Query()

def salvar_usuario(user):
    """Salva ou atualiza um usuário no banco principal"""
    # Garantir que o usuário tenha todos os campos necessários
    default_user = {
        "id": user.get("id"),
        "username": user["username"],
        "password": user.get("password"),
        "nome": user.get("nome"),
        "objetivo": user.get("objetivo"),
        "height_cm": user.get("height_cm"),
        "initial_weight": user.get("initial_weight"),
        "weight_logs": user.get("weight_logs", []),
        "refeicoes": user.get("refeicoes", []),
        "chat_history": user.get("chat_history", [])  # Manter para compatibilidade
    }
    
    if db.search(User.username == user['username']):
        db.update(default_user, User.username == user['username'])
        print(f"✅ Usuário {user['username']} atualizado no banco")
    else:
        db.insert(default_user)
        print(f"✅ Usuário {user['username']} inserido no banco")

def buscar_usuario(username):
    """Busca um usuário no banco principal"""
    result = db.search(User.username == username)
    if result:
        user = result[0]
        print(f"✅ Usuário {username} encontrado no banco")
        return user
    else:
        print(f"❌ Usuário {username} não encontrado")
        return None

def salvar_chat_message(username, role, text, msg_type="text"):
    """Salva uma mensagem de chat no banco separado"""
    chat_message = {
        "username": username,
        "role": role,
        "text": text,
        "type": msg_type,
        "created_at": datetime.now().isoformat()
    }
    chat_db.insert(chat_message)
    print(f"✅ Mensagem de chat salva para {username}")

def buscar_chat_history(username, limit=10):
    """Busca histórico de chat de um usuário"""
    messages = chat_db.search(Chat.username == username)
    # Ordenar por data e pegar as últimas X mensagens
    messages = sorted(messages, key=lambda x: x.get('created_at', ''), reverse=False)
    
    # Limitar quantidade se especificado
    if limit:
        messages = messages[-limit:]
    
    print(f"✅ Histórico de chat carregado para {username}: {len(messages)} mensagens")
    return messages

def salvar_meal_analysis(username, analise, imagem_nome=None):
    """Salva análise de refeição no banco separado"""
    meal_data = {
        "usuario": username,
        "analise": analise,
        "imagem_nome": imagem_nome,
        "data": datetime.now().isoformat()
    }
    meals_db.insert(meal_data)
    print(f"✅ Análise de refeição salva para {username}")

def buscar_meal_history(username, limit=10):
    """Busca histórico de refeições de um usuário"""
    meals = meals_db.search(Meal.usuario == username)
    # Ordenar por data e pegar as últimas X refeições
    meals = sorted(meals, key=lambda x: x.get('data', ''), reverse=True)[:limit]
    
    print(f"✅ Histórico de refeições carregado para {username}: {len(meals)} refeições")
    return meals