"""CORS, retorno do login por frontend, /rh/token e o contrato publicado no Swagger."""
from fastapi.routing import APIRoute

from tests.test_fluxo import SECRET, auth, ctx, novo_codigo  # noqa: F401

from app import docs
from app.main import app

FRONT = "http://localhost:3000"


def test_cors_aceita_o_frontend_com_credenciais(ctx):  # noqa: F811
    http = ctx["http"]
    pre = http.options("/rh/me", headers={"Origin": FRONT, "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == FRONT
    assert pre.headers["access-control-allow-credentials"] == "true"

    r = http.get("/rh/me", headers={"Origin": FRONT, **auth(ctx["users"]["rh"])})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == FRONT
    negado = http.get("/rh/me", headers={"Origin": FRONT})  # o 401 também precisa do cabeçalho
    assert negado.status_code == 401 and negado.headers["access-control-allow-origin"] == FRONT

    outro = http.get("/rh/me", headers={"Origin": "http://malicioso.example", **auth(ctx["users"]["rh"])})
    assert "access-control-allow-origin" not in outro.headers


def test_login_volta_para_o_frontend_que_pediu(ctx, monkeypatch):  # noqa: F811
    from app.config import settings

    monkeypatch.setattr(settings, "rh_client_secret", SECRET)
    http = ctx["http"]
    assert http.get("/rh/login", params={"retorno": "http://malicioso.example/"}, follow_redirects=False).status_code == 400

    r = http.get("/rh/login", params={"retorno": f"{FRONT}/painel"}, follow_redirects=False)
    assert r.status_code == 302 and http.cookies.get("rh_retorno")
    state = http.cookies.get("rh_state")
    volta = http.get("/rh/callback", params={"code": novo_codigo(ctx), "state": state}, follow_redirects=False)
    assert volta.status_code == 302 and volta.headers["location"] == f"{FRONT}/painel"
    assert http.cookies.get("rh_session") and not http.cookies.get("rh_retorno")

    http.cookies.set("rh_state", "abc")
    http.cookies.set("rh_retorno", f"{FRONT}/")
    negado = http.get("/rh/callback", params={"error": "access_denied", "state": "abc"}, follow_redirects=False)
    assert negado.headers["location"] == f"{FRONT}/?acesso=negado"

    sair = http.get("/rh/logout", params={"retorno": f"{FRONT}/"}, follow_redirects=False)
    assert sair.headers["location"] == f"{FRONT}/"


def test_token_a_partir_da_sessao(ctx):  # noqa: F811
    http = ctx["http"]
    assert http.get("/rh/token").status_code == 401
    r = http.get("/rh/token", headers=auth(ctx["users"]["consulta"]))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    corpo = r.json()
    assert corpo["token_type"] == "Bearer" and corpo["expires_in"] == 900
    me = http.get("/rh/me", headers={"Authorization": f"Bearer {corpo['access_token']}"}).json()
    assert me["email"] == "consulta@teste.gov.br" and me["roles"] == ["consulta"]


def _rotas(rotas):
    for r in rotas:
        if isinstance(r, APIRoute):
            yield from ((m.lower(), r.path) for m in r.methods)
        elif hasattr(r, "routes"):
            yield from _rotas(r.routes)
        elif hasattr(r, "original_router"):
            yield from _rotas(r.original_router.routes)


def test_swagger_documenta_todas_as_rotas(ctx):  # noqa: F811
    spec = ctx["http"].get("/openapi.json").json()
    publicadas = {(m, c) for c, ops in spec["paths"].items() for m in ops}
    assert publicadas == set(docs.ROTAS), publicadas ^ set(docs.ROTAS)  # nenhuma rota sem documentação
    assert len(publicadas) == 26

    for (metodo, caminho), (resumo, permissao, _) in docs.ROTAS.items():
        op = spec["paths"][caminho][metodo]
        assert op["summary"] == resumo and permissao in op["description"]

    assert set(spec["components"]["securitySchemes"]) == {"sessao", "bearer"}
    me = spec["paths"]["/rh/me"]["get"]
    assert me["security"] == [{"sessao": []}, {"bearer": []}] and "401" in me["responses"]
    assert me["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/Usuario"}
    assert "security" not in spec["paths"]["/rh/login"]["get"] and "302" in spec["paths"]["/rh/login"]["get"]["responses"]
    painel = spec["paths"]["/rh/diagnostico"]["get"]
    assert "403" in painel["responses"] and "rh:diagnostico:painel" in painel["description"]
    assert "text/csv" in spec["paths"]["/rh/diagnostico/{codigo}"]["get"]["responses"]["200"]["content"]
    lista = spec["paths"]["/rh/admin/usuarios"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert lista == {"type": "array", "items": {"$ref": "#/components/schemas/UsuarioAdmin"}}

    # toda referência aponta para um esquema que existe
    import json, re
    refs = set(re.findall(r'#/components/schemas/([A-Za-z0-9_]+)', json.dumps(spec)))
    assert refs <= set(spec["components"]["schemas"]), refs - set(spec["components"]["schemas"])
    assert ctx["http"].get("/docs").status_code == 200


def test_modelos_batem_com_as_respostas_reais(ctx, monkeypatch):  # noqa: F811
    """Os modelos do Swagger são só documentação; aqui garantimos que não mentem."""
    from tests.test_diagnostico import _preparar

    _preparar(monkeypatch)
    http, adm = ctx["http"], auth(ctx["users"]["admin"])
    pares = [
        ("/rh/me", docs.Usuario), ("/rh/token", docs.Token), ("/rh/diagnostico", docs.Painel),
        ("/rh/diagnostico/D03", docs.ListaDaRegra), ("/rh/servidores/1/pendencias", docs.Ficha),
        ("/rh/servidores", docs.ListaServidores), ("/rh/admin/auditoria", docs.Auditoria),
    ]
    for caminho, modelo in pares:
        corpo = http.get(caminho, headers=adm).json()
        assert set(modelo.model_fields) >= set(corpo), (caminho, set(corpo) - set(modelo.model_fields))
        modelo.model_validate(corpo)
    for caminho, modelo in [
        ("/rh/diagnostico/por-divisao", docs.ResumoDivisao), ("/rh/admin/roles", docs.Perfil),
        ("/rh/admin/usuarios", docs.UsuarioAdmin),
    ]:
        for item in http.get(caminho, headers=adm).json():
            assert set(modelo.model_fields) >= set(item), (caminho, set(item) - set(modelo.model_fields))
            modelo.model_validate(item)
    item = http.get("/rh/diagnostico/D03", headers=adm).json()["itens"][0]
    assert set(docs.Ocorrencia.model_fields) >= set(item), set(item) - set(docs.Ocorrencia.model_fields)
