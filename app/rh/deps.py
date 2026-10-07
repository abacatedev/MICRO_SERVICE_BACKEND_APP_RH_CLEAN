"""Proteção das rotas do RH.

Navegador: cookie de sessão (8 h) + JWT RS256 (15 min) renovado automaticamente.
Clientes de API: header Authorization: Bearer com o JWT.
Em ambos, acesso e permissões são conferidos no banco a cada requisição.
"""
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import check_access
from app.auth.rbac import user_permissions
from app.config import settings
from app.database import get_db
from app.models import Application, User, as_utc, utcnow
from app.rh import sessions
from app.security import create_access_token, decode_access_token

COOKIE_NAME = "rh_token"
SESSION_COOKIE = "rh_session"


def _secure() -> bool:
    return settings.base_url.startswith("https")


def set_token_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=settings.access_token_seconds,
        httponly=True, samesite="lax", secure=_secure(),
    )


def set_session_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, raw, max_age=settings.session_hours * 3600,
        httponly=True, samesite="lax", secure=_secure(),
    )


def _claims(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return decode_access_token(token, audience=settings.rh_client_id)
    except jwt.PyJWTError:
        return None


def current_user(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    app = db.scalar(select(Application).where(Application.client_id == settings.rh_client_id))
    header = request.headers.get("authorization", "")
    sess = None

    if header.lower().startswith("bearer "):
        claims = _claims(header[7:])
        if claims is None:
            raise HTTPException(401, "Token inválido ou expirado")
        user_id = int(claims["sub"]) if claims["sub"].isdigit() else 0
    else:
        raw = request.cookies.get(SESSION_COOKIE)
        sess = sessions.validar(db, raw)
        if sess is None or app is None or sess.application_id != app.id:
            raise HTTPException(401, "Sessão expirada" if raw else "Não autenticado")
        user_id = sess.user_id
        claims = _claims(request.cookies.get(COOKIE_NAME))
        if claims is not None and claims["sub"] != str(user_id):
            claims = None

    user = db.get(User, user_id)
    roles = check_access(db, user, app)
    if roles is None:
        if sess is not None:
            sessions.encerrar(db, sess)
        raise HTTPException(403, "Acesso revogado")

    if sess is not None:
        if claims is None:  # JWT venceu: emite outro sem passar pelo Google
            token = create_access_token(
                user_id=user.id, email=user.email, name=user.name, roles=roles,
                client_id=app.client_id,
            )
            set_token_cookie(response, token)
            exp = int((utcnow() + timedelta(seconds=settings.access_token_seconds)).timestamp())
        else:
            exp = claims["exp"]
        sessions.tocar(db, sess)
    else:
        exp = claims["exp"]

    return {
        "id": user.id,
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "roles": roles,
        "permissions": user_permissions(db, user.id, app.id),
        "exp": exp,
        "sessao_expira_em": as_utc(sess.expires_at) if sess is not None else None,
    }


def require_permission(slug: str):
    def dependency(user: dict = Depends(current_user)) -> dict:
        if slug not in user["permissions"]:
            raise HTTPException(403, "Sem permissão")
        return user

    return dependency
