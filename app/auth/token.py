"""Authorization Code: criação, troca por JWT e consumo de uso único."""
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import clients
from app.auth.access import check_access
from app.auth.errors import OAuthError
from app.config import settings
from app.models import Application, OAuthAuthorizationCode, User, as_utc, utcnow
from app.security import create_access_token, new_secret, safe_equal, sha256_hex


def create_code(db: Session, user: User, app: Application, redirect_uri: str) -> str:
    code = new_secret()
    db.add(
        OAuthAuthorizationCode(
            code_hash=sha256_hex(code),
            user_id=user.id,
            application_id=app.id,
            redirect_uri=redirect_uri,
            expires_at=utcnow() + timedelta(seconds=settings.auth_code_seconds),
        )
    )
    db.commit()
    return code


def exchange_code(
    db: Session, *, client_id: str, client_secret: str, code: str, redirect_uri: str, ip: str = ""
) -> dict:
    invalid_grant = OAuthError(400, "invalid_grant")

    # 1. Aplicação existe e está ativa?
    app = db.scalar(select(Application).where(Application.client_id == client_id))
    if app is None or not app.is_active or not app.client_secret_hash:
        raise OAuthError(401, "invalid_client")

    # 2. client_secret (mesmo 401 para cliente inexistente e segredo errado)
    if not safe_equal(sha256_hex(client_secret), app.client_secret_hash):
        if clients.register_failure(f"{client_id}|{ip}"):
            raise OAuthError(429, "rate_limit_exceeded")
        raise OAuthError(401, "invalid_client")

    # 3. Código: existe, é desta aplicação, redirect_uri confere, não expirou, não foi usado
    row = db.scalar(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code_hash == sha256_hex(code),
            OAuthAuthorizationCode.application_id == app.id,
        )
    )
    if row is None or row.redirect_uri != redirect_uri:
        raise invalid_grant
    if as_utc(row.expires_at) <= utcnow() or row.used_at is not None:
        raise invalid_grant

    # 4. Usuário ativo, com acesso à aplicação e role ativa (reconferido na troca)
    user = db.get(User, row.user_id)
    roles = check_access(db, user, app)
    if roles is None:
        raise invalid_grant

    # 5. Consumo atômico: só um UPDATE vence em caso de concorrência
    result = db.execute(
        update(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.id == row.id, OAuthAuthorizationCode.used_at.is_(None))
        .values(used_at=utcnow())
    )
    db.commit()
    if result.rowcount != 1:
        raise invalid_grant

    token = create_access_token(
        user_id=user.id, email=user.email, name=user.name, roles=roles, client_id=app.client_id
    )
    return {"access_token": token, "token_type": "Bearer", "expires_in": settings.access_token_seconds}
