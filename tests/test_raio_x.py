"""Testes do Raio-X das Secretarias: agregação por divisão, sem acessar o Firebird."""
from collections import Counter
from datetime import date, datetime, timezone

from app.rh import diagnostico as dg
from app.rh import regras


def _servidor(registro: str, divisao: str, nome: str, local: str = "SEDE", cargo: str = "AUX", vinculo: str = "EFETIVO"):
    return {
        "REGISTRO": registro, "DIVISAO": divisao, "DIVISAO_NOME": nome,
        "LOCAL_TRABALHO_NOME": local, "CARGOATUAL_NOME": cargo, "VINCULO_NOME": vinculo,
    }


def _dados() -> dict:
    servidores = {
        "000001": _servidor("000001", "000006", "SECRETARIA MUNICIPAL DE EDUCAÇÃO", "EM A", "PROF"),
        "000002": _servidor("000002", "000006", "SECRETARIA MUNICIPAL DE EDUCAÇÃO", "EM A", "PROF"),
        "000003": _servidor("000003", "000006", "SECRETARIA MUNICIPAL DE EDUCAÇÃO", "EM A", "PROF", "CONTRATADO"),
        "000004": _servidor("000004", "000005", "SECRETARIA MUNICIPAL DE SAÚDE", None, "ENF"),
        "000005": {**_servidor("000005", "", None), "DIVISAO": None, "DIVISAO_NOME": None},
    }
    por_regra = {r.codigo: [] for r in regras.REGRAS}
    # IRRF: o vínculo 000001 aparece nas duas regras e em dois dependentes; deve contar uma vez
    por_regra["D03"] = [{"REGISTRO": "000001"}, {"REGISTRO": "000001"}]
    por_regra["D13"] = [{"REGISTRO": "000001"}, {"REGISTRO": "000002"}]
    por_regra["S02"] = [{"REGISTRO": "000004"}]
    por_regra["D12"] = [{"REGISTRO": "000003"}, {"REGISTRO": "000004"}]
    classe = {"000001": "erro", "000002": "alerta", "000003": "ok", "000004": "alerta", "000005": "ok"}
    return {
        "gerado_em": datetime(2026, 10, 19, tzinfo=timezone.utc),
        "servidores": servidores,
        "por_regra": por_regra,
        "classe": classe,
        "deps_por_registro": Counter({"000001": 2, "000002": 1, "000004": 3}),
    }


def test_cartao_conta_o_vinculo_uma_vez():
    r = dg.agregar_por_divisao(_dados())
    assert r["total"]["cartoes"]["irrf"] == 2          # 000001 e 000002, sem repetir
    assert r["total"]["regras"]["D03"] == 1
    assert r["total"]["regras"]["D13"] == 2


def test_totais_por_divisao():
    r = dg.agregar_por_divisao(_dados())
    por_cod = {d["codigo"]: d for d in r["divisoes"]}
    edu, sau = por_cod["000006"], por_cod["000005"]
    assert edu["vinculos"] == 3 and edu["dependentes"] == 3
    assert edu["cartoes"]["irrf"] == 2 and edu["cartoes"]["cert"] == 1
    assert edu["com_erro"] == 1 and edu["com_alerta"] == 1 and edu["sem_pendencia"] == 1
    assert edu["conformidade"] == 33.3
    assert sau["cartoes"]["semEmail"] == 1 and sau["dependentes"] == 3
    assert "SEM" in por_cod and por_cod["SEM"]["nome"] == "Sem divisão"


def test_total_bate_com_a_soma_das_divisoes():
    r = dg.agregar_por_divisao(_dados())
    for campo in ("vinculos", "dependentes", "com_erro", "com_alerta", "sem_pendencia"):
        assert r["total"][campo] == sum(d[campo] for d in r["divisoes"])
    for cartao in dg.CARTOES:
        assert r["total"]["cartoes"][cartao["id"]] == sum(d["cartoes"][cartao["id"]] for d in r["divisoes"])


def test_ordem_e_cartoes_declarados():
    r = dg.agregar_por_divisao(_dados())
    assert [d["codigo"] for d in r["divisoes"]][:2] == ["000006", "000005"]
    assert [c["id"] for c in r["cartoes"]] == ["irrf", "salfam", "depCpf", "depNasc", "cert", "semEmail", "semFone"]
    assert [c["id"] for c in r["cartoes"] if c["critica"]] == ["cert"]
    # todo código usado num cartão existe nas regras
    assert all(c in regras.POR_CODIGO for k in dg.CARTOES for c in k["regras"])


def test_perfil_aplica_minimos():
    p = dg.perfil_por_divisao(_dados())["divisoes"]
    assert p["000006"]["locais"] == [{"nome": "EM A", "vinculos": 3}]
    assert p["000006"]["cargos"] == []                      # 3 professores < mínimo de 5
    assert p["000006"]["tipos_vinculo"][0] == {"nome": "EFETIVO", "vinculos": 2}
    assert p["000005"]["locais"] == []                      # 1 vínculo < mínimo de 3


def test_irrf_perde_no_ano_seguinte_ao_limite():
    """Limite 21 (24 universitário): conta a partir do ano seguinte ao que completou o limite."""
    hoje = date(2026, 10, 19)
    servidor = {
        "REGISTRO": "000001", "NOME": "TESTE", "CPF": "52998224725", "CELULAR": "1", "EMAIL": "a@b.c",
        "ELEITOR": "123", "PIS": "12345678900", "NOMEMAE": "MAE",
        "IDADE_IRRF_MASC": 21, "IDADE_IRRF_FEMI": 21, "IDADE_IRRF_UNIVERSITARIO": 24,
    }

    def pendente(nascimento: date, universitario: str = "N") -> bool:
        dep = {"REGISTRO": "000001", "ITEM": 1, "NOME": "FILHO", "PARENTESCO": "03", "SEXO": "M",
               "DTNASC": nascimento, "CPF": "11144477735", "IRRF": "S", "UNIVERSITARIO": universitario}
        return len(regras.avaliar([servidor], [dep], set(), hoje)["D03"]) == 1

    assert not pendente(date(2005, 12, 1))   # completa 21 em dez/2026: ainda dependente
    assert not pendente(date(2005, 1, 1))    # completou 21 em 2026: dependente até 31/12/2026
    assert pendente(date(2004, 12, 31))      # completou 21 em 2025: perdeu em 2026 (antes não contava)
    assert not pendente(date(2002, 6, 1), "S")   # universitário, completa 24 em 2026
    assert pendente(date(2001, 12, 31), "S")     # universitário, completou 24 em 2025


def test_d16_dependente_sem_nascimento():
    servidor = {
        "REGISTRO": "000001", "NOME": "TESTE", "CPF": "52998224725", "CELULAR": "65999999999",
        "EMAIL": "a@b.c", "ELEITOR": "123", "PIS": "12345678900", "NOMEMAE": "MAE",
    }
    dependente = {"REGISTRO": "000001", "ITEM": 1, "NOME": "FILHO", "PARENTESCO": "03", "DTNASC": None, "CPF": None}
    hoje = date(2026, 10, 19)
    out = regras.avaliar([servidor], [dependente], set(), hoje)
    assert len(out["D16"]) == 1 and out["D16"][0]["DETALHE"] == "Data vazia"

    # datas falsas ou futuras contam como ausentes e não geram idade para as outras regras
    for falsa in (date(1900, 1, 1), date(1198, 1, 23), date(2026, 11, 16)):
        dependente.update(DTNASC=falsa, IRRF="S", SALFAMILIA="S")
        servidor.update(IDADE_IRRF_MASC=21, IDADESALFAMMASC=14)
        out = regras.avaliar([servidor], [dependente], set(), hoje)
        assert len(out["D16"]) == 1 and out["D16"][0]["DETALHE"].startswith("Data inválida")
        assert out["D03"] == [] and out["D04"] == [] and out["D05"] == []

    dependente["DTNASC"] = date(2015, 1, 1)
    out = regras.avaliar([servidor], [dependente], set(), hoje)
    assert out["D16"] == []
