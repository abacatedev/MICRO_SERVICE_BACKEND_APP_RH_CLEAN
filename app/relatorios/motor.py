"""
Executa um relatório: valida filtros, carrega, completa dados do vínculo, filtra,
busca, agrupa por pessoa, ordena, pagina e escolhe as colunas.

Não conhece o SIP: recebe o relatório (com sua função `carregar`) e, opcionalmente,
uma função que completa as linhas com os dados do vínculo pelo REGISTRO.
"""
from collections import Counter
from datetime import date, datetime, timezone

from . import busca as B
from .modelo import PERM_SENSIVEL, Filtro, Relatorio

POR_PAGINA_MAX = 500
EXPORTACAO_MAX = 50_000

VERDADE = {"true", "1", "sim", "s", "yes"}
FALSO = {"false", "0", "nao", "não", "n", "no"}


class ErroDeParametro(ValueError):
    """Parâmetro inválido: a rota responde 422 com esta mensagem."""


# --------------------------------------------------------------------------- filtros
def _converter(f: Filtro, brutos: list[str]):
    brutos = [b.strip() for b in brutos if b is not None and b.strip() != ""]
    if f.tipo == "multipla":
        valores = [p.strip() for b in brutos for p in b.split(",") if p.strip()]
        if not valores:
            return None
        permitidas = f.lista_opcoes()
        if permitidas is not None:
            ok = {v for v, _ in permitidas}
            invalidos = [v for v in valores if v not in ok]
            if invalidos:
                raise ErroDeParametro(f"{f.rotulo}: valor inválido {', '.join(invalidos)}")
        return valores
    if not brutos:
        return None
    bruto = brutos[-1]
    if f.tipo == "selecao":
        permitidas = f.lista_opcoes()
        if permitidas is not None and bruto not in {v for v, _ in permitidas}:
            raise ErroDeParametro(f"{f.rotulo}: valor inválido {bruto}")
        return bruto
    if f.tipo == "numero":
        try:
            n = int(bruto)
        except ValueError:
            raise ErroDeParametro(f"{f.rotulo}: informe um número") from None
        if (f.minimo is not None and n < f.minimo) or (f.maximo is not None and n > f.maximo):
            raise ErroDeParametro(f"{f.rotulo}: use um valor entre {f.minimo} e {f.maximo}")
        return n
    if f.tipo == "data":
        try:
            return date.fromisoformat(bruto)
        except ValueError:
            raise ErroDeParametro(f"{f.rotulo}: use a data no formato AAAA-MM-DD") from None
    if f.tipo == "booleano":
        b = bruto.lower()
        if b in VERDADE:
            return True
        if b in FALSO:
            return False
        raise ErroDeParametro(f"{f.rotulo}: use true ou false")
    raise ErroDeParametro(f"Filtro {f.id} com tipo desconhecido")


def validar_filtros(rel: Relatorio, brutos: dict[str, list[str]]) -> dict:
    conhecidos = {f.id for f in rel.filtros}
    estranhos = sorted(set(brutos) - conhecidos)
    if estranhos:
        raise ErroDeParametro(f"Filtro não existe neste relatório: {', '.join(estranhos)}")
    valores = {}
    for f in rel.filtros:
        v = _converter(f, brutos.get(f.id, []))
        if v is None:
            v = f.padrao
        if v is None and f.obrigatorio:
            raise ErroDeParametro(f"Escolha {f.rotulo.lower()}")
        valores[f.id] = v
    return valores


def _mesmo_codigo(a, b) -> bool:
    a, b = str(a).strip(), str(b).strip()
    if a == b:
        return True
    return a.isdigit() and b.isdigit() and (a.lstrip("0") or "0") == (b.lstrip("0") or "0")


def _passa(linha: dict, f: Filtro, valor) -> bool:
    atual = linha.get(f.campo)
    if f.tipo == "booleano":
        return bool(atual) == valor
    if atual is None:
        return False
    valores = valor if isinstance(valor, list) else [valor]
    return any(_mesmo_codigo(atual, v) for v in valores)


def contar_opcoes(linhas: list[dict], f: Filtro) -> list[dict]:
    """Valores que aparecem nas linhas, com quantas linhas cada um tem."""
    rotulos: dict = {}
    contagem: Counter = Counter()
    for l in linhas:
        v = l.get(f.campo)
        if v is None or v == "":
            continue
        chave = str(v).strip()
        contagem[chave] += 1
        rotulos.setdefault(chave, l.get(f.campo_rotulo) if f.campo_rotulo else v)
    return [{"valor": v, "rotulo": str(rotulos[v]) if rotulos[v] is not None else v, "total": n}
            for v, n in sorted(contagem.items(), key=lambda x: (-x[1], B.normalizar(rotulos[x[0]])))]


# --------------------------------------------------------------------------- execução
def executar(
    rel: Relatorio,
    permissoes,
    filtros: dict[str, list[str]] | None = None,
    q: str | None = None,
    colunas: list[str] | None = None,
    agrupar: bool = False,
    ordenar: str | None = None,
    decrescente: bool | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    completo: bool = False,
    completar=None,
    com_opcoes: bool = True,
) -> dict:
    permissoes = set(permissoes or ())
    pode_ver_sensivel = PERM_SENSIVEL in permissoes
    visiveis = [c for c in rel.colunas if pode_ver_sensivel or not c.sensivel]
    ids_visiveis = [c.id for c in visiveis]

    valores = validar_filtros(rel, filtros or {})
    da_fonte = {f.id: valores[f.id] for f in rel.filtros if f.campo is None}
    carregado = rel.carregar(da_fonte)
    linhas = list(carregado.get("linhas", []))
    if completar is not None and rel.nominal:
        completar(linhas)
    total_carregado = len(linhas)

    # busca primeiro; depois os filtros por campo
    campos_busca = [c.id for c in visiveis if c.busca]
    if q and campos_busca:
        linhas = B.filtrar(linhas, q, campos_busca, pode_ver_sensivel)

    ativos = [f for f in rel.filtros
              if f.campo is not None and valores.get(f.id) is not None and not (f.somente and valores[f.id] is False)]

    def aplicar(ls, exceto=None):
        for f in ativos:
            if f is not exceto:
                ls = [l for l in ls if _passa(l, f, valores[f.id])]
        return ls

    # Opções de cada filtro: contam o que sobra com a busca e os OUTROS filtros
    # (o próprio filtro fica de fora, para dar para marcar mais de um valor).
    opcoes = {}
    if com_opcoes:
        for f in rel.filtros:
            if f.campo is not None and f.lista_opcoes() is None and f.tipo in ("selecao", "multipla"):
                opcoes[f.id] = contar_opcoes(aplicar(linhas, exceto=f), f)
    linhas = aplicar(linhas)

    # colunas de saída
    if colunas:
        desconhecidas = [c for c in colunas if rel.coluna(c) is None and c != "vinculos"]
        if desconhecidas:
            raise ErroDeParametro(f"Coluna não existe neste relatório: {', '.join(desconhecidas)}")
        saida = [c for c in colunas if c in ids_visiveis or c == "vinculos"]
    else:
        padrao = carregado.get("colunas_padrao") or [c.id for c in visiveis if c.padrao]
        saida = [c for c in padrao if c in ids_visiveis]

    agrupado = bool(agrupar and rel.nominal)
    if agrupado:
        linhas = B.agrupar_por_pessoa(linhas, saida)
        if "vinculos" not in saida:
            saida = saida[:1] + ["vinculos"] + saida[1:]

    ordem_campo, ordem_desc = rel.ordem_padrao or (None, False)
    if ordenar:
        if ordenar not in ids_visiveis and not (agrupado and ordenar == "vinculos"):
            raise ErroDeParametro(f"Não dá para ordenar por {ordenar}")
        ordem_campo, ordem_desc = ordenar, bool(decrescente)
    elif decrescente is not None:
        ordem_desc = decrescente
    if ordem_campo and (ordem_campo in ids_visiveis or ordem_campo == "vinculos"):
        linhas = B.ordenar(linhas, ordem_campo, ordem_desc)

    total = len(linhas)
    if completo:
        if total > EXPORTACAO_MAX:
            raise ErroDeParametro(
                f"O resultado tem {total} linhas; filtre mais para exportar (máximo {EXPORTACAO_MAX}).")
        pagina_linhas = linhas
    else:
        por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAX))
        pagina = max(1, int(pagina))
        inicio = (pagina - 1) * por_pagina
        pagina_linhas = linhas[inicio:inicio + por_pagina]

    projetadas = []
    for l in pagina_linhas:
        item = {c: l.get(c) for c in saida}
        if rel.nominal and "registro" not in item:
            item["registro"] = l.get("registro")   # para o link da ficha
        projetadas.append(item)

    meta_colunas = []
    for c in saida:
        col = rel.coluna(c)
        meta_colunas.append(col.descrever() if col else
                            {"id": "vinculos", "rotulo": "Vínculos", "tipo": "numero", "padrao": True,
                             "sensivel": False})

    return {
        "relatorio": {"id": rel.id, "titulo": rel.titulo, "grupo": rel.grupo, "natureza": rel.natureza},
        "data_referencia": carregado.get("data_referencia"),
        "gerado_em": carregado.get("gerado_em") or datetime.now(timezone.utc),
        "contexto": carregado.get("contexto"),
        "filtros": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in valores.items()},
        "q": q or None,
        "agrupado_por_pessoa": agrupado,
        "ordenado_por": {"coluna": ordem_campo, "decrescente": ordem_desc} if ordem_campo else None,
        "total_carregado": total_carregado,
        "total": total,
        "pagina": 1 if completo else pagina,
        "por_pagina": total if completo else por_pagina,
        "opcoes": opcoes,
        "totais": carregado.get("totais"),
        "colunas": meta_colunas,
        "itens": projetadas,
    }
