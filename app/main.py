# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Carrega variáveis de ambiente
load_dotenv()

# Importa routers
from app.endpoints.user import router as user_router
from app.endpoints.dashboard import router as dashboard_router
from app.endpoints.weight_logs import router as weight_logs_router
from app.endpoints.chat import router as chat_router
from app.endpoints.chat_history import router as chat_history_router
from app.endpoints.image import router as image_router
from app.endpoints.meal import router as meal_router
from app.endpoints.webhook import router as webhook_router  # webhook Disrupty

# Inicializa app
app = FastAPI(title="IA Nutricionista SaaS", version="0.1.0")

# Configurações de CORS
origins = [
    "https://app-nutriflow.onrender.com",
    "http://localhost:5173",
    "http://localhost:4173",
]
# Em produção, remova o "*" e use apenas your domínio

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"msg": "API online!"}

# Registra routers
app.include_router(user_router,         prefix="/api/user",         tags=["user"])
app.include_router(dashboard_router,    prefix="/api/dashboard",    tags=["dashboard"])
app.include_router(weight_logs_router,  prefix="/api/weight-logs",   tags=["weight-logs"])
app.include_router(chat_router,         prefix="/api/chat",          tags=["chat"])
app.include_router(chat_history_router, prefix="/api/chat-history",  tags=["chat-history"])
app.include_router(image_router,        prefix="/api/image",         tags=["image"])
app.include_router(meal_router,         prefix="/api/meal",          tags=["meal"])
app.include_router(webhook_router,      prefix="/api/webhook",       tags=["webhook"])
