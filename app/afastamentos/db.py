"""
Conexão SOMENTE LEITURA com o SIP (Firebird 2.5).

Dentro do backend do RH, reaproveita app.rh.firebird._connect_garantindo_usuario()
(mesmas configurações do .env e recriação automática do usuário SIPANALISE).
Fora dele (testes isolados), conecta com fdb e as variáveis SIP_DB_*.
Em ambos os casos a transação é aberta como READ ONLY.
"""
import os
import re
from contextlib import contextmanager
from decimal import Decimal

import fdb

try:
    from app.rh.firebird import _connect_garantindo_usuario as _conectar_backend
except ImportError:
    _conectar_backend = None

_IDENT = re.compile(r"^[A-Z0-9_$]+$")


def ident(nome: str) -> str:
    """Valida um nome de coluna vindo da config antes de colocá-lo no SQL."""
    if not _IDENT.match(nome or ""):
        raise ValueError(f"Nome de coluna inválido na configuração: {nome!r}")
    return nome


def _conectar_isolado():
    database = next((os.getenv(v) for v in ("SIP_DB_DATABASE", "SIP_DB_PATH", "SIP_DB_NAME") if os.getenv(v)), None)
    if not database:
        raise RuntimeError("Defina SIP_DB_DATABASE no .env (ex.: /firebird/data/SIP_ANALISE_2.FDB).")
    return fdb.connect(
        host=os.getenv("SIP_DB_HOST", "firebird"),
        port=int(os.getenv("SIP_DB_PORT", "3050")),
        database=database,
        user=os.getenv("SIP_DB_USER", "SIPANALISE"),
        password=os.environ["SIP_DB_PASSWORD"],
        charset=os.getenv("SIP_DB_CHARSET", "WIN1252"),
        sql_dialect=int(os.getenv("SIP_DB_DIALECT", "3")),
    )


@contextmanager
def conexao_somente_leitura():
    """Abre conexão com transação READ ONLY e sempre faz rollback ao final."""
    con = _conectar_backend() if _conectar_backend else _conectar_isolado()
    try:
        # O Firebird recusa qualquer escrita numa transação read only.
        con.begin(tpb=fdb.ISOLATION_LEVEL_READ_COMMITED_RO)
        yield con
    finally:
        try:
            con.rollback()
        finally:
            con.close()


def _limpar(valor):
    if isinstance(valor, str):
        return valor.strip()
    if isinstance(valor, (bytes, bytearray)):
        return None  # BLOB binário fica fora da resposta
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    return valor


def consultar(con, sql: str, params=()) -> list[dict]:
    """Executa um SELECT e devolve lista de dicts com chaves em minúsculas."""
    if not sql.lstrip().upper().startswith("SELECT"):
        raise ValueError("Somente SELECT é permitido no SIP")
    cur = con.cursor()
    try:
        cur.execute(sql, tuple(params))
        colunas = [d[0].strip().lower() for d in cur.description]
        return [{c: _limpar(v) for c, v in zip(colunas, linha)} for linha in cur.fetchall()]
    finally:
        cur.close()
