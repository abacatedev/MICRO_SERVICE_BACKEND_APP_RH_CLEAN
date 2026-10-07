"""Administração do RH: usuários, perfis e auditoria."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.auth.rbac import PERMISSIONS, ROLE_PERMISSIONS, ROLES, set_user_role
from app.config import settings
from app.database import get_db
from app.models import Application, AuditLog, Role, Session as Sessao, User, UserApplication, UserRole
from app.rh import sessions
from app.rh.deps import require_permission

router = APIRouter(prefix="/rh/admin", tags=["rh-admin"])
gerenciar = require_permission("rh:usuarios:gerenciar")
EMAIL = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
Perfil = Literal["admin", "rh", "consulta"]


class UsuarioNovo(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {"email": "fulano@gmail.com", "nome": "Fulano de Tal", "role": "consulta"}
        }
    }
    email: str = Field(pattern=EMAIL, max_length=255)
    nome: str = Field(min_length=2, max_length=255)
    role: Perfil


class UsuarioAlteracao(BaseModel):
    model_config = {"json_schema_extra": {"example": {"role": "rh", "ativo": True}}}
    nome: str | None = Field(None, min_length=2, max_length=255)
    role: Perfil | None = None
    ativo: bool | None = None


def _app(db: Session) -> Application:
    return db.scalar(select(Application).where(Application.client_id == settings.rh_client_id))


def _role_slug(db: Session, user_id: int, app_id: int) -> str | None:
    return db.scalar(
        select(Role.slug)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, Role.application_id == app_id)
    )


def _saida(db: Session, user: User, link: UserApplication) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nome": user.name,
        "role": _role_slug(db, user.id, link.application_id),
        "ativo": bool(user.is_active and link.is_active),
        "ja_entrou": user.google_id is not None,
        "ultimo_login": user.last_login_at,
        "criado_em": user.created_at,
    }


def _admins_ativos(db: Session, app_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .join(User, User.id == UserRole.user_id)
        .join(
            UserApplication,
            (UserApplication.user_id == User.id) & (UserApplication.application_id == app_id),
        )
        .where(
            Role.application_id == app_id,
            Role.slug == "admin",
            User.is_active.is_(True),
            UserApplication.is_active.is_(True),
        )
    )


@router.get("/roles")
def listar_roles(_: dict = Depends(gerenciar)):
    return [
        {
            "role": slug,
            "nome": nome,
            "permissoes": [{"slug": p, "descricao": PERMISSIONS[p]} for p in ROLE_PERMISSIONS[slug]],
        }
        for slug, nome in ROLES.items()
    ]


@router.get("/usuarios")
def listar_usuarios(_: dict = Depends(gerenciar), db: Session = Depends(get_db)):
    app = _app(db)
    rows = db.execute(
        select(User, UserApplication)
        .join(UserApplication, UserApplication.user_id == User.id)
        .where(UserApplication.application_id == app.id)
        .order_by(User.name, User.email)
    ).all()
    return [_saida(db, user, link) for user, link in rows]


@router.post("/usuarios", status_code=201)
def criar_usuario(
    dados: UsuarioNovo,
    request: Request,
    admin: dict = Depends(gerenciar),
    db: Session = Depends(get_db),
):
    """Pré-cadastro: a pessoa entra com a conta Google deste e-mail."""
    if dados.role not in ROLES:
        raise HTTPException(422, f"Role inválida. Use: {', '.join(ROLES)}")
    app = _app(db)
    email = dados.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, name=dados.nome.strip())
        db.add(user)
        db.flush()
    link = db.get(UserApplication, (user.id, app.id))
    if link is not None:
        raise HTTPException(409, "Este e-mail já está cadastrado nesta aplicação")
    link = UserApplication(user_id=user.id, application_id=app.id)
    db.add(link)
    set_user_role(db, user.id, app, dados.role)
    db.commit()
    audit.registrar(
        db, request, "usuarios.criar", user_id=admin["id"], email=admin["email"],
        target=user.id, detail={"email": email, "role": dados.role},
    )
    return _saida(db, user, link)


@router.patch("/usuarios/{user_id}")
def alterar_usuario(
    user_id: int,
    dados: UsuarioAlteracao,
    request: Request,
    admin: dict = Depends(gerenciar),
    db: Session = Depends(get_db),
):
    app = _app(db)
    user = db.get(User, user_id)
    link = db.get(UserApplication, (user_id, app.id)) if user else None
    if link is None:
        raise HTTPException(404, "Usuário não encontrado nesta aplicação")
    if dados.role is not None and dados.role not in ROLES:
        raise HTTPException(422, f"Role inválida. Use: {', '.join(ROLES)}")

    role_atual = _role_slug(db, user_id, app.id)
    era_admin_ativo = role_atual == "admin" and user.is_active and link.is_active
    deixa_de_ser = (dados.ativo is False) or (dados.role is not None and dados.role != "admin")
    if era_admin_ativo and deixa_de_ser and _admins_ativos(db, app.id) <= 1:
        raise HTTPException(409, "Não é possível remover o último administrador ativo")

    mudancas: dict = {}
    if dados.nome is not None and dados.nome.strip() != user.name:
        mudancas["nome"] = [user.name, dados.nome.strip()]
        user.name = dados.nome.strip()
    if dados.role is not None and dados.role != role_atual:
        mudancas["role"] = [role_atual, dados.role]
        set_user_role(db, user_id, app, dados.role)
    if dados.ativo is not None and dados.ativo != link.is_active:
        mudancas["ativo"] = [link.is_active, dados.ativo]
        link.is_active = dados.ativo  # desativa nesta aplicação, sem apagar nada
    db.commit()
    if dados.ativo is False:
        sessions.encerrar_do_usuario(db, user_id, app.id)
    if mudancas:
        audit.registrar(
            db, request, "usuarios.alterar", user_id=admin["id"], email=admin["email"],
            target=user_id, detail=mudancas,
        )
    return _saida(db, user, link)


@router.get("/sessoes")
def listar_sessoes(
    somente_ativas: bool = True,
    usuario_id: int | None = None,
    _: dict = Depends(gerenciar),
    db: Session = Depends(get_db),
):
    app = _app(db)
    filtros = [Sessao.application_id == app.id]
    if usuario_id is not None:
        filtros.append(Sessao.user_id == usuario_id)
    rows = db.execute(
        select(Sessao, User)
        .join(User, User.id == Sessao.user_id)
        .where(*filtros)
        .order_by(Sessao.last_used_at.desc())
        .limit(500)
    ).all()
    return [
        {
            "id": s.id,
            "usuario_id": u.id,
            "usuario_email": u.email,
            "usuario_nome": u.name,
            "ativa": sessions.ativa(s),
            "criada_em": s.created_at,
            "ultimo_uso": s.last_used_at,
            "expira_em": s.expires_at,
            "encerrada_em": s.revoked_at,
            "ip": s.ip,
            "navegador": s.user_agent,
        }
        for s, u in rows
        if not somente_ativas or sessions.ativa(s)
    ]


@router.delete("/sessoes/{sessao_id}")
def encerrar_sessao(
    sessao_id: int,
    request: Request,
    admin: dict = Depends(gerenciar),
    db: Session = Depends(get_db),
):
    sess = db.get(Sessao, sessao_id)
    if sess is None or sess.application_id != _app(db).id:
        raise HTTPException(404, "Sessão não encontrada")
    sessions.encerrar(db, sess)
    audit.registrar(
        db, request, "sessoes.encerrar", user_id=admin["id"], email=admin["email"],
        target=sess.user_id, detail={"sessao_id": sessao_id},
    )
    return {"encerradas": 1}


@router.delete("/usuarios/{user_id}/sessoes")
def encerrar_sessoes_do_usuario(
    user_id: int,
    request: Request,
    admin: dict = Depends(gerenciar),
    db: Session = Depends(get_db),
):
    quantidade = sessions.encerrar_do_usuario(db, user_id, _app(db).id)
    audit.registrar(
        db, request, "sessoes.encerrar", user_id=admin["id"], email=admin["email"],
        target=user_id, detail={"todas": True, "quantidade": quantidade},
    )
    return {"encerradas": quantidade}


@router.get("/auditoria")
def listar_auditoria(
    usuario_id: int | None = None,
    acao: str | None = Query(None, description="Ex.: servidores.detalhar ou prefixo 'usuarios.'"),
    alvo: str | None = Query(None, description="REGISTRO do servidor ou id do usuário"),
    de: datetime | None = None,
    ate: datetime | None = None,
    limite: int = Query(100, ge=1, le=500),
    pagina: int = Query(1, ge=1),
    _: dict = Depends(require_permission("rh:auditoria:ler")),
    db: Session = Depends(get_db),
):
    filtros = []
    if usuario_id is not None:
        filtros.append(AuditLog.user_id == usuario_id)
    if acao:
        filtros.append(AuditLog.action.startswith(acao))
    if alvo:
        filtros.append(AuditLog.target.in_({alvo, alvo.zfill(6)}))  # aceita 3 ou 000003
    if de:
        filtros.append(AuditLog.created_at >= de)
    if ate:
        filtros.append(AuditLog.created_at <= ate)

    total = db.scalar(select(func.count()).select_from(AuditLog).where(*filtros))
    rows = db.scalars(
        select(AuditLog)
        .where(*filtros)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limite)
        .offset((pagina - 1) * limite)
    ).all()
    return {
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "itens": [
            {
                "id": r.id,
                "quando": r.created_at,
                "usuario_id": r.user_id,
                "usuario_email": r.user_email,
                "acao": r.action,
                "alvo": r.target,
                "detalhe": r.detail,
                "ip": r.ip,
            }
            for r in rows
        ],
    }
