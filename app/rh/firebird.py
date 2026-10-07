"""Acesso SOMENTE LEITURA ao SIP (Firebird 2.5) com fdb + libfbclient."""
import logging

import fdb
import fdb.services

from app.config import settings

log = logging.getLogger("uvicorn.error")
LOGIN_RECUSADO = 335544472  # "Your user name and password are not defined"


def _clean(value):
    if isinstance(value, str):
        return value.rstrip()
    if isinstance(value, (bytes, bytearray)):
        return None  # BLOB binário fica fora da resposta
    return value


def _connect():
    return fdb.connect(
        host=settings.sip_db_host,
        port=settings.sip_db_port,
        database=settings.sip_db_database,
        user=settings.sip_db_user,
        password=settings.sip_db_password,
        charset=settings.sip_db_charset,
        sql_dialect=settings.sip_db_dialect,
    )


def garantir_usuario() -> bool:
    """Cria o usuário de leitura no servidor Firebird se ele não existir.

    No Firebird 2.5 os usuários ficam no banco de segurança do servidor (dentro
    do contêiner), não no arquivo .FDB; por isso somem quando o contêiner é
    recriado. Devolve True quando o usuário foi criado agora.
    """
    if not settings.sip_db_sysdba_password:
        return False
    svc = fdb.services.connect(
        host=f"{settings.sip_db_host}/{settings.sip_db_port}",
        user="SYSDBA",
        password=settings.sip_db_sysdba_password,
    )
    try:
        if svc.user_exists(settings.sip_db_user):
            return False
        user = fdb.services.User(settings.sip_db_user)
        user.password = settings.sip_db_password
        svc.add_user(user)
        log.info("Usuário %s criado no servidor Firebird", settings.sip_db_user)
        return True
    finally:
        svc.close()


def _connect_garantindo_usuario():
    try:
        return _connect()
    except fdb.DatabaseError as exc:
        codigo = exc.args[2] if len(exc.args) > 2 else None
        if codigo != LOGIN_RECUSADO or not garantir_usuario():
            raise
        return _connect()  # usuário recém-criado: tenta mais uma vez


def query(sql: str, params: tuple = ()) -> list[dict]:
    if not sql.lstrip().upper().startswith("SELECT"):
        raise ValueError("Somente SELECT é permitido no SIP")
    conn = _connect_garantindo_usuario()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0].strip() for d in cur.description]
        return [{c: _clean(v) for c, v in zip(cols, row)} for row in cur.fetchall()]
    finally:
        conn.close()
