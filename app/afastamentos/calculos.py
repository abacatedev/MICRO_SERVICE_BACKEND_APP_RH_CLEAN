"""
Cálculos em Python puro (sem banco) — testados em tests/test_calculos.py.

Convenção interna: todo período é [inicio, fim_exclusivo), ou seja,
o fim é o primeiro dia em que a pessoa NÃO está mais afastada.
"""
from datetime import date, timedelta

from . import config as C

STATUS_ESOCIAL = {0: "nao_enviado", 1: "aguardando", 2: "valido", 3: "invalido"}
STATUS_CODIGOS = {v: k for k, v in STATUS_ESOCIAL.items()}
ORDEM_STATUS = ("valido", "aguardando", "nao_enviado", "invalido", "sem_status")


def nome_status(codigo) -> str:
    if codigo is None:
        return "sem_status"
    return STATUS_ESOCIAL.get(int(codigo), f"desconhecido_{codigo}")


def fim_exclusivo(dtfim: date | None) -> date | None:
    if dtfim is None:
        return None
    return dtfim if C.DTFIM_E_DIA_DO_RETORNO else dtfim + timedelta(days=1)


def param_ainda_afastado(dia: date) -> date:
    """Valor p tal que 'DTFIM > p' significa 'ainda afastado no dia'."""
    return dia if C.DTFIM_E_DIA_DO_RETORNO else dia - timedelta(days=1)


def duracao_dias(dtini: date, dtfim: date | None) -> int | None:
    fe = fim_exclusivo(dtfim)
    return None if fe is None or dtini is None else (fe - dtini).days


def unir_intervalos(intervalos, tolerancia_dias: int = 0):
    """Une períodos sobrepostos (ou separados por até `tolerancia_dias`)."""
    validos = sorted((i, f) for i, f in intervalos if i is not None and f is not None and f > i)
    unidos: list[tuple[date, date]] = []
    folga = timedelta(days=tolerancia_dias)
    for ini, fim in validos:
        if unidos and ini <= unidos[-1][1] + folga:
            if fim > unidos[-1][1]:
                unidos[-1] = (unidos[-1][0], fim)
        else:
            unidos.append((ini, fim))
    return unidos


def total_dias(intervalos) -> int:
    return sum((f - i).days for i, f in intervalos)


def dias_no_periodo(lancamentos, inicio: date, fim_exc: date) -> int:
    """Dias afastados dentro de [inicio, fim_exc), sem contar duas vezes os sobrepostos.

    lancamentos: iterável de (dtini, dtfim) como vêm do SIP.
    Afastamento sem DTFIM conta até fim_exc.
    """
    pedacos = []
    for dtini, dtfim in lancamentos:
        if dtini is None:
            continue
        fe = fim_exclusivo(dtfim) or fim_exc
        i, f = max(dtini, inicio), min(fe, fim_exc)
        if f > i:
            pedacos.append((i, f))
    return total_dias(unir_intervalos(pedacos))


def agrupar_episodios(pedacos) -> list[dict]:
    """Agrupa períodos [inicio, fim_exclusivo) em episódios.

    Regra:
    - intervalo de até TOLERANCIA_EMENDA_DIAS (1) entre dois afastamentos: mesmo episódio;
    - intervalo de até TOLERANCIA_RENOVACAO_DIAS (3) quando o afastamento anterior durou
      RENOVACAO_MIN_DIAS (15) dias ou mais: mesmo episódio (licença renovada depois de um fim de semana);
    - atestados curtos separados por um fim de semana continuam sendo episódios diferentes.

    Cada episódio traz `dias` = dias realmente afastados (sem contar os intervalos).
    """
    validos = sorted((i, f) for i, f in pedacos if i is not None and f is not None and f > i)
    grupos: list[dict] = []
    for ini, fim in validos:
        if grupos:
            g = grupos[-1]
            intervalo = (ini - g["fim"]).days            # dias sem afastamento entre os dois
            limite = (C.TOLERANCIA_RENOVACAO_DIAS if g["ultimo_dias"] >= C.RENOVACAO_MIN_DIAS
                      else C.TOLERANCIA_EMENDA_DIAS)
            if intervalo <= limite:
                g["pedacos"].append((ini, fim))
                g["fim"] = max(g["fim"], fim)
                g["ultimo_dias"] = (fim - ini).days
                continue
        grupos.append({"inicio": ini, "fim": fim, "pedacos": [(ini, fim)], "ultimo_dias": (fim - ini).days})
    return [{"inicio": g["inicio"], "retorno": g["fim"], "dias": total_dias(unir_intervalos(g["pedacos"])),
             "lancamentos": len(g["pedacos"])} for g in grupos]


def inicio_bloco_continuo(lancamentos, ref: date, tolerancia_dias: int | None = None) -> date | None:
    """Data em que começou o afastamento contínuo que contém `ref`.

    Afastamentos emendados (licença renovada, licença do município que vira
    auxílio-doença do INSS etc.) contam como um só bloco, pela regra de agrupar_episodios.
    `tolerancia_dias` explícito usa uma tolerância única (compatibilidade).
    """
    pedacos = []
    for dtini, dtfim in lancamentos:
        if dtini is None or dtini > ref:
            continue
        pedacos.append((dtini, fim_exclusivo(dtfim) or ref + timedelta(days=1)))
    if tolerancia_dias is not None:
        blocos = unir_intervalos(pedacos, tolerancia_dias)
    else:
        blocos = [(e["inicio"], e["retorno"]) for e in agrupar_episodios(pedacos)]
    for ini, fim in blocos:
        if ini <= ref < fim:
            return ini
    return None


def meses_ate(ref: date, quantidade: int) -> list[tuple[date, date]]:
    """Os `quantidade` meses que terminam no mês de `ref`, como [inicio, fim_exclusivo).

    O último mês é cortado no dia seguinte a `ref` (a cópia não tem dados depois dela).
    """
    resultado = []
    ano, mes = ref.year, ref.month
    for _ in range(quantidade):
        inicio = date(ano, mes, 1)
        fim = date(ano + (mes == 12), mes % 12 + 1, 1)
        resultado.append((inicio, min(fim, ref + timedelta(days=1))))
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return list(reversed(resultado))


def afastado_no_dia(dtini: date, dtfim: date | None, dia: date) -> bool:
    fe = fim_exclusivo(dtfim)
    return dtini <= dia and (fe is None or fe > dia)


def episodios(lancamentos) -> list[dict]:
    """Episódios de afastamento a partir de (dtini, dtfim) do SIP (ver agrupar_episodios)."""
    pedacos = [(i, fim_exclusivo(f) or i + timedelta(days=1)) for i, f in lancamentos if i is not None]
    return agrupar_episodios(pedacos)


def fator_bradford(episodios: int, dias: int) -> int:
    """Fator de Bradford: S² × D (S = episódios, D = dias afastados)."""
    return episodios * episodios * dias


def perfil_recorrencia(episodios: int, curtos: int, maior: int) -> str:
    """frequente (muitas faltas curtas), prolongado (episódio longo), misto (os dois) ou moderado."""
    frequente = episodios > 0 and curtos / episodios >= C.PERFIL_FREQUENTE_PROPORCAO
    prolongado = maior >= C.PERFIL_PROLONGADO_DIAS
    if frequente and prolongado:
        return "misto"
    if frequente:
        return "frequente"
    if prolongado:
        return "prolongado"
    return "moderado"


def dias_sobrepostos(a_ini, a_fim, b_ini, b_fim, ref: date) -> int:
    limite = ref + timedelta(days=1)
    fa = fim_exclusivo(a_fim) or limite
    fb = fim_exclusivo(b_fim) or limite
    return max(0, (min(fa, fb) - max(a_ini, b_ini)).days)


def agregar_esocial(linhas: list[dict]) -> dict:
    """Agrupa lançamentos por tipo e situação de envio ao eSocial.

    Os lançamentos sem status são separados por duração, porque a obrigação
    de envio de afastamentos curtos ainda precisa ser confirmada no Manual.
    """
    por_tipo: dict = {}
    for l in linhas:
        chave = l["reduzido"]
        t = por_tipo.get(chave)
        if t is None:
            motivo = None
            if l.get("motivo_id") is not None:
                motivo = {
                    "id": l["motivo_id"],
                    "codigo": l.get("motivo_codigo"),
                    "descricao": l.get("motivo_descricao"),
                    "encerrado_em": l.get("motivo_dtfim"),
                }
            t = por_tipo[chave] = {
                "reduzido": chave,
                "tipo": l.get("tipo"),
                "motivo_esocial": motivo,
                "total": 0,
                "por_status": {s: 0 for s in ORDEM_STATUS},
                "sem_status_por_duracao": {"ate_15_dias": 0, "mais_de_15_dias": 0, "em_aberto": 0},
            }
        t["total"] += 1
        status = nome_status(l.get("status_esocial"))
        t["por_status"][status] = t["por_status"].get(status, 0) + 1
        if status == "sem_status":
            dur = duracao_dias(l["dtini"], l.get("dtfim"))
            faixa = "em_aberto" if dur is None else ("ate_15_dias" if dur <= 15 else "mais_de_15_dias")
            t["sem_status_por_duracao"][faixa] += 1

    itens = sorted(por_tipo.values(), key=lambda x: -x["total"])
    totais = {"total": sum(i["total"] for i in itens)}
    for s in ORDEM_STATUS:
        totais[s] = sum(i["por_status"].get(s, 0) for i in itens)
    return {"totais": totais, "itens": itens}
