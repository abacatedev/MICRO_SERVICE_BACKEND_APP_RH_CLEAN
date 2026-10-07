"""Auditoria: quem fez o quê, quando e de onde."""
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def registrar(
    db: Session,
    request: Request,
    action: str,
    *,
    user_id: int | None = None,
    email: str | None = None,
    target: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            user_email=email,
            action=action,
            target=str(target) if target is not None else None,
            detail=detail,
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
