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


def inicio_bloco_continuo(lancamentos, ref: date, tolerancia_dias: int | None = None) -> date | None:
    """Data em que começou o afastamento contínuo que contém `ref`.

    Afastamentos emendados (licença renovada, licença do município que vira
    auxílio-doença do INSS etc.) contam como um só bloco.
    """
    tol = C.TOLERANCIA_EMENDA_DIAS if tolerancia_dias is None else tolerancia_dias
    pedacos = []
    for dtini, dtfim in lancamentos:
        if dtini is None or dtini > ref:
            continue
        pedacos.append((dtini, fim_exclusivo(dtfim) or ref + timedelta(days=1)))
    for ini, fim in unir_intervalos(pedacos, tol):
        if ini <= ref < fim:
            return ini
    return None


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
