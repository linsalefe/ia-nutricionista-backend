# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Importação dos routers
try:
    from app.endpoints.user import router as user_router
    from app.endpoints.dashboard import router as dashboard_router
    from app.endpoints.weight_logs import router as weight_logs_router
    from app.endpoints.chat import router as chat_router
    from app.endpoints.chat_history import router as chat_history_router
    from app.endpoints.image import router as image_router
    from app.endpoints.meal import router as meal_router
    print("✅ Todos os routers importados com sucesso!")
except ImportError as e:
    print(f"❌ Erro ao importar routers: {e}")

# Inicialização da aplicação FastAPI
app = FastAPI(title="IA Nutricionista SaaS", version="0.1.0")

# Configuração de CORS para permitir chamadas do frontend
origins = [
    "https://app-nutriflow.onrender.com",  # domínio de produção
    "http://localhost:5173",               # Vite dev
    "http://localhost:4173",               # Vite preview
]

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

@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "NutriFlow API funcionando!"}

# Rotas dos endpoints da aplicação
try:
    app.include_router(user_router,         prefix="/api/user",      tags=["user"])
    app.include_router(dashboard_router,    prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(weight_logs_router,  prefix="/api/weight-logs", tags=["weight-logs"])
    app.include_router(chat_router,         prefix="/api/chat",       tags=["chat"])
    app.include_router(chat_history_router, prefix="/api/chat-history", tags=["chat-history"])
    app.include_router(image_router,        prefix="/api/image",      tags=["image"])
    app.include_router(meal_router,         prefix="/api/meal",       tags=["meal"])
    print("✅ Todos os routers registrados com sucesso!")
except Exception as e:
    print(f"❌ Erro ao registrar routers: {e}")

# Endpoint para debug
@app.get("/api/debug")
def debug_info():
    return {
        "status": "online",
        "endpoints": [
            "/api/user/signup",
            "/api/user/login", 
            "/api/user/me",
            "/api/chat/send",
            "/api/chat/history",
            "/api/chat/save",
            "/api/image/analyze"
        ]
    }