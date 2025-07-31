from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from app.auth import SECRET_KEY, ALGORITHM
from tinydb import TinyDB, Query
from pydantic import BaseModel
from datetime import datetime
import os
from dotenv import load_dotenv
from app.utils.metrics import compute_bmi, compute_progress

load_dotenv()

db = TinyDB('meals_db.json')
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")

def get_current_username(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception

class MealIn(BaseModel):
    analise: str
    imagem_nome: str = None  # pode ser None, se não quiser salvar imagem

@router.post("/save")
def save_meal(meal: MealIn, username: str = Depends(get_current_username)):
    meal_data = {
        "usuario": username,
        "analise": meal.analise,
        "imagem_nome": meal.imagem_nome,
        "data": datetime.now().isoformat()
    }
    db.insert(meal_data)
    return {"msg": "Refeição salva com sucesso!"}

@router.get("/history")
def get_meal_history(username: str = Depends(get_current_username)):
    UserQ = Query()
    meals = db.search(UserQ.usuario == username)
    return meals
