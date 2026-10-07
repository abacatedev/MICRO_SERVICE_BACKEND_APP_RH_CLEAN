"""Regras do diagnóstico (funções puras) e rotas, sem Firebird."""
from datetime import date

from tests.test_fluxo import auth, ctx  # noqa: F401  (reaproveita o ambiente de teste)

from app.rh import diagnostico, regras

HOJE = date(2026, 10, 6)
CPF_OK = ["52998224725", "11144477735", "39053344705", "12345678909"]


def cpf_de_teste(n: int) -> str:
    """CPF válido e único para cada número (só para os testes)."""
    base = f"{700000000 + n:09d}"
    for tamanho in (9, 10):
        soma = sum(int(base[i]) * (tamanho + 1 - i) for i in range(tamanho))
        base += str((soma * 10) % 11 % 10)
    return base


def servidor(registro="000001", **extra):
    base = {
        "REGISTRO": registro, "MATRICULA": 10, "CONTRATO": 1, "NOME": "SERVIDOR " + registro, "CPF": CPF_OK[0],
        "PIS": "12285091984", "ELEITOR": "123456780191", "DTNASCIMENTO": date(1970, 5, 1),
        "NOMEMAE": "MAE", "DTADMISSAO": date(2010, 2, 3), "ESTADOCIVIL": "2", "CARGOATUAL_NOME": "AGENTE", "CELULAR": "65999990000", "EMAIL": "a@b.gov.br", "DTTERMINO": None,
        "SITUACAO_NOME": "Normal", "VINCULO_NOME": "EFETIVO", "DIVISAO_NOME": "SAUDE",
        "LOCAL_TRABALHO_NOME": "UBS", "IDADE_IRRF_MASC": 21, "IDADE_IRRF_FEMI": 21,
        "IDADE_IRRF_UNIVERSITARIO": 24, "IDADESALFAMMASC": 14, "IDADESALFAMFEM": 14,
    }
    return {**base, **extra}


def dependente(registro="000001", item=1, **extra):
    base = {
        "REGISTRO": registro, "ITEM": item, "NOME": f"DEP {item}", "CPF": cpf_de_teste(item),
        "DTNASC": date(2015, 1, 1), "SEXO": "M", "PARENTESCO": "03", "PARENTESCO_NOME": "Filho(a)",
        "IRRF": "N", "SALFAMILIA": "N", "UNIVERSITARIO": "N", "DEFICIENTE": "N",
        "FAIXA_IDADE": None, "DTENTREGA": date(2025, 3, 1), "NUMREGISTRO": "123", "NOMEMAE": "MAE DO DEP",
    }
    return {**base, **extra}


def codigos(resultado):
    return {c: len(v) for c, v in resultado.items() if v}


def test_utilitarios():
    assert regras.cpf_valido("529.982.247-25") and not regras.cpf_valido("52998224724")
    assert not regras.cpf_valido("00000000000") and not regras.cpf_valido("123")
    for falso in (None, "", "  ", "0", "00000000000", "99999999999"):
        assert regras.ausente(falso)
    assert not regras.ausente("12285091984") and not regras.ausente("SN")
    assert regras.anos_entre(date(2007, 1, 4), HOJE) == 19
    assert regras.anos_entre(date(2001, 8, 13), HOJE) == 25
    assert regras.anos_entre(date(2011, 10, 7), HOJE) == 14  # aniversário amanhã
    assert regras.anos_entre(None, HOJE) is None


def test_cadastro_limpo_nao_gera_ocorrencia():
    r = regras.avaliar([servidor()], [dependente()], set(), HOJE)
    assert codigos(r) == {}


def test_caso_real_do_registro_001750():
    """Três filhos marcados com IRRF e salário-família: 19, 25 e 15 anos."""
    deps = [
        dependente(item=1, DTNASC=date(2007, 1, 4), IRRF="S", SALFAMILIA="S"),
        dependente(item=2, DTNASC=date(2001, 8, 13), IRRF="S", SALFAMILIA="S", SEXO="F"),
        dependente(item=3, DTNASC=date(2011, 6, 21), IRRF="S", SALFAMILIA="S", SEXO="F"),
    ]
    r = regras.avaliar([servidor()], deps, set(), HOJE)
    assert [o["ITEM"] for o in r["D03"]] == [2]           # só a de 25 passou do IRRF
    assert [o["ITEM"] for o in r["D04"]] == [1, 2, 3]     # os três passaram dos 14
    assert [o["ITEM"] for o in r["D05"]] == [2]           # "menor de 21" com 25
    assert "25 anos" in r["D03"][0]["DETALHE"] and r["D03"][0]["SERVIDOR"] == "SERVIDOR 000001"


def test_irrf_universitario_deficiente_e_parentesco_sem_limite():
    deps = [
        dependente(item=1, DTNASC=date(2003, 1, 1), IRRF="S", UNIVERSITARIO="S"),            # 23, univ: ok
        dependente(item=2, DTNASC=date(2001, 1, 1), IRRF="S", UNIVERSITARIO="S"),            # 25, univ: fora
        dependente(item=3, DTNASC=date(1990, 1, 1), IRRF="S", DEFICIENTE="S", PARENTESCO="04"),  # sem limite
        dependente(item=4, DTNASC=date(1975, 1, 1), IRRF="S", PARENTESCO="01"),              # cônjuge
        dependente(item=5, DTNASC=date(2005, 1, 1), IRRF="S"),                               # 21: ainda dentro
        dependente(item=6, DTNASC=date(2004, 1, 1), IRRF="S"),                               # 22: fora
    ]
    r = regras.avaliar([servidor(DTNASCIMENTO=date(1960, 1, 1))], deps, set(), HOJE)
    assert [o["ITEM"] for o in r["D03"]] == [2, 6]
    assert "universitário" in r["D03"][0]["DETALHE"]


def test_regras_de_cpf_e_parentesco():
    s = servidor(DTNASCIMENTO=date(1980, 1, 1))
    deps = [
        dependente(item=1, CPF=""),                                         # D01
        dependente(item=2, CPF="12345678900"),                              # D02 inválido
        dependente(item=3, CPF=s["CPF"]),                                   # D02 igual ao servidor
        dependente(item=4, CPF=CPF_OK[3]), dependente(item=5, CPF=CPF_OK[3]),  # D02 repetido
        dependente(item=6, PARENTESCO="01", DTNASC=date(1982, 1, 1)),
        dependente(item=7, PARENTESCO="02", DTNASC=date(1983, 1, 1)),       # D06 (dois)
        dependente(item=8, DTNASC=date(1985, 1, 1)),                        # D07: filho 5 anos mais novo; D05
        dependente(item=9, PARENTESCO="13", SEXO="M", DTNASC=date(1975, 1, 1)),  # D08 e D07
        dependente(item=10, PARENTESCO="00"),                               # D10
        dependente(item=11, NOME="ANA  LIMA", DTNASC=date(2016, 2, 2)),
        dependente(item=12, NOME="Ana Lima", DTNASC=date(2016, 2, 2)),      # D09
    ]
    r = regras.avaliar([s], deps, set(), HOJE)
    assert [o["ITEM"] for o in r["D01"]] == [1]
    assert {o["ITEM"]: o["DETALHE"] for o in r["D02"]} == {
        2: "CPF inválido", 3: "Igual ao CPF do servidor",
        4: "CPF repetido no mesmo servidor", 5: "CPF repetido no mesmo servidor",
    }
    assert [o["ITEM"] for o in r["D06"]] == [6, 7]
    assert [o["ITEM"] for o in r["D07"]] == [8, 9]
    assert [o["ITEM"] for o in r["D08"]] == [9]
    assert [o["ITEM"] for o in r["D09"]] == [11, 12]
    assert [o["ITEM"] for o in r["D10"]] == [10]


def test_regras_do_servidor_e_indicadores():
    servidores = [
        servidor("000001", CELULAR=" ", EMAIL=None, ELEITOR="0", PIS="99999999999", NOMEMAE="",
                 CPF="00000000000", DTTERMINO=date(2026, 1, 1)),
        servidor("000002", CPF=CPF_OK[1]),                 # sem dependentes em lugar nenhum
        servidor("000003", CPF=CPF_OK[2]),                 # dependentes ficaram no registro antigo
        servidor("000004", CPF=CPF_OK[3]),                 # dois vínculos ativos, dependentes só no 000005
        servidor("000005", CPF=CPF_OK[3]),
        servidor("000006", CPF="12345678900"),             # CPF inválido
    ]
    deps = [dependente("000005"), dependente("000001"), dependente("000006")]
    r = regras.avaliar(servidores, deps, {CPF_OK[2]}, HOJE)
    for c in ("S01", "S02", "S03", "S04", "S05", "V01"):
        assert [o["REGISTRO"] for o in r[c]] == ["000001"], c
    assert {o["REGISTRO"]: o["DETALHE"] for o in r["S06"]} == {"000001": "CPF ausente", "000006": "CPF inválido"}
    assert sorted(o["REGISTRO"] for o in r["V02"]) == ["000004", "000005"]
    assert [o["REGISTRO"] for o in r["I01"]] == ["000002"]
    assert sorted(o["REGISTRO"] for o in r["I02"]) == ["000003", "000004"]


# ---------------- rotas ----------------

def _preparar(monkeypatch):
    servidores = [servidor("000001"), servidor("000002", CPF=CPF_OK[1], EMAIL="")]
    deps = [
        dependente("000001", 1, DTNASC=date(2001, 8, 13), IRRF="S", SALFAMILIA="S"),
        dependente("000001", 2, CPF=""),
    ]
    monkeypatch.setattr(diagnostico, "carregar", lambda: (servidores, deps, set()))
    diagnostico.limpar_cache()


def test_painel_lista_csv_e_ficha(ctx, monkeypatch):  # noqa: F811
    _preparar(monkeypatch)
    http, rh = ctx["http"], auth(ctx["users"]["rh"])

    painel = http.get("/rh/diagnostico", headers=rh).json()
    assert painel["universo"] == {"empresa": "001", "situacoes": ["1", "3"], "vinculos": 2, "dependentes": 2}
    contagem = {r["codigo"]: (r["servidores"], r["ocorrencias"]) for r in painel["regras"]}
    assert contagem["D01"] == (1, 1) and contagem["D03"] == (1, 1) and contagem["D04"] == (1, 1)
    assert contagem["S02"] == (1, 1) and contagem["I01"] == (1, 1) and contagem["S01"] == (0, 0)
    assert len(painel["regras"]) == len(regras.REGRAS)
    assert painel["resumo"] == {"vinculos": 2, "com_erro": 1, "com_alerta": 1, "sem_pendencia": 0}
    assert [r["tipo"] for r in painel["regras"]][:3] == ["erro", "erro", "erro"]  # erros primeiro
    assert all(r["descricao"] and r["orientacao"] for r in painel["regras"])
    divisoes = http.get("/rh/diagnostico/por-divisao", headers=rh).json()
    assert divisoes == [{"divisao": "SAUDE", "vinculos": 2, "com_erro": 1, "com_alerta": 1, "sem_pendencia": 0}]

    lista = http.get("/rh/diagnostico/d03", headers=rh).json()
    assert lista["total"] == 1 and lista["itens"][0]["DEPENDENTE"] == "DEP 1"
    assert lista["itens"][0]["REGISTRO"] == "000001" and lista["itens"][0]["CONTRATO"] == 1
    assert lista["itens"][0]["DIVISAO"] == "SAUDE" and lista["regra"]["tipo"] == "erro"
    assert http.get("/rh/diagnostico/X99", headers=rh).status_code == 404

    arquivo = http.get("/rh/diagnostico/D03", headers=rh, params={"formato": "csv"})
    assert arquivo.status_code == 200 and "diagnostico_D03.csv" in arquivo.headers["content-disposition"]
    linhas = arquivo.text.lstrip("\ufeff").splitlines()
    assert linhas[0] == (
        "REGISTRO;MATRICULA;CONTRATO;SERVIDOR;CPF_SERVIDOR;ADMISSAO;SITUACAO;VINCULO;CARGO;DIVISAO;LOCAL_TRABALHO;CELULAR;EMAIL;"
        "ITEM;DEPENDENTE;PARENTESCO;NASCIMENTO;IDADE;CPF_DEPENDENTE;DEPENDENTE_IRRF;SALARIO_FAMILIA;FAIXA_IDADE;"
        "UNIVERSITARIO;DEFICIENTE;DOCUMENTOS;DATA_ENTREGA;NOME_MAE;DETALHE"
    )
    assert linhas[1].startswith("000001;10;1;SERVIDOR 000001;529.982.247-25;03/02/2010;Normal;EFETIVO;AGENTE;SAUDE;UBS;65999990000;a@b.gov.br;1;DEP 1;Filho(a);13/08/2001;25;")
    assert ";Sim;Sim;Não;Não;Não;CPF, Certidão;01/03/2025;MAE DO DEP;" in linhas[1]

    ficha = http.get("/rh/servidores/1/pendencias", headers=rh).json()
    assert ficha["registro"] == "000001" and ficha["total"] == 4
    assert [p["codigo"] for p in ficha["pendencias"]] == ["D01", "D03", "D04", "D05"]
    assert http.get("/rh/servidores/999/pendencias", headers=rh).status_code == 404


def test_consulta_ve_painel_mas_nao_lista_nominal(ctx, monkeypatch):  # noqa: F811
    _preparar(monkeypatch)
    http, consulta = ctx["http"], auth(ctx["users"]["consulta"])
    assert http.get("/rh/diagnostico", headers=consulta).status_code == 200
    assert http.get("/rh/diagnostico/D01", headers=consulta).status_code == 403
    assert http.get("/rh/servidores/1/pendencias", headers=consulta).status_code == 403
    assert http.get("/rh/diagnostico").status_code == 401


def test_dominios_e_cache(ctx, monkeypatch):  # noqa: F811
    http, rh = ctx["http"], auth(ctx["users"]["rh"])
    assert http.get("/rh/dominios/vinculos", headers=rh).status_code == 200
    sql, params = ctx["consultas"][-1]
    assert sql == "SELECT CODIGO, NOME FROM VINCULO WHERE EMPRESA = ? ORDER BY NOME" and params == ("001",)
    assert http.get("/rh/dominios/parentescos", headers=rh).status_code == 200
    assert "SIPREV_TIPODEPEN" in ctx["consultas"][-1][0]
    assert http.get("/rh/dominios/senhas", headers=rh).status_code == 404

    chamadas = []
    monkeypatch.setattr(diagnostico, "carregar", lambda: (chamadas.append(1), ([], [], set()))[1])
    diagnostico.limpar_cache()
    http.get("/rh/diagnostico", headers=rh)
    http.get("/rh/diagnostico", headers=rh)
    assert len(chamadas) == 1  # segunda chamada veio do cache
    http.get("/rh/diagnostico", headers=rh, params={"atualizar": True})
    assert len(chamadas) == 2


def test_faixa_de_idade_divide_irrf_e_salario_familia():
    deps = [
        dependente(item=1, DTNASC=date(1990, 8, 21), IRRF="S", SALFAMILIA="S", FAIXA_IDADE="N"),
        dependente(item=2, DTNASC=date(1990, 8, 21), IRRF="S", SALFAMILIA="S", FAIXA_IDADE="S"),
        dependente(item=3, DTNASC=date(1990, 8, 21), IRRF="S", SALFAMILIA="S", FAIXA_IDADE=None),
    ]
    r = regras.avaliar([servidor(DTNASCIMENTO=date(1960, 1, 1))], deps, set(), HOJE)
    assert [o["ITEM"] for o in r["D03"]] == [1, 3] and [o["ITEM"] for o in r["D13"]] == [2]
    assert [o["ITEM"] for o in r["D04"]] == [1, 3] and [o["ITEM"] for o in r["D14"]] == [2]
    assert r["D13"][0]["FAIXA_IDADE"] == "Sim" and r["D03"][0]["FAIXA_IDADE"] == "Não"
    assert regras.POR_CODIGO["D03"].tipo == "erro" and regras.POR_CODIGO["D13"].tipo == "alerta"


def test_documentacao_certidao_entrega_e_estado_civil():
    sem_nada = {"CPF": "", "NUMREGISTRO": None}
    deps = [
        dependente(item=1, **sem_nada),                                   # D01 + D11 + D12
        dependente(item=2, CPF="", RG="1234567"),                         # D01, mas tem RG e certidão
        dependente(item=3, NUMREGISTRO="", NOMECARTORIO=" "),             # D12: filho sem certidão
        dependente(item=4, PARENTESCO="01", NUMREGISTRO=None, DTNASC=date(1983, 11, 5)),  # cônjuge: sem D12
        dependente(item=5, DTENTREGA=date(2014, 2, 1)),                   # D15
        dependente(item=6, **sem_nada, TIPODOC=55, NUMDOC="34056/2026"),  # tem outro documento
    ]
    r = regras.avaliar([servidor(ESTADOCIVIL="1")], deps, set(), HOJE)
    assert [o["ITEM"] for o in r["D11"]] == [1] and r["D11"][0]["DOCUMENTOS"] == "Nenhum"
    assert [o["ITEM"] for o in r["D01"]] == [1, 2, 6]
    assert [o["ITEM"] for o in r["D12"]] == [1, 3, 6]
    assert [o["ITEM"] for o in r["D15"]] == [5] and "há 12 anos" in r["D15"][0]["DETALHE"]
    assert r["D01"][1]["DOCUMENTOS"] == "RG, Certidão" and r["D01"][2]["DOCUMENTOS"] == "Outro documento"
    assert [o["REGISTRO"] for o in r["S07"]] == ["000001"] and "DEP 4" in r["S07"][0]["DETALHE"]
    assert regras.avaliar([servidor(ESTADOCIVIL="2")], deps, set(), HOJE)["S07"] == []
    assert regras.POR_CODIGO["D11"].tipo == "erro"
