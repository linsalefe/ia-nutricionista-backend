# app/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# === Pastas para arquivos estáticos (avatars, etc.) ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOADS_ROOT = os.path.join(BASE_DIR, "uploads")
AVATARS_DIR = os.path.join(UPLOADS_ROOT, "avatars")
os.makedirs(AVATARS_DIR, exist_ok=True)

# Importa routers
from app.endpoints.user import router as user_router
from app.endpoints.dashboard import router as dashboard_router
from app.endpoints.weight_logs import router as weight_logs_router
from app.endpoints.chat import router as chat_router
from app.endpoints.chat_history import router as chat_history_router
from app.endpoints.image import router as image_router
from app.endpoints.meal import router as meal_router
from app.endpoints.webhook import router as webhook_router  # webhook Disrupty
from app.endpoints.webhook_kiwify import router as webhook_kiwify_router  # webhook Kiwify
from app.endpoints.nutrition import router as nutrition_router  # NOVO: perfil e metas nutricionais

# Inicializa app
app = FastAPI(title="IA Nutricionista SaaS", version="0.1.0")

# -------- CORS --------
ALLOWED_ORIGINS = [
    os.getenv("FRONTEND_URL", "https://app-nutriflow.onrender.com"),
    "https://portal.nutriflow.cloud",  # NOVO DOMÍNIO
    "https://nutriflow-api.duckdns.org",
    "http://44.204.161.228",   # NOVO IP DO FRONTEND LIGHTSAIL
    "https://44.204.161.228",  # VERSÃO HTTPS PARA O FUTURO
    "http://localhost:5173",
    "http://localhost:4173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https?://(.+\.)?onrender\.com$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Static files (acesso público a /static/avatars/...)
app.mount("/static", StaticFiles(directory=UPLOADS_ROOT), name="static")

@app.get("/")
def read_root():
    return {"msg": "API online!"}

@app.get("/health")
def health():
    return {"status": "ok"}

# Alias dentro de /api para facilitar ping de aquecimento do front
@app.get("/api/health")
def api_health():
    return {"status": "ok"}

# -------- Routers --------
app.include_router(user_router,         prefix="/api/user",         tags=["user"])
app.include_router(dashboard_router,    prefix="/api/dashboard",    tags=["dashboard"])
app.include_router(weight_logs_router,  prefix="/api/weight-logs",  tags=["weight-logs"])
app.include_router(chat_router,         prefix="/api/chat",         tags=["chat"])
app.include_router(chat_history_router, prefix="/api/chat-history", tags=["chat-history"])
app.include_router(image_router,        prefix="/api/image",        tags=["image"])

# Rotas de refeição: singular (oficial) + plural (compat com front)
app.include_router(meal_router,         prefix="/api/meal",         tags=["meal"])
app.include_router(meal_router,         prefix="/api/meals",        tags=["meal-compat"])

# Webhooks
app.include_router(webhook_router,        prefix="/api/webhook", tags=["webhook-disrupty"])
app.include_router(webhook_kiwify_router, prefix="/api/webhook", tags=["webhook-kiwify"])

# Nutrição (perfil + metas)
app.include_router(nutrition_router,      prefix="/api/nutrition", tags=["nutrition"])
