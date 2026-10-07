"""Decisão de acesso: usuário -> aplicação -> user_application -> role ativa."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, Role, User, UserApplication, UserRole


def check_access(db: Session, user: User | None, app: Application | None) -> list[str] | None:
    """Devolve os slugs das roles ativas, ou None quando o acesso é negado."""
    if user is None or not user.is_active:
        return None
    if app is None or not app.is_active:
        return None
    link = db.get(UserApplication, (user.id, app.id))
    if link is None or not link.is_active:
        return None
    roles = db.scalars(
        select(Role.slug)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            Role.application_id == app.id,
            Role.is_active.is_(True),
        )
    ).all()
    return list(roles) or None
