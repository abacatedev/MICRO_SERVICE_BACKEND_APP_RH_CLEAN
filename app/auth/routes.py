from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.auth import google
from app.auth.access import check_access
from app.auth.errors import OAuthError
from app.auth.token import create_code, exchange_code
from app.database import get_db
from app.models import Application, User, utcnow
from app.security import jwks, new_secret, safe_equal

router = APIRouter(tags=["auth"])


def _redirect(uri: str, **params) -> RedirectResponse:
    parts = urlsplit(uri)
    query = dict(parse_qsl(parts.query))
    query.update({k: v for k, v in params.items() if v})
    return RedirectResponse(urlunsplit(parts._replace(query=urlencode(query))), status_code=302)


@router.get("/auth/google")
def login(
    request: Request,
    client_id: str,
    redirect_uri: str,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """Passo 2: valida cliente e redirect_uri ANTES de ir ao Google."""
    app = db.scalar(select(Application).where(Application.client_id == client_id))
    if app is None or not app.is_active or redirect_uri not in (app.redirect_uris or []):
        # redirect_uri não confiável: responde aqui, sem redirecionar
        raise HTTPException(400, "invalid_client")

    google_state = new_secret()
    request.session["oauth"] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "client_state": state,
        "google_state": google_state,
    }
    return RedirectResponse(google.authorization_url(google_state), status_code=302)


@router.get("/auth/google/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """Passos 5 a 8: identidade -> acesso -> authorization code -> volta ao cliente."""
    pending = request.session.get("oauth")
    request.session.clear()  # a sessão do Auth só existe durante o login
    if not pending or not state or not safe_equal(state, pending["google_state"]):
        raise HTTPException(400, "invalid_state")

    redirect_uri, client_state = pending["redirect_uri"], pending["client_state"]

    def denied():
        return _redirect(redirect_uri, error="access_denied", state=client_state)

    if not code:
        return denied()
    try:
        profile = google.fetch_profile(code)
    except Exception:
        return denied()
    if not profile.get("email_verified") or not profile.get("email") or not profile.get("sub"):
        return denied()

    email = profile["email"].lower()
    user = db.scalar(select(User).where(User.google_id == profile["sub"]))
    if user is None:
        # pré-cadastro por e-mail: vincula o google_id no primeiro login
        user = db.scalar(select(User).where(User.email == email, User.google_id.is_(None)))
        if user is not None:
            user.google_id = profile["sub"]

    app = db.scalar(select(Application).where(Application.client_id == pending["client_id"]))
    if check_access(db, user, app) is None:
        db.rollback()
        audit.registrar(
            db, request, "login.negado", email=email, detail={"client_id": pending["client_id"]}
        )
        return denied()

    user.name = profile.get("name") or user.name
    user.last_login_at = utcnow()  # só depois do acesso confirmado
    db.commit()

    audit.registrar(
        db, request, "login.sucesso", user_id=user.id, email=user.email,
        detail={"client_id": app.client_id},
    )
    auth_code = create_code(db, user, app, redirect_uri)
    return _redirect(redirect_uri, code=auth_code, state=client_state)


@router.post("/oauth/token")
def token(
    request: Request,
    grant_type: str | None = Form(None),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Passos 9 a 12: client_id + client_secret + code -> JWT RS256."""
    if not all([grant_type, client_id, client_secret, code, redirect_uri]):
        raise OAuthError(400, "invalid_request")
    if grant_type != "authorization_code":
        raise OAuthError(400, "unsupported_grant_type")
    body = exchange_code(
        db,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
        ip=request.client.host if request.client else "",
    )
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


@router.get("/.well-known/jwks.json")
def jwks_endpoint():
    return JSONResponse(jwks(), headers={"Cache-Control": "public, max-age=3600"})
