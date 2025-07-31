# app/db.py

from tinydb import TinyDB, Query
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '../db.json')
db = TinyDB(DB_PATH)
User = Query()

def salvar_usuario(user):
    if db.search(User.username == user['username']):
        db.update(user, User.username == user['username'])
    else:
        db.insert(user)

def buscar_usuario(username):
    result = db.search(User.username == username)
    return result[0] if result else None
