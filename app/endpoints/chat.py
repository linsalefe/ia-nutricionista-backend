import os
from datetime import datetime
import openai
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from openai import OpenAI  # nova interface v1+
from app.auth import get_current_username  # Importar a função do auth.py
from app.db import salvar_chat_message, buscar_chat_history

# Inicializa o cliente com sua chave de .env
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Router sem prefix interno; prefix será aplicado em main.py
router = APIRouter(
    tags=["chat"],
)

def get_lina_chat_prompt(username: str, nome: str = None) -> str:
    """Retorna o prompt da Lina para conversas em chat"""
    nome_exibicao = nome if nome else username
    return f"""Você é a Lina, assistente nutricional da NutriFlow. Você está conversando com {nome_exibicao} ({username}).

🎯 Sua missão: Ser a companheira nutricional de {nome_exibicao}, sempre positiva, encorajadora e prestativa.

💬 **Como a Lina conversa:**
- Se apresente como "Lina" na primeira interação
- Use o nome {nome_exibicao} de forma natural nas conversas
- Seja amigável, acolhedora e motivadora
- Foque em nutrição, alimentação saudável e bem-estar
- Use emojis moderadamente para deixar a conversa mais leve
- Dê dicas práticas e personalizadas
- Sempre encoraje hábitos saudáveis

⚠️ Importante:
- Mantenha o foco em nutrição e saúde
- Seja precisa mas acessível nas informações
- Não dê conselhos médicos específicos
- Encoraje a buscar profissionais quando necessário
- Seja sempre positiva e motivadora

Lembre-se: Você é a parceira nutricional de {nome_exibicao}! 😊"""

class ChatSendPayload(BaseModel):
    message: str = Field(..., description="Texto que o usuário enviou")

class ChatResponse(BaseModel):
    response: str

@router.post("/send", response_model=ChatResponse)
def send_to_ai(
    payload: ChatSendPayload,
    username: str = Depends(get_current_username),
):
    """
    Envia a mensagem do usuário para a OpenAI e retorna a resposta.
    """
    try:
        # DEBUG: Verificar se os dados chegaram
        print(f"🔍 DEBUG - Username: {username}")
        
        # Buscar histórico de chat do usuário (últimas 10 mensagens)
        history = buscar_chat_history(username, limit=10)
        
        # Gerar prompt personalizado da Lina
        from app.db import buscar_usuario
        user_data = buscar_usuario(username)
        nome = user_data.get("nome") if user_data else None
        
        lina_prompt = get_lina_chat_prompt(username, nome)
        print(f"🔍 DEBUG - Prompt da Lina gerado para {username}")
        print(f"🔍 DEBUG - Nome do usuário: {nome}")
        
        # Preparar mensagens para a API
        messages = [{"role": "system", "content": lina_prompt}]
        
        # Adicionar histórico
        for msg in history:
            messages.append({
                "role": msg["role"], 
                "content": msg["text"]
            })
        
        # Adicionar mensagem atual do usuário
        messages.append({
            "role": "user", 
            "content": payload.message
        })

        print(f"🔍 DEBUG - Total de mensagens enviadas para OpenAI: {len(messages)}")

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        content = resp.choices[0].message.content.strip()
        print(f"🔍 DEBUG - Resposta da OpenAI: {content[:100]}...")
        
        # Salvar mensagens no histórico
        salvar_chat_message(username, "user", payload.message, "text")
        salvar_chat_message(username, "assistant", content, "text")
        
        return ChatResponse(response=content)
        
    except Exception as e:
        print(f"❌ ERRO: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro ao conectar com a IA: {e}"
        )
