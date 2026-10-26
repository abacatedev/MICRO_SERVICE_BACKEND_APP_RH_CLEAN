"""
Página Relatórios: catálogo, consulta e exportação. Somente leitura no SIP.

Montagem no main.py do backend:
    from app.relatorios.router import router as relatorios_router
    app.include_router(relatorios_router)

Rotas:
    GET /rh/relatorios                      catálogo (só o que o usuário pode ver)
    GET /rh/relatorios/{id}                 linhas, com busca, filtros, colunas, agrupamento e página
    GET /rh/relatorios/{id}/exportar        o mesmo resultado inteiro, em CSV ou Excel

Os filtros vão na query com o id do filtro (ex.: ?secretaria=000003&secretaria=000010&ano=2026).
Cada consulta e cada exportação fica registrada na auditoria.
"""
from datetime import date
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app import audit
from app.database import get_db
from app.rh.deps import current_user

from . import exportar as EX
from . import fontes
from .catalogo import CATALOGO, POR_ID
from .modelo import PERM_SENSIVEL
from .motor import ErroDeParametro, executar

router = APIRouter(prefix="/rh/relatorios", tags=["rh-relatorios"])

# Lista de ids para o Swagger mostrar uma caixa de seleção em {rid}
RelatorioId = Enum("RelatorioId", {r.id.replace("-", "_"): r.id for r in CATALOGO}, type=str)

RESERVADOS = {"q", "colunas", "agrupar", "ordenar", "direcao", "pagina", "por_pagina", "formato", "opcoes"}


def _relatorio(rid, user: dict):
    rel = POR_ID.get(getattr(rid, "value", rid))
    if rel is None:
        raise HTTPException(404, "Relatório não encontrado")
    if rel.permissao not in user.get("permissions", []):
        raise HTTPException(403, "Sem permissão para este relatório")
    return rel


def _filtros(request: Request) -> dict[str, list[str]]:
    brutos: dict[str, list[str]] = {}
    for chave, valor in request.query_params.multi_items():
        if chave not in RESERVADOS:
            brutos.setdefault(chave, []).append(valor)
    return brutos


def _colunas(valor: str | None) -> list[str] | None:
    if not valor:
        return None
    return [c.strip() for c in valor.split(",") if c.strip()]


def _rodar(rel, user, request, q, colunas, agrupar, ordenar, direcao, pagina, por_pagina, completo,
           com_opcoes=True):
    try:
        return executar(
            rel, user.get("permissions", []), _filtros(request), q=q, colunas=_colunas(colunas),
            agrupar=agrupar, ordenar=ordenar,
            decrescente=None if direcao is None else direcao == "desc",
            pagina=pagina, por_pagina=por_pagina, completo=completo, completar=fontes.completar,
            com_opcoes=com_opcoes,
        )
    except ErroDeParametro as erro:
        raise HTTPException(422, str(erro)) from None


def _auditar(db, request, user, acao, rel, resultado, extra: dict):
    filtros = {k: v for k, v in resultado["filtros"].items() if v not in (None, [], False)}
    audit.registrar(
        db, request, acao, user_id=user["id"], email=user["email"], target=rel.id,
        detail={"filtros": filtros, "q": resultado["q"], "agrupado": resultado["agrupado_por_pessoa"],
                "total": resultado["total"], **extra},
    )


@router.get("", summary="Catálogo de relatórios")
def catalogo(user: dict = Depends(current_user)):
    """Relatórios que o usuário pode abrir, com colunas, filtros e opções.

    Colunas sensíveis (CPF, celular, e-mail) só aparecem para quem tem `rh:servidores:detalhar`.
    """
    perms = set(user.get("permissions", []))
    sensivel = PERM_SENSIVEL in perms
    return {
        "pode_ver_dados_sensiveis": sensivel,
        "relatorios": [r.descrever(sensivel) for r in CATALOGO if r.permissao in perms],
    }


@router.get("/{rid}", summary="Consultar um relatório")
def consultar(
    rid: RelatorioId,
    request: Request,
    q: str | None = Query(None, max_length=100,
                          description="Busca por nome, matrícula, CPF, cargo ou secretaria (sem acento, CPF com ou sem pontuação)"),
    colunas: str | None = Query(None, description="Ids das colunas separados por vírgula. Em branco: as colunas padrão."),
    agrupar: bool = Query(False, description="Uma linha por pessoa (CPF), juntando os vínculos"),
    ordenar: str | None = Query(None, description="Id da coluna"),
    direcao: str | None = Query(None, pattern="^(asc|desc)$"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=500),
    opcoes: bool = Query(True, description="false: não devolve as listas de opções dos filtros"),
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Demais parâmetros da query são os filtros do relatório (veja o catálogo).

    `itens` é o resultado. `opcoes` são as listas dos filtros (valor, nome e quantas linhas
    sobram com a busca e os outros filtros), para a tela montar as caixas de seleção.
    """
    rel = _relatorio(rid, user)
    resultado = _rodar(rel, user, request, q, colunas, agrupar, ordenar, direcao, pagina, por_pagina, False,
                       com_opcoes=opcoes)
    _auditar(db, request, user, "relatorios.consultar", rel, resultado, {"pagina": pagina})
    return resultado


@router.get("/{rid}/exportar", summary="Exportar um relatório (CSV, Excel ou PDF)")
def exportar(
    rid: RelatorioId,
    request: Request,
    formato: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    q: str | None = Query(None, max_length=100),
    colunas: str | None = Query(None),
    agrupar: bool = Query(False),
    ordenar: str | None = Query(None),
    direcao: str | None = Query(None, pattern="^(asc|desc)$"),
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Exporta exatamente o que a tela mostra (mesmos filtros, busca, colunas e ordem), sem paginar."""
    rel = _relatorio(rid, user)
    resultado = _rodar(rel, user, request, q, colunas, agrupar, ordenar, direcao, 1, 1, True)  # opções: nomes dos filtros no cabeçalho
    if formato == "pdf" and resultado["total"] > EX.PDF_MAX:
        raise HTTPException(422, f"O resultado tem {resultado['total']} linhas; para PDF o máximo é "
                                 f"{EX.PDF_MAX}. Filtre mais ou exporte em Excel.")
    _auditar(db, request, user, "relatorios.exportar", rel, resultado,
             {"formato": formato, "colunas": [c["id"] for c in resultado["colunas"]]})
    nome = f"{rel.id}_{date.today().isoformat()}.{formato}"
    if formato == "xlsx":
        try:
            conteudo = EX.para_xlsx(resultado, descrever_filtros(rel, resultado))
        except RuntimeError as erro:
            raise HTTPException(501, str(erro)) from None
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif formato == "pdf":
        try:
            conteudo = EX.para_pdf(resultado, descrever_filtros(rel, resultado), user.get("email"))
        except RuntimeError as erro:
            raise HTTPException(501, str(erro)) from None
        tipo = "application/pdf"
    else:
        conteudo, tipo = EX.para_csv(resultado), "text/csv; charset=utf-8"
    return Response(conteudo, media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"',
                             "Cache-Control": "no-store"})


def descrever_filtros(rel, resultado) -> str:
    partes = []
    for f in rel.filtros:
        v = resultado["filtros"].get(f.id)
        if v in (None, [], ""):
            continue
        if isinstance(v, bool):
            v = "Sim" if v else "Não"
        elif isinstance(v, list):
            rotulos = dict(f.lista_opcoes() or [])
            opcoes = {o["valor"]: o["rotulo"] for o in resultado["opcoes"].get(f.id, [])}
            v = ", ".join(rotulos.get(x) or opcoes.get(x) or x for x in v)
        else:
            rotulos = dict(f.lista_opcoes() or [])
            v = rotulos.get(v, v)
            if isinstance(v, str) and len(v) == 10 and v[4] == "-":
                v = f"{v[8:10]}/{v[5:7]}/{v[0:4]}"
        partes.append(f"{f.rotulo}: {v}")
    if resultado.get("q"):
        partes.append(f'Busca: "{resultado["q"]}"')
    if resultado.get("agrupado_por_pessoa"):
        partes.append("Agrupado por pessoa")
    return " · ".join(partes)
