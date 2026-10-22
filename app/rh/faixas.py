"""Faixa etária dos dependentes dos vínculos ativos (gráfico do painel e do Raio-X).

GET /rh/indicadores/faixa-dependentes

- Só leitura no SIP: um SELECT de DEPENDENTES x TRABALHADOR (vínculos ativos da empresa),
  com os limites de idade do VINCULO. O resultado fica em memória por
  DIAGNOSTICO_CACHE_MINUTES; os filtros (secretaria, subdivisão, vínculo) são aplicados
  em cima do cache, sem nova consulta ao Firebird.
- Só números: nenhuma linha nominal sai desta rota (permissão rh:diagnostico:painel).

Desconformidade (dependente fora da condição marcada, deficientes excluídos, só parentescos
com limite de idade: filho, irmão, enteado, tutelado, neto, menor sob guarda):
- IRRF: perde a condição no ano seguinte ao que completa o limite do vínculo
  (21 anos; 24 se universitário). Ex.: nasceu em 2004, completa 21 em 2025, sai em 2026.
- Salário-família: a partir do aniversário do limite do vínculo (14 anos).
"""
import time
from datetime import date, datetime, timezone
from threading import Lock

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app import audit
from app.config import settings
from app.database import get_db
from app.rh import firebird
from app.rh.deps import require_permission

router = APIRouter(prefix="/rh/indicadores", tags=["rh-diagnostico"])

# (rótulo, idade mínima, idade máxima ou None). "Sem data" é acrescentada no fim.
FAIXAS: list[tuple[str, int, int | None]] = [
    ("0-13", 0, 13),
    ("14-17", 14, 17),
    ("18-20", 18, 20),
    ("21-23", 21, 23),
    ("24-29", 24, 29),
    ("30-39", 30, 39),
    ("40+", 40, None),
]
SEM_DATA = "Sem data"
IDADE_COMPROVACAO = 21  # a partir daqui a faixa exige comprovação (universitário, deficiência)

# Parentescos do SIPREV_TIPODEPEN que têm limite de idade (mesma lista das regras D03/D04)
COM_LIMITE_IDADE = {"03", "06", "08", "10", "15", "17"}

PADRAO_IRRF, PADRAO_UNIVERSITARIO, PADRAO_SALFAM = 21, 24, 14

_cache: dict = {}
_lock = Lock()


def _sim(valor) -> bool:
    return str(valor or "").strip().upper() == "S"


def _data(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None


def idade(nascimento, hoje: date) -> int | None:
    nascimento = _data(nascimento)
    if nascimento is None or nascimento > hoje:
        return None
    return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


def faixa_de(anos: int | None) -> str:
    if anos is None:
        return SEM_DATA
    for rotulo, minimo, maximo in FAIXAS:
        if anos >= minimo and (maximo is None or anos <= maximo):
            return rotulo
    return SEM_DATA


def _limite(valor, padrao: int) -> int:
    try:
        return int(valor) if valor is not None else padrao
    except (TypeError, ValueError):
        return padrao


def desconformidades(d: dict, hoje: date) -> tuple[bool, bool]:
    """(IRRF fora do limite, salário-família fora do limite) para um dependente."""
    nascimento = _data(d.get("DTNASC"))
    if nascimento is None or _sim(d.get("DEFICIENTE")):
        return False, False
    if str(d.get("PARENTESCO") or "").strip() not in COM_LIMITE_IDADE:
        return False, False
    feminino = str(d.get("SEXO") or "").strip().upper() == "F"

    if _sim(d.get("UNIVERSITARIO")):
        lim_irrf = _limite(d.get("IDADE_IRRF_UNIVERSITARIO"), PADRAO_UNIVERSITARIO)
    else:
        lim_irrf = _limite(d.get("IDADE_IRRF_FEMI" if feminino else "IDADE_IRRF_MASC"), PADRAO_IRRF)
    irrf_fora = _sim(d.get("IRRF")) and hoje.year > nascimento.year + lim_irrf

    lim_sf = _limite(d.get("IDADESALFAMFEM" if feminino else "IDADESALFAMMASC"), PADRAO_SALFAM)
    anos = idade(nascimento, hoje)
    salfam_fora = _sim(d.get("SALFAMILIA")) and anos is not None and anos >= lim_sf
    return irrf_fora, salfam_fora


def carregar() -> list[dict]:
    situacoes = settings.situacoes_ativas
    marcas = ", ".join("?" for _ in situacoes)
    return firebird.query(
        "SELECT T.REGISTRO, T.DIVISAO, DV.NOME AS DIVISAO_NOME, T.SUBDIVISAO, "
        "SD.NOME AS SUBDIVISAO_NOME, T.VINCULO, V.NOME AS VINCULO_NOME, "
        "V.IDADE_IRRF_MASC, V.IDADE_IRRF_FEMI, V.IDADE_IRRF_UNIVERSITARIO, "
        "V.IDADESALFAMMASC, V.IDADESALFAMFEM, "
        "D.ITEM, D.DTNASC, D.SEXO, D.PARENTESCO, D.IRRF, D.SALFAMILIA, D.UNIVERSITARIO, D.DEFICIENTE "
        "FROM DEPENDENTES D "
        "JOIN TRABALHADOR T ON T.EMPRESA = D.EMPRESA AND T.REGISTRO = D.REGISTRO "
        "LEFT JOIN VINCULO V ON V.EMPRESA = T.EMPRESA AND V.CODIGO = T.VINCULO "
        "LEFT JOIN DIVISAO DV ON DV.EMPRESA = T.EMPRESA AND DV.CODIGO = T.DIVISAO "
        "LEFT JOIN SUBDIVISAO SD ON SD.EMPRESA = T.EMPRESA AND SD.CODIGO = T.SUBDIVISAO "
        f"WHERE T.EMPRESA = ? AND T.SITUACAO IN ({marcas})",
        (settings.sip_empresa, *situacoes),
    )


def dados(atualizar: bool = False) -> dict:
    with _lock:
        validade = settings.diagnostico_cache_minutes * 60
        if not atualizar and _cache and time.monotonic() - _cache["t"] < validade:
            return _cache["dados"]
        resultado = {"linhas": carregar(), "gerado_em": datetime.now(timezone.utc)}
        _cache.update(t=time.monotonic(), dados=resultado)
        return resultado


def _confere(valor_codigo, valor_nome, filtro: str | None) -> bool:
    """Aceita o código (com ou sem zeros à esquerda) ou o nome exato, sem diferenciar maiúsculas."""
    if not filtro:
        return True
    filtro = filtro.strip()
    codigo = str(valor_codigo or "").strip()
    if codigo and (codigo == filtro or codigo.lstrip("0") == filtro.lstrip("0")):
        return True
    return str(valor_nome or "").strip().upper() == filtro.upper()


def montar(linhas: list[dict], hoje: date, divisao=None, subdivisao=None, vinculo=None) -> dict:
    rotulos = [f[0] for f in FAIXAS] + [SEM_DATA]
    contagem = {
        r: {"dependentes": 0, "irrf": 0, "salario_familia": 0, "universitario": 0, "deficiente": 0,
            "irrf_fora_do_limite": 0, "salario_familia_fora_do_limite": 0, "em_desconformidade": 0}
        for r in rotulos
    }
    registros: set[str] = set()
    for d in linhas:
        if not (_confere(d.get("DIVISAO"), d.get("DIVISAO_NOME"), divisao)
                and _confere(d.get("SUBDIVISAO"), d.get("SUBDIVISAO_NOME"), subdivisao)
                and _confere(d.get("VINCULO"), d.get("VINCULO_NOME"), vinculo)):
            continue
        registros.add(d.get("REGISTRO"))
        c = contagem[faixa_de(idade(d.get("DTNASC"), hoje))]
        c["dependentes"] += 1
        c["irrf"] += _sim(d.get("IRRF"))
        c["salario_familia"] += _sim(d.get("SALFAMILIA"))
        c["universitario"] += _sim(d.get("UNIVERSITARIO"))
        c["deficiente"] += _sim(d.get("DEFICIENTE"))
        irrf_fora, salfam_fora = desconformidades(d, hoje)
        c["irrf_fora_do_limite"] += irrf_fora
        c["salario_familia_fora_do_limite"] += salfam_fora
        c["em_desconformidade"] += irrf_fora or salfam_fora

    faixas = []
    for rotulo, minimo, maximo in FAIXAS:
        faixas.append({"faixa": rotulo, "idade_minima": minimo, "idade_maxima": maximo,
                       "exige_comprovacao": minimo >= IDADE_COMPROVACAO, **contagem[rotulo]})
    faixas.append({"faixa": SEM_DATA, "idade_minima": None, "idade_maxima": None,
                   "exige_comprovacao": True, **contagem[SEM_DATA]})
    return {
        "filtros": {"divisao": divisao, "subdivisao": subdivisao, "vinculo": vinculo},
        "vinculos_com_dependentes": len(registros),
        "dependentes": sum(f["dependentes"] for f in faixas),
        "em_desconformidade": sum(f["em_desconformidade"] for f in faixas),
        "sem_data": contagem[SEM_DATA]["dependentes"],
        "faixas": faixas,
    }


@router.get("/faixa-dependentes")
def faixa_dependentes(
    request: Request,
    divisao: str | None = Query(None, description="Secretaria: código (000003 ou 3) ou nome exato"),
    subdivisao: str | None = Query(None, description="Subdivisão: código ou nome exato"),
    vinculo: str | None = Query(None, description="Vínculo: código ou nome exato"),
    atualizar: bool = Query(False, description="true relê o SIP agora"),
    user: dict = Depends(require_permission("rh:diagnostico:painel")),
    db: Session = Depends(get_db),
):
    """Dependentes dos vínculos ativos por faixa etária, com as marcações de IRRF e
    salário-família e quantos estão fora do limite de idade do vínculo."""
    base = dados(atualizar)
    resposta = montar(base["linhas"], date.today(), divisao, subdivisao, vinculo)
    audit.registrar(db, request, "diagnostico.faixas", user_id=user["id"], email=user["email"],
                    detail={k: v for k, v in resposta["filtros"].items() if v})
    return {"gerado_em": base["gerado_em"], **resposta}
