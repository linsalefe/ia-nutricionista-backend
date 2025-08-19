import os
from datetime import datetime
import openai
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from openai import OpenAI  # nova interface v1+
from app.auth import get_current_username  # Importar a função do auth.py
from app.db import salvar_chat_message, buscar_chat_history

# Verificar se a chave existe
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ ERRO: OPENAI_API_KEY não está definida no .env")
else:
    print(f"✅ OpenAI API Key encontrada: {api_key[:10]}...")

# Inicializa o cliente com sua chave de .env
client = OpenAI(api_key=api_key)

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

class ChatHistoryResponse(BaseModel):
    history: list

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
        print(f"🔍 DEBUG - Mensagem recebida: {payload.message}")
        
        # Verificar se a API key está disponível
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API key não configurada"
            )
        
        # Buscar histórico de chat do usuário (últimas 10 mensagens)
        history = buscar_chat_history(username, limit=3)
        print(f"🔍 DEBUG - Histórico encontrado: {len(history)} mensagens")
        
        # Gerar prompt personalizado da Lina
        from app.db import buscar_usuario
        user_data = buscar_usuario(username)
        nome = user_data.get("nome") if user_data else None
        
        lina_prompt = get_lina_chat_prompt(username, nome)
        print(f"🔍 DEBUG - Prompt da Lina gerado para {username}")
        print(f"🔍 DEBUG - Nome do usuário: {nome}")
        
        # Preparar mensagens para a API
        messages = [{"role": "system", "content": lina_prompt}]
        
        # Adicionar histórico (mapear "bot" para "assistant")
        for msg in history:
            if isinstance(msg, dict) and "role" in msg and "text" in msg:
                role = msg["role"]
                if role == "bot":
                    role = "assistant"
                messages.append({
                    "role": role,
                    "content": msg["text"]
                })
            else:
                print(f"⚠️ Mensagem do histórico sem formato correto: {msg}")
        
        # Adicionar mensagem atual do usuário
        messages.append({
            "role": "user", 
            "content": payload.message
        })

        print(f"🔍 DEBUG - Total de mensagens enviadas para OpenAI: {len(messages)}")
        print(f"🔍 DEBUG - Chamando OpenAI API...")

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        content = resp.choices[0].message.content.strip()
        print(f"🔍 DEBUG - Resposta da OpenAI recebida: {content[:100]}...")
        
        # Salvar mensagens no histórico
        salvar_chat_message(username, "user", payload.message, "text")
        salvar_chat_message(username, "assistant", content, "text")
        print(f"🔍 DEBUG - Mensagens salvas no histórico")
        
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
        print(f"❌ ERRO geral: {type(e).__name__}: {str(e)}")
        import traceback
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
        print(f"🔍 Buscando histórico para: {username}")
        history = buscar_chat_history(username, limit=50)
        
        # Garantir que history é sempre uma lista
        if not isinstance(history, list):
            history = []
        
        # Converter para formato que o frontend espera
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
        
        print(f"✅ Histórico formatado: {len(formatted_history)} mensagens")
        return ChatHistoryResponse(history=formatted_history)
        
    except Exception as e:
        print(f"❌ ERRO ao buscar histórico: {str(e)}")
        # Sempre retornar array vazio em caso de erro
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
