#!/usr/bin/env python3
import os
import uuid
import getpass
from pathlib import Path
from passlib.context import CryptContext
from tinydb import TinyDB, Query

# Configurações TinyDB e hashing
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'db.json'
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
db = TinyDB(DB_PATH)
User = Query()

# Criação interativa
print('=== Criar usuário ADMIN ===')
username = input('Digite o username (ex: admin): ').strip()
# Verifica duplicado
if db.search(User.username == username):
    print(f"❌ Usuário '{username}' já existe.")
    exit(1)

password = getpass.getpass('Digite a senha: ')
hash_senha = pwd_context.hash(password)

new_user = {
    'id': str(uuid.uuid4()),
    'username': username,
    'password': hash_senha,
    'password_hash': hash_senha,
    'has_access': True,
    'is_admin': True,
}

# Insere no TinyDB
db.insert(new_user)
print(f"✅ Usuário ADMIN '{username}' criado com sucesso.")
