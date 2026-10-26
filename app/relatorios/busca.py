"""
Busca, agrupamento e ordenação das linhas de um relatório. Funções puras, sem SIP.

Regras da busca (campo "Buscar por nome, matrícula, CPF, cargo ou secretaria"):
- não diferencia maiúsculas nem acentos: "natalia" acha NATÁLIA, "goncalo" acha GONÇALO;
- pontuação vira espaço, nos dois lados: "c/doc" acha "C/DOC";
- várias palavras = todas precisam aparecer (em qualquer campo de busca, em qualquer ordem):
  "maria educacao" acha MARIA ... da SECRETARIA MUNICIPAL DE EDUCAÇÃO;
- só números (com ou sem ponto, traço, barra): compara com REGISTRO, matrícula e contrato
  (ignorando zeros à esquerda) e, para quem pode ver CPF, com o CPF sem pontuação
  (11 dígitos = CPF exato; de 6 a 10 dígitos = começo do CPF).
  Quem não pode ver CPF não consegue achar alguém pelo CPF.
"""
import re
import unicodedata
from datetime import date, datetime

_NAO_ALNUM = re.compile(r"[^0-9a-z]+")
_SO_NUMERO = re.compile(r"^[\d\s.\-/]+$")
CPF_PREFIXO_MIN = 6


def normalizar(valor) -> str:
    """Minúsculas, sem acento, pontuação vira espaço, espaços simples."""
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return " ".join(_NAO_ALNUM.sub(" ", texto).split())


def digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _sem_zeros(valor) -> str:
    d = digitos(valor)
    return d.lstrip("0") or ("0" if d else "")


def e_numerico(termo: str) -> bool:
    return bool(termo and _SO_NUMERO.match(termo) and digitos(termo))


def preparar(termo: str | None):
    """Converte o texto digitado num "casador" (função linha -> bool) ou None se vazio."""
    termo = (termo or "").strip()
    if not termo:
        return None
    if e_numerico(termo):
        return ("numero", digitos(termo))
    palavras = normalizar(termo).split()
    return ("texto", palavras) if palavras else None


def casa(linha: dict, busca, campos_texto: list[str], pode_ver_cpf: bool) -> bool:
    if busca is None:
        return True
    modo, valor = busca
    if modo == "numero":
        alvo = valor.lstrip("0") or "0"
        for campo in ("registro", "matricula", "contrato"):
            if linha.get(campo) is not None and _sem_zeros(linha.get(campo)) == alvo:
                return True
        if pode_ver_cpf:
            cpf = digitos(linha.get("cpf"))
            if cpf and (cpf == valor if len(valor) >= 11 else len(valor) >= CPF_PREFIXO_MIN and cpf.startswith(valor)):
                return True
        return False
    blob = linha.get("_busca")
    if blob is None:
        partes = [normalizar(linha.get(c)) for c in campos_texto]
        partes += [_sem_zeros(linha.get(c)) for c in ("registro", "matricula") if linha.get(c) is not None]
        blob = " " + " ".join(p for p in partes if p) + " "
        linha["_busca"] = blob
    return all(p in blob for p in valor)


def filtrar(linhas: list[dict], termo: str | None, campos_texto: list[str], pode_ver_cpf: bool) -> list[dict]:
    busca = preparar(termo)
    if busca is None:
        return linhas
    return [l for l in linhas if casa(l, busca, campos_texto, pode_ver_cpf)]


# --------------------------------------------------------------------------- agrupar por pessoa
def chave_pessoa(linha: dict) -> str:
    cpf = digitos(linha.get("cpf"))
    return f"CPF:{cpf}" if cpf else f"REG:{linha.get('registro')}"


def _distintos(valores):
    vistos, saida = set(), []
    for v in valores:
        if v is None or v == "":
            continue
        k = repr(v) if isinstance(v, (dict, list)) else v
        if k not in vistos:
            vistos.add(k)
            saida.append(v)
    return saida


def agrupar_por_pessoa(linhas: list[dict], colunas: list[str]) -> list[dict]:
    """Uma linha por pessoa (CPF; sem CPF, fica o REGISTRO).

    Campo igual em todas as linhas fica como está; campos diferentes viram
    "valor 1 | valor 2". Acrescenta `vinculos` (quantos REGISTRO diferentes)
    e `linhas_agrupadas` (quantas linhas foram juntadas).
    """
    grupos: dict[str, list[dict]] = {}
    for l in linhas:
        grupos.setdefault(chave_pessoa(l), []).append(l)
    saida = []
    for ls in grupos.values():
        nova = {}
        for c in set(colunas) | {"registro", "cpf", "nome"}:
            vals = _distintos(l.get(c) for l in ls)
            if not vals:
                nova[c] = None
            elif len(vals) == 1:
                nova[c] = vals[0]
            else:
                nova[c] = " | ".join(_texto(v) for v in vals)
        nova["vinculos"] = len({l.get("registro") for l in ls})
        nova["linhas_agrupadas"] = len(ls)
        saida.append(nova)
    return saida


def _texto(v) -> str:
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return str(v)


# --------------------------------------------------------------------------- ordenar
def _chave(v):
    if isinstance(v, bool):
        return (0, int(v))
    if isinstance(v, (int, float)):
        return (0, v)
    if isinstance(v, datetime):
        return (1, v.date().toordinal(), v.time().isoformat())
    if isinstance(v, date):
        return (1, v.toordinal(), "")
    return (2, normalizar(v) if not isinstance(v, (dict, list)) else normalizar(repr(v)))


def ordenar(linhas: list[dict], campo: str | None, decrescente: bool = False) -> list[dict]:
    """Ordena sem diferenciar acentos; vazios sempre no fim, nas duas direções."""
    if not campo:
        return linhas
    cheios = [l for l in linhas if l.get(campo) not in (None, "")]
    vazios = [l for l in linhas if l.get(campo) in (None, "")]
    cheios.sort(key=lambda l: _chave(l.get(campo)), reverse=decrescente)
    return cheios + vazios
