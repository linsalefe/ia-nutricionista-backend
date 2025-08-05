# app/db.py

from tinydb import TinyDB, Query
import os

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
    print(f"❌ Usuário {username} não encontrado")
    return None

def salvar_chat_message(username, role, text, message_type="text"):
    """Salva uma mensagem de chat no banco de chat separado"""
    from datetime import datetime
    
    message = {
        "username": username,
        "role": role,
        "text": text,
        "type": message_type,
        "created_at": datetime.utcnow().isoformat()
    }
    
    chat_db.insert(message)
    print(f"✅ Mensagem de chat salva para {username}")

def buscar_chat_history(username, limit=20):
    """Busca o histórico de chat de um usuário"""
    messages = chat_db.search(Chat.username == username)
    # Ordenar por data e pegar as últimas X mensagens
    messages = sorted(messages, key=lambda x: x.get('created_at', ''), reverse=True)[:limit]
    messages.reverse()  # Voltar para ordem cronológica
    
    # Converter para formato esperado pela API
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "role": msg["role"],
            "text": msg["text"]
        })
    
    print(f"✅ Histórico de chat carregado para {username}: {len(formatted_messages)} mensagens")
    return formatted_messages

def salvar_meal_analysis(username, analise, imagem_nome=None):
    """Salva análise de refeição no banco de meals"""
    from datetime import datetime
    
    meal = {
        "usuario": username,
        "analise": analise,
        "imagem_nome": imagem_nome,
        "data": datetime.utcnow().isoformat()
    }
    
    meals_db.insert(meal)
    print(f"✅ Análise de refeição salva para {username}")

def buscar_meal_history(username, limit=10):
    """Busca histórico de refeições de um usuário"""
    meals = meals_db.search(Meal.usuario == username)
    # Ordenar por data e pegar as últimas X refeições
    meals = sorted(meals, key=lambda x: x.get('data', ''), reverse=True)[:limit]
    
    print(f"✅ Histórico de refeições carregado para {username}: {len(meals)} refeições")
    return meals

# Função para migrar dados antigos (executar uma vez)
def migrate_old_data():
    """Migra dados antigos para nova estrutura"""
    print("🔄 Iniciando migração de dados...")
    
    # Buscar todos os usuários
    all_users = db.all()
    
    for user in all_users:
        username = user.get("username")
        
        # Migrar chat_history do usuário para chat_db separado
        if "chat_history" in user and user["chat_history"]:
            print(f"Migrando chat para {username}...")
            for msg in user["chat_history"]:
                # Verificar se já existe no chat_db
                existing = chat_db.search(
                    (Chat.username == username) & 
                    (Chat.text == msg.get("text")) & 
                    (Chat.created_at == msg.get("created_at"))
                )
                if not existing:
                    chat_message = {
                        "username": username,
                        "role": msg.get("role"),
                        "text": msg.get("text"),
                        "type": msg.get("type", "text"),
                        "created_at": msg.get("created_at")
                    }
                    chat_db.insert(chat_message)
    
    print("✅ Migração concluída!")

# Para executar a migração uma vez:
# migrate_old_data()