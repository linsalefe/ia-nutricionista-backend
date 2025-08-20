# app/endpoints/chat.py
import os
from datetime import datetime
import openai
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from openai import OpenAI  # nova interface v1+
from app.auth import get_current_username
from app.db import salvar_chat_message, buscar_chat_history, buscar_usuario
from app.services.lina_context import build_lina_system_prompt  # << INTEGRAÇÃO NOVA

# Verificar se a chave existe
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ ERRO: OPENAI_API_KEY não está definida no .env")
else:
    print(f"✅ OpenAI API Key encontrada: {api_key[:10]}...")

# Inicializa o cliente com sua chave de .env
client = OpenAI(api_key=api_key)

# Router sem prefix interno; prefix será aplicado em main.py
router = APIRouter(tags=["chat"])

def get_lina_chat_prompt(username: str, nome: str | None = None) -> str:
    """Prompt fallback da Lina (sem metas)"""
    nome_exibicao = nome if nome else username
    return f"""Você é a Lina, assistente nutricional da NutriFlow. Você está conversando com {nome_exibicao} ({username}).

🎯 Sua missão: Ser a companheira nutricional de {nome_exibicao}, sempre positiva, encorajadora e prestativa.

💬 Como a Lina conversa:
- Se apresente como "Lina" na primeira interação
- Use o nome {nome_exibicao} de forma natural
- Seja amigável e motivadora
- Foque em nutrição e alimentação saudável
- Emojis com moderação
- Dicas práticas e personalizadas

⚠️ Importante:
- Nada de conselhos médicos específicos
- Sugira procurar profissional quando necessário
- Seja sempre positiva e motivadora
"""

class ChatSendPayload(BaseModel):
    message: str = Field(..., description="Texto que o usuário enviou")

class ChatResponse(BaseModel):
    response: str

class ChatHistoryResponse(BaseModel):
    history: list

@router.post("/send", response_model=ChatResponse)
def send_to_ai(
    payload: ChatSendPayload,
    username: str = Depends(get_current_username),
):
    """
    Envia a mensagem do usuário para a OpenAI e retorna a resposta.
    Injeta profile+targets no system prompt quando disponível.
    """
    try:
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API key não configurada"
            )

        # Buscar informações básicas do usuário (nome para personalização)
        user_data = buscar_usuario(username)
        nome = user_data.get("nome") if user_data else None

        # Tenta construir o system prompt com profile+targets
        try:
            sys_prompt, ctx = build_lina_system_prompt(username)
        except Exception as _:
            # Perfil incompleto ou erro: usa fallback simples
            sys_prompt = get_lina_chat_prompt(username, nome)
            ctx = {"profile": None, "targets": None}

        # Histórico (últimas N mensagens)
        history = buscar_chat_history(username, limit=8) or []

        # Monta mensagens para a API
        messages: list[dict] = [{"role": "system", "content": sys_prompt}]

        # Mapeia histórico: 'bot' -> 'assistant'
        for msg in history:
            if isinstance(msg, dict) and "role" in msg and "text" in msg:
                role = msg.get("role", "user")
                if role == "bot":
                    role = "assistant"
                content = msg.get("text", "")
                if content:
                    messages.append({"role": role, "content": content})

        # Mensagem atual do usuário
        messages.append({"role": "user", "content": payload.message})

        # Chamada ao modelo
        model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=700,
            temperature=0.6,
        )

        content = (resp.choices[0].message.content or "").strip()

        # Persistência do histórico (⚠️ usar 'bot' para compat com front)
        salvar_chat_message(username, "user", payload.message, "text")
        salvar_chat_message(username, "bot", content, "text")

        return ChatResponse(response=content)

    except openai.AuthenticationError as e:
        print(f"❌ ERRO de autenticação OpenAI: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Erro de autenticação com OpenAI. Verifique a API key."
        )
    except openai.APIError as e:
        print(f"❌ ERRO da API OpenAI: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro da API OpenAI: {str(e)}"
        )
    except Exception as e:
        import traceback
        print(f"❌ ERRO geral: {type(e).__name__}: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro ao conectar com a IA: {str(e)}"
        )

@router.get("/history", response_model=ChatHistoryResponse)
def get_chat_history(username: str = Depends(get_current_username)):
    """
    Retorna o histórico de chat do usuário
    """
    try:
        history = buscar_chat_history(username, limit=50) or []
        formatted_history = []
        for msg in history:
            if isinstance(msg, dict):
                formatted_history.append({
                    "role": msg.get("role", "user"),
                    "text": msg.get("text", ""),
                    "type": msg.get("type", "text"),
                    "imageUrl": msg.get("imageUrl"),
                    "created_at": msg.get("created_at", "")
                })
        return ChatHistoryResponse(history=formatted_history)
    except Exception as e:
        print(f"❌ ERRO ao buscar histórico: {str(e)}")
        return ChatHistoryResponse(history=[])

@router.post("/save")
def save_chat_message(
    message_data: dict,
    username: str = Depends(get_current_username)
):
    """
    Salva uma mensagem de chat (compatibilidade com frontend)
    """
    try:
        role = message_data.get("role", "user")
        text = message_data.get("text", "")
        message_type = message_data.get("type", "text")
        salvar_chat_message(username, role, text, message_type)
        return {"status": "success", "message": "Mensagem salva"}
    except Exception as e:
        print(f"❌ ERRO ao salvar mensagem: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao salvar mensagem: {e}"
        )
