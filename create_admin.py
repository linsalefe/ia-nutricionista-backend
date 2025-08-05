#!/usr/bin/env python3
import os
import json
import uuid
import getpass
from passlib.hash import bcrypt

# Diretório base e caminho do DB
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'db.json')

# Carrega o JSON
with open(DB_PATH, 'r', encoding='utf-8') as f:
    db = json.load(f)

# Garante a lista de usuários
if 'users' not in db:
    db['users'] = []

# Criação interativa
print('=== Criar usuário ADMIN ===')
username = input('Digite o username (ex: admin): ').strip()
if any(u.get('username') == username for u in db['users']):
    print(f"❌ Usuário '{username}' já existe.")
    exit(1)

password = getpass.getpass('Digite a senha: ')
hash_senha = bcrypt.hash(password)

new_user = {
    'id': str(uuid.uuid4()),
    'username': username,
    'password_hash': hash_senha,
    'password': hash_senha,   # compatibilidade login
    'is_admin': True,
    'has_access': True
}

db['users'].append(new_user)

# Salva de volta no JSON
with open(DB_PATH, 'w', encoding='utf-8') as f:
    json.dump(db, f, indent=2, ensure_ascii=False)

print(f"✅ Usuário ADMIN '{username}' criado com sucesso.")
