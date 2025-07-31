# app/models.py

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    password: str
    nome: Optional[str] = None
    objetivo: Optional[str] = None
    height_cm: Optional[float] = None    # altura em centímetros
    initial_weight: Optional[float] = None  # peso inicial em kg


class UserLogin(BaseModel):
    username: str
    password: str


class WeightLog(BaseModel):
    weight: float
    recorded_at: datetime


class UserDB(BaseModel):
    id: str
    username: str
    nome: Optional[str]
    objetivo: Optional[str]
    height_cm: Optional[float]
    initial_weight: Optional[float]
    # histórico de registros de peso
    weight_logs: Optional[List[WeightLog]] = []
    refeicoes: Optional[List[dict]] = []

    class Config:
        # Pydantic V2: permitir criação a partir de atributos ORM
        from_attributes = True
