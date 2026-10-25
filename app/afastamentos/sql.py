"""
SQL do módulo de afastamentos — apenas SELECT.

Tabelas e chaves confirmadas no catálogo do SIP:
  MOVTOSEFIP (PK ITEM; FK EMPRESA+REGISTRO -> TRABALHADOR; EMPRESA+REDUZIDO -> SEFIPREDUZIDO;
              TIPOLEGAL -> TIPOLEGAL)
  SEFIPREDUZIDO (PK EMPRESA+CODIGO; TIPO_MOVIMENTO_ESOCIAL -> TIPO_MOVIMENTO_ESOCIAL)
  TIPO_MOVIMENTO_ESOCIAL (ID, TIPO 0=afastamento/1=desligamento, CODIGO, DESCRICAO, DTFIM)
  CARGOS, DIVISAO (EMPRESA, CODIGO, NOME)
"""
from . import config as C
from .db import ident

SIT_ATIVAS = ", ".join(str(int(s)) for s in C.SITUACOES_ATIVAS)
SIT_DESLIGADO = int(C.SITUACAO_DESLIGADO)

_MAT = ident(C.COL_TRAB_MATRICULA)
_NOME = ident(C.COL_TRAB_NOME)
_CPF = ident(C.COL_TRAB_CPF)
_DIV = ident(C.COL_TRAB_DIVISAO)
_CARGO = ident(C.COL_TRAB_CARGO)
_NASC = ident(C.COL_DEP_NASCIMENTO)


def temporario(alias: str = "r") -> str:
    """Condição SQL: o tipo de lançamento é afastamento temporário."""
    base = f"{alias}.SEFIPENT IS NOT NULL"
    extras = ", ".join(str(int(c)) for c in C.TIPOS_TEMPORARIOS_EXTRAS)
    return f"({base} OR {alias}.CODIGO IN ({extras}))" if extras else base


def _lista_int(valores) -> str:
    return ", ".join(str(int(v)) for v in valores)


def select_base(extra: str = "") -> str:
    """Afastamento + servidor + secretaria + cargo + documento + motivo eSocial."""
    return f"""
SELECT m.REGISTRO, t.{_MAT} AS MATRICULA, t.{_NOME} AS NOME, t.{_CPF} AS CPF,
       t.SITUACAO AS SITUACAO_VINCULO,
       d.CODIGO AS DIVISAO_CODIGO, d.NOME AS DIVISAO,
       c.CODIGO AS CARGO_CODIGO, c.NOME AS CARGO,
       m.ITEM, m.REDUZIDO, r.NOME AS TIPO, r.CAUSA,
       m.DTINI, m.DTFIM, m.DTALTA, m.STATUS_ESOCIAL,
       tl.NOME AS DOCUMENTO_TIPO, m.NUMDOCUMENTO AS DOCUMENTO_NUMERO, m.DTDOCUMENTO AS DOCUMENTO_DATA,
       tme.CODIGO AS MOTIVO_CODIGO{extra}
FROM MOVTOSEFIP m
JOIN SEFIPREDUZIDO r ON r.EMPRESA = m.EMPRESA AND r.CODIGO = m.REDUZIDO
JOIN TRABALHADOR t ON t.EMPRESA = m.EMPRESA AND t.REGISTRO = m.REGISTRO
LEFT JOIN DIVISAO d ON d.EMPRESA = t.EMPRESA AND d.CODIGO = t.{_DIV}
LEFT JOIN CARGOS c ON c.EMPRESA = t.EMPRESA AND c.CODIGO = t.{_CARGO}
LEFT JOIN TIPOLEGAL tl ON tl.CODIGO = m.TIPOLEGAL
LEFT JOIN TIPO_MOVIMENTO_ESOCIAL tme ON tme.ID = r.TIPO_MOVIMENTO_ESOCIAL
"""


# Parâmetros: empresa, ref, ref_ainda_afastado
_VIGENTE = (
    f"m.EMPRESA = ? AND {temporario()} AND t.SITUACAO IN ({SIT_ATIVAS}) "
    "AND m.DTINI <= ? AND (m.DTFIM IS NULL OR m.DTFIM > ?)"
)

DATA_REFERENCIA = """
SELECT CAST(MAX(m.DT_INCLUSAO) AS DATE) AS DATA_COPIA, MAX(m.DTINI) AS ULTIMO_DTINI
FROM MOVTOSEFIP m
WHERE m.EMPRESA = ?
"""

# 1) Afastados numa data
VIGENTES = select_base() + "WHERE " + _VIGENTE

# 2) Retornos previstos (+ marca se emenda em outro afastamento)
RETORNOS = select_base(f""",
       CASE WHEN EXISTS (
            SELECT 1 FROM MOVTOSEFIP n
            JOIN SEFIPREDUZIDO rn ON rn.EMPRESA = n.EMPRESA AND rn.CODIGO = n.REDUZIDO
            WHERE n.EMPRESA = m.EMPRESA AND n.REGISTRO = m.REGISTRO AND n.ITEM <> m.ITEM
              AND {temporario('rn')}
              AND n.DTINI BETWEEN m.DTFIM - 1 AND m.DTFIM + 1)
       THEN 1 ELSE 0 END AS EMENDA_OUTRO""") + "WHERE " + _VIGENTE + " AND m.DTFIM IS NOT NULL AND m.DTFIM <= ?"

# 3) Histórico do servidor
SERVIDOR = f"""
SELECT t.REGISTRO, t.{_MAT} AS MATRICULA, t.{_NOME} AS NOME, t.{_CPF} AS CPF,
       t.SITUACAO AS SITUACAO_VINCULO, d.NOME AS DIVISAO, c.NOME AS CARGO
FROM TRABALHADOR t
LEFT JOIN DIVISAO d ON d.EMPRESA = t.EMPRESA AND d.CODIGO = t.{_DIV}
LEFT JOIN CARGOS c ON c.EMPRESA = t.EMPRESA AND c.CODIGO = t.{_CARGO}
WHERE t.EMPRESA = ? AND t.REGISTRO = ?
"""

HISTORICO = f"""
SELECT m.ITEM, m.REDUZIDO, r.NOME AS TIPO, r.CAUSA, ca.NOME AS CAUSA_NOME,
       r.SEFIPSAI, r.SEFIPENT,
       CASE WHEN {temporario()} THEN 1 ELSE 0 END AS TEMPORARIO,
       m.DTINI, m.DTFIM, m.DTALTA, m.STATUS_ESOCIAL, tme.CODIGO AS MOTIVO_CODIGO,
       tl.NOME AS DOCUMENTO_TIPO, m.NUMDOCUMENTO AS DOCUMENTO_NUMERO, m.DTDOCUMENTO AS DOCUMENTO_DATA,
       r.ABATE_TEMPOSERVICO, r.ABATE_TEMPOCONTRIB, r.ABATE_FERIAS, r.ABATE_LICENCAPREMIO,
       m.DT_INCLUSAO
FROM MOVTOSEFIP m
LEFT JOIN SEFIPREDUZIDO r ON r.EMPRESA = m.EMPRESA AND r.CODIGO = m.REDUZIDO
LEFT JOIN CAUSAS ca ON ca.CODIGO = r.CAUSA
LEFT JOIN TIPOLEGAL tl ON tl.CODIGO = m.TIPOLEGAL
LEFT JOIN TIPO_MOVIMENTO_ESOCIAL tme ON tme.ID = r.TIPO_MOVIMENTO_ESOCIAL
WHERE m.EMPRESA = ? AND m.REGISTRO = ?
ORDER BY m.DTINI DESC, m.ITEM DESC
"""

# 4a) Afastamentos que tocam um ano (para dias acumulados)
# Parâmetros: empresa, fim_exclusivo_do_ano, inicio_ano_ainda_afastado
NO_ANO = select_base() + (
    f"WHERE m.EMPRESA = ? AND {temporario()} AND t.SITUACAO IN ({SIT_ATIVAS}) "
    "AND m.DTINI < ? AND (m.DTFIM IS NULL OR m.DTFIM > ?)"
)


# 4b) Períodos de afastamento de uma lista de registros (para afastamento contínuo)
def periodos_dos_registros(qtd: int) -> str:
    marcadores = ", ".join("?" * qtd)
    return f"""
SELECT m.REGISTRO, m.DTINI, m.DTFIM
FROM MOVTOSEFIP m
JOIN SEFIPREDUZIDO r ON r.EMPRESA = m.EMPRESA AND r.CODIGO = m.REDUZIDO
WHERE m.EMPRESA = ? AND {temporario()} AND m.DTINI <= ? AND m.REGISTRO IN ({marcadores})
"""


# 5) eSocial
ESOCIAL_LANCAMENTOS = f"""
SELECT m.REDUZIDO, r.NOME AS TIPO, r.TIPO_MOVIMENTO_ESOCIAL AS MOTIVO_ID,
       tme.CODIGO AS MOTIVO_CODIGO, tme.DESCRICAO AS MOTIVO_DESCRICAO, tme.DTFIM AS MOTIVO_DTFIM,
       m.STATUS_ESOCIAL, m.DTINI, m.DTFIM
FROM MOVTOSEFIP m
JOIN SEFIPREDUZIDO r ON r.EMPRESA = m.EMPRESA AND r.CODIGO = m.REDUZIDO
LEFT JOIN TIPO_MOVIMENTO_ESOCIAL tme ON tme.ID = r.TIPO_MOVIMENTO_ESOCIAL
WHERE m.EMPRESA = ? AND {temporario()} AND m.DTINI >= ?
"""

# Parâmetros: desde (subconsulta), empresa
ESOCIAL_TIPOS_COM_PROBLEMA = f"""
SELECT r.CODIGO AS REDUZIDO, r.NOME AS TIPO, r.SEFIPSAI, r.SEFIPENT,
       r.TIPO_MOVIMENTO_ESOCIAL AS MOTIVO_ID, tme.TIPO AS MOTIVO_TIPO,
       tme.CODIGO AS MOTIVO_CODIGO, tme.DESCRICAO AS MOTIVO_DESCRICAO, tme.DTFIM AS MOTIVO_DTFIM,
       (SELECT COUNT(*) FROM MOVTOSEFIP x
         WHERE x.EMPRESA = r.EMPRESA AND x.REDUZIDO = r.CODIGO AND x.DTINI >= ?) AS LANCAMENTOS_DESDE,
       (SELECT MAX(x.DTINI) FROM MOVTOSEFIP x
         WHERE x.EMPRESA = r.EMPRESA AND x.REDUZIDO = r.CODIGO) AS ULTIMO_USO
FROM SEFIPREDUZIDO r
LEFT JOIN TIPO_MOVIMENTO_ESOCIAL tme ON tme.ID = r.TIPO_MOVIMENTO_ESOCIAL
WHERE r.EMPRESA = ? AND {temporario()}
  AND (r.TIPO_MOVIMENTO_ESOCIAL IS NULL OR tme.ID IS NULL
       OR tme.DTFIM IS NOT NULL OR tme.TIPO <> 0)
ORDER BY 10 DESC
"""


def esocial_pendencias(condicao_status: str, com_tipo: bool) -> str:
    sql = select_base(", tme.DESCRICAO AS MOTIVO_DESCRICAO") + (
        f"WHERE m.EMPRESA = ? AND {temporario()} AND m.DTINI >= ? AND ({condicao_status})"
    )
    if com_tipo:
        sql += " AND m.REDUZIDO = ?"
    return sql + " ORDER BY m.DTINI DESC"


# 6) Erros de lançamento
SOBREPOSTOS = f"""
SELECT a.REGISTRO, t.{_MAT} AS MATRICULA, t.{_NOME} AS NOME, d.NOME AS DIVISAO,
       a.ITEM AS A_ITEM, a.REDUZIDO AS A_REDUZIDO, ra.NOME AS A_TIPO, a.DTINI AS A_DTINI, a.DTFIM AS A_DTFIM,
       b.ITEM AS B_ITEM, b.REDUZIDO AS B_REDUZIDO, rb.NOME AS B_TIPO, b.DTINI AS B_DTINI, b.DTFIM AS B_DTFIM
FROM MOVTOSEFIP a
JOIN SEFIPREDUZIDO ra ON ra.EMPRESA = a.EMPRESA AND ra.CODIGO = a.REDUZIDO
JOIN MOVTOSEFIP b ON b.EMPRESA = a.EMPRESA AND b.REGISTRO = a.REGISTRO AND b.ITEM > a.ITEM
JOIN SEFIPREDUZIDO rb ON rb.EMPRESA = b.EMPRESA AND rb.CODIGO = b.REDUZIDO
JOIN TRABALHADOR t ON t.EMPRESA = a.EMPRESA AND t.REGISTRO = a.REGISTRO
LEFT JOIN DIVISAO d ON d.EMPRESA = t.EMPRESA AND d.CODIGO = t.{_DIV}
WHERE a.EMPRESA = ? AND {temporario('ra')} AND {temporario('rb')}
  AND (a.DTINI >= ? OR b.DTINI >= ?)
  AND b.DTINI <= COALESCE(a.DTFIM, DATE '2999-12-31')
  AND a.DTINI <= COALESCE(b.DTFIM, DATE '2999-12-31')
ORDER BY a.REGISTRO, a.DTINI
"""

SEM_TIPO = f"""
SELECT m.REGISTRO, t.{_MAT} AS MATRICULA, t.{_NOME} AS NOME, t.SITUACAO AS SITUACAO_VINCULO,
       d.NOME AS DIVISAO, m.ITEM, m.DTINI, m.DTFIM, m.DT_INCLUSAO, m.STATUS_ESOCIAL
FROM MOVTOSEFIP m
LEFT JOIN TRABALHADOR t ON t.EMPRESA = m.EMPRESA AND t.REGISTRO = m.REGISTRO
LEFT JOIN DIVISAO d ON d.EMPRESA = t.EMPRESA AND d.CODIGO = t.{_DIV}
WHERE m.EMPRESA = ? AND m.REDUZIDO IS NULL
ORDER BY m.DTINI DESC
"""

# Parâmetros: empresa, ref, ref_ainda_afastado, limite_uso
TIPO_DESCONTINUADO = VIGENTES + """
  AND NOT EXISTS (SELECT 1 FROM MOVTOSEFIP x
                  WHERE x.EMPRESA = m.EMPRESA AND x.REDUZIDO = m.REDUZIDO AND x.DTINI > ?)
"""

# Parâmetros: empresa, ref, ref_ainda_afastado
DESLIGADO_COM_AFASTAMENTO = select_base() + (
    f"WHERE m.EMPRESA = ? AND {temporario()} AND t.SITUACAO = {SIT_DESLIGADO} "
    "AND m.DTINI <= ? AND (m.DTFIM IS NULL OR m.DTFIM > ?)"
)

# 7) Abatimento de tempo de serviço/contribuição — parâmetros: empresa, ref
ABATE_TEMPO = select_base(", r.ABATE_TEMPOSERVICO, r.ABATE_TEMPOCONTRIB") + (
    f"WHERE m.EMPRESA = ? AND {temporario()} AND t.SITUACAO IN ({SIT_ATIVAS}) AND m.DTINI <= ? "
    "AND (r.ABATE_TEMPOSERVICO = 'S' OR r.ABATE_TEMPOCONTRIB = 'S')"
)

# 8) Maternidade/paternidade sem filho cadastrado — parâmetros: empresa, desde, ref, ref
MATERNIDADE_SEM_DEPENDENTE = select_base(""",
       (SELECT COUNT(*) FROM DEPENDENTES q
         WHERE q.EMPRESA = m.EMPRESA AND q.REGISTRO = m.REGISTRO) AS QTD_DEPENDENTES""") + f"""
WHERE m.EMPRESA = ?
  AND m.REDUZIDO IN ({_lista_int(C.TIPOS_MATERNIDADE + C.TIPOS_PATERNIDADE)})
  AND t.SITUACAO IN ({SIT_ATIVAS})
  AND m.DTINI >= ? AND m.DTINI <= ?
  AND NOT EXISTS (
      SELECT 1 FROM DEPENDENTES dep
      WHERE dep.EMPRESA = m.EMPRESA AND dep.REGISTRO = m.REGISTRO
        AND dep.{_NASC} >= m.DTINI - {int(C.JANELA_NASCIMENTO_ANTES_DIAS)}
        AND dep.{_NASC} <= COALESCE(m.DTFIM, CAST(? AS DATE)))
ORDER BY m.DTINI DESC
"""
