"""
De onde vêm as linhas de cada relatório. Tudo somente leitura.

- Vínculos: um SELECT de TRABALHADOR com os nomes das tabelas de domínio,
  guardado em memória por DIAGNOSTICO_CACHE_MINUTES (como o diagnóstico).
  Também serve para completar as outras listas pelo REGISTRO
  (secretaria, cargo, vínculo, situação e local com código e nome).
- Diagnóstico: reaproveita app.rh.diagnostico.resultado() (o mesmo cache do painel).
- Afastamentos: reaproveita app.afastamentos.servico com conexão READ ONLY.

As linhas saem com nomes de campo iguais em todos os relatórios:
registro, matricula, contrato, nome, cpf, secretaria, secretaria_codigo, cargo, cargo_codigo,
vinculo, vinculo_codigo, situacao, situacao_codigo, subdivisao, local_trabalho...
"""
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from threading import Lock


# --------------------------------------------------------------------------- acesso ao backend
# Importações tardias: o pacote pode ser testado sem o backend.
def _settings():
    from app.config import settings
    return settings


def _firebird():
    from app.rh import firebird
    return firebird


def _diagnostico():
    from app.rh import diagnostico
    return diagnostico


def _regras():
    from app.rh import regras
    return regras


def _faixas():
    from app.rh import faixas
    return faixas


def _afastamentos():
    from app.afastamentos import servico
    return servico


@contextmanager
def _conexao_afastamentos():
    from app.afastamentos.db import conexao_somente_leitura
    with conexao_somente_leitura() as con:
        yield con


# --------------------------------------------------------------------------- conversões
def _txt(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _data(v):
    """date de datetime/date ou de texto dd/mm/aaaa (as listas do diagnóstico já vêm assim)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v.strip():
        try:
            return datetime.strptime(v.strip()[:10], "%d/%m/%Y").date()
        except ValueError:
            try:
                return date.fromisoformat(v.strip()[:10])
            except ValueError:
                return None
    return None


def _sim_nao(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    t = str(v).strip().lower()
    if t in ("sim", "s", "true", "1"):
        return True
    if t in ("não", "nao", "n", "false", "0"):
        return False
    return None


def _cod(v):
    v = _txt(v)
    return None if v is None else str(v)


# --------------------------------------------------------------------------- vínculos (cache)
SQL_VINCULOS = (
    "SELECT T.REGISTRO, T.MATRICULA, T.CONTRATO, T.NOME, T.CPF, "
    "T.SITUACAO, S.NOME AS SITUACAO_NOME, T.VINCULO, V.NOME AS VINCULO_NOME, "
    "T.CARGOATUAL, C.NOME AS CARGOATUAL_NOME, T.DIVISAO, DV.NOME AS DIVISAO_NOME, "
    "T.SUBDIVISAO, SD.NOME AS SUBDIVISAO_NOME, T.LOCAL_TRABALHO, LT.NOME AS LOCAL_TRABALHO_NOME, "
    "T.DTADMISSAO, T.DTDEMISSAO "
    "FROM TRABALHADOR T "
    "LEFT JOIN SITUACOES S ON S.CODIGO = T.SITUACAO "
    "LEFT JOIN VINCULO V ON V.EMPRESA = T.EMPRESA AND V.CODIGO = T.VINCULO "
    "LEFT JOIN CARGOS C ON C.EMPRESA = T.EMPRESA AND C.CODIGO = T.CARGOATUAL "
    "LEFT JOIN DIVISAO DV ON DV.EMPRESA = T.EMPRESA AND DV.CODIGO = T.DIVISAO "
    "LEFT JOIN SUBDIVISAO SD ON SD.EMPRESA = T.EMPRESA AND SD.CODIGO = T.SUBDIVISAO "
    "LEFT JOIN LOCAL_TRABALHO LT ON LT.EMPRESA = T.EMPRESA AND LT.CODIGO = T.LOCAL_TRABALHO "
    "WHERE T.EMPRESA = ?"
)

_cache: dict = {}
_lock = Lock()


def linha_vinculo(r: dict, ativas: set[str]) -> dict:
    situacao = _cod(r.get("SITUACAO"))
    return {
        "registro": _txt(r.get("REGISTRO")),
        "matricula": r.get("MATRICULA"),
        "contrato": r.get("CONTRATO"),
        "nome": _txt(r.get("NOME")),
        "cpf": _txt(r.get("CPF")),
        "situacao_codigo": situacao,
        "situacao": _txt(r.get("SITUACAO_NOME")),
        "ativo": situacao is not None and (situacao.lstrip("0") or "0") in ativas,
        "vinculo_codigo": _cod(r.get("VINCULO")),
        "vinculo": _txt(r.get("VINCULO_NOME")),
        "cargo_codigo": _cod(r.get("CARGOATUAL")),
        "cargo": _txt(r.get("CARGOATUAL_NOME")),
        "secretaria_codigo": _cod(r.get("DIVISAO")),
        "secretaria": _txt(r.get("DIVISAO_NOME")),
        "subdivisao_codigo": _cod(r.get("SUBDIVISAO")),
        "subdivisao": _txt(r.get("SUBDIVISAO_NOME")),
        "local_trabalho_codigo": _cod(r.get("LOCAL_TRABALHO")),
        "local_trabalho": _txt(r.get("LOCAL_TRABALHO_NOME")),
        "admissao": _data(r.get("DTADMISSAO")),
        "demissao": _data(r.get("DTDEMISSAO")),
    }


def vinculos(atualizar: bool = False) -> dict:
    """Todos os vínculos da empresa (qualquer situação), em memória por alguns minutos."""
    settings = _settings()
    with _lock:
        validade = settings.diagnostico_cache_minutes * 60
        if not atualizar and _cache and time.monotonic() - _cache["t"] < validade:
            return _cache["dados"]
        ativas = {str(s).strip().lstrip("0") or "0" for s in settings.situacoes_ativas}
        linhas = [linha_vinculo(r, ativas) for r in _firebird().query(SQL_VINCULOS, (settings.sip_empresa,))]
        dados = {"linhas": linhas, "por_registro": {l["registro"]: l for l in linhas},
                 "gerado_em": datetime.now(timezone.utc)}
        _cache.update(t=time.monotonic(), dados=dados)
        return dados


def limpar_cache() -> None:
    with _lock:
        _cache.clear()


CAMPOS_DO_VINCULO = (
    "matricula", "contrato", "nome", "cpf", "situacao_codigo", "situacao", "ativo",
    "vinculo_codigo", "vinculo", "cargo_codigo", "cargo", "secretaria_codigo", "secretaria",
    "subdivisao_codigo", "subdivisao", "local_trabalho_codigo", "local_trabalho", "admissao", "demissao",
)


def completar(linhas: list[dict], indice: dict | None = None) -> None:
    """Preenche o que faltar em cada linha com os dados do vínculo (pelo REGISTRO).
    Não sobrescreve o que a lista já trouxe."""
    if not linhas:
        return
    indice = indice if indice is not None else vinculos()["por_registro"]
    for l in linhas:
        base = indice.get(str(l.get("registro") or "").strip())
        if not base:
            continue
        for campo in CAMPOS_DO_VINCULO:
            if l.get(campo) in (None, ""):
                l[campo] = base.get(campo)


def carregar_vinculos(_: dict) -> dict:
    d = vinculos()
    return {"linhas": d["linhas"], "gerado_em": d["gerado_em"]}


# --------------------------------------------------------------------------- diagnóstico
def opcoes_regras() -> list[tuple[str, str]]:
    return [(r.codigo, f"{r.codigo} — {r.titulo}") for r in _regras().REGRAS]


def opcoes_regras_pendencia() -> list[tuple[str, str]]:
    return [(r.codigo, f"{r.codigo} — {r.titulo}") for r in _regras().REGRAS
            if r.tipo in ("erro", "alerta", "recadastro")]


COLUNAS_SERVIDOR_DIAG = ["registro", "matricula", "nome", "cpf", "secretaria", "cargo", "vinculo"]
COLUNAS_DEPENDENTE_DIAG = ["dependente", "parentesco", "nascimento", "idade", "cpf_dependente"]


def ocorrencia(o: dict) -> dict:
    return {
        "registro": _txt(o.get("REGISTRO")),
        "matricula": o.get("MATRICULA"),
        "contrato": o.get("CONTRATO"),
        "nome": _txt(o.get("SERVIDOR")),
        "cpf": _txt(o.get("CPF_SERVIDOR")),
        "admissao": _data(o.get("ADMISSAO")),
        "situacao": _txt(o.get("SITUACAO")),
        "vinculo": _txt(o.get("VINCULO")),
        "cargo": _txt(o.get("CARGO")),
        "secretaria": _txt(o.get("DIVISAO")),
        "local_trabalho": _txt(o.get("LOCAL_TRABALHO")),
        "celular": _txt(o.get("CELULAR")),
        "email": _txt(o.get("EMAIL")),
        "item": o.get("ITEM"),
        "dependente": _txt(o.get("DEPENDENTE")),
        "parentesco": _txt(o.get("PARENTESCO")),
        "nascimento": _data(o.get("NASCIMENTO")),
        "idade": o.get("IDADE"),
        "cpf_dependente": _txt(o.get("CPF_DEPENDENTE")),
        "dependente_irrf": _sim_nao(o.get("DEPENDENTE_IRRF")),
        "salario_familia": _sim_nao(o.get("SALARIO_FAMILIA")),
        "universitario": _sim_nao(o.get("UNIVERSITARIO")),
        "deficiente": _sim_nao(o.get("DEFICIENTE")),
        "documentos": _txt(o.get("DOCUMENTOS")),
        "data_entrega": _data(o.get("DATA_ENTREGA")),
        "nome_mae": _txt(o.get("NOME_MAE")),
        "detalhe": _txt(o.get("DETALHE")),
    }


def carregar_diagnostico_regra(f: dict) -> dict:
    regras = _regras()
    regra = regras.POR_CODIGO[f["regra"]]
    dados = _diagnostico().resultado()
    linhas = [ocorrencia(o) for o in dados["por_regra"][regra.codigo]]
    padrao = COLUNAS_SERVIDOR_DIAG + (COLUNAS_DEPENDENTE_DIAG if regra.alvo == "dependente" else []) + ["detalhe"]
    return {
        "linhas": linhas, "gerado_em": dados["gerado_em"], "colunas_padrao": padrao,
        "contexto": {"regra": {"codigo": regra.codigo, "titulo": regra.titulo, "tipo": regra.tipo,
                               "alvo": regra.alvo, "descricao": regra.descricao,
                               "orientacao": regra.orientacao}},
    }


SITUACAO_CADASTRAL = {"erro": "Com erro", "alerta": "Com alerta", "ok": "Sem pendência"}


def carregar_diagnostico_vinculos(f: dict) -> dict:
    """Uma linha por vínculo ativo, com a pior situação e as regras que o atingem."""
    regras = _regras()
    dados = _diagnostico().resultado()
    por_registro: dict = defaultdict(lambda: {"erro": set(), "alerta": set(), "outras": set()})
    for r in regras.REGRAS:
        grupo = "erro" if r.tipo == "erro" else "alerta" if r.tipo in ("alerta", "recadastro") else "outras"
        for o in dados["por_regra"][r.codigo]:
            por_registro[o["REGISTRO"]][grupo].add(r.codigo)

    escolhidas = set(f.get("regra") or [])
    linhas = []
    for registro, s in dados["servidores"].items():
        p = por_registro.get(registro, {"erro": set(), "alerta": set(), "outras": set()})
        todas = p["erro"] | p["alerta"]
        if escolhidas and not (todas & escolhidas):
            continue
        classe = dados["classe"].get(registro, "ok")
        linhas.append({
            "registro": _txt(registro), "matricula": s.get("MATRICULA"), "contrato": s.get("CONTRATO"),
            "nome": _txt(s.get("NOME")), "cpf": _txt(s.get("CPF")),
            "celular": _txt(s.get("CELULAR")), "email": _txt(s.get("EMAIL")),
            "secretaria_codigo": _cod(s.get("DIVISAO")), "secretaria": _txt(s.get("DIVISAO_NOME")),
            "cargo": _txt(s.get("CARGOATUAL_NOME")), "vinculo": _txt(s.get("VINCULO_NOME")),
            "situacao": _txt(s.get("SITUACAO_NOME")), "local_trabalho": _txt(s.get("LOCAL_TRABALHO_NOME")),
            "admissao": _data(s.get("DTADMISSAO")),
            "situacao_cadastral_codigo": classe,
            "situacao_cadastral": SITUACAO_CADASTRAL.get(classe, classe),
            "erros": len(p["erro"]), "alertas": len(p["alerta"]),
            "regras": ", ".join(sorted(todas)) or None,
            "dependentes": dados.get("deps_por_registro", {}).get(registro, 0),
        })
    return {"linhas": linhas, "gerado_em": dados["gerado_em"]}


def carregar_diagnostico_secretarias(_: dict) -> dict:
    diag = _diagnostico()
    r = diag.agregar_por_divisao(diag.resultado())
    def linha(d):
        return {"secretaria_codigo": d["codigo"], "secretaria": d["nome"], "vinculos": d["vinculos"],
                "com_erro": d["com_erro"], "com_alerta": d["com_alerta"], "sem_pendencia": d["sem_pendencia"],
                "dependentes": d["dependentes"], "conformidade": d["conformidade"]}
    return {"linhas": [linha(d) for d in r["divisoes"]], "totais": linha(r["total"]), "gerado_em": r["gerado_em"]}


def carregar_faixas(f: dict) -> dict:
    fx = _faixas()
    base = fx.dados()
    r = fx.montar(base["linhas"], date.today(), f.get("divisao"), f.get("subdivisao"), f.get("vinculo"))
    linhas = [{"faixa": x["faixa"], "exige_comprovacao": x["exige_comprovacao"],
               **{k: x[k] for k in ("dependentes", "irrf", "salario_familia", "universitario", "deficiente",
                                    "irrf_fora_do_limite", "salario_familia_fora_do_limite",
                                    "em_desconformidade")}} for x in r["faixas"]]
    return {"linhas": linhas, "gerado_em": base["gerado_em"],
            "totais": {"faixa": "Total", "dependentes": r["dependentes"],
                       "em_desconformidade": r["em_desconformidade"]}}


# --------------------------------------------------------------------------- afastamentos
STATUS_ESOCIAL = [("sem_status", "Sem envio"), ("invalido", "Com erro"), ("nao_enviado", "Não enviado"),
                  ("aguardando", "Aguardando retorno"), ("valido", "Válido")]
NOMES_STATUS_ESOCIAL = dict(STATUS_ESOCIAL)


def _af_linha(l: dict) -> dict:
    """Linha do módulo de afastamentos com os nomes de campo comuns."""
    l = dict(l)
    if "divisao" in l:
        l["secretaria"] = l.pop("divisao")
    if "divisao_codigo" in l:
        l["secretaria_codigo"] = _cod(l.pop("divisao_codigo"))
    if "cargo_codigo" in l:
        l["cargo_codigo"] = _cod(l["cargo_codigo"])
    if "reduzido" in l and l["reduzido"] is not None:
        l["reduzido"] = str(l["reduzido"])
    if "situacao_vinculo_nome" in l:
        l["situacao"] = l.pop("situacao_vinculo_nome")
        l.pop("situacao_vinculo", None)
    if "status_esocial" in l:
        codigo = l["status_esocial"]
        l["status_esocial_codigo"] = codigo
        l["status_esocial"] = NOMES_STATUS_ESOCIAL.get(codigo, codigo)
    return l


def _tipos_texto(lista) -> str | None:
    if not lista:
        return None
    return "; ".join(f'{x.get("reduzido")} {x.get("tipo")}'.strip() for x in lista)


def _dict_texto(d) -> str | None:
    if not d:
        return None
    return "; ".join(f"{k}: {v}" for k, v in d.items())


def _af(nome_funcao: str, transformar=None, **kwargs) -> dict:
    sv = _afastamentos()
    with _conexao_afastamentos() as con:
        r = getattr(sv, nome_funcao)(con, **kwargs)
        copia = sv.data_da_copia(con).get("data_copia")
    linhas = [_af_linha(i) for i in r.get("itens", [])]
    if transformar:
        linhas = [transformar(l) for l in linhas]
    return {"linhas": linhas, "data_referencia": r.get("data_referencia") or copia, "bruto": r}


def carregar_af_vigentes(f):
    return _af("listar_vigentes", data_ref=f.get("data_ref"))


def carregar_af_retornos(f):
    return _af("listar_retornos", dias=f.get("dias") or 30, data_ref=f.get("data_ref"))


def _longo(l):
    l["tipos_vigentes"] = _tipos_texto(l.pop("afastamentos_vigentes", None))
    return l


def carregar_af_longos(f):
    return _af("afastamentos_longos", _longo, min_dias=f.get("min_dias") or 60,
               somente_sem_remuneracao=bool(f.get("somente_sem_remuneracao")), data_ref=f.get("data_ref"))


def _acumulado(l):
    l["dias_por_tipo"] = _dict_texto(l.get("dias_por_tipo"))
    return l


def carregar_af_acumulado(f):
    r = _af("acumulado_no_ano", _acumulado, ano=f.get("ano"), min_dias=f.get("min_dias") or 1)
    r["contexto"] = {"ano": r["bruto"].get("ano"), "periodo": r["bruto"].get("periodo")}
    return r


def _recorrente(l):
    l["tipos"] = _dict_texto(l.get("tipos"))
    l.pop("lista_episodios", None)
    return l


def carregar_af_recorrentes(f):
    r = _af("recorrentes", _recorrente, ano=f.get("ano"), min_episodios=f.get("min_episodios") or 4)
    r["contexto"] = {"ano": r["bruto"].get("ano"), "legenda": r["bruto"].get("legenda"),
                     "total_por_perfil": r["bruto"].get("total_por_perfil")}
    return r




def carregar_af_esocial(f):
    kwargs = {"status": f.get("status") or ["sem_status", "invalido"]}
    if f.get("desde"):
        kwargs["desde"] = f["desde"]
    return _af("esocial_pendencias", **kwargs)


REGRAS_INCONSISTENCIA = [
    ("sobrepostos", "Afastamentos sobrepostos"),
    ("sem-tipo", "Lançamento sem tipo"),
    ("tipo-descontinuado", "Tipo antigo em aberto"),
    ("desligado-com-afastamento", "Desligado com afastamento aberto"),
]
COLUNAS_INCONSISTENCIA = {
    "sobrepostos": ["registro", "matricula", "nome", "secretaria", "a_tipo", "a_dtini", "a_dtfim",
                    "b_tipo", "b_dtini", "b_dtfim", "dias_sobrepostos"],
    "sem-tipo": ["registro", "matricula", "nome", "secretaria", "situacao", "item", "dtini", "dtfim",
                 "dt_inclusao", "status_esocial"],
    "tipo-descontinuado": ["registro", "matricula", "nome", "secretaria", "cargo", "reduzido", "tipo",
                           "dtini", "retorno_previsto"],
    "desligado-com-afastamento": ["registro", "matricula", "nome", "secretaria", "situacao", "reduzido",
                                  "tipo", "dtini", "retorno_previsto"],
}


def carregar_af_inconsistencias(f):
    regra = f["regra"]
    kwargs = {"regra": regra, "data_ref": f.get("data_ref")}
    if f.get("desde"):
        kwargs["desde"] = f["desde"]
    r = _af("inconsistencias", **kwargs)
    for l in r["linhas"]:
        for lado in ("a", "b"):
            if f"{lado}_reduzido" in l and l.get(f"{lado}_tipo"):
                l[f"{lado}_tipo"] = f'{l[f"{lado}_reduzido"]} {l[f"{lado}_tipo"]}'
    r["colunas_padrao"] = COLUNAS_INCONSISTENCIA[regra]
    r["contexto"] = {"regra": regra, "descricao": r["bruto"].get("descricao")}
    return r


def carregar_af_abate(f):
    def tirar(l):
        l["tipos"] = _tipos_texto(l.pop("afastamentos", None))
        return l
    return _af("abate_tempo", tirar, min_dias=f.get("min_dias") or 1, data_ref=f.get("data_ref"))


def carregar_af_maternidade(f):
    kwargs = {"data_ref": f.get("data_ref")}
    if f.get("desde"):
        kwargs["desde"] = f["desde"]
    return _af("maternidade_sem_dependente", **kwargs)


# agregados
def carregar_af_agrupado(f):
    r = _af("resumir_vigentes", por=f.get("por") or "tipo", data_ref=f.get("data_ref"))
    for l in r["linhas"]:
        l["codigo"] = _cod(l.get("codigo"))
    b = r["bruto"]
    r["totais"] = {"nome": "Total", "vinculos": b.get("total_vinculos"), "afastamentos": b.get("total_afastamentos")}
    return r


def carregar_af_absenteismo(f):
    r = _af("absenteismo", ano=f.get("ano"), mes=f.get("mes"), data_ref=f.get("data_ref"))
    b = r["bruto"]
    if b.get("total"):
        r["totais"] = _af_linha(b["total"])
    r["contexto"] = {"periodo": b.get("periodo"), "observacao": b.get("observacao")}
    return r


def carregar_af_serie(f):
    kwargs = {"meses": f.get("meses") or 12, "data_ref": f.get("data_ref")}
    if f.get("divisao"):
        kwargs["divisao"] = f["divisao"]
    return _af("serie_mensal", **kwargs)


PROBLEMAS_ESOCIAL = {
    "sem_motivo_configurado": "Sem motivo eSocial configurado",
    "motivo_inexistente": "Motivo configurado não existe",
    "motivo_de_desligamento_em_tipo_de_afastamento": "Motivo de desligamento num tipo de afastamento",
    "motivo_encerrado": "Motivo encerrado no eSocial",
}


def carregar_af_tipos_problema(f):
    def rotular(l):
        l["problema"] = PROBLEMAS_ESOCIAL.get(l.get("problema"), l.get("problema"))
        return l
    kwargs = {"desde": f["desde"]} if f.get("desde") else {}
    return _af("esocial_tipos_com_problema", rotular, **kwargs)
