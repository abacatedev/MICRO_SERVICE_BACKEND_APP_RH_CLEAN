"""
Rotas do núcleo de afastamentos + eSocial.

Montagem no main.py do backend:
    from <pacote>.afastamentos.router import router as afastamentos_router
    app.include_router(afastamentos_router)
"""
from datetime import date
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from . import config as C
from . import servico as SV
from . import exportar as EX
from .db import conexao_somente_leitura
from .deps import exigir_permissao

router = APIRouter(prefix="/rh", tags=["Afastamentos (SIP, somente leitura)"])

resumo = Depends(exigir_permissao(C.PERM_RESUMO))
nominal = Depends(exigir_permissao(C.PERM_NOMINAL))
servidor = Depends(exigir_permissao(C.PERM_SERVIDOR))


def conexao():
    with conexao_somente_leitura() as con:
        yield con


DataRef = Query(None, description="Data de referência (AAAA-MM-DD). Padrão: data da cópia do SIP.")
Desde = Query(C.DESDE_PADRAO, description="Considera lançamentos com início a partir desta data.")


class Agrupamento(str, Enum):
    tipo = "tipo"
    divisao = "divisao"
    cargo = "cargo"


class StatusEsocial(str, Enum):
    valido = "valido"
    aguardando = "aguardando"
    nao_enviado = "nao_enviado"
    invalido = "invalido"
    sem_status = "sem_status"


class Relatorio(str, Enum):
    vigentes = "vigentes"
    retornos = "retornos"
    longos = "longos"
    acumulado = "acumulado"
    recorrentes = "recorrentes"
    esocial_pendencias = "esocial-pendencias"


class OrdemRecorrentes(str, Enum):
    bradford = "bradford"
    episodios = "episodios"
    dias = "dias"


class Regra(str, Enum):
    sobrepostos = "sobrepostos"
    sem_tipo = "sem-tipo"
    tipo_descontinuado = "tipo-descontinuado"
    desligado_com_afastamento = "desligado-com-afastamento"


# ---------------------------------------------------------------- referência
@router.get("/afastamentos/referencia", dependencies=[resumo],
            summary="Data da cópia do SIP usada como 'hoje' nas consultas")
def referencia(con=Depends(conexao)):
    return SV.data_da_copia(con)


# ---------------------------------------------------------------- 1) afastados
@router.get("/afastamentos/vigentes", dependencies=[nominal],
            summary="1. Afastados numa data (lista nominal)")
def vigentes(data_ref: date | None = DataRef,
             reduzido: list[int] | None = Query(None, description="Filtra por tipo (SEFIPREDUZIDO)"),
             divisao: str | None = Query(None, description="Código da divisão/secretaria"),
             cargo: str | None = Query(None, description="Código do cargo"),
             con=Depends(conexao)):
    return SV.listar_vigentes(con, data_ref, reduzido, divisao, cargo)


@router.get("/afastamentos/vigentes/resumo", dependencies=[resumo],
            summary="1. Afastados numa data (contagem por tipo, secretaria ou cargo)")
def vigentes_resumo(por: Agrupamento = Agrupamento.tipo, data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.resumir_vigentes(con, data_ref, por.value)


# ---------------------------------------------------------------- 2) retornos
@router.get("/afastamentos/retornos", dependencies=[nominal],
            summary="2. Retornos previstos nos próximos N dias")
def retornos(dias: int = Query(30, ge=1, le=180), data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.listar_retornos(con, dias, data_ref)


# ---------------------------------------------------------------- 3) histórico
@router.get("/servidores/{registro}/afastamentos", dependencies=[servidor],
            summary="3. Histórico de afastamentos do vínculo (REGISTRO)")
def historico(registro: str = Path(..., description="REGISTRO do vínculo, como no SIP (ex.: 000123)"),
              data_ref: date | None = DataRef, con=Depends(conexao)):
    resultado = SV.historico_servidor(con, registro.strip(), data_ref)
    if resultado is None:
        raise HTTPException(status_code=404, detail="REGISTRO não encontrado na empresa 001.")
    return resultado


# ---------------------------------------------------------------- 4) tempo afastado
@router.get("/afastamentos/acumulado", dependencies=[nominal],
            summary="4. Dias afastados no ano por vínculo (sem contar sobreposições duas vezes)")
def acumulado(ano: int | None = Query(None, ge=2000, le=2100), min_dias: int = Query(1, ge=1),
              data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.acumulado_no_ano(con, ano, min_dias, data_ref)


@router.get("/afastamentos/longos", dependencies=[nominal],
            summary="4. Afastados continuamente há N dias ou mais (afastamentos emendados contam juntos)")
def longos(min_dias: int = Query(C.DIAS_LONGO_PADRAO, ge=1),
           somente_sem_remuneracao: bool = False,
           data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.afastamentos_longos(con, min_dias, somente_sem_remuneracao, data_ref)


# ---------------------------------------------------------------- 5) eSocial
@router.get("/esocial/afastamentos/resumo", dependencies=[resumo],
            summary="5. Situação de envio ao eSocial por tipo de afastamento")
def esocial_resumo(desde: date = Desde, con=Depends(conexao)):
    return SV.esocial_resumo(con, desde)


@router.get("/esocial/afastamentos/tipos-com-problema", dependencies=[resumo],
            summary="5. Tipos de afastamento sem motivo eSocial válido configurado no SIP")
def esocial_tipos(desde: date = Desde, con=Depends(conexao)):
    return SV.esocial_tipos_com_problema(con, desde)


@router.get("/esocial/afastamentos/pendencias", dependencies=[nominal],
            summary="5. Lançamentos por situação de envio (padrão: inválido, não enviado, aguardando)")
def esocial_pendencias(status: list[StatusEsocial] = Query(
                           [StatusEsocial.invalido, StatusEsocial.nao_enviado, StatusEsocial.aguardando]),
                       reduzido: int | None = None, desde: date = Desde, con=Depends(conexao)):
    return SV.esocial_pendencias(con, [s.value for s in status], desde, reduzido)


# ---------------------------------------------------------------- 6) erros
@router.get("/afastamentos/inconsistencias/resumo", dependencies=[resumo],
            summary="6. Quantidade de casos por regra de erro de lançamento")
def inconsistencias_resumo(desde: date = Desde, data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.inconsistencias_resumo(con, desde, data_ref)


@router.get("/afastamentos/inconsistencias/{regra}", dependencies=[nominal],
            summary="6. Lista nominal de uma regra de erro de lançamento")
def inconsistencias(regra: Regra, desde: date = Desde, data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.inconsistencias(con, regra.value, desde, data_ref)


# ---------------------------------------------------------------- 7) tempo de serviço
@router.get("/afastamentos/abate-tempo", dependencies=[nominal],
            summary="7. Afastamentos que abatem tempo de serviço ou de contribuição, por vínculo ativo")
def abate_tempo(min_dias: int = Query(1, ge=1), data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.abate_tempo(con, min_dias, data_ref)


# ---------------------------------------------------------------- 8) dependentes
@router.get("/afastamentos/maternidade-sem-dependente", dependencies=[nominal],
            summary="8. Licença maternidade/paternidade sem filho cadastrado como dependente")
def maternidade_sem_dependente(desde: date = Desde, data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.maternidade_sem_dependente(con, desde, data_ref)


# ================================================================ FASE 2
# ---------------------------------------------------------------- linha do tempo
@router.get("/afastamentos/serie-mensal", dependencies=[resumo],
            summary="Linha do tempo: afastamentos iniciados, vínculos afastados e dias afastados por mês")
def serie_mensal(meses: int = Query(C.MESES_SERIE_PADRAO, ge=1, le=60),
                 divisao: str | None = Query(None, description="Código da divisão/secretaria"),
                 reduzido: list[int] | None = Query(None, description="Filtra por tipo (SEFIPREDUZIDO)"),
                 data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.serie_mensal(con, meses, data_ref, divisao, reduzido)


# ---------------------------------------------------------------- percentual por secretaria
@router.get("/afastamentos/absenteismo", dependencies=[resumo],
            summary="Dias afastados no mês e % de dias afastados por secretaria")
def absenteismo(ano: int | None = Query(None, ge=2000, le=2100), mes: int | None = Query(None, ge=1, le=12),
                data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.absenteismo(con, ano, mes, data_ref)


# ---------------------------------------------------------------- recorrentes
@router.get("/afastamentos/recorrentes", dependencies=[nominal],
            summary="Vínculos com N ou mais episódios de afastamento no ano, ordenados pelo fator de Bradford")
def recorrentes(ano: int | None = Query(None, ge=2000, le=2100),
                min_episodios: int = Query(C.RECORRENTES_MIN_PADRAO, ge=1),
                somente_saude: bool = True,
                ordenar: OrdemRecorrentes = Query(OrdemRecorrentes.bradford,
                                                  description="bradford (episódios² × dias), episodios ou dias"),
                data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.recorrentes(con, ano, min_episodios, somente_saude, data_ref, ordenar.value)


# ---------------------------------------------------------------- gerencial
@router.get("/afastamentos/gerencial", dependencies=[resumo],
            summary="Resumo para o gabinete: só números, sem nomes, CPF ou CID")
def gerencial(data_ref: date | None = DataRef, con=Depends(conexao)):
    return SV.gerencial(con, data_ref)


# ---------------------------------------------------------------- exportação
@router.get("/afastamentos/exportar/{relatorio}", dependencies=[nominal],
            summary="Exporta uma lista nominal em CSV (Excel em português)",
            response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def exportar(relatorio: Relatorio,
             data_ref: date | None = DataRef,
             dias: int = Query(30, ge=1, le=180, description="retornos"),
             ano: int | None = Query(None, ge=2000, le=2100, description="acumulado, recorrentes"),
             min_dias: int | None = Query(None, ge=1, description="longos, acumulado"),
             min_episodios: int = Query(C.RECORRENTES_MIN_PADRAO, ge=1, description="recorrentes"),
             desde: date = Desde, con=Depends(conexao)):
    r = relatorio.value
    if r == "vigentes":
        dados = SV.listar_vigentes(con, data_ref)
    elif r == "retornos":
        dados = SV.listar_retornos(con, dias, data_ref)
    elif r == "longos":
        dados = SV.afastamentos_longos(con, min_dias or C.DIAS_LONGO_PADRAO, False, data_ref)
    elif r == "acumulado":
        dados = SV.acumulado_no_ano(con, ano, min_dias or 1, data_ref)
    elif r == "recorrentes":
        dados = SV.recorrentes(con, ano, min_episodios, True, data_ref)
    else:
        dados = SV.esocial_pendencias(con, ["invalido", "nao_enviado", "aguardando", "sem_status"], desde)
    ref = dados.get("data_referencia") or desde
    nome = f"afastamentos_{r}_{ref:%Y-%m-%d}.csv"
    return Response(content=EX.para_csv(r, dados["itens"]), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})
