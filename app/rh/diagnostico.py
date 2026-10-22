"""Diagnóstico cadastral: carrega o universo do SIP, aplica as regras e expõe
painel, lista nominal (JSON ou CSV) e ficha de pendências por servidor."""
import csv
import io
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import audit
from app.config import settings
from app.database import get_db
from app.rh import firebird, regras
from app.rh.deps import require_permission

router = APIRouter(prefix="/rh", tags=["rh-diagnostico"])
_cache: dict = {}
_lock = Lock()


def _universo() -> tuple[str, tuple]:
    """Filtro de situação do universo: 1 = Normal e 3 = Afastado, por padrão."""
    situacoes = settings.situacoes_ativas
    return ", ".join("?" for _ in situacoes), tuple(situacoes)


def carregar() -> tuple[list[dict], list[dict], set[str]]:
    marcas, situacoes = _universo()
    servidores = firebird.query(
        "SELECT T.REGISTRO, T.MATRICULA, T.CONTRATO, T.NOME, T.CPF, T.PIS, T.ELEITOR, "
        "T.DTNASCIMENTO, T.NOMEMAE, T.CELULAR, T.EMAIL, T.DTTERMINO, T.DTADMISSAO, T.ESTADOCIVIL, "
        "T.DIVISAO, "
        "S.NOME AS SITUACAO_NOME, V.NOME AS VINCULO_NOME, C.NOME AS CARGOATUAL_NOME, "
        "DV.NOME AS DIVISAO_NOME, LT.NOME AS LOCAL_TRABALHO_NOME, "
        "V.IDADE_IRRF_MASC, V.IDADE_IRRF_FEMI, V.IDADE_IRRF_UNIVERSITARIO, "
        "V.IDADESALFAMMASC, V.IDADESALFAMFEM "
        "FROM TRABALHADOR T "
        "LEFT JOIN SITUACOES S ON S.CODIGO = T.SITUACAO "
        "LEFT JOIN VINCULO V ON V.EMPRESA = T.EMPRESA AND V.CODIGO = T.VINCULO "
        "LEFT JOIN CARGOS C ON C.EMPRESA = T.EMPRESA AND C.CODIGO = T.CARGOATUAL "
        "LEFT JOIN DIVISAO DV ON DV.EMPRESA = T.EMPRESA AND DV.CODIGO = T.DIVISAO "
        "LEFT JOIN LOCAL_TRABALHO LT ON LT.EMPRESA = T.EMPRESA AND LT.CODIGO = T.LOCAL_TRABALHO "
        f"WHERE T.EMPRESA = ? AND T.SITUACAO IN ({marcas})",
        (settings.sip_empresa, *situacoes),
    )
    dependentes = firebird.query(
        "SELECT D.REGISTRO, D.ITEM, D.NOME, D.CPF, D.DTNASC, D.SEXO, D.PARENTESCO, "
        "TP.NOME AS PARENTESCO_NOME, D.IRRF, D.SALFAMILIA, D.UNIVERSITARIO, D.DEFICIENTE, "
        "D.FAIXA_IDADE, D.DTENTREGA, D.RG, D.PIS, D.TIPODOC, D.NUMDOC, D.NOMEMAE, "
        "D.NOMECARTORIO, D.NUMLIVRO, D.NUMREGISTRO, D.NUMFOLHA, D.MATRICULA AS CERTIDAO_MATRICULA "
        "FROM DEPENDENTES D "
        "JOIN TRABALHADOR T ON T.EMPRESA = D.EMPRESA AND T.REGISTRO = D.REGISTRO "
        "LEFT JOIN SIPREV_TIPODEPEN TP ON TP.CODIGO = D.PARENTESCO "
        f"WHERE T.EMPRESA = ? AND T.SITUACAO IN ({marcas})",
        (settings.sip_empresa, *situacoes),
    )
    fora = firebird.query(
        "SELECT DISTINCT T.CPF FROM TRABALHADOR T "
        f"WHERE T.EMPRESA = ? AND T.SITUACAO NOT IN ({marcas}) "
        "AND EXISTS (SELECT 1 FROM DEPENDENTES D "
        "WHERE D.EMPRESA = T.EMPRESA AND D.REGISTRO = T.REGISTRO)",
        (settings.sip_empresa, *situacoes),
    )
    return servidores, dependentes, {r["CPF"] for r in fora if r["CPF"]}


ORDEM_TIPO = {"erro": 0, "alerta": 1, "recadastro": 2, "conferencia": 3, "indicador": 4}


def _classificar(servidores: list[dict], por_regra: dict) -> dict[str, str]:
    """Pior situação de cada vínculo: erro, alerta (inclui recadastro) ou ok.
    Indicadores e conferências não contam como pendência."""
    classe = {s["REGISTRO"]: "ok" for s in servidores}
    for regra in regras.REGRAS:
        if regra.tipo not in ("erro", "alerta", "recadastro"):
            continue
        nivel = "erro" if regra.tipo == "erro" else "alerta"
        for o in por_regra[regra.codigo]:
            if nivel == "erro" or classe[o["REGISTRO"]] == "ok":
                classe[o["REGISTRO"]] = nivel
    return classe


def _resumo(registros, classe: dict) -> dict:
    registros = list(registros)
    com_erro = sum(1 for r in registros if classe[r] == "erro")
    com_alerta = sum(1 for r in registros if classe[r] == "alerta")
    return {
        "vinculos": len(registros),
        "com_erro": com_erro,
        "com_alerta": com_alerta,
        "sem_pendencia": len(registros) - com_erro - com_alerta,
    }


def limpar_cache() -> None:
    with _lock:
        _cache.clear()


def resultado(atualizar: bool = False) -> dict:
    """Roda o diagnóstico; o resultado fica em memória por alguns minutos."""
    with _lock:
        validade = settings.diagnostico_cache_minutes * 60
        if not atualizar and _cache and time.monotonic() - _cache["t"] < validade:
            return _cache["dados"]
        servidores, dependentes, fora = carregar()
        por_regra = regras.avaliar(servidores, dependentes, fora, date.today())
        classe = _classificar(servidores, por_regra)
        dados = {
            "classe": classe,
            "gerado_em": datetime.now(timezone.utc),
            "universo": {
                "empresa": settings.sip_empresa,
                "situacoes": settings.situacoes_ativas,
                "vinculos": len(servidores),
                "dependentes": len(dependentes),
            },
            "servidores": {s["REGISTRO"]: s for s in servidores},
            "por_regra": por_regra,
            # quantos dependentes cada vínculo tem (para os totais por secretaria)
            "deps_por_registro": Counter(d["REGISTRO"] for d in dependentes),
        }
        _cache.update(t=time.monotonic(), dados=dados)
        return dados


@router.get("/diagnostico")
def painel(
    request: Request,
    atualizar: bool = False,
    user: dict = Depends(require_permission("rh:diagnostico:painel")),
    db: Session = Depends(get_db),
):
    """Contagem por regra: quantos servidores e quantas ocorrências."""
    dados = resultado(atualizar)
    audit.registrar(db, request, "diagnostico.painel", user_id=user["id"], email=user["email"])
    return {
        "gerado_em": dados["gerado_em"],
        "universo": dados["universo"],
        "resumo": _resumo(dados["servidores"], dados["classe"]),
        "regras": sorted(
            (
                {
                    "codigo": r.codigo,
                    "titulo": r.titulo,
                    "tipo": r.tipo,
                    "alvo": r.alvo,
                    "descricao": r.descricao,
                    "orientacao": r.orientacao,
                    "servidores": len({o["REGISTRO"] for o in dados["por_regra"][r.codigo]}),
                    "ocorrencias": len(dados["por_regra"][r.codigo]),
                }
                for r in regras.REGRAS
            ),
            key=lambda x: (ORDEM_TIPO[x["tipo"]], -x["servidores"], x["codigo"]),
        ),
    }


@router.get("/diagnostico/por-divisao")
def por_divisao(
    _: dict = Depends(require_permission("rh:diagnostico:painel")),
):
    """Situação dos vínculos em cada secretaria (DIVISAO), da pior para a melhor."""
    dados = resultado()
    grupos: dict[str, list[str]] = {}
    for registro, s in dados["servidores"].items():
        grupos.setdefault(s.get("DIVISAO_NOME") or "Sem divisão", []).append(registro)
    linhas = [{"divisao": nome, **_resumo(regs, dados["classe"])} for nome, regs in grupos.items()]
    return sorted(linhas, key=lambda x: (-x["com_erro"], -x["vinculos"], x["divisao"]))


# ---------- Raio-X das Secretarias (frontend) ----------

# Cartões da tela: cada um soma uma ou mais regras e conta o vínculo uma vez só.
# Para mudar o que um cartão mostra, altere só esta lista.
CARTOES = [
    {"id": "irrf", "titulo": "IRRF acima da idade", "regras": ["D03", "D13"]},
    {"id": "salfam", "titulo": "Salário-família acima da idade", "regras": ["D04", "D14"]},
    {"id": "depCpf", "titulo": "Dependente sem CPF", "regras": ["D01"]},
    {"id": "depNasc", "titulo": "Dependente sem nascimento", "regras": ["D16"]},
    {"id": "cert", "titulo": "Certidão ausente", "regras": ["D12"], "critica": True},
    {"id": "semEmail", "titulo": "Servidor sem e-mail", "regras": ["S02"]},
    {"id": "semFone", "titulo": "Servidor sem celular", "regras": ["S01"]},
]
MINIMO_LOCAL = 3   # locais de trabalho com pelo menos 3 vínculos
MINIMO_CARGO = 5   # cargos com pelo menos 5 vínculos


def _divisao_de(servidor: dict) -> tuple[str, str]:
    codigo = str(servidor.get("DIVISAO") or "").strip()
    return (codigo or "SEM", servidor.get("DIVISAO_NOME") or "Sem divisão")


def agregar_por_divisao(dados: dict) -> dict:
    """Vínculos, dependentes, situação e contagem de cada regra e cartão, por secretaria.
    Função pura sobre o resultado do diagnóstico: só números, nenhum dado pessoal."""
    servidores = dados["servidores"]
    deps = dados.get("deps_por_registro", {})
    classe = dados["classe"]

    grupos: dict[str, dict] = {}
    for registro, s in servidores.items():
        codigo, nome = _divisao_de(s)
        grupos.setdefault(codigo, {"nome": nome, "registros": []})["registros"].append(registro)

    regs_regra = {c: {o["REGISTRO"] for o in oc} for c, oc in dados["por_regra"].items()}
    regs_cartao = {
        k["id"]: set().union(*(regs_regra.get(c, set()) for c in k["regras"])) for k in CARTOES
    }

    def linha(codigo: str, nome: str, registros: list[str]) -> dict:
        conjunto = set(registros)
        resumo = _resumo(registros, classe)
        return {
            "codigo": codigo,
            "nome": nome,
            **resumo,
            "dependentes": sum(deps.get(r, 0) for r in registros),
            "conformidade": (
                round(resumo["sem_pendencia"] / resumo["vinculos"] * 100, 1) if resumo["vinculos"] else 0.0
            ),
            "cartoes": {k: len(v & conjunto) for k, v in regs_cartao.items()},
            "regras": {c: len(v & conjunto) for c, v in regs_regra.items()},
        }

    divisoes = sorted(
        (linha(cod, g["nome"], g["registros"]) for cod, g in grupos.items()),
        key=lambda x: (-x["vinculos"], x["nome"]),
    )
    return {
        "gerado_em": dados["gerado_em"],
        "cartoes": [
            {"id": k["id"], "titulo": k["titulo"], "regras": k["regras"], "critica": k.get("critica", False)}
            for k in CARTOES
        ],
        "total": linha("ALL", "Toda a Prefeitura", list(servidores)),
        "divisoes": divisoes,
    }


def perfil_por_divisao(dados: dict) -> dict:
    """Locais de trabalho, cargos e tipos de vínculo de cada secretaria (contagens)."""
    por_div: dict[str, dict[str, Counter]] = defaultdict(
        lambda: {"locais": Counter(), "cargos": Counter(), "vinculos": Counter()}
    )
    for s in dados["servidores"].values():
        p = por_div[_divisao_de(s)[0]]
        p["locais"][s.get("LOCAL_TRABALHO_NOME") or "Local não identificado"] += 1
        p["cargos"][s.get("CARGOATUAL_NOME") or "Sem cargo"] += 1
        p["vinculos"][s.get("VINCULO_NOME") or "Sem vínculo"] += 1

    def lista(contagem: Counter, minimo: int = 1) -> list[dict]:
        return [{"nome": n, "vinculos": q} for n, q in contagem.most_common() if q >= minimo]

    return {
        "gerado_em": dados["gerado_em"],
        "minimos": {"local": MINIMO_LOCAL, "cargo": MINIMO_CARGO},
        "divisoes": {
            cod: {
                "locais": lista(p["locais"], MINIMO_LOCAL),
                "cargos": lista(p["cargos"], MINIMO_CARGO),
                "tipos_vinculo": lista(p["vinculos"]),
            }
            for cod, p in por_div.items()
        },
    }


@router.get("/diagnostico/por-divisao/regras")
def por_divisao_regras(
    atualizar: bool = False,
    _: dict = Depends(require_permission("rh:diagnostico:painel")),
):
    """Raio-X: contagem de cada regra e de cada cartão por secretaria, mais o total da Prefeitura.
    Cada regra conta o vínculo uma vez, mesmo com vários dependentes no mesmo problema."""
    return agregar_por_divisao(resultado(atualizar))


@router.get("/diagnostico/por-divisao/perfil")
def por_divisao_perfil(
    _: dict = Depends(require_permission("rh:diagnostico:painel")),
):
    """Raio-X, aba Quadro: locais (3+), cargos (5+) e tipos de vínculo de cada secretaria."""
    return perfil_por_divisao(resultado())


@router.get("/diagnostico/{codigo}")
def lista_nominal(
    codigo: str,
    request: Request,
    formato: str = Query("json", pattern="^(json|csv)$"),
    limite: int = Query(100, ge=1, le=1000),
    pagina: int = Query(1, ge=1),
    user: dict = Depends(require_permission("rh:diagnostico:listar")),
    db: Session = Depends(get_db),
):
    """Lista nominal de uma regra. Com formato=csv, baixa tudo para o Excel."""
    regra = regras.POR_CODIGO.get(codigo.upper())
    if regra is None:
        raise HTTPException(404, "Regra não encontrada")
    dados = resultado()
    ocorrencias = dados["por_regra"][regra.codigo]
    audit.registrar(
        db, request, "diagnostico.listar", user_id=user["id"], email=user["email"],
        target=regra.codigo, detail={"formato": formato, "total": len(ocorrencias)},
    )
    if formato == "csv":
        colunas = regras.COLUNAS_DEPENDENTE if regra.alvo == "dependente" else regras.COLUNAS_SERVIDOR
        saida = io.StringIO()
        escritor = csv.DictWriter(saida, fieldnames=colunas, delimiter=";", extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(ocorrencias)
        return Response(
            "\ufeff" + saida.getvalue(),  # BOM: o Excel abre com os acentos certos
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="diagnostico_{regra.codigo}.csv"'},
        )
    inicio = (pagina - 1) * limite
    return {
        "regra": {
            "codigo": regra.codigo, "titulo": regra.titulo, "tipo": regra.tipo, "alvo": regra.alvo,
            "descricao": regra.descricao, "orientacao": regra.orientacao,
        },
        "gerado_em": dados["gerado_em"],
        "total": len(ocorrencias),
        "servidores": len({o["REGISTRO"] for o in ocorrencias}),
        "pagina": pagina,
        "limite": limite,
        "itens": ocorrencias[inicio:inicio + limite],
    }


@router.get("/servidores/{registro}/pendencias")
def ficha_de_pendencias(
    registro: str,
    request: Request,
    user: dict = Depends(require_permission("rh:diagnostico:listar")),
    db: Session = Depends(get_db),
):
    """Tudo o que o diagnóstico encontrou para um vínculo ativo."""
    registro = registro.strip().zfill(6) if registro.strip().isdigit() else registro.strip()
    dados = resultado()
    servidor = dados["servidores"].get(registro)
    audit.registrar(
        db, request, "diagnostico.ficha", user_id=user["id"], email=user["email"],
        target=registro, detail={"encontrado": servidor is not None},
    )
    if servidor is None:
        raise HTTPException(404, "Registro fora do universo do diagnóstico (não é vínculo ativo)")
    pendencias = [
        {
            "codigo": r.codigo, "titulo": r.titulo, "tipo": r.tipo,
            "item": o.get("ITEM"), "dependente": o.get("DEPENDENTE"),
            "parentesco": o.get("PARENTESCO"), "idade": o.get("IDADE"), "detalhe": o.get("DETALHE"),
            "dados": {k: v for k, v in o.items() if k not in regras.COLUNAS_SERVIDOR},
        }
        for r in regras.REGRAS
        for o in dados["por_regra"][r.codigo]
        if o["REGISTRO"] == registro
    ]
    return {
        "registro": registro,
        "matricula": servidor.get("MATRICULA"),
        "contrato": servidor.get("CONTRATO"),
        "servidor": servidor.get("NOME"),
        "situacao": servidor.get("SITUACAO_NOME"),
        "vinculo": servidor.get("VINCULO_NOME"),
        "divisao": servidor.get("DIVISAO_NOME"),
        "local_trabalho": servidor.get("LOCAL_TRABALHO_NOME"),
        "gerado_em": dados["gerado_em"],
        "total": len(pendencias),
        "pendencias": pendencias,
    }
