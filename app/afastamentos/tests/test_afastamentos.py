"""
Testes do módulo de afastamentos (não precisam do Firebird).

Rodar a partir da pasta que contém o pacote `afastamentos`:
    uv run pytest afastamentos/tests -q
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from afastamentos import calculos as K  # noqa: E402
from afastamentos import config as C  # noqa: E402

D = date


# ------------------------------------------------------------------ cálculos
def test_duracao_com_dtfim_dia_do_retorno():
    # Amostra real do SIP: DTINI 18/12/2008, DTFIM 29/12/2008, eSocial fim 28/12 -> 11 dias
    assert K.duracao_dias(D(2008, 12, 18), D(2008, 12, 29)) == 11
    assert K.fim_exclusivo(D(2008, 12, 29)) == D(2008, 12, 29)


def test_duracao_com_dtfim_ultimo_dia(monkeypatch):
    monkeypatch.setattr(C, "DTFIM_E_DIA_DO_RETORNO", False)
    assert K.duracao_dias(D(2008, 12, 18), D(2008, 12, 29)) == 12
    assert K.param_ainda_afastado(D(2026, 9, 29)) == D(2026, 9, 28)


def test_unir_intervalos_sobrepostos_e_emendados():
    ints = [(D(2026, 1, 1), D(2026, 1, 11)), (D(2026, 1, 5), D(2026, 1, 20)), (D(2026, 1, 21), D(2026, 1, 25))]
    assert K.unir_intervalos(ints) == [(D(2026, 1, 1), D(2026, 1, 20)), (D(2026, 1, 21), D(2026, 1, 25))]
    assert K.unir_intervalos(ints, tolerancia_dias=1) == [(D(2026, 1, 1), D(2026, 1, 25))]


def test_dias_no_periodo_nao_conta_duas_vezes_e_recorta_ano():
    lanc = [(D(2025, 12, 20), D(2026, 1, 11)),   # 10 dias em 2026
            (D(2026, 1, 5), D(2026, 1, 15)),     # sobrepõe: só +4
            (D(2026, 3, 1), None)]               # em aberto, conta até o fim informado
    assert K.dias_no_periodo(lanc, D(2026, 1, 1), D(2026, 3, 11)) == 14 + 10


def test_inicio_bloco_continuo_licenca_renovada():
    lanc = [(D(2026, 5, 1), D(2026, 6, 1)), (D(2026, 6, 1), D(2026, 8, 1)), (D(2026, 8, 2), D(2026, 12, 1))]
    assert K.inicio_bloco_continuo(lanc, D(2026, 9, 29)) == D(2026, 5, 1)
    assert K.inicio_bloco_continuo(lanc, D(2026, 9, 29), tolerancia_dias=0) == D(2026, 8, 2)
    assert K.inicio_bloco_continuo(lanc, D(2027, 1, 1)) is None


def test_dias_sobrepostos():
    assert K.dias_sobrepostos(D(2026, 1, 1), D(2026, 1, 11), D(2026, 1, 10), D(2026, 1, 20), D(2026, 9, 29)) == 1
    assert K.dias_sobrepostos(D(2026, 1, 1), D(2026, 1, 11), D(2026, 1, 11), D(2026, 1, 20), D(2026, 9, 29)) == 0


def test_agregar_esocial():
    linhas = [
        {"reduzido": 12, "tipo": "LIC MEDICA EFETIVOS", "motivo_id": None, "status_esocial": None,
         "dtini": D(2026, 1, 1), "dtfim": D(2026, 1, 6)},
        {"reduzido": 12, "tipo": "LIC MEDICA EFETIVOS", "motivo_id": None, "status_esocial": None,
         "dtini": D(2026, 1, 1), "dtfim": D(2026, 3, 1)},
        {"reduzido": 12, "tipo": "LIC MEDICA EFETIVOS", "motivo_id": None, "status_esocial": 2,
         "dtini": D(2026, 1, 1), "dtfim": D(2026, 1, 6)},
        {"reduzido": 228, "tipo": "AUXILIO DOENCA", "motivo_id": 2, "motivo_codigo": "03", "status_esocial": 3,
         "dtini": D(2026, 1, 1), "dtfim": None},
    ]
    r = K.agregar_esocial(linhas)
    t12 = r["itens"][0]
    assert t12["reduzido"] == 12 and t12["total"] == 3
    assert t12["por_status"]["sem_status"] == 2 and t12["por_status"]["valido"] == 1
    assert t12["sem_status_por_duracao"] == {"ate_15_dias": 1, "mais_de_15_dias": 1, "em_aberto": 0}
    assert t12["motivo_esocial"] is None
    assert r["itens"][1]["motivo_esocial"]["codigo"] == "03"
    assert r["totais"] == {"total": 4, "valido": 1, "aguardando": 0, "nao_enviado": 0, "invalido": 1, "sem_status": 2}


# ------------------------------------------------------------------ SQL
def test_sql_so_tem_select():
    from afastamentos import sql as S
    textos = [v for v in vars(S).values() if isinstance(v, str)] + [S.periodos_dos_registros(3),
                                                                    S.esocial_pendencias("1=1", True)]
    proibidas = ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP ", "CREATE ", "EXECUTE ", "MERGE ")
    for t in textos:
        if "SELECT" in t.upper():
            assert not any(p in t.upper() for p in proibidas), t


def test_contagem_de_parametros():
    from afastamentos import sql as S
    assert S.VIGENTES.count("?") == 3
    assert S.RETORNOS.count("?") == 4
    assert S.TIPO_DESCONTINUADO.count("?") == 4
    assert S.SOBREPOSTOS.count("?") == 3
    assert S.ESOCIAL_TIPOS_COM_PROBLEMA.count("?") == 2
    assert S.MATERNIDADE_SEM_DEPENDENTE.count("?") == 4
    assert S.NO_ANO.count("?") == 3
    assert S.ABATE_TEMPO.count("?") == 2
    assert S.periodos_dos_registros(5).count("?") == 2 + 5


# ------------------------------------------------------------------ rotas
class _CursorFalso:
    """Devolve linhas vazias, exceto para a data de referência."""

    def __init__(self):
        self.description = []
        self._linhas = []

    def execute(self, sql, params):
        if "MAX(m.DT_INCLUSAO)" in sql:
            self.description = [("DATA_COPIA",), ("ULTIMO_DTINI",)]
            self._linhas = [(D(2026, 9, 29), D(2026, 10, 1))]
        else:
            self.description = [("REGISTRO",)]
            self._linhas = []

    def fetchall(self):
        return self._linhas

    def close(self):
        pass


class _ConexaoFalsa:
    def cursor(self):
        return _CursorFalso()


@pytest.fixture
def cliente():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from afastamentos import deps, router as R

    app = fastapi.FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.conexao] = lambda: _ConexaoFalsa()
    app.dependency_overrides[deps.obter_usuario_atual] = lambda: {"permissions": TODAS}
    return TestClient(app)


TODAS = ["rh:diagnostico:painel", "rh:diagnostico:listar", "rh:servidores:detalhar"]

ROTAS = [
    "/rh/afastamentos/referencia",
    "/rh/afastamentos/vigentes",
    "/rh/afastamentos/vigentes/resumo?por=divisao",
    "/rh/afastamentos/retornos?dias=15",
    "/rh/afastamentos/acumulado?ano=2026",
    "/rh/afastamentos/longos",
    "/rh/esocial/afastamentos/resumo",
    "/rh/esocial/afastamentos/tipos-com-problema",
    "/rh/esocial/afastamentos/pendencias?status=sem_status",
    "/rh/afastamentos/inconsistencias/resumo",
    "/rh/afastamentos/inconsistencias/sobrepostos",
    "/rh/afastamentos/abate-tempo",
    "/rh/afastamentos/maternidade-sem-dependente",
]


@pytest.mark.parametrize("rota", ROTAS)
def test_rotas_respondem(cliente, rota):
    r = cliente.get(rota)
    assert r.status_code == 200, r.text


def test_historico_registro_inexistente(cliente):
    assert cliente.get("/rh/servidores/999999/afastamentos").status_code == 404


def test_so_painel_nao_ve_lista_nominal(cliente):
    from afastamentos import deps
    cliente.app.dependency_overrides[deps.obter_usuario_atual] = lambda: {"permissions": ["rh:diagnostico:painel"]}
    assert cliente.get("/rh/afastamentos/vigentes").status_code == 403
    assert cliente.get("/rh/afastamentos/vigentes/resumo").status_code == 200


def test_sem_autenticacao_configurada_fica_fechado():
    fastapi = pytest.importorskip("fastapi")
    from afastamentos import deps
    if deps.INTEGRADO:
        pytest.skip("dentro do backend a autenticação real está ligada")
    from fastapi.testclient import TestClient

    from afastamentos import router as R
    app = fastapi.FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.conexao] = lambda: _ConexaoFalsa()
    assert TestClient(app).get("/rh/afastamentos/resumo").status_code in (404, 503)
    assert TestClient(app).get("/rh/afastamentos/vigentes/resumo").status_code == 503


# ------------------------------------------------------------------ fase 2
def test_meses_ate_corta_no_dia_da_copia():
    meses = K.meses_ate(D(2026, 9, 29), 3)
    assert meses == [(D(2026, 7, 1), D(2026, 8, 1)), (D(2026, 8, 1), D(2026, 9, 1)), (D(2026, 9, 1), D(2026, 9, 30))]
    assert K.meses_ate(D(2026, 1, 15), 2)[0] == (D(2025, 12, 1), D(2026, 1, 1))


def test_episodios_licenca_renovada_conta_uma_vez():
    lanc = [(D(2026, 2, 1), D(2026, 2, 16)), (D(2026, 2, 16), D(2026, 3, 1)),   # renovação emendada
            (D(2026, 5, 1), D(2026, 5, 4)), (D(2026, 8, 10), D(2026, 8, 12))]
    assert len(K.episodios(lanc)) == 3


def test_csv_para_excel_brasileiro():
    from afastamentos import exportar as EX
    dados = EX.para_csv("retornos", [{"registro": "000123", "nome": "Fulana", "dtini": D(2026, 9, 1),
                                      "retorno_previsto": D(2026, 10, 2), "emenda_outro_afastamento": True}])
    texto = dados.decode("utf-8")
    assert texto.startswith("﻿REGISTRO;Matrícula;Nome")
    assert "000123;;Fulana;;;;;;01/09/2026;02/10/2026;;Sim" in texto


ROTAS_FASE2 = [
    "/rh/afastamentos/serie-mensal?meses=6",
    "/rh/afastamentos/absenteismo",
    "/rh/afastamentos/recorrentes",
    "/rh/afastamentos/gerencial",
]


@pytest.mark.parametrize("rota", ROTAS_FASE2)
def test_rotas_fase2_respondem(cliente, rota):
    r = cliente.get(rota)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("rel", ["vigentes", "retornos", "longos", "acumulado", "recorrentes", "esocial-pendencias"])
def test_exportar_csv(cliente, rel):
    r = cliente.get(f"/rh/afastamentos/exportar/{rel}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]


def test_gerencial_sem_dados_pessoais(cliente):
    texto = cliente.get("/rh/afastamentos/gerencial").text.lower()
    assert '"cpf"' not in texto and '"registro"' not in texto and '"matricula"' not in texto


# ------------------------------------------------------------------ fase 2 com dados
class _ConexaoComDados:
    """Responde cada SQL pelo trecho que o identifica."""

    def __init__(self, respostas):
        self.respostas = respostas

    def cursor(self):
        conexao = self

        class _Cur:
            description, _l = [], []

            def execute(self, sql, params):
                for trecho, linhas in conexao.respostas:
                    if trecho in sql:
                        self.description = [(k.upper(),) for k in (linhas[0] if linhas else {"x": 0})]
                        self._l = [tuple(l.values()) for l in linhas]
                        return
                self.description, self._l = [("X",)], []

            def fetchall(self):
                return self._l

            def close(self):
                pass

        return _Cur()


def _af(reg, div, ini, fim, reduzido=12, causa="94"):
    return {"registro": reg, "matricula": reg, "nome": f"S{reg}", "cpf": "", "situacao_vinculo": 1,
            "divisao_codigo": div, "divisao": f"D{div}", "cargo_codigo": "1", "cargo": "C", "item": hash((reg, ini)) % 10**6,
            "reduzido": reduzido, "tipo": f"T{reduzido}", "causa": causa, "dtini": ini, "dtfim": fim}


def test_absenteismo_percentual_por_secretaria(monkeypatch):
    from afastamentos import servico as SV
    monkeypatch.setenv("SIP_DATA_COPIA", "2026-09-29")
    con = _ConexaoComDados([
        ("GROUP BY d.CODIGO", [{"divisao_codigo": "1", "divisao": "D1", "vinculos": 10},
                               {"divisao_codigo": "2", "divisao": "D2", "vinculos": 5}]),
        ("m.DTINI < ?", [_af("A", "1", D(2026, 9, 1), D(2026, 9, 11)),      # 10 dias
                         _af("A", "1", D(2026, 9, 5), D(2026, 9, 15)),      # sobrepõe: +4
                         _af("B", "2", D(2026, 8, 20), D(2026, 9, 3))]),    # 2 dias em setembro
    ])
    r = SV.absenteismo(con)
    assert r["periodo"]["dias"] == 29
    d1 = next(i for i in r["itens"] if i["divisao_codigo"] == "1")
    assert d1["dias_afastados"] == 14 and d1["vinculos_afastados"] == 1
    assert d1["percentual_dias_afastados"] == round(100 * 14 / (10 * 29), 2)
    assert r["total"]["dias_afastados"] == 16 and r["total"]["vinculos"] == 15


def test_serie_mensal_e_recorrentes(monkeypatch):
    from afastamentos import servico as SV
    monkeypatch.setenv("SIP_DATA_COPIA", "2026-09-29")
    linhas = [_af("A", "1", D(2026, 8, 25), D(2026, 9, 5)),
              _af("A", "1", D(2026, 3, 1), D(2026, 3, 3)), _af("A", "1", D(2026, 4, 1), D(2026, 4, 3)),
              _af("A", "1", D(2026, 6, 1), D(2026, 6, 2)),
              _af("B", "2", D(2026, 9, 10), D(2026, 9, 12), reduzido=168, causa="95")]
    con = _ConexaoComDados([("m.DTINI < ?", linhas), ("m.DTINI >= ?", linhas)])
    s = SV.serie_mensal(con, 2)
    ago, setb = s["itens"]
    assert ago["mes"] == "2026-08" and ago["dias_afastados"] == 7 and ago["vinculos_afastados_no_fim_do_mes"] == 1
    assert setb["afastamentos_iniciados"] == 1 and setb["dias_afastados"] == 4 + 2 and setb["mes_incompleto"]
    rec = SV.recorrentes(con, min_episodios=4)
    assert rec["total"] == 1 and rec["itens"][0]["registro"] == "A" and rec["itens"][0]["episodios"] == 4
    assert SV.recorrentes(con, min_episodios=1, somente_saude=False)["total"] == 2
    a = rec["itens"][0]
    # episódios: 25/08-05/09 (11 d), 01-03/03 (2 d), 01-03/04 (2 d), 01-02/06 (1 d) -> 16 dias em 2026
    assert a["dias_afastado"] == 16 and a["fator_bradford"] == 4 * 4 * 16
    assert a["episodios_curtos"] == 3 and a["maior_episodio_dias"] == 11


def test_ordem_bradford_prioriza_faltas_frequentes():
    assert K.fator_bradford(10, 10) > K.fator_bradford(2, 100)
