# app/endpoints/image.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.auth import get_current_username
from openai import OpenAI
from dotenv import load_dotenv
from app.db import salvar_meal_analysis

import os
import base64
import imghdr

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

router = APIRouter()

ALLOWED_IMG_TYPES = {"jpeg", "png", "webp", "gif"}


def _sniff_image_type(data: bytes, fallback: str = "jpeg") -> str:
    kind = imghdr.what(None, h=data)
    return kind if kind in ALLOWED_IMG_TYPES else fallback


def get_lina_prompt(username: str) -> str:
    """Prompt da Lina (formato exigido p/ o front)."""
    return f"""Você é a Lina, assistente nutricional da NutriFlow. O usuário {username} está compartilhando uma refeição com você.

🎯 Sua missão: Ajudar {username} a alcançar seus objetivos através de uma alimentação consciente.

📸 Ao analisar a imagem, forneça a resposta EXATAMENTE neste formato:

🍽️ Alimentos identificados:
- [Alimento 1]: [quantidade estimada]
- [Alimento 2]: [quantidade estimada]
- [Alimento 3]: [quantidade estimada]

📊 Informações Nutricionais Totais:
• Calorias: XXX kcal
• Proteínas: XX g
• Carboidratos: XX g
• Gorduras: XX g

💡 Dica da Lina:
[Forneça uma dica personalizada - pode ser sobre o prato, sugestões de melhorias, ou palavras motivadoras]

⚠️ Se identifiquei o alimento errado, coloque o nome correto aqui embaixo que eu corrijo a quantidade de nutrientes:
[Campo para correção do usuário]

⚠️ Importante:
- Seja precisa mas amigável
- Use o nome {username} quando apropriado
- Se não tiver certeza dos valores, faça estimativas conservadoras
- Foque APENAS em nutrição e alimentação saudável
- Use emojis moderadamente para tornar a conversa mais leve
- Mantenha o formato limpo e organizado

Lembre-se: Você é a companheira nutricional de {username}, sempre positiva e encorajadora! 😊"""


@router.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    username: str = Depends(get_current_username),
):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada.")

    # Lê arquivo
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Arquivo de imagem vazio.")

    # Tamanho (8MB)
    if len(image_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Imagem muito grande (máx. 8MB).")

    # Content-Type seguro
    content_type = file.content_type or f"image/{_sniff_image_type(image_bytes)}"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Envie um arquivo de imagem válido.")

    # Data URL
    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

    # Prompts
    system_prompt = get_lina_prompt(username)

    # OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Olá Lina! Sou o {username}. Analise nutricionalmente esse prato que estou compartilhando com você:",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            max_tokens=800,
            temperature=0.3,
        )
        resultado = response.choices[0].message.content or ""
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha na análise: {e}")

    # Persistência (não quebra a resposta se falhar)
    try:
        salvar_meal_analysis(username, resultado, getattr(file, "filename", "upload"))
    except Exception as e:
        print(f"[WARN] Falha ao salvar análise: {e}")

    return {"usuario": username, "analise": resultado}
