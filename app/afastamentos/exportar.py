"""
Exportação das listas nominais em CSV (abre direto no Excel/LibreOffice em português):
separador ";", UTF-8 com BOM, datas DD/MM/AAAA, Sim/Não.
"""
import csv
import io
from datetime import date, datetime

SERVIDOR = [("registro", "REGISTRO"), ("matricula", "Matrícula"), ("nome", "Nome"), ("cpf", "CPF"),
            ("divisao", "Secretaria"), ("cargo", "Cargo")]

COLUNAS = {
    "vigentes": SERVIDOR + [("reduzido", "Cód. tipo"), ("tipo", "Tipo de afastamento"), ("dtini", "Início"),
                            ("retorno_previsto", "Retorno previsto"), ("duracao_dias", "Dias"),
                            ("sem_remuneracao", "Sem remuneração"), ("documento_tipo", "Documento"),
                            ("documento_numero", "Nº documento"), ("status_esocial", "eSocial")],
    "retornos": SERVIDOR + [("reduzido", "Cód. tipo"), ("tipo", "Tipo de afastamento"), ("dtini", "Início"),
                            ("retorno_previsto", "Retorno previsto"), ("dias_ate_retorno", "Dias até o retorno"),
                            ("emenda_outro_afastamento", "Emenda em outro afastamento")],
    "longos": SERVIDOR + [("afastado_desde", "Afastado desde"), ("dias_continuos", "Dias contínuos"),
                          ("sem_remuneracao", "Sem remuneração"), ("afastamentos_vigentes", "Afastamentos em curso")],
    "acumulado": SERVIDOR + [("dias_afastado", "Dias afastados no ano"), ("afastamentos", "Lançamentos"),
                             ("dias_por_tipo", "Dias por tipo")],
    "recorrentes": SERVIDOR + [("perfil", "Perfil"), ("fator_bradford", "Fator de Bradford"), ("episodios", "Episódios"),
                               ("episodios_curtos", "Episódios de até 2 dias"),
                               ("maior_episodio_dias", "Maior episódio (dias)"), ("lancamentos", "Lançamentos"),
                               ("dias_afastado", "Dias afastados no ano"), ("tipos", "Tipos")],
    "esocial-pendencias": SERVIDOR + [("reduzido", "Cód. tipo"), ("tipo", "Tipo de afastamento"), ("dtini", "Início"),
                                      ("dtfim", "Fim (DTFIM)"), ("motivo_codigo", "Motivo eSocial"),
                                      ("status_esocial", "Situação no eSocial")],
}


def _valor(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, dict):
        return "; ".join(f"{k}: {x}" for k, x in v.items())
    if isinstance(v, list):
        return "; ".join(f'{i.get("reduzido", "")} {i.get("tipo", "")}'.strip() if isinstance(i, dict) else str(i)
                         for i in v)
    return str(v)


def para_csv(relatorio: str, itens: list[dict]) -> bytes:
    colunas = COLUNAS[relatorio]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    w.writerow([titulo for _, titulo in colunas])
    for item in itens:
        w.writerow([_valor(item.get(chave)) for chave, _ in colunas])
    return ("﻿" + buf.getvalue()).encode("utf-8")
