from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from app.auth import SECRET_KEY, ALGORITHM
import openai
import os
from dotenv import load_dotenv
import base64
from app.utils.metrics import compute_bmi, compute_progress

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")

def get_current_username(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception

@router.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...), 
    username: str = Depends(get_current_username)
):
    # Lê o arquivo enviado
    image_bytes = await file.read()
    # Codifica em base64
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    # Descobre o tipo da imagem (opcional, mas bom para PNG/JPEG)
    content_type = file.content_type  # Exemplo: "image/jpeg"
    if content_type is None:
        content_type = "image/jpeg"
    data_url = f"data:{content_type};base64,{image_base64}"

    # Envia para o GPT-4o Vision (OpenAI)
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Você é uma nutricionista especialista em análise de pratos por foto. Seja objetiva e detalhada, respondendo em tópicos. Informe as calorias, proteínas, carboidratos e gorduras totais do prato. Se não souber o valor exato, faça uma estimativa baseada em porção comum no Brasil. Não peça para o usuário digitar nada, nem envie links, apenas responda o que conseguir analisar pela imagem."},
            {"role": "user", "content": [
                {"type": "text", "text": "Analise nutricionalmente esse prato:"},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]}
        ],
        max_tokens=700,
        temperature=0.2
    )
    resultado = response.choices[0].message.content

    return {
        "usuario": username,
        "analise": resultado
    }