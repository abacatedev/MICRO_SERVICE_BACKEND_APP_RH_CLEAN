"""Cria a aplicação RH (na primeira vez) e cadastra um usuário pela linha de comando.

Uso: python -m scripts.seed email@dominio "Nome da Pessoa" [role]
Roles: admin (padrão), rh, consulta. Depois do primeiro admin, o cadastro
do dia a dia é feito pelas rotas /rh/admin/usuarios.
"""
import sys

from sqlalchemy import select

from app.auth.rbac import ROLES, set_user_role, sync_rbac
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Application, User, UserApplication
from app.security import new_secret, sha256_hex


def main(email: str, name: str, role_slug: str = "admin") -> None:
    if role_slug not in ROLES:
        sys.exit(f"Role inválida: {role_slug}. Use: {', '.join(ROLES)}")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        app = db.scalar(select(Application).where(Application.client_id == settings.rh_client_id))
        if app is None:
            secret = new_secret()
            app = Application(
                name="RH",
                client_id=settings.rh_client_id,
                client_secret_hash=sha256_hex(secret),
                redirect_uris=[f"{settings.base_url}/rh/callback"],
            )
            db.add(app)
            db.flush()
            print("Aplicação criada. Guarde no .env (mostrado uma única vez):")
            print(f"RH_CLIENT_SECRET={secret}")
        sync_rbac(db, app)

        email = email.strip().lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name=name)
            db.add(user)
            db.flush()
        if db.get(UserApplication, (user.id, app.id)) is None:
            db.add(UserApplication(user_id=user.id, application_id=app.id))
        set_user_role(db, user.id, app, role_slug)
        db.commit()
    print(f"Usuário {email} com a role '{role_slug}' na aplicação '{settings.rh_client_id}'.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
