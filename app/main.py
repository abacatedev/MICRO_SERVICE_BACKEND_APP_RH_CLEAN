from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from app.auth.errors import OAuthError
from app.auth.rbac import sync_rbac
from app.auth.routes import router as auth_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Application
from app.rh.admin import router as rh_admin_router
from app.rh.diagnostico import router as rh_diagnostico_router
from app.rh.routes import router as rh_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # simples por enquanto; depois, Alembic
    with SessionLocal() as db:  # perfis e permissões sempre iguais ao código
        rh_app = db.scalar(select(Application).where(Application.client_id == settings.rh_client_id))
        if rh_app is not None:
            sync_rbac(db, rh_app)
    yield


app = FastAPI(title="RH Backend + Auth Service", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="auth_session",
    max_age=600,
    same_site="lax",
    https_only=settings.base_url.startswith("https"),
)


@app.exception_handler(OAuthError)
async def oauth_error_handler(request: Request, exc: OAuthError):
    return JSONResponse(
        {"error": exc.error}, status_code=exc.status_code, headers={"Cache-Control": "no-store"}
    )


app.include_router(auth_router)
app.include_router(rh_router)
app.include_router(rh_admin_router)
app.include_router(rh_diagnostico_router)


@app.get("/", tags=["infra"])
def health():
    return {"status": "ok"}
