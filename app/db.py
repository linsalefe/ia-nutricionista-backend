# app/db.py
import os
from datetime import datetime
from typing import Any, Dict, Optional, List
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import (
    create_engine, select, func, String, Float, Text, Boolean,
    DateTime, ForeignKey, Enum, text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import UUID, JSONB


# =========================
# Conexão / Engine / Sessão
# =========================
def _normalize_database_url(url: str) -> str:
    """
    Converte para driver psycopg e garante sslmode=require.
    Aceita 'postgres://' ou 'postgresql://'.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL não definida no .env")

ENGINE = create_engine(_normalize_database_url(DATABASE_URL), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=ENGINE, autocommit=False, autoflush=False)


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =========================
# Modelos (mínimos) SQLA
# =========================
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    nome: Mapped[Optional[str]] = mapped_column(String(255))
    objetivo: Mapped[Optional[str]] = mapped_column(String(255))
    height_cm: Mapped[Optional[float]] = mapped_column(Float)
    initial_weight: Mapped[Optional[float]] = mapped_column(Float)
    has_access: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    weight_logs: Mapped[List["WeightLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    chats: Mapped[List["ChatMessage"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    meals: Mapped[List["MealAnalysis"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    user: Mapped["User"] = relationship(back_populates="weight_logs")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # ✅ inclui 'assistant' no enum
    role: Mapped[str] = mapped_column(Enum("user", "assistant", "bot", name="chat_role"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[Optional[str]] = mapped_column(Enum("text", "image", name="message_type"))
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="chats")


class MealAnalysis(Base):
    __tablename__ = "meal_analyses"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    analysis: Mapped[dict] = mapped_column(JSONB, nullable=False)
    image_name: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="meals")


# Cria tabelas (temporário até Alembic)
Base.metadata.create_all(bind=ENGINE)


def _ensure_pg_enums():
    """Garante que o enum chat_role tenha o valor 'assistant' no banco."""
    with ENGINE.begin() as conn:
        conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'chat_role' AND e.enumlabel = 'assistant'
            ) THEN
                ALTER TYPE chat_role ADD VALUE 'assistant';
            END IF;
        END $$;
        """))

# aplica ajuste de enum
_ensure_pg_enums()


# =========================
# API compatível com TinyDB
# =========================
def _user_to_dict(u: User) -> Dict[str, Any]:
    """Converte User + weight_logs para o formato que o app já usa."""
    return {
        "id": str(u.id),
        "username": u.username,
        "password": u.password_hash,
        "password_hash": u.password_hash,
        "nome": u.nome,
        "objetivo": u.objetivo,
        "height_cm": u.height_cm,
        "initial_weight": u.initial_weight,
        "weight_logs": [
            {"weight": wl.weight, "recorded_at": wl.recorded_at.isoformat()}
            for wl in sorted(u.weight_logs, key=lambda x: x.recorded_at)
        ],
        "refeicoes": [],
        "chat_history": [],
        "has_access": u.has_access,
        "is_admin": u.is_admin,
        "avatar_url": u.avatar_url,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def buscar_usuario(username: str) -> Optional[Dict[str, Any]]:
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        return _user_to_dict(u) if u else None


def buscar_usuario_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as db:
        u = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        return _user_to_dict(u) if u else None


def _defaults_para_insercao(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "username": user["username"],
        "password_hash": user.get("password") or user.get("password_hash"),
        "nome": user.get("nome"),
        "objetivo": user.get("objetivo"),
        "height_cm": user.get("height_cm"),
        "initial_weight": user.get("initial_weight"),
        "has_access": bool(user.get("has_access", False)),
        "is_admin": bool(user.get("is_admin", False)),
        "avatar_url": user.get("avatar_url"),
    }


def salvar_usuario(user: Dict[str, Any]) -> None:
    if "username" not in user:
        raise ValueError("salvar_usuario: campo 'username' é obrigatório")

    with session_scope() as db:
        u = db.execute(select(User).where(User.username == user["username"])).scalar_one_or_none()
        if not u:
            u = User(**_defaults_para_insercao(user))
            db.add(u)
            db.flush()
        else:
            for k, v in _defaults_para_insercao(user).items():
                if v is not None:
                    setattr(u, k, v)

        for item in user.get("weight_logs", []) or []:
            try:
                ts = item.get("recorded_at")
                dt = datetime.fromisoformat(ts) if isinstance(ts, str) else (ts or datetime.utcnow())
                wl = WeightLog(user_id=u.id, weight=float(item["weight"]), recorded_at=dt)
                db.add(wl)
            except Exception:
                continue


async def grant_user_access(user_id: str) -> None:
    with session_scope() as db:
        u = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not u:
            raise ValueError(f"Usuário '{user_id}' não encontrado no DB")
        u.has_access = True


def salvar_chat_message(username: str, role: str, text_: str, msg_type: str = "text") -> None:
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            u = User(username=username)
            db.add(u)
            db.flush()
        msg = ChatMessage(user_id=u.id, role=role, text=text_, type=msg_type)
        db.add(msg)


def buscar_chat_history(username: str, limit: int = 10) -> List[Dict[str, Any]]:
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            return []
        rows = (
            db.execute(
                select(ChatMessage)
                .where(ChatMessage.user_id == u.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        rows = list(reversed(rows))
        return [
            {
                "username": username,
                "role": r.role,
                "text": r.text,
                "type": r.type or "text",
                "imageUrl": r.image_url,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


def salvar_meal_analysis(username: str, analise: Dict[str, Any], imagem_nome: Optional[str] = None) -> None:
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            u = User(username=username)
            db.add(u)
            db.flush()
        meal = MealAnalysis(user_id=u.id, analysis=analise, image_name=imagem_nome)
        db.add(meal)


def buscar_meal_history(username: str, limit: int = 10) -> List[Dict[str, Any]]:
    with session_scope() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not u:
            return []
        rows = (
            db.execute(
                select(MealAnalysis)
                .where(MealAnalysis.user_id == u.id)
                .order_by(MealAnalysis.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "usuario": username,
                "analise": r.analysis,
                "imagem_nome": r.image_name,
                "data": r.created_at.isoformat(),
            }
            for r in rows
        ]
