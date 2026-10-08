from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.auth.errors import OAuthError
from app.auth.token import exchange_code
from app.config import settings
from app.database import get_db
from app.models import Application, User
from app.rh import firebird, sessions
from app.rh.deps import (
    COOKIE_NAME, SESSION_COOKIE, current_user, require_permission,
    set_session_cookie, set_token_cookie,
)
from app.security import create_access_token, decode_access_token, new_secret, safe_equal

router = APIRouter(prefix="/rh", tags=["rh"])
STATE_COOKIE = "rh_state"

# Colunas devolvidas pela API. Nada fora destas listas sai do SIP.
COLUNAS_LISTA = [
    "REGISTRO", "MATRICULA", "CONTRATO", "NOME", "SITUACAO", "VINCULO", "CARGOATUAL",
    "DIVISAO", "SUBDIVISAO", "LOCAL_TRABALHO", "DTADMISSAO", "DTDEMISSAO",
]
COLUNAS_DETALHE = COLUNAS_LISTA + [
    "CPF", "SEXO", "DTNASCIMENTO", "ESTADOCIVIL", "INSTRUCAO", "NOMEMAE", "NOMEPAI",
    "CEP", "ENDERECO", "NUMERO", "BAIRRO", "COMPL", "CIDADE", "UF",
    "TELEFONE", "CELULAR", "EMAIL",
    "PIS", "RG", "RGORGAOEMISSOR", "UFRG", "DTRG", "CTPS", "SERIE", "UFCTPS",
    "CLT_OU_ESTATUTO", "HORASEMANAL", "CAT_TRAB_ESOCIAL", "STATUS_ESOCIAL", "DH_ALTEROU",
]
COLUNAS_DEPENDENTE = [
    "ITEM", "NOME", "DTNASC", "IDADE", "SEXO", "PARENTESCO", "CPF", "NOMEMAE",
    "IRRF", "SALFAMILIA", "DEFICIENTE", "UNIVERSITARIO", "DTOBITO",
    "INI_IRRF", "FIM_IRRF", "INI_SALFAM", "FIM_SALFAM",
]


def _callback_url() -> str:
    return f"{settings.base_url}/rh/callback"


def _registro(valor: str) -> str:
    """REGISTRO é texto com zeros à esquerda: 3 -> 000003."""
    valor = valor.strip()
    return valor.zfill(6) if valor.isdigit() else valor


RETORNO_COOKIE = "rh_retorno"


def _retorno_permitido(url: str | None) -> str | None:
    """Só aceita voltar para um frontend da lista CORS_ORIGINS (evita redirecionamento aberto)."""
    if not url:
        return None
    partes = urlsplit(url)
    origem = f"{partes.scheme}://{partes.netloc}"
    return url if origem in settings.origens else None


def _destino(request: Request) -> str:
    return _retorno_permitido(request.cookies.get(RETORNO_COOKIE)) or settings.frontend_url


def _negado(request: Request):
    """Com frontend configurado, volta para ele com o aviso; sem ele, responde 403."""
    destino = _destino(request)
    if destino.startswith("http"):
        sep = "&" if "?" in destino else "?"
        resp = RedirectResponse(f"{destino}{sep}acesso=negado", status_code=302)
        resp.delete_cookie(RETORNO_COOKIE)
        return resp
    raise HTTPException(403, "Acesso negado")


# ---------- login do RH (a aplicação como cliente do Auth) ----------

@router.get("/login")
def login(
    retorno: str | None = Query(
        None, description="Para onde voltar depois do login. Precisa ser um frontend de CORS_ORIGINS."
    ),
):
    if retorno and _retorno_permitido(retorno) is None:
        raise HTTPException(400, "Endereço de retorno não autorizado")
    state = new_secret()
    params = {"client_id": settings.rh_client_id, "redirect_uri": _callback_url(), "state": state}
    resp = RedirectResponse(f"/auth/google?{urlencode(params)}", status_code=302)
    resp.set_cookie(STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    if retorno:
        resp.set_cookie(RETORNO_COOKIE, retorno, max_age=600, httponly=True, samesite="lax")
    else:
        resp.delete_cookie(RETORNO_COOKIE)
    return resp


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    saved = request.cookies.get(STATE_COOKIE)
    if not saved or not state or not safe_equal(state, saved):
        raise HTTPException(400, "state inválido")
    if error or not code:
        return _negado(request)
    try:
        # mesmo processo: chama o serviço direto, sem HTTP para si mesmo
        tokens = exchange_code(
            db,
            client_id=settings.rh_client_id,
            client_secret=settings.rh_client_secret,
            code=code,
            redirect_uri=_callback_url(),
        )
    except OAuthError:
        return _negado(request)

    # Sessão longa: é ela que renova o token de 15 min sem novo login no Google
    claims = decode_access_token(tokens["access_token"], audience=settings.rh_client_id)
    rh_app = db.scalar(select(Application).where(Application.client_id == settings.rh_client_id))
    raw = sessions.criar(db, int(claims["sub"]), rh_app.id, request)

    resp = RedirectResponse(_destino(request), status_code=302)
    resp.delete_cookie(STATE_COOKIE)
    resp.delete_cookie(RETORNO_COOKIE)
    set_token_cookie(resp, tokens["access_token"])
    set_session_cookie(resp, raw)
    return resp


@router.get("/logout")
def logout(
    request: Request,
    retorno: str | None = Query(None, description="Para onde voltar depois de sair."),
    db: Session = Depends(get_db),
):
    sess = sessions.validar(db, request.cookies.get(SESSION_COOKIE))
    if sess is not None:
        sessions.encerrar(db, sess)
        user = db.get(User, sess.user_id)
        audit.registrar(
            db, request, "logout", user_id=sess.user_id, email=user.email if user else None
        )
    destino = _retorno_permitido(retorno) or (
        settings.frontend_url if settings.frontend_url.startswith("http") else "/"
    )
    resp = RedirectResponse(destino, status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.get("/me")
def me(user: dict = Depends(current_user)):
    campos = ("sub", "email", "name", "roles", "permissions", "exp", "sessao_expira_em")
    return {k: user[k] for k in campos}


@router.get("/token")
def token(response: Response, user: dict = Depends(current_user)):
    """Token de acesso (JWT RS256, 15 min) para quem está com a sessão aberta.

    Para frontends que preferem enviar `Authorization: Bearer` em vez de depender do cookie.
    Quando vencer, basta chamar esta rota de novo: a sessão emite outro.
    """
    access = create_access_token(
        user_id=user["id"], email=user["email"], name=user["name"], roles=user["roles"],
        client_id=settings.rh_client_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"access_token": access, "token_type": "Bearer", "expires_in": settings.access_token_seconds}


# ---------- dados do SIP (empresa fixa, somente leitura) ----------

# Tabelas de domínio do SIP: todas guardam a descrição na coluna NOME
JOINS_DOMINIO = (
    " LEFT JOIN SITUACOES S ON S.CODIGO = T.SITUACAO"
    " LEFT JOIN VINCULO V ON V.EMPRESA = T.EMPRESA AND V.CODIGO = T.VINCULO"
    " LEFT JOIN CARGOS C ON C.EMPRESA = T.EMPRESA AND C.CODIGO = T.CARGOATUAL"
    " LEFT JOIN DIVISAO DV ON DV.EMPRESA = T.EMPRESA AND DV.CODIGO = T.DIVISAO"
    " LEFT JOIN SUBDIVISAO SD ON SD.EMPRESA = T.EMPRESA AND SD.CODIGO = T.SUBDIVISAO"
    " LEFT JOIN LOCAL_TRABALHO LT ON LT.EMPRESA = T.EMPRESA AND LT.CODIGO = T.LOCAL_TRABALHO"
)
NOMES_DOMINIO = (
    "S.NOME AS SITUACAO_NOME, V.NOME AS VINCULO_NOME, C.NOME AS CARGOATUAL_NOME, "
    "DV.NOME AS DIVISAO_NOME, SD.NOME AS SUBDIVISAO_NOME, LT.NOME AS LOCAL_TRABALHO_NOME"
)
DOMINIOS = {  # nome na API -> (tabela, tem EMPRESA na chave?)
    "situacoes": ("SITUACOES", False),
    "parentescos": ("SIPREV_TIPODEPEN", False),
    "vinculos": ("VINCULO", True),
    "cargos": ("CARGOS", True),
    "divisoes": ("DIVISAO", True),
    "subdivisoes": ("SUBDIVISAO", True),
    "locais_trabalho": ("LOCAL_TRABALHO", True),
}


def _colunas(colunas: list[str]) -> str:
    return ", ".join(f"T.{c}" for c in colunas) + ", " + NOMES_DOMINIO


@router.get("/dominios/{nome}")
def listar_dominio(nome: str, _: dict = Depends(require_permission("rh:servidores:listar"))):
    """Códigos e nomes de uma tabela de domínio, para filtros e caixas de seleção."""
    if nome not in DOMINIOS:
        raise HTTPException(404, f"Domínio inválido. Use: {', '.join(DOMINIOS)}")
    tabela, por_empresa = DOMINIOS[nome]
    if por_empresa:
        return firebird.query(
            f"SELECT CODIGO, NOME FROM {tabela} WHERE EMPRESA = ? ORDER BY NOME",
            (settings.sip_empresa,),
        )
    return firebird.query(f"SELECT CODIGO, NOME FROM {tabela} ORDER BY CODIGO")


@router.get("/servidores")
def listar_servidores(
    request: Request,
    nome: str | None = Query(None, min_length=2, description="Trecho do nome"),
    situacao: str | None = Query(None, max_length=2, description="Código SITUACAO (1 = Normal)"),
    ativos: bool = Query(False, description="Só vínculos ativos (Normal e Afastado)"),
    limite: int = Query(50, ge=1, le=200),
    pagina: int = Query(1, ge=1),
    user: dict = Depends(require_permission("rh:servidores:listar")),
    db: Session = Depends(get_db),
):
    filtros, params = ["T.EMPRESA = ?"], [settings.sip_empresa]
    if situacao:
        filtros.append("T.SITUACAO = ?")
        params.append(situacao)
    if ativos:
        filtros.append(f"T.SITUACAO IN ({', '.join('?' for _ in settings.situacoes_ativas)})")
        params.extend(settings.situacoes_ativas)
    if nome:
        filtros.append("T.NOME CONTAINING ?")
        params.append(nome.strip())
    where = " AND ".join(filtros)

    colunas = list(COLUNAS_LISTA)
    if "rh:servidores:detalhar" in user["permissions"]:
        colunas.insert(4, "CPF")  # o perfil consulta não recebe CPF

    total = firebird.query(f"SELECT COUNT(*) AS TOTAL FROM TRABALHADOR T WHERE {where}", tuple(params))
    itens = firebird.query(
        f"SELECT FIRST {limite} SKIP {(pagina - 1) * limite} {_colunas(colunas)} "
        f"FROM TRABALHADOR T{JOINS_DOMINIO} WHERE {where} ORDER BY T.NOME, T.REGISTRO",
        tuple(params),
    )
    audit.registrar(
        db, request, "servidores.listar", user_id=user["id"], email=user["email"],
        detail={"nome": nome, "situacao": situacao, "ativos": ativos, "pagina": pagina, "limite": limite},
    )
    return {"total": total[0]["TOTAL"], "pagina": pagina, "limite": limite, "itens": itens}


@router.get("/servidores/{registro}")
def obter_servidor(
    registro: str,
    request: Request,
    user: dict = Depends(require_permission("rh:servidores:detalhar")),
    db: Session = Depends(get_db),
):
    registro = _registro(registro)
    rows = firebird.query(
        f"SELECT {_colunas(COLUNAS_DETALHE)} FROM TRABALHADOR T{JOINS_DOMINIO} "
        "WHERE T.EMPRESA = ? AND T.REGISTRO = ?",
        (settings.sip_empresa, registro),
    )
    audit.registrar(
        db, request, "servidores.detalhar", user_id=user["id"], email=user["email"],
        target=registro, detail={"encontrado": bool(rows)},
    )
    if not rows:
        raise HTTPException(404, "Servidor não encontrado")
    return rows[0]


@router.get("/servidores/{registro}/dependentes")
def listar_dependentes(
    registro: str,
    request: Request,
    user: dict = Depends(require_permission("rh:dependentes:ler")),
    db: Session = Depends(get_db),
):
    registro = _registro(registro)
    rows = firebird.query(
        f"SELECT {', '.join('D.' + c for c in COLUNAS_DEPENDENTE)}, TP.NOME AS PARENTESCO_NOME "
        "FROM DEPENDENTES D LEFT JOIN SIPREV_TIPODEPEN TP ON TP.CODIGO = D.PARENTESCO "
        "WHERE D.EMPRESA = ? AND D.REGISTRO = ? ORDER BY D.ITEM",
        (settings.sip_empresa, registro),
    )
    audit.registrar(
        db, request, "dependentes.listar", user_id=user["id"], email=user["email"],
        target=registro, detail={"quantidade": len(rows)},
    )
    return rows
