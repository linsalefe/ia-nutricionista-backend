from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from app.auth import get_current_username  # Importar a função do auth.py
import openai
import os
from dotenv import load_dotenv
import base64
from app.db import salvar_meal_analysis

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

router = APIRouter()

def get_lina_prompt(username: str) -> str:
    """Retorna o prompt personalizado da Lina com o nome do usuário"""
    return f"""Você é a Lina, assistente nutricional da NutriFlow. O usuário {username} está compartilhando uma refeição com você.

🎯 Sua missão: Ajudar {username} a alcançar seus objetivos através de uma alimentação consciente.

📸 Ao analisar a imagem, forneça:

🍽️ **Alimentos identificados:**
- Liste cada alimento com a quantidade estimada (use porções típicas brasileiras)

📊 **Informações Nutricionais Totais:**
• Calorias: XXX kcal
• Proteínas: XX g  
• Carboidratos: XX g
• Gorduras: XX g

💡 **Dica da Lina:**
[Forneça uma dica personalizada - pode ser sobre o prato, sugestões de melhorias, ou palavras motivadoras]

⚠️ Importante: 
- Seja precisa mas amigável
- Use o nome {username} quando apropriado
- Se não tiver certeza dos valores, faça estimativas conservadoras
- Foque APENAS em nutrição e alimentação saudável
- Use emojis moderadamente para tornar a conversa mais leve

Lembre-se: Você é a companheira nutricional de {username}, sempre positiva e encorajadora! 😊"""

@router.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...), 
    username: str = Depends(get_current_username)
):
    try:
        # Lê o arquivo enviado
        image_bytes = await file.read()
        # Codifica em base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        # Descobre o tipo da imagem (opcional, mas bom para PNG/JPEG)
        content_type = file.content_type  # Exemplo: "image/jpeg"
        if content_type is None:
            content_type = "image/jpeg"
        data_url = f"data:{content_type};base64,{image_base64}"

        # Debug: verificar se o username está chegando
        print(f"DEBUG: Username recebido: {username}")
        
        # Gerar o prompt da Lina
        lina_system_prompt = get_lina_prompt(username)
        print(f"DEBUG: Prompt gerado para {username}")

        # Envia para o GPT-4o Vision (OpenAI)
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": lina_system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": f"Olá Lina! Sou o {username}. Analise nutricionalmente esse prato que estou compartilhando com você:"},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]}
            ],
            max_tokens=800,
            temperature=0.3
        )
        resultado = response.choices[0].message.content

        # Salvar análise no banco de meals
        salvar_meal_analysis(username, resultado, file.filename)

        return {
            "usuario": username,
            "analise": resultado
        }
    
    except Exception as e:
        print(f"Erro na análise: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao analisar imagem: {str(e)}")