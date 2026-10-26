"""
Exportação do relatório filtrado: CSV (separador ";", UTF-8 com BOM, datas DD/MM/AAAA)
e Excel (.xlsx, com cabeçalho fixo, filtro automático e datas como data).
"""
import csv
import io
from datetime import date, datetime

def texto(v, tipo: str = "texto") -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    if isinstance(v, dict):
        return "; ".join(f"{k}: {x}" for k, x in v.items())
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


def para_csv(resultado: dict) -> bytes:
    colunas = resultado["colunas"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    w.writerow([c["rotulo"] for c in colunas])
    for item in resultado["itens"]:
        w.writerow([texto(item.get(c["id"]), c["tipo"]) for c in colunas])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _celula(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, (int, float, date)):
        return v
    if isinstance(v, (dict, list)):
        return texto(v)
    return str(v)


def para_xlsx(resultado: dict, descricao_filtros: str) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as erro:  # pragma: no cover
        raise RuntimeError("Instale openpyxl no backend para exportar em Excel.") from erro

    colunas = resultado["colunas"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"[:31]
    ref = resultado.get("data_referencia")
    ws.append([resultado["relatorio"]["titulo"]])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"Dados do SIP de {texto(ref)}" if ref else
               f"Gerado em {texto(resultado.get('gerado_em'))}"])
    ws.append([descricao_filtros or "Sem filtros"])
    ws.append([f"{resultado['total']} linha(s)"])
    ws.append([])
    linha_cab = ws.max_row + 1
    ws.append([c["rotulo"] for c in colunas])
    for celula in ws[linha_cab]:
        celula.font = Font(bold=True)
        celula.fill = PatternFill("solid", fgColor="DDE6F0")
    for item in resultado["itens"]:
        ws.append([_celula(item.get(c["id"])) for c in colunas])

    for i, c in enumerate(colunas, start=1):
        letra = get_column_letter(i)
        if c["tipo"] == "data":
            for (cel,) in ws.iter_rows(min_row=linha_cab + 1, min_col=i, max_col=i):
                cel.number_format = "DD/MM/YYYY"
        if c["tipo"] == "percentual":
            for (cel,) in ws.iter_rows(min_row=linha_cab + 1, min_col=i, max_col=i):
                cel.number_format = "0.0"
        maior = max([len(str(c["rotulo"]))] + [len(texto(it.get(c["id"]))) for it in resultado["itens"][:500]])
        ws.column_dimensions[letra].width = min(max(10, maior + 2), 60)
    ws.freeze_panes = ws.cell(row=linha_cab + 1, column=1)
    if colunas:
        ws.auto_filter.ref = f"A{linha_cab}:{get_column_letter(len(colunas))}{max(ws.max_row, linha_cab)}"
    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue()
