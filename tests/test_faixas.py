"""Faixa etária dos dependentes: funções puras e rota, sem Firebird."""
from datetime import date

from tests.test_fluxo import auth, ctx  # noqa: F401

from app.rh import faixas

HOJE = date(2026, 10, 21)


def dep(nasc, **extra):
    base = {"REGISTRO": "000001", "DIVISAO": "000003", "DIVISAO_NOME": "SAUDE", "SUBDIVISAO": "003001",
            "SUBDIVISAO_NOME": "SAUDE ADM", "VINCULO": "02", "VINCULO_NOME": "EFETIVO",
            "IDADE_IRRF_MASC": 21, "IDADE_IRRF_FEMI": 21, "IDADE_IRRF_UNIVERSITARIO": 24,
            "IDADESALFAMMASC": 14, "IDADESALFAMFEM": 14, "ITEM": 1, "DTNASC": nasc, "SEXO": "M",
            "PARENTESCO": "03", "IRRF": "N", "SALFAMILIA": "N", "UNIVERSITARIO": "N", "DEFICIENTE": "N"}
    return {**base, **extra}


def test_faixa_de():
    assert faixas.faixa_de(0) == "0-13" and faixas.faixa_de(13) == "0-13"
    assert faixas.faixa_de(14) == "14-17" and faixas.faixa_de(20) == "18-20"
    assert faixas.faixa_de(21) == "21-23" and faixas.faixa_de(24) == "24-29"
    assert faixas.faixa_de(39) == "30-39" and faixas.faixa_de(75) == "40+"
    assert faixas.faixa_de(None) == "Sem data"
    assert faixas.idade(date(2030, 1, 1), HOJE) is None  # nascimento no futuro


def test_irrf_perde_no_ano_seguinte():
    # completa 21 em 2026: ainda vale em 2026
    assert faixas.desconformidades(dep(date(2005, 3, 1), IRRF="S"), HOJE) == (False, False)
    # completou 21 em 2025: fora em 2026
    assert faixas.desconformidades(dep(date(2004, 12, 31), IRRF="S"), HOJE) == (True, False)
    # universitário: limite 24
    assert faixas.desconformidades(dep(date(2004, 1, 1), IRRF="S", UNIVERSITARIO="S"), HOJE) == (False, False)
    assert faixas.desconformidades(dep(date(2001, 1, 1), IRRF="S", UNIVERSITARIO="S"), HOJE) == (True, False)
    # deficiente e cônjuge não entram
    assert faixas.desconformidades(dep(date(1990, 1, 1), IRRF="S", DEFICIENTE="S"), HOJE) == (False, False)
    assert faixas.desconformidades(dep(date(1990, 1, 1), IRRF="S", PARENTESCO="01"), HOJE) == (False, False)


def test_salario_familia_no_aniversario():
    assert faixas.desconformidades(dep(date(2012, 10, 22), SALFAMILIA="S"), HOJE) == (False, False)
    assert faixas.desconformidades(dep(date(2012, 10, 21), SALFAMILIA="S"), HOJE) == (False, True)


def test_montar_e_filtros():
    linhas = [
        dep(date(2015, 1, 1)),
        dep(date(2004, 1, 1), IRRF="S", ITEM=2),
        dep(None, ITEM=3),
        dep(date(2000, 1, 1), REGISTRO="000002", DIVISAO="000004", DIVISAO_NOME="EDUCACAO", SALFAMILIA="S"),
    ]
    r = faixas.montar(linhas, HOJE)
    por = {f["faixa"]: f for f in r["faixas"]}
    assert r["dependentes"] == 4 and r["vinculos_com_dependentes"] == 2 and r["sem_data"] == 1
    assert por["0-13"]["dependentes"] == 1 and not por["0-13"]["exige_comprovacao"]
    assert por["21-23"]["irrf_fora_do_limite"] == 1 and por["21-23"]["exige_comprovacao"]
    assert por["24-29"]["salario_familia_fora_do_limite"] == 1
    assert r["em_desconformidade"] == 2
    assert [f["faixa"] for f in r["faixas"]][-1] == "Sem data"

    assert faixas.montar(linhas, HOJE, divisao="3")["dependentes"] == 3
    assert faixas.montar(linhas, HOJE, divisao="educacao")["dependentes"] == 1
    assert faixas.montar(linhas, HOJE, divisao="000004", vinculo="02")["dependentes"] == 1
    assert faixas.montar(linhas, HOJE, divisao="999")["dependentes"] == 0


def test_rota(ctx, monkeypatch):  # noqa: F811
    http, users = ctx["http"], ctx["users"]
    monkeypatch.setattr(faixas, "carregar", lambda: [dep(date(2015, 1, 1)), dep(date(2004, 1, 1), IRRF="S")])
    faixas._cache.clear()
    r = http.get("/rh/indicadores/faixa-dependentes", headers=auth(users["consulta"]), params={"divisao": "3"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["dependentes"] == 2 and corpo["em_desconformidade"] == 1
    assert len(corpo["faixas"]) == 8 and corpo["filtros"]["divisao"] == "3"
    assert http.get("/rh/indicadores/faixa-dependentes").status_code == 401
