"""Testa auth, permissões, administração e auditoria sem Google e sem Firebird (SQLite)."""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/teste.db",
    SESSION_SECRET="teste",
    JWT_PRIVATE_KEY_PATH=f"{_tmp}/private.pem",
    JWT_PUBLIC_KEY_PATH=f"{_tmp}/public.pem",
    RH_CLIENT_ID="rh",
)

from scripts.gerar_chaves import gerar  # noqa: E402

gerar(_tmp)

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import clients  # noqa: E402
from app.auth.rbac import set_user_role, sync_rbac  # noqa: E402
from app.auth.token import create_code  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from datetime import timedelta  # noqa: E402

from app.models import Application, AuditLog, Session, User, UserApplication, utcnow  # noqa: E402
from app.rh import firebird, sessions  # noqa: E402
from app.security import create_access_token, sha256_hex  # noqa: E402

REDIRECT = "http://localhost:8000/rh/callback"
SECRET = "segredo-de-teste"


@pytest.fixture()
def ctx(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    clients.reset()
    db = SessionLocal()
    application = Application(
        name="RH", client_id="rh", client_secret_hash=sha256_hex(SECRET), redirect_uris=[REDIRECT]
    )
    db.add(application)
    db.flush()
    sync_rbac(db, application)

    def novo(email, role):
        user = User(email=email, name=email.split("@")[0])
        db.add(user)
        db.flush()
        db.add(UserApplication(user_id=user.id, application_id=application.id))
        set_user_role(db, user.id, application, role)
        db.commit()
        return user

    users = {r: novo(f"{r}@teste.gov.br", r) for r in ("admin", "rh", "consulta")}

    consultas = []

    def fake_query(sql, params=()):
        consultas.append((sql, params))
        if "COUNT(*)" in sql:
            return [{"TOTAL": 1}]
        return [{"REGISTRO": "000003", "NOME": "FULANA"}]

    monkeypatch.setattr(firebird, "query", fake_query)
    yield {
        "db": db, "app": application, "user": users["rh"], "users": users,
        "http": TestClient(app), "consultas": consultas,
    }
    db.close()


def auth(user):
    token = create_access_token(
        user_id=user.id, email=user.email, name=user.name, roles=[], client_id="rh"
    )
    return {"Authorization": f"Bearer {token}"}


def trocar(ctx, code, **extra):
    data = {
        "grant_type": "authorization_code", "client_id": "rh", "client_secret": SECRET,
        "code": code, "redirect_uri": REDIRECT, **extra,
    }
    return ctx["http"].post("/oauth/token", data=data)


def novo_codigo(ctx):
    return create_code(ctx["db"], ctx["user"], ctx["app"], REDIRECT)


# ---------------- fluxo OAuth ----------------

def test_fluxo_completo_e_reuso(ctx):
    code = novo_codigo(ctx)
    r = trocar(ctx, code)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    token = r.json()["access_token"]
    assert r.json()["token_type"] == "Bearer" and r.json()["expires_in"] == 900

    me = ctx["http"].get("/rh/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["roles"] == ["rh"]
    assert "rh:servidores:detalhar" in me.json()["permissions"]

    again = trocar(ctx, code)
    assert again.status_code == 400 and again.json() == {"error": "invalid_grant"}


def test_segredo_errado_e_rate_limit(ctx):
    code = novo_codigo(ctx)
    for _ in range(5):
        assert trocar(ctx, code, client_secret="errado").status_code == 401
    assert trocar(ctx, code, client_secret="errado").status_code == 429
    assert trocar(ctx, code, client_id="nao-existe").status_code == 401


def test_parametros_e_redirect(ctx):
    assert ctx["http"].post("/oauth/token", data={"client_id": "rh"}).json() == {"error": "invalid_request"}
    assert trocar(ctx, novo_codigo(ctx), redirect_uri="http://outro/cb").status_code == 400


def test_usuario_inativo_nao_troca_codigo(ctx):
    code = novo_codigo(ctx)
    ctx["user"].is_active = False
    ctx["db"].merge(ctx["user"])
    ctx["db"].commit()
    assert trocar(ctx, code).json() == {"error": "invalid_grant"}


def test_token_de_outra_audiencia_ou_invalido(ctx):
    outro = create_access_token(user_id=1, email="a@b", name="A", roles=["rh"], client_id="turismo")
    assert ctx["http"].get("/rh/me", headers={"Authorization": f"Bearer {outro}"}).status_code == 401
    assert ctx["http"].get("/rh/me").status_code == 401
    assert ctx["http"].get("/rh/servidores", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_jwks_valida_o_token(ctx):
    token = trocar(ctx, novo_codigo(ctx)).json()["access_token"]
    jwk = ctx["http"].get("/.well-known/jwks.json").json()["keys"][0]
    assert jwk["kid"] == jwt.get_unverified_header(token)["kid"]
    key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
    claims = jwt.decode(token, key, algorithms=["RS256"], audience="rh")
    assert claims["email"] == "rh@teste.gov.br" and claims["jti"]


def test_login_recusa_redirect_nao_cadastrado(ctx):
    r = ctx["http"].get(
        "/auth/google", params={"client_id": "rh", "redirect_uri": "http://mal/cb"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    ok = ctx["http"].get(
        "/auth/google", params={"client_id": "rh", "redirect_uri": REDIRECT, "state": "x"},
        follow_redirects=False,
    )
    assert ok.status_code == 302 and ok.headers["location"].startswith("https://accounts.google.com")


# ---------------- perfis e dados do SIP ----------------

def test_consulta_lista_sem_cpf_e_nao_detalha(ctx):
    h = auth(ctx["users"]["consulta"])
    r = ctx["http"].get("/rh/servidores", params={"nome": "fulana", "situacao": "1"}, headers=h)
    assert r.status_code == 200 and r.json()["total"] == 1 and r.json()["itens"][0]["NOME"] == "FULANA"
    sql, params = ctx["consultas"][-1]
    assert "CPF" not in sql and "SENHAWEB" not in sql and "*" not in sql
    assert "S.NOME AS SITUACAO_NOME" in sql and "LEFT JOIN CARGOS" in sql
    assert "T.NOME CONTAINING ?" in sql and params == ("001", "1", "fulana")
    assert ctx["http"].get("/rh/servidores/3", headers=h).status_code == 403
    assert ctx["http"].get("/rh/servidores/3/dependentes", headers=h).status_code == 403
    assert ctx["http"].get("/rh/admin/usuarios", headers=h).status_code == 403


def test_rh_detalha_com_registro_normalizado_e_gera_auditoria(ctx):
    h = auth(ctx["users"]["rh"])
    lista = ctx["http"].get("/rh/servidores", headers=h)
    assert "CPF" in ctx["consultas"][-1][0] and lista.status_code == 200
    assert ctx["http"].get("/rh/servidores/3", headers=h).status_code == 200
    sql, params = ctx["consultas"][-1]
    assert params == ("001", "000003") and "SENHAWEB" not in sql and "*" not in sql
    assert ctx["http"].get("/rh/servidores/3/dependentes", headers=h).status_code == 200
    assert ctx["http"].get("/rh/admin/auditoria", headers=h).status_code == 403

    acoes = [(a.action, a.target, a.user_email) for a in ctx["db"].query(AuditLog).order_by(AuditLog.id)]
    assert acoes == [
        ("servidores.listar", None, "rh@teste.gov.br"),
        ("servidores.detalhar", "000003", "rh@teste.gov.br"),
        ("dependentes.listar", "000003", "rh@teste.gov.br"),
    ]


# ---------------- administração ----------------

def test_admin_cadastra_altera_e_desativa(ctx):
    h = auth(ctx["users"]["admin"])
    http = ctx["http"]
    assert [r["role"] for r in http.get("/rh/admin/roles", headers=h).json()] == ["admin", "rh", "consulta"]

    novo = http.post("/rh/admin/usuarios", headers=h, json={"email": "Bia@Teste.gov.br", "nome": "Bia", "role": "consulta"})
    assert novo.status_code == 201 and novo.json()["email"] == "bia@teste.gov.br"
    assert novo.json()["ativo"] is True and novo.json()["ja_entrou"] is False
    uid = novo.json()["id"]
    assert http.post("/rh/admin/usuarios", headers=h, json={"email": "bia@teste.gov.br", "nome": "Bia", "role": "rh"}).status_code == 409
    assert http.post("/rh/admin/usuarios", headers=h, json={"email": "x@y.gov.br", "nome": "X", "role": "chefe"}).status_code == 422
    assert http.post("/rh/admin/usuarios", headers=h, json={"email": "sem-arroba", "nome": "X", "role": "rh"}).status_code == 422
    assert len(http.get("/rh/admin/usuarios", headers=h).json()) == 4

    bia = ctx["db"].get(User, uid)
    hb = auth(bia)
    assert http.get("/rh/servidores/3", headers=hb).status_code == 403
    assert http.patch(f"/rh/admin/usuarios/{uid}", headers=h, json={"role": "rh"}).json()["role"] == "rh"
    assert http.get("/rh/servidores/3", headers=hb).status_code == 200  # vale na hora, mesmo token

    assert http.patch(f"/rh/admin/usuarios/{uid}", headers=h, json={"ativo": False}).json()["ativo"] is False
    assert http.get("/rh/me", headers=hb).status_code == 403  # revogado na hora
    assert http.patch("/rh/admin/usuarios/9999", headers=h, json={"ativo": False}).status_code == 404

    log = http.get("/rh/admin/auditoria", headers=h, params={"acao": "usuarios."}).json()
    assert log["total"] == 3 and log["itens"][0]["detalhe"] == {"ativo": [True, False]}
    assert log["itens"][0]["usuario_email"] == "admin@teste.gov.br"
    por_alvo = http.get("/rh/admin/auditoria", headers=h, params={"alvo": "3"}).json()
    assert por_alvo["total"] == 1 and por_alvo["itens"][0]["acao"] == "servidores.detalhar"


def test_ultimo_admin_e_protegido(ctx):
    admin = ctx["users"]["admin"]
    h = auth(admin)
    http = ctx["http"]
    assert http.patch(f"/rh/admin/usuarios/{admin.id}", headers=h, json={"ativo": False}).status_code == 409
    assert http.patch(f"/rh/admin/usuarios/{admin.id}", headers=h, json={"role": "rh"}).status_code == 409
    outro = ctx["users"]["rh"]
    assert http.patch(f"/rh/admin/usuarios/{outro.id}", headers=h, json={"role": "admin"}).status_code == 200
    assert http.patch(f"/rh/admin/usuarios/{admin.id}", headers=h, json={"role": "rh"}).status_code == 200
    assert http.get("/rh/admin/usuarios", headers=h).status_code == 403  # deixou de ser admin


# ---------------- sessão e renovação do token ----------------

class _Req:  # o mínimo que sessions.criar usa
    client = None
    headers = {"user-agent": "pytest"}


def abrir_sessao(ctx, user):
    raw = sessions.criar(ctx["db"], user.id, ctx["app"].id, _Req())
    ctx["http"].cookies.set("rh_session", raw)
    return ctx["db"].query(Session).order_by(Session.id.desc()).first()


def test_sessao_renova_o_token_sem_google(ctx):
    http = ctx["http"]
    abrir_sessao(ctx, ctx["users"]["rh"])
    r = http.get("/rh/me")  # sem rh_token: como se os 15 min tivessem passado
    assert r.status_code == 200 and r.json()["email"] == "rh@teste.gov.br"
    assert r.json()["sessao_expira_em"] and "rh_token=" in r.headers["set-cookie"]
    claims = jwt.decode(http.cookies.get("rh_token"), options={"verify_signature": False})
    assert claims["sub"] == str(ctx["users"]["rh"].id) and claims["aud"] == "rh"

    r2 = http.get("/rh/me")  # token ainda válido: não emite outro
    assert r2.status_code == 200 and "set-cookie" not in r2.headers

    http.cookies.set("rh_token", "lixo")  # token inválido no cookie também é renovado
    assert http.get("/rh/servidores").status_code == 200


def test_sessao_expira_por_tempo_e_por_inatividade(ctx):
    http = ctx["http"]
    sess = abrir_sessao(ctx, ctx["users"]["rh"])
    assert http.get("/rh/me").status_code == 200

    sess.last_used_at = utcnow() - timedelta(minutes=31)
    ctx["db"].commit()
    r = http.get("/rh/me")
    assert r.status_code == 401 and r.json() == {"detail": "Sessão expirada"}

    sess.last_used_at = utcnow()
    sess.expires_at = utcnow() - timedelta(seconds=1)
    ctx["db"].commit()
    assert http.get("/rh/me").status_code == 401

    http.cookies.clear()
    assert http.get("/rh/me").json() == {"detail": "Não autenticado"}


def test_logout_e_encerramento_pelo_admin(ctx):
    http, admin = ctx["http"], auth(ctx["users"]["admin"])
    sess = abrir_sessao(ctx, ctx["users"]["rh"])
    assert http.get("/rh/me").status_code == 200

    outra = TestClient(app)  # o admin em outro navegador
    lista = outra.get("/rh/admin/sessoes", headers=admin).json()
    assert [s["usuario_email"] for s in lista] == ["rh@teste.gov.br"] and lista[0]["ativa"]
    assert outra.delete(f"/rh/admin/sessoes/{sess.id}", headers=admin).json() == {"encerradas": 1}
    assert http.get("/rh/me").status_code == 401  # derrubada na hora, mesmo com token válido
    assert outra.get("/rh/admin/sessoes", headers=admin).json() == []
    assert len(outra.get("/rh/admin/sessoes", headers=admin, params={"somente_ativas": False}).json()) == 1

    abrir_sessao(ctx, ctx["users"]["rh"])
    abrir_sessao(ctx, ctx["users"]["rh"])
    uid = ctx["users"]["rh"].id
    assert outra.delete(f"/rh/admin/usuarios/{uid}/sessoes", headers=admin).json() == {"encerradas": 2}

    abrir_sessao(ctx, ctx["users"]["rh"])
    assert http.get("/rh/me").status_code == 200
    assert http.get("/rh/logout", follow_redirects=False).status_code == 302
    saida = ctx["db"].query(AuditLog).filter(AuditLog.action == "logout").one()
    assert saida.user_email == "rh@teste.gov.br" and saida.user_id == uid
    http.cookies.set("rh_session", http.cookies.get("rh_session") or "x")
    assert http.get("/rh/me").status_code == 401

    abrir_sessao(ctx, ctx["users"]["rh"])
    assert outra.patch(f"/rh/admin/usuarios/{uid}", headers=admin, json={"ativo": False}).status_code == 200
    assert http.get("/rh/me").status_code == 401  # desativar também encerra as sessões


def test_callback_do_login_cria_sessao_e_cookies(ctx, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rh_client_secret", SECRET)
    http = ctx["http"]
    http.cookies.set("rh_state", "abc")
    r = http.get("/rh/callback", params={"code": novo_codigo(ctx), "state": "abc"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/rh/me"
    assert http.cookies.get("rh_token") and http.cookies.get("rh_session")
    assert ctx["db"].query(Session).count() == 1
    http.cookies.delete("rh_token")
    assert http.get("/rh/me").json()["roles"] == ["rh"]
