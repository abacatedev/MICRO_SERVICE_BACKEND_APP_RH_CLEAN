"""Perfis e permissões da aplicação RH (fonte única; sincronizado com o banco)."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Application, Permission, Role, RolePermission, UserRole

ROLES = {
    "admin": "Administrador",
    "rh": "Recursos Humanos",
    "consulta": "Consulta",
}

PERMISSIONS = {
    "rh:servidores:listar": "Listar servidores (dados funcionais, sem documentos)",
    "rh:servidores:detalhar": "Ver dados pessoais e documentos do servidor",
    "rh:dependentes:ler": "Ver dependentes do servidor",
    "rh:diagnostico:painel": "Ver o painel do diagnóstico (contagens por regra)",
    "rh:diagnostico:listar": "Ver listas nominais, CSV e ficha de pendências",
    "rh:usuarios:gerenciar": "Cadastrar usuários, trocar perfil e ativar/desativar",
    "rh:auditoria:ler": "Consultar o registro de auditoria",
}

ROLE_PERMISSIONS = {
    "admin": list(PERMISSIONS),
    "rh": [
        "rh:servidores:listar", "rh:servidores:detalhar", "rh:dependentes:ler",
        "rh:diagnostico:painel", "rh:diagnostico:listar",
    ],
    "consulta": ["rh:servidores:listar", "rh:diagnostico:painel"],
}


def sync_rbac(db: Session, app: Application) -> dict[str, Role]:
    """Deixa roles, permissões e vínculos do banco iguais às tabelas acima."""
    roles: dict[str, Role] = {}
    for slug, label in ROLES.items():
        role = db.scalar(select(Role).where(Role.application_id == app.id, Role.slug == slug))
        if role is None:
            role = Role(application_id=app.id, slug=slug, name=label)
            db.add(role)
            db.flush()
        roles[slug] = role

    perms: dict[str, Permission] = {}
    for perm in db.scalars(select(Permission).where(Permission.application_id == app.id)).all():
        if perm.slug in PERMISSIONS:
            perms[perm.slug] = perm
        else:  # permissão que saiu da lista
            db.execute(delete(RolePermission).where(RolePermission.permission_id == perm.id))
            db.delete(perm)
    for slug, desc in PERMISSIONS.items():
        if slug not in perms:
            perms[slug] = Permission(application_id=app.id, slug=slug, description=desc)
            db.add(perms[slug])
    db.flush()

    for slug, role in roles.items():
        wanted = {perms[p].id for p in ROLE_PERMISSIONS[slug]}
        current = set(
            db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id))
        )
        for pid in wanted - current:
            db.add(RolePermission(role_id=role.id, permission_id=pid))
        if current - wanted:
            db.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id.in_(current - wanted),
                )
            )
    db.commit()
    return roles


def user_permissions(db: Session, user_id: int, app_id: int) -> list[str]:
    rows = db.scalars(
        select(Permission.slug)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, Role.application_id == app_id, Role.is_active.is_(True))
        .distinct()
    ).all()
    return sorted(rows)


def set_user_role(db: Session, user_id: int, app: Application, role_slug: str) -> None:
    """Um perfil por pessoa nesta aplicação: troca o que houver pelo novo."""
    app_roles = {r.slug: r for r in db.scalars(select(Role).where(Role.application_id == app.id))}
    db.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id, UserRole.role_id.in_([r.id for r in app_roles.values()])
        )
    )
    db.add(UserRole(user_id=user_id, role_id=app_roles[role_slug].id))
