"""
Regras do núcleo de afastamentos + eSocial.

Cada função recebe uma conexão aberta (somente leitura) e devolve dados
prontos para a API. Nada aqui altera o SIP.
"""
import os
import time
from collections import defaultdict
from datetime import date, timedelta

from . import calculos as K
from . import config as C
from . import sql as S
from .db import consultar

# --------------------------------------------------------------------------
# Data de referência (a cópia do banco não é "hoje")
# --------------------------------------------------------------------------
_cache_ref: dict = {}


def data_da_copia(con) -> dict:
    """Data da cópia do SIP = maior DT_INCLUSAO em MOVTOSEFIP (cache de 10 min).

    Pode ser fixada com a variável SIP_DATA_COPIA=AAAA-MM-DD no .env.
    """
    fixa = os.getenv("SIP_DATA_COPIA")
    if fixa:
        return {"data_copia": date.fromisoformat(fixa), "origem": "SIP_DATA_COPIA", "ultimo_dtini": None}
    if _cache_ref and time.time() - _cache_ref["em"] < 600:
        return _cache_ref["valor"]
    linha = consultar(con, S.DATA_REFERENCIA, (C.EMPRESA,))[0]
    valor = {"data_copia": linha["data_copia"], "origem": "MAX(MOVTOSEFIP.DT_INCLUSAO)",
             "ultimo_dtini": linha["ultimo_dtini"]}
    _cache_ref.update(em=time.time(), valor=valor)
    return valor


def resolver_ref(con, data_ref: date | None) -> date:
    return data_ref or data_da_copia(con)["data_copia"] or date.today()


# --------------------------------------------------------------------------
# Apoio
# --------------------------------------------------------------------------
def _enriquecer(l: dict) -> dict:
    """Acrescenta campos calculados a uma linha de afastamento."""
    l["situacao_vinculo_nome"] = C.NOMES_SITUACAO.get(l.get("situacao_vinculo"))
    l["duracao_dias"] = K.duracao_dias(l.get("dtini"), l.get("dtfim"))
    l["retorno_previsto"] = K.fim_exclusivo(l.get("dtfim"))
    l["sem_remuneracao"] = str(l.get("causa") or "") == C.CAUSA_SEM_REMUNERACAO
    l["status_esocial"] = K.nome_status(l.get("status_esocial"))
    return l


def _resposta(ref: date | None, itens: list, **extra) -> dict:
    corpo = {"data_referencia": ref, "total": len(itens)}
    corpo.update(extra)
    corpo["itens"] = itens
    return corpo


def _filtrar(itens, reduzido=None, divisao=None, cargo=None):
    if reduzido:
        itens = [i for i in itens if i["reduzido"] in reduzido]
    if divisao is not None:
        itens = [i for i in itens if str(i.get("divisao_codigo")) == str(divisao)]
    if cargo is not None:
        itens = [i for i in itens if str(i.get("cargo_codigo")) == str(cargo)]
    return itens


# --------------------------------------------------------------------------
# 1) Afastados numa data
# --------------------------------------------------------------------------
def listar_vigentes(con, data_ref=None, reduzido=None, divisao=None, cargo=None) -> dict:
    ref = resolver_ref(con, data_ref)
    linhas = consultar(con, S.VIGENTES, (C.EMPRESA, ref, K.param_ainda_afastado(ref)))
    itens = [_enriquecer(l) for l in _filtrar(linhas, reduzido, divisao, cargo)]
    itens.sort(key=lambda i: (i.get("divisao") or "", i.get("nome") or ""))
    return _resposta(ref, itens, vinculos=len({i["registro"] for i in itens}))


def resumir_vigentes(con, data_ref=None, por: str = "tipo") -> dict:
    """Contagem de vínculos afastados agrupada por tipo, divisão ou cargo."""
    base = listar_vigentes(con, data_ref)
    campo_cod, campo_nome = {
        "tipo": ("reduzido", "tipo"),
        "divisao": ("divisao_codigo", "divisao"),
        "cargo": ("cargo_codigo", "cargo"),
    }[por]
    grupos: dict = {}
    for i in base["itens"]:
        g = grupos.setdefault(i.get(campo_cod), {"codigo": i.get(campo_cod), "nome": i.get(campo_nome),
                                                 "vinculos": set(), "afastamentos": 0})
        g["vinculos"].add(i["registro"])
        g["afastamentos"] += 1
    itens = [{**g, "vinculos": len(g["vinculos"])} for g in grupos.values()]
    itens.sort(key=lambda g: -g["vinculos"])
    return {"data_referencia": base["data_referencia"], "agrupado_por": por,
            "total_vinculos": base["vinculos"], "total_afastamentos": base["total"], "itens": itens}


# --------------------------------------------------------------------------
# 2) Retornos previstos
# --------------------------------------------------------------------------
def listar_retornos(con, dias: int = 30, data_ref=None) -> dict:
    ref = resolver_ref(con, data_ref)
    ate = ref + timedelta(days=dias)
    # retorno = fim_exclusivo(DTFIM) <= ate
    limite_dtfim = ate if C.DTFIM_E_DIA_DO_RETORNO else ate - timedelta(days=1)
    linhas = consultar(con, S.RETORNOS, (C.EMPRESA, ref, K.param_ainda_afastado(ref), limite_dtfim))
    itens = []
    for l in linhas:
        l = _enriquecer(l)
        l["emenda_outro_afastamento"] = bool(l.pop("emenda_outro", 0))
        l["dias_ate_retorno"] = (l["retorno_previsto"] - ref).days
        itens.append(l)
    itens.sort(key=lambda i: (i["retorno_previsto"], i.get("nome") or ""))
    return _resposta(ref, itens, ate=ate)


# --------------------------------------------------------------------------
# 3) Histórico do servidor
# --------------------------------------------------------------------------
def historico_servidor(con, registro: str, data_ref=None) -> dict | None:
    servidor = consultar(con, S.SERVIDOR, (C.EMPRESA, registro))
    if not servidor:
        return None
    ref = resolver_ref(con, data_ref)
    serv = servidor[0]
    serv["situacao_vinculo_nome"] = C.NOMES_SITUACAO.get(serv.get("situacao_vinculo"))

    lancamentos = []
    for l in consultar(con, S.HISTORICO, (C.EMPRESA, registro)):
        l["temporario"] = bool(l["temporario"])
        l["duracao_dias"] = K.duracao_dias(l["dtini"], l["dtfim"])
        l["retorno_previsto"] = K.fim_exclusivo(l["dtfim"]) if l["temporario"] else None
        l["vigente"] = bool(l["temporario"] and l["dtini"] <= ref
                            and (l["dtfim"] is None or l["dtfim"] > K.param_ainda_afastado(ref)))
        l["status_esocial"] = K.nome_status(l["status_esocial"])
        lancamentos.append(l)

    temporarios = [(l["dtini"], l["dtfim"]) for l in lancamentos if l["temporario"]]
    ano = ref.year
    resumo = {
        "afastado_na_data": any(l["vigente"] for l in lancamentos),
        "afastado_continuamente_desde": K.inicio_bloco_continuo(temporarios, ref),
        "dias_afastado_no_ano": K.dias_no_periodo(temporarios, date(ano, 1, 1), ref + timedelta(days=1)),
        "total_lancamentos": len(lancamentos),
        "total_afastamentos_temporarios": len(temporarios),
    }
    return {"data_referencia": ref, "servidor": serv, "resumo": resumo, "lancamentos": lancamentos}


# --------------------------------------------------------------------------
# 4a) Dias afastados no ano
# --------------------------------------------------------------------------
def acumulado_no_ano(con, ano: int | None = None, min_dias: int = 1, data_ref=None) -> dict:
    ref = resolver_ref(con, data_ref)
    ano = ano or ref.year
    inicio, fim_ano = date(ano, 1, 1), date(ano + 1, 1, 1)
    fim = min(fim_ano, ref + timedelta(days=1))
    if fim <= inicio:
        return _resposta(ref, [], ano=ano)

    linhas = consultar(con, S.NO_ANO, (C.EMPRESA, fim, K.param_ainda_afastado(inicio)))
    por_registro: dict = defaultdict(list)
    for l in linhas:
        por_registro[l["registro"]].append(l)

    itens = []
    for registro, ls in por_registro.items():
        periodos = [(l["dtini"], l["dtfim"]) for l in ls]
        dias = K.dias_no_periodo(periodos, inicio, fim)
        if dias < min_dias:
            continue
        por_tipo: dict = defaultdict(int)
        for l in ls:
            por_tipo[f'{l["reduzido"]} {l["tipo"]}'] += K.dias_no_periodo([(l["dtini"], l["dtfim"])], inicio, fim)
        p = ls[0]
        itens.append({
            "registro": registro, "matricula": p["matricula"], "nome": p["nome"], "cpf": p["cpf"],
            "divisao": p["divisao"], "cargo": p["cargo"],
            "dias_afastado": dias, "afastamentos": len(ls),
            "dias_por_tipo": dict(sorted(por_tipo.items(), key=lambda x: -x[1])),
        })
    itens.sort(key=lambda i: -i["dias_afastado"])
    return _resposta(ref, itens, ano=ano, periodo={"inicio": inicio, "ate": fim - timedelta(days=1)})


# --------------------------------------------------------------------------
# 4b) Afastamentos longos (contínuos)
# --------------------------------------------------------------------------
def afastamentos_longos(con, min_dias: int = C.DIAS_LONGO_PADRAO, somente_sem_remuneracao=False,
                        data_ref=None) -> dict:
    vig = listar_vigentes(con, data_ref)
    ref = vig["data_referencia"]
    por_registro: dict = defaultdict(list)
    for i in vig["itens"]:
        por_registro[i["registro"]].append(i)

    periodos: dict = defaultdict(list)
    registros = list(por_registro)
    for k in range(0, len(registros), 500):
        lote = registros[k:k + 500]
        for l in consultar(con, S.periodos_dos_registros(len(lote)), (C.EMPRESA, ref, *lote)):
            periodos[l["registro"]].append((l["dtini"], l["dtfim"]))

    itens = []
    for registro, vigentes in por_registro.items():
        desde = K.inicio_bloco_continuo(periodos[registro], ref)
        if desde is None:
            continue
        dias = (ref - desde).days + 1
        sem_rem = any(v["sem_remuneracao"] for v in vigentes)
        if dias < min_dias or (somente_sem_remuneracao and not sem_rem):
            continue
        p = vigentes[0]
        itens.append({
            "registro": registro, "matricula": p["matricula"], "nome": p["nome"], "cpf": p["cpf"],
            "divisao": p["divisao"], "cargo": p["cargo"],
            "afastado_desde": desde, "dias_continuos": dias, "sem_remuneracao": sem_rem,
            "afastamentos_vigentes": [
                {"item": v["item"], "reduzido": v["reduzido"], "tipo": v["tipo"], "dtini": v["dtini"],
                 "retorno_previsto": v["retorno_previsto"]} for v in vigentes],
        })
    itens.sort(key=lambda i: -i["dias_continuos"])
    return _resposta(ref, itens, min_dias=min_dias)


# --------------------------------------------------------------------------
# 5) eSocial
# --------------------------------------------------------------------------
def esocial_resumo(con, desde: date = C.DESDE_PADRAO) -> dict:
    linhas = consultar(con, S.ESOCIAL_LANCAMENTOS, (C.EMPRESA, desde))
    corpo = K.agregar_esocial(linhas)
    return {"desde": desde, **corpo,
            "observacao": "sem_status = lançamento que nunca entrou no fluxo do eSocial. "
                          "Confirmar no Manual quais afastamentos curtos são dispensados."}


def esocial_tipos_com_problema(con, desde: date = C.DESDE_PADRAO) -> dict:
    itens = []
    for l in consultar(con, S.ESOCIAL_TIPOS_COM_PROBLEMA, (desde, C.EMPRESA)):
        if l["motivo_id"] is None:
            problema = "sem_motivo_configurado"
        elif l["motivo_codigo"] is None:
            problema = "motivo_inexistente"
        elif l["motivo_tipo"] not in (0, None):
            problema = "motivo_de_desligamento_em_tipo_de_afastamento"
        else:
            problema = "motivo_encerrado"
        l["problema"] = problema
        itens.append(l)
    return {"desde": desde, "total": len(itens), "itens": itens}


def esocial_pendencias(con, status: list[str], desde: date = C.DESDE_PADRAO, reduzido: int | None = None) -> dict:
    partes = []
    codigos = [K.STATUS_CODIGOS[s] for s in status if s in K.STATUS_CODIGOS]
    if codigos:
        partes.append(f"m.STATUS_ESOCIAL IN ({', '.join(str(c) for c in codigos)})")
    if "sem_status" in status:
        partes.append("m.STATUS_ESOCIAL IS NULL")
    if not partes:
        return {"desde": desde, "status": status, "total": 0, "itens": []}
    params = [C.EMPRESA, desde] + ([reduzido] if reduzido is not None else [])
    linhas = consultar(con, S.esocial_pendencias(" OR ".join(partes), reduzido is not None), params)
    itens = [_enriquecer(l) for l in linhas]
    return {"desde": desde, "status": status, "total": len(itens), "itens": itens}


# --------------------------------------------------------------------------
# 6) Erros de lançamento
# --------------------------------------------------------------------------
REGRAS_INCONSISTENCIA = {
    "sobrepostos": "Dois afastamentos do mesmo REGISTRO com períodos que se cruzam",
    "sem-tipo": "Lançamento em MOVTOSEFIP sem tipo (REDUZIDO vazio)",
    "tipo-descontinuado": f"Afastamento em aberto de tipo sem lançamento novo há mais de {C.DIAS_TIPO_DESCONTINUADO} dias",
    "desligado-com-afastamento": "Vínculo desligado (situação 6) com afastamento em aberto",
}


def inconsistencias(con, regra: str, desde: date = C.DESDE_PADRAO, data_ref=None) -> dict:
    ref = resolver_ref(con, data_ref)
    aa = K.param_ainda_afastado(ref)

    if regra == "sobrepostos":
        itens = []
        for l in consultar(con, S.SOBREPOSTOS, (C.EMPRESA, desde, desde)):
            dias = K.dias_sobrepostos(l["a_dtini"], l["a_dtfim"], l["b_dtini"], l["b_dtfim"], ref)
            if dias > 0:
                l["dias_sobrepostos"] = dias
                itens.append(l)
    elif regra == "sem-tipo":
        itens = consultar(con, S.SEM_TIPO, (C.EMPRESA,))
        for l in itens:
            l["status_esocial"] = K.nome_status(l["status_esocial"])
    elif regra == "tipo-descontinuado":
        limite = ref - timedelta(days=C.DIAS_TIPO_DESCONTINUADO)
        itens = [_enriquecer(l) for l in consultar(con, S.TIPO_DESCONTINUADO, (C.EMPRESA, ref, aa, limite))]
    elif regra == "desligado-com-afastamento":
        itens = [_enriquecer(l) for l in consultar(con, S.DESLIGADO_COM_AFASTAMENTO, (C.EMPRESA, ref, aa))]
    else:
        raise ValueError(regra)

    return _resposta(ref, itens, regra=regra, descricao=REGRAS_INCONSISTENCIA[regra], desde=desde)


def inconsistencias_resumo(con, desde: date = C.DESDE_PADRAO, data_ref=None) -> dict:
    ref = resolver_ref(con, data_ref)
    itens = []
    for regra, descricao in REGRAS_INCONSISTENCIA.items():
        r = inconsistencias(con, regra, desde, ref)
        itens.append({"regra": regra, "descricao": descricao, "total": r["total"]})
    return {"data_referencia": ref, "desde": desde, "itens": itens}


# --------------------------------------------------------------------------
# 7) Abatimento de tempo de serviço / contribuição
# --------------------------------------------------------------------------
def abate_tempo(con, min_dias: int = 1, data_ref=None) -> dict:
    ref = resolver_ref(con, data_ref)
    ate = ref + timedelta(days=1)
    por_registro: dict = defaultdict(list)
    for l in consultar(con, S.ABATE_TEMPO, (C.EMPRESA, ref)):
        por_registro[l["registro"]].append(l)

    itens = []
    for registro, ls in por_registro.items():
        serv = [(l["dtini"], l["dtfim"]) for l in ls if l["abate_temposervico"] == "S"]
        contrib = [(l["dtini"], l["dtfim"]) for l in ls if l["abate_tempocontrib"] == "S"]
        d_serv = K.dias_no_periodo(serv, date.min, ate)
        d_contrib = K.dias_no_periodo(contrib, date.min, ate)
        if max(d_serv, d_contrib) < min_dias:
            continue
        p = ls[0]
        itens.append({
            "registro": registro, "matricula": p["matricula"], "nome": p["nome"], "cpf": p["cpf"],
            "divisao": p["divisao"], "cargo": p["cargo"],
            "dias_abatidos_tempo_servico": d_serv, "dias_abatidos_tempo_contribuicao": d_contrib,
            "afastamentos": [
                {"item": l["item"], "reduzido": l["reduzido"], "tipo": l["tipo"], "dtini": l["dtini"],
                 "dtfim": l["dtfim"], "duracao_dias": K.duracao_dias(l["dtini"], l["dtfim"]),
                 "abate_tempo_servico": l["abate_temposervico"] == "S",
                 "abate_tempo_contribuicao": l["abate_tempocontrib"] == "S"}
                for l in sorted(ls, key=lambda x: x["dtini"])],
        })
    itens.sort(key=lambda i: -max(i["dias_abatidos_tempo_servico"], i["dias_abatidos_tempo_contribuicao"]))
    return _resposta(ref, itens, min_dias=min_dias)


# --------------------------------------------------------------------------
# 8) Licença maternidade/paternidade sem filho cadastrado
# --------------------------------------------------------------------------
def maternidade_sem_dependente(con, desde: date = C.DESDE_PADRAO, data_ref=None) -> dict:
    ref = resolver_ref(con, data_ref)
    linhas = consultar(con, S.MATERNIDADE_SEM_DEPENDENTE, (C.EMPRESA, desde, ref, ref))
    itens = []
    for l in linhas:
        l = _enriquecer(l)
        l["licenca"] = "paternidade" if l["reduzido"] in C.TIPOS_PATERNIDADE else "maternidade"
        itens.append(l)
    return _resposta(ref, itens, desde=desde,
                     regra=f"Nenhum dependente do REGISTRO nascido entre {C.JANELA_NASCIMENTO_ANTES_DIAS} "
                           "dias antes do início da licença e o fim dela")


# ==========================================================================
# FASE 2 — linha do tempo, percentual por secretaria, recorrentes, gerencial
# ==========================================================================
def _por_registro(linhas) -> dict:
    grupos: dict = defaultdict(list)
    for l in linhas:
        grupos[l["registro"]].append(l)
    return grupos


def serie_mensal(con, meses: int = C.MESES_SERIE_PADRAO, data_ref=None, divisao=None, reduzido=None) -> dict:
    """Evolução mês a mês: afastamentos iniciados, vínculos afastados e dias afastados.

    Considera vínculos de qualquer situação (quem foi desligado depois também entra
    nos meses em que estava afastado).
    """
    ref = resolver_ref(con, data_ref)
    janela = K.meses_ate(ref, meses)
    inicio, fim = janela[0][0], janela[-1][1]
    linhas = consultar(con, S.NA_JANELA_TODOS, (C.EMPRESA, fim, K.param_ainda_afastado(inicio)))
    linhas = _filtrar(linhas, reduzido, divisao)
    grupos = _por_registro(linhas)

    itens = []
    for ini_m, fim_m in janela:
        ultimo_dia = fim_m - timedelta(days=1)
        iniciados = sum(1 for l in linhas if ini_m <= l["dtini"] < fim_m)
        afastados_no_mes = afastados_no_fim = dias = 0
        for ls in grupos.values():
            periodos = [(l["dtini"], l["dtfim"]) for l in ls]
            d = K.dias_no_periodo(periodos, ini_m, fim_m)
            if d:
                afastados_no_mes += 1
                dias += d
            if any(K.afastado_no_dia(i, f, ultimo_dia) for i, f in periodos):
                afastados_no_fim += 1
        itens.append({
            "mes": ini_m.strftime("%Y-%m"), "ate": ultimo_dia,
            "mes_incompleto": fim_m.day != 1 or (fim_m - ini_m).days < 28,
            "afastamentos_iniciados": iniciados,
            "vinculos_afastados_no_mes": afastados_no_mes,
            "vinculos_afastados_no_fim_do_mes": afastados_no_fim,
            "dias_afastados": dias,
        })
    return {"data_referencia": ref, "meses": meses, "filtros": {"divisao": divisao, "reduzido": reduzido},
            "itens": itens}


def absenteismo(con, ano: int | None = None, mes: int | None = None, data_ref=None) -> dict:
    """Dias afastados no mês e percentual por secretaria (dias afastados ÷ dias possíveis).

    Denominador = vínculos ativos de hoje (o SIP não guarda o quadro mês a mês),
    por isso o percentual é mais fiel para meses recentes.
    """
    ref = resolver_ref(con, data_ref)
    ano, mes = ano or ref.year, mes or ref.month
    inicio = date(ano, mes, 1)
    fim = min(date(ano + (mes == 12), mes % 12 + 1, 1), ref + timedelta(days=1))
    if fim <= inicio:
        return {"data_referencia": ref, "periodo": {"inicio": inicio, "ate": None}, "total": None, "itens": []}
    dias_periodo = (fim - inicio).days

    linhas = consultar(con, S.NO_ANO, (C.EMPRESA, fim, K.param_ainda_afastado(inicio)))
    vinculos = {str(v["divisao_codigo"]): v for v in consultar(con, S.VINCULOS_POR_DIVISAO, (C.EMPRESA,))}

    por_div: dict = defaultdict(lambda: {"vinculos_afastados": 0, "dias_afastados": 0})
    por_tipo: dict = defaultdict(int)
    for registro, ls in _por_registro(linhas).items():
        d = K.dias_no_periodo([(l["dtini"], l["dtfim"]) for l in ls], inicio, fim)
        if not d:
            continue
        g = por_div[str(ls[0]["divisao_codigo"])]
        g["vinculos_afastados"] += 1
        g["dias_afastados"] += d
        for l in ls:
            por_tipo[(l["reduzido"], l["tipo"])] += K.dias_no_periodo([(l["dtini"], l["dtfim"])], inicio, fim)

    def _linha(codigo, nome, qtd, g):
        possiveis = qtd * dias_periodo
        return {"divisao_codigo": codigo, "divisao": nome, "vinculos": qtd,
                "vinculos_afastados": g["vinculos_afastados"], "dias_afastados": g["dias_afastados"],
                "percentual_dias_afastados": round(100 * g["dias_afastados"] / possiveis, 2) if possiveis else None}

    itens = [_linha(c, v["divisao"], v["vinculos"], por_div.get(c, {"vinculos_afastados": 0, "dias_afastados": 0}))
             for c, v in vinculos.items()]
    itens.sort(key=lambda i: -(i["percentual_dias_afastados"] or 0))
    total_vinc = sum(v["vinculos"] for v in vinculos.values())
    total = _linha(None, "Toda a Prefeitura", total_vinc, {
        "vinculos_afastados": sum(g["vinculos_afastados"] for g in por_div.values()),
        "dias_afastados": sum(g["dias_afastados"] for g in por_div.values())})
    tipos = [{"reduzido": k[0], "tipo": k[1], "dias_afastados": v}
             for k, v in sorted(por_tipo.items(), key=lambda x: -x[1])]
    return {"data_referencia": ref, "periodo": {"inicio": inicio, "ate": fim - timedelta(days=1), "dias": dias_periodo},
            "total": total, "itens": itens, "dias_por_tipo": tipos,
            "observacao": "Percentual = dias afastados ÷ (vínculos ativos × dias do período). "
                          "Afastamentos sobrepostos do mesmo vínculo contam uma vez."}


def recorrentes(con, ano: int | None = None, min_episodios: int = C.RECORRENTES_MIN_PADRAO,
                somente_saude: bool = True, data_ref=None, ordenar: str = "bradford") -> dict:
    """Vínculos com muitos episódios de afastamento no ano.

    Episódio = afastamentos emendados contam como um só (licença renovada não infla a conta).
    Saúde = tipos cuja causa é acidente ou doença (CAUSAS 91 a 94); não usa CID.
    Fator de Bradford = episódios² × dias afastados no ano: pesa mais quem falta
    muitas vezes por pouco tempo do que quem teve um afastamento longo.
    """
    ref = resolver_ref(con, data_ref)
    ano = ano or ref.year
    inicio, fim = date(ano, 1, 1), min(date(ano + 1, 1, 1), ref + timedelta(days=1))
    linhas = consultar(con, S.INICIADOS_NO_PERIODO, (C.EMPRESA, inicio, fim))
    if somente_saude:
        linhas = [l for l in linhas if str(l.get("causa") or "") in C.CAUSAS_SAUDE]

    itens = []
    for registro, ls in _por_registro(linhas).items():
        eps = K.episodios([(l["dtini"], l["dtfim"]) for l in ls])
        if len(eps) < min_episodios:
            continue
        p = ls[0]
        tipos: dict = defaultdict(int)
        for l in ls:
            tipos[f'{l["reduzido"]} {l["tipo"]}'] += 1
        dias = K.dias_no_periodo([(l["dtini"], l["dtfim"]) for l in ls], inicio, fim)
        duracoes = [(f - i).days for i, f in eps]
        itens.append({
            "registro": registro, "matricula": p["matricula"], "nome": p["nome"], "cpf": p["cpf"],
            "divisao": p["divisao"], "cargo": p["cargo"],
            "episodios": len(eps), "lancamentos": len(ls), "dias_afastado": dias,
            "fator_bradford": K.fator_bradford(len(eps), dias),
            "episodios_curtos": sum(1 for d in duracoes if d <= C.EPISODIO_CURTO_DIAS),
            "maior_episodio_dias": max(duracoes) if duracoes else 0,
            "tipos": dict(sorted(tipos.items(), key=lambda x: -x[1])),
            "lista_episodios": [{"inicio": i, "retorno": f, "dias": (f - i).days} for i, f in eps],
        })
    chave = {"bradford": lambda i: (-i["fator_bradford"], -i["episodios"]),
             "episodios": lambda i: (-i["episodios"], -i["dias_afastado"]),
             "dias": lambda i: (-i["dias_afastado"], -i["episodios"])}[ordenar]
    itens.sort(key=chave)
    return _resposta(ref, itens, ano=ano, min_episodios=min_episodios, somente_saude=somente_saude,
                     ordenado_por=ordenar,
                     legenda={"fator_bradford": "episódios² × dias afastados no ano",
                              "episodios_curtos": f"episódios de até {C.EPISODIO_CURTO_DIAS} dias"})


def gerencial(con, data_ref=None) -> dict:
    """Resumo para o gabinete: só números, sem nomes, CPF ou CID."""
    ref = resolver_ref(con, data_ref)
    por_tipo = resumir_vigentes(con, ref, "tipo")
    por_div = resumir_vigentes(con, ref, "divisao")
    ret7 = listar_retornos(con, 7, ref)
    longos_sem_rem = afastamentos_longos(con, C.DIAS_LONGO_PADRAO, True, ref)
    tipos_problema = esocial_tipos_com_problema(con, date(ref.year, 1, 1))
    esoc = esocial_resumo(con, date(ref.year, 1, 1))
    return {
        "data_referencia": ref,
        "afastados_na_data": {"vinculos": por_tipo["total_vinculos"],
                              "por_tipo": por_tipo["itens"][:10], "por_secretaria": por_div["itens"]},
        "retornos_em_7_dias": {"total": ret7["total"],
                               "emendam_outro_afastamento": sum(1 for i in ret7["itens"] if i["emenda_outro_afastamento"])},
        "absenteismo_mes": absenteismo(con, data_ref=ref),
        "linha_do_tempo": serie_mensal(con, C.MESES_SERIE_PADRAO, ref)["itens"],
        "afastados_longos_sem_remuneracao": longos_sem_rem["total"],
        "esocial_no_ano": {"totais": esoc["totais"],
                           "tipos_sem_motivo": [{"reduzido": t["reduzido"], "tipo": t["tipo"],
                                                 "lancamentos": t["lancamentos_desde"]} for t in tipos_problema["itens"]]},
    }
