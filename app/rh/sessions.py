"""Sessões do RH: duração máxima, limite de inatividade e encerramento."""
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session as Db

from app.config import settings
from app.models import Session, as_utc, utcnow
from app.security import new_secret, sha256_hex

TOQUE_SEGUNDOS = 60  # grava o último uso no máximo uma vez por minuto


def criar(db: Db, user_id: int, application_id: int, request: Request) -> str:
    """Cria a sessão e devolve o identificador (só o hash fica no banco)."""
    raw = new_secret()
    db.add(
        Session(
            token_hash=sha256_hex(raw),
            user_id=user_id,
            application_id=application_id,
            expires_at=utcnow() + timedelta(hours=settings.session_hours),
            ip=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
        )
    )
    db.commit()
    return raw


def ativa(sess: Session) -> bool:
    agora = utcnow()
    if sess.revoked_at is not None or as_utc(sess.expires_at) <= agora:
        return False
    limite = settings.session_idle_minutes
    if limite and agora - as_utc(sess.last_used_at) > timedelta(minutes=limite):
        return False
    return True


def validar(db: Db, raw: str | None) -> Session | None:
    if not raw:
        return None
    sess = db.scalar(select(Session).where(Session.token_hash == sha256_hex(raw)))
    return sess if sess is not None and ativa(sess) else None


def tocar(db: Db, sess: Session) -> None:
    agora = utcnow()
    if (agora - as_utc(sess.last_used_at)).total_seconds() >= TOQUE_SEGUNDOS:
        sess.last_used_at = agora
        db.commit()


def encerrar(db: Db, sess: Session) -> None:
    if sess.revoked_at is None:
        sess.revoked_at = utcnow()
        db.commit()


def encerrar_do_usuario(db: Db, user_id: int, application_id: int) -> int:
    result = db.execute(
        update(Session)
        .where(
            Session.user_id == user_id,
            Session.application_id == application_id,
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    db.commit()
    return result.rowcount
