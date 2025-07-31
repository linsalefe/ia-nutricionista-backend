import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from openai import OpenAI  # nova interface v1+
from app.auth import get_current_user
from app.db import salvar_usuario

# inicializa o cliente com sua chave de .env
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Router sem prefix interno; prefix será aplicado em main.py
router = APIRouter(
    tags=["chat"],
)

class ChatSendPayload(BaseModel):
    message: str = Field(..., description="Texto que o usuário enviou")

class ChatResponse(BaseModel):
    response: str

@router.post("/send", response_model=ChatResponse)
def send_to_ai(
    payload: ChatSendPayload,
    current_user: dict = Depends(get_current_user),
):
    """
    Envia a mensagem do usuário para a OpenAI e retorna a resposta.
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": payload.message}],
        )
        content = resp.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro ao conectar com a IA: {e}"
        )

    # Salva a resposta no histórico do usuário
    history = current_user.get("chat_history") or []
    history.append({
        "role": "bot",
        "text": content,
        "created_at": datetime.utcnow().isoformat(),
    })
    current_user["chat_history"] = history
    salvar_usuario(current_user)

    return ChatResponse(response=content)
