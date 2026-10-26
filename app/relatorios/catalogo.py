"""
Catálogo da página Relatórios.

Para criar um relatório: escreva a função `carregar` em fontes.py e acrescente
um Relatorio na lista CATALOGO. A tela passa a mostrá-lo sozinha.
"""
from . import fontes as F
from .modelo import (PERM_NOMINAL, PERM_PAINEL, PERM_SERVIDORES, Coluna, Filtro, Relatorio)

C = Coluna

# ---------------------------------------------------------------- colunas comuns
REGISTRO = C("registro", "REGISTRO", busca=True)
MATRICULA = C("matricula", "Matrícula", "numero", busca=True)
CONTRATO = C("contrato", "Contrato", "numero", padrao=False)
NOME = C("nome", "Nome", busca=True)
CPF = C("cpf", "CPF", sensivel=True)
SECRETARIA = C("secretaria", "Secretaria", busca=True)
CARGO = C("cargo", "Cargo", busca=True)
VINCULO = C("vinculo", "Vínculo", padrao=False, busca=True)
SITUACAO = C("situacao", "Situação do vínculo", padrao=False)
LOCAL = C("local_trabalho", "Local de trabalho", padrao=False, busca=True)
SUBDIVISAO = C("subdivisao", "Subdivisão", padrao=False, busca=True)
ADMISSAO = C("admissao", "Admissão", "data", padrao=False)
CELULAR = C("celular", "Celular", padrao=False, sensivel=True)
EMAIL = C("email", "E-mail", padrao=False, sensivel=True)

PESSOA = [REGISTRO, MATRICULA, CONTRATO, NOME, CPF, SECRETARIA, CARGO, VINCULO, SITUACAO, LOCAL]

# afastamento
TIPO_COD = C("reduzido", "Cód. tipo", padrao=False)
TIPO = C("tipo", "Tipo de afastamento", busca=True)
INICIO = C("dtini", "Início", "data")
RETORNO = C("retorno_previsto", "Retorno previsto", "data")
ESOCIAL = C("status_esocial", "eSocial")

# ---------------------------------------------------------------- filtros comuns
F_SECRETARIA = Filtro("secretaria", "Secretaria", "multipla", campo="secretaria_codigo", campo_rotulo="secretaria")
F_CARGO = Filtro("cargo", "Cargo", "multipla", campo="cargo_codigo", campo_rotulo="cargo")
F_VINCULO = Filtro("vinculo", "Vínculo", "multipla", campo="vinculo_codigo", campo_rotulo="vinculo")
F_LOCAL = Filtro("local_trabalho", "Local de trabalho", "multipla", campo="local_trabalho_codigo",
                 campo_rotulo="local_trabalho")
F_TIPO = Filtro("tipo", "Tipo de afastamento", "multipla", campo="reduzido", campo_rotulo="tipo")
F_DATA_REF = Filtro("data_ref", "Data de referência", "data",
                    ajuda="Em branco, usa a data da cópia do SIP.")
F_DESDE = Filtro("desde", "Lançamentos desde", "data", ajuda="Em branco, desde 01/01/2025.")
F_ANO = Filtro("ano", "Ano", "numero", minimo=2000, maximo=2100, ajuda="Em branco, o ano da cópia do SIP.")
FILTROS_PESSOA = [F_SECRETARIA, F_CARGO, F_VINCULO]

DIAG, AFAST, SERV = "Diagnóstico cadastral", "Afastamentos", "Servidores"

CATALOGO: list[Relatorio] = [
    # ============================================================ Servidores
    Relatorio(
        "vinculos", SERV, "Vínculos do SIP",
        "Todos os vínculos da Prefeitura, de qualquer situação. Por padrão, só os ativos.",
        "nominal", PERM_SERVIDORES,
        colunas=PESSOA + [SUBDIVISAO, ADMISSAO, C("demissao", "Desligamento", "data", padrao=False)],
        filtros=[
            Filtro("ativo", "Somente vínculos ativos", "booleano", campo="ativo", padrao=True, somente=True,
                   ajuda="Normal e Afastado. Desmarque para incluir desligados."),
            Filtro("situacao", "Situação", "multipla", campo="situacao_codigo", campo_rotulo="situacao"),
            *FILTROS_PESSOA, F_LOCAL,
            Filtro("subdivisao", "Subdivisão", "multipla", campo="subdivisao_codigo", campo_rotulo="subdivisao"),
        ],
        ordem_padrao=("nome", False), fichas=("pendencias", "afastamentos"),
        carregar=F.carregar_vinculos,
    ),
    # ============================================================ Diagnóstico
    Relatorio(
        "diagnostico-vinculos", DIAG, "Vínculos com pendência",
        "Uma linha por vínculo ativo, com a pior situação e as regras do diagnóstico que o atingem.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [CELULAR, EMAIL, ADMISSAO,
                          C("situacao_cadastral", "Situação cadastral"),
                          C("erros", "Regras de erro", "numero"), C("alertas", "Regras de alerta", "numero"),
                          C("regras", "Regras", busca=True), C("dependentes", "Dependentes", "numero", padrao=False)],
        filtros=[
            Filtro("situacao_cadastral", "Situação cadastral", "multipla", campo="situacao_cadastral_codigo",
                   opcoes=[("erro", "Com erro"), ("alerta", "Com alerta"), ("ok", "Sem pendência")],
                   padrao=["erro", "alerta"]),
            Filtro("regra", "Atingido pela regra", "multipla", opcoes=F.opcoes_regras_pendencia),
            *FILTROS_PESSOA, F_LOCAL,
        ],
        ordem_padrao=("erros", True), fichas=("pendencias",),
        carregar=F.carregar_diagnostico_vinculos,
    ),
    Relatorio(
        "diagnostico-regra", DIAG, "Lista de uma regra",
        "Cada ocorrência de uma regra do diagnóstico (servidor ou dependente), com o detalhe e a orientação.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [CELULAR, EMAIL, ADMISSAO,
                          C("dependente", "Dependente", padrao=False, busca=True),
                          C("parentesco", "Parentesco", padrao=False),
                          C("nascimento", "Nascimento do dependente", "data", padrao=False),
                          C("idade", "Idade", "numero", padrao=False),
                          C("cpf_dependente", "CPF do dependente", padrao=False, sensivel=True),
                          C("dependente_irrf", "Dependente de IRRF", "sim_nao", padrao=False),
                          C("salario_familia", "Salário-família", "sim_nao", padrao=False),
                          C("universitario", "Universitário", "sim_nao", padrao=False),
                          C("deficiente", "Deficiente", "sim_nao", padrao=False),
                          C("documentos", "Documentos", padrao=False),
                          C("data_entrega", "Entrega dos documentos", "data", padrao=False),
                          C("nome_mae", "Mãe do dependente", padrao=False, sensivel=True),
                          C("detalhe", "Detalhe")],
        filtros=[Filtro("regra", "Regra", "selecao", opcoes=F.opcoes_regras, obrigatorio=True), *FILTROS_PESSOA],
        ordem_padrao=("nome", False), fichas=("pendencias",),
        carregar=F.carregar_diagnostico_regra,
    ),
    Relatorio(
        "diagnostico-secretarias", DIAG, "Situação por secretaria",
        "Vínculos com erro, com alerta e sem pendência em cada secretaria, com o percentual de conformidade.",
        "agregado", PERM_PAINEL,
        colunas=[C("secretaria", "Secretaria", busca=True), C("vinculos", "Vínculos", "numero"),
                 C("com_erro", "Com erro", "numero"), C("com_alerta", "Com alerta", "numero"),
                 C("sem_pendencia", "Sem pendência", "numero"), C("dependentes", "Dependentes", "numero"),
                 C("conformidade", "Conformidade", "percentual")],
        ordem_padrao=("com_erro", True),
        carregar=F.carregar_diagnostico_secretarias,
    ),
    Relatorio(
        "dependentes-faixa", DIAG, "Dependentes por faixa etária",
        "Dependentes dos vínculos ativos por faixa de idade, com IRRF e salário-família fora do limite.",
        "agregado", PERM_PAINEL,
        colunas=[C("faixa", "Faixa etária"), C("dependentes", "Dependentes", "numero"),
                 C("irrf", "Com IRRF", "numero"), C("salario_familia", "Com salário-família", "numero"),
                 C("universitario", "Universitários", "numero"), C("deficiente", "Deficientes", "numero"),
                 C("irrf_fora_do_limite", "IRRF fora do limite", "numero"),
                 C("salario_familia_fora_do_limite", "Salário-família fora do limite", "numero"),
                 C("em_desconformidade", "Em desconformidade", "numero")],
        filtros=[Filtro("divisao", "Secretaria", "selecao", dominio="divisoes"),
                 Filtro("subdivisao", "Subdivisão", "selecao", dominio="subdivisoes"),
                 Filtro("vinculo", "Vínculo", "selecao", dominio="vinculos")],
        carregar=F.carregar_faixas,
    ),
    # ============================================================ Afastamentos (nominais)
    Relatorio(
        "afastamentos-vigentes", AFAST, "Afastados na data",
        "Afastamentos em curso na data de referência. Um vínculo pode ter mais de uma linha.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [TIPO_COD, TIPO, INICIO, RETORNO, C("duracao_dias", "Dias", "numero"),
                          C("sem_remuneracao", "Sem remuneração", "sim_nao"),
                          C("documento_tipo", "Documento"), C("documento_numero", "Nº documento", padrao=False),
                          ESOCIAL],
        filtros=[F_DATA_REF, F_TIPO,
                 Filtro("sem_remuneracao", "Sem remuneração", "booleano", campo="sem_remuneracao"),
                 Filtro("esocial", "eSocial", "multipla", campo="status_esocial_codigo", campo_rotulo="status_esocial"),
                 *FILTROS_PESSOA],
        ordem_padrao=("secretaria", False), fichas=("afastamentos",),
        carregar=F.carregar_af_vigentes,
    ),
    Relatorio(
        "afastamentos-retornos", AFAST, "Retornos previstos",
        "Quem volta ao trabalho nos próximos dias e se emenda em outro afastamento.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [TIPO_COD, TIPO, INICIO, RETORNO, C("dias_ate_retorno", "Dias até o retorno", "numero"),
                          C("emenda_outro_afastamento", "Emenda em outro afastamento", "sim_nao")],
        filtros=[Filtro("dias", "Próximos dias", "numero", padrao=30, minimo=1, maximo=180), F_DATA_REF, F_TIPO,
                 Filtro("emenda", "Emenda em outro afastamento", "booleano", campo="emenda_outro_afastamento"),
                 *FILTROS_PESSOA],
        ordem_padrao=("retorno_previsto", False), fichas=("afastamentos",),
        carregar=F.carregar_af_retornos,
    ),
    Relatorio(
        "afastamentos-longos", AFAST, "Afastamentos longos",
        "Vínculos afastados sem interrupção há muitos dias (licenças renovadas contam juntas).",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [C("afastado_desde", "Afastado desde", "data"),
                          C("dias_continuos", "Dias contínuos", "numero"),
                          C("sem_remuneracao", "Sem remuneração", "sim_nao"),
                          C("tipos_vigentes", "Afastamentos em curso", busca=True)],
        filtros=[Filtro("min_dias", "Mínimo de dias", "numero", padrao=60, minimo=1, maximo=20000),
                 Filtro("somente_sem_remuneracao", "Somente sem remuneração", "booleano", padrao=False),
                 F_DATA_REF, *FILTROS_PESSOA],
        ordem_padrao=("dias_continuos", True), fichas=("afastamentos",),
        carregar=F.carregar_af_longos,
    ),
    Relatorio(
        "afastamentos-acumulado", AFAST, "Dias afastados no ano",
        "Soma dos dias afastados de cada vínculo no ano (afastamentos sobrepostos contam uma vez).",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [C("dias_afastado", "Dias afastados no ano", "numero"),
                          C("afastamentos", "Lançamentos", "numero"),
                          C("dias_por_tipo", "Dias por tipo", busca=True)],
        filtros=[F_ANO, Filtro("min_dias", "Mínimo de dias", "numero", padrao=1, minimo=1, maximo=366),
                 *FILTROS_PESSOA],
        ordem_padrao=("dias_afastado", True), fichas=("afastamentos",),
        carregar=F.carregar_af_acumulado,
    ),
    Relatorio(
        "afastamentos-recorrentes", AFAST, "Afastamentos recorrentes",
        "Vínculos com muitos episódios de afastamento por saúde no ano, com perfil e fator de Bradford. Não usa CID.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [C("perfil", "Perfil"), C("fator_bradford", "Fator de Bradford", "numero"),
                          C("episodios", "Episódios", "numero"),
                          C("episodios_curtos", "Episódios de até 2 dias", "numero"),
                          C("maior_episodio_dias", "Maior episódio (dias)", "numero"),
                          C("lancamentos", "Lançamentos", "numero", padrao=False),
                          C("dias_afastado", "Dias afastados no ano", "numero"),
                          C("tipos", "Tipos", padrao=False, busca=True)],
        filtros=[F_ANO, Filtro("min_episodios", "Mínimo de episódios", "numero", padrao=4, minimo=1, maximo=100),
                 Filtro("perfil", "Perfil", "multipla", campo="perfil",
                        opcoes=[("frequente", "Faltas frequentes"), ("prolongado", "Afastamento prolongado"),
                                ("misto", "Misto"), ("moderado", "Moderado")]),
                 *FILTROS_PESSOA],
        ordem_padrao=("fator_bradford", True), fichas=("afastamentos",),
        carregar=F.carregar_af_recorrentes,
    ),
    Relatorio(
        "afastamentos-esocial", AFAST, "Pendências do eSocial",
        "Lançamentos de afastamento sem envio ou com erro no eSocial.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [TIPO_COD, TIPO, INICIO, C("dtfim", "Fim (DTFIM)", "data"),
                          C("motivo_codigo", "Motivo eSocial"), ESOCIAL],
        filtros=[Filtro("status", "Situação no eSocial", "multipla", opcoes=F.STATUS_ESOCIAL,
                        padrao=["sem_status", "invalido"]),
                 F_DESDE, F_TIPO, *FILTROS_PESSOA],
        ordem_padrao=("dtini", True), fichas=("afastamentos",),
        carregar=F.carregar_af_esocial,
    ),
    Relatorio(
        "afastamentos-inconsistencias", AFAST, "Inconsistências de lançamento",
        "Afastamentos sobrepostos, sem tipo, de tipo antigo em aberto ou de vínculo desligado.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [C("item", "Item", "numero", padrao=False), TIPO_COD, TIPO, INICIO,
                          C("dtfim", "Fim (DTFIM)", "data", padrao=False), RETORNO,
                          C("dt_inclusao", "Incluído em", "data", padrao=False),
                          C("a_tipo", "1º afastamento", padrao=False, busca=True),
                          C("a_dtini", "1º início", "data", padrao=False), C("a_dtfim", "1º fim", "data", padrao=False),
                          C("b_tipo", "2º afastamento", padrao=False, busca=True),
                          C("b_dtini", "2º início", "data", padrao=False), C("b_dtfim", "2º fim", "data", padrao=False),
                          C("dias_sobrepostos", "Dias sobrepostos", "numero", padrao=False), ESOCIAL],
        filtros=[Filtro("regra", "Regra", "selecao", opcoes=F.REGRAS_INCONSISTENCIA, obrigatorio=True),
                 F_DESDE, F_DATA_REF, *FILTROS_PESSOA],
        ordem_padrao=("nome", False), fichas=("afastamentos",),
        carregar=F.carregar_af_inconsistencias,
    ),
    Relatorio(
        "afastamentos-abate-tempo", AFAST, "Tempo que não conta",
        "Dias de afastamento que abatem tempo de serviço ou de contribuição, por vínculo ativo.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [C("dias_abatidos_tempo_servico", "Dias abatidos do tempo de serviço", "numero"),
                          C("dias_abatidos_tempo_contribuicao", "Dias abatidos da contribuição", "numero"),
                          C("tipos", "Afastamentos", padrao=False, busca=True)],
        filtros=[Filtro("min_dias", "Mínimo de dias", "numero", padrao=1, minimo=1, maximo=20000),
                 F_DATA_REF, *FILTROS_PESSOA],
        ordem_padrao=("dias_abatidos_tempo_servico", True), fichas=("afastamentos",),
        carregar=F.carregar_af_abate,
    ),
    Relatorio(
        "afastamentos-maternidade", AFAST, "Licença sem filho cadastrado",
        "Licença maternidade ou paternidade sem dependente nascido perto do período da licença.",
        "nominal", PERM_NOMINAL,
        colunas=PESSOA + [C("licenca", "Licença"), TIPO, INICIO, RETORNO,
                          C("qtd_dependentes", "Dependentes cadastrados", "numero")],
        filtros=[F_DESDE, F_DATA_REF, *FILTROS_PESSOA],
        ordem_padrao=("dtini", True), fichas=("afastamentos", "pendencias"),
        carregar=F.carregar_af_maternidade,
    ),
    # ============================================================ Afastamentos (agregados)
    Relatorio(
        "afastamentos-agrupados", AFAST, "Afastados por tipo, secretaria ou cargo",
        "Quantos vínculos estão afastados na data, agrupados.",
        "agregado", PERM_PAINEL,
        colunas=[C("nome", "Grupo", busca=True), C("codigo", "Código", padrao=False),
                 C("vinculos", "Vínculos afastados", "numero"), C("afastamentos", "Afastamentos", "numero")],
        filtros=[Filtro("por", "Agrupar por", "selecao", padrao="tipo", obrigatorio=True,
                        opcoes=[("tipo", "Tipo de afastamento"), ("divisao", "Secretaria"), ("cargo", "Cargo")]),
                 F_DATA_REF],
        ordem_padrao=("vinculos", True),
        carregar=F.carregar_af_agrupado,
    ),
    Relatorio(
        "afastamentos-absenteismo", AFAST, "Absenteísmo por secretaria",
        "Dias afastados no mês e percentual sobre os dias possíveis de cada secretaria.",
        "agregado", PERM_PAINEL,
        colunas=[C("secretaria", "Secretaria", busca=True), C("vinculos", "Vínculos ativos", "numero"),
                 C("vinculos_afastados", "Vínculos afastados no mês", "numero"),
                 C("dias_afastados", "Dias afastados", "numero"),
                 C("percentual_dias_afastados", "% de dias afastados", "percentual")],
        filtros=[F_ANO, Filtro("mes", "Mês", "numero", minimo=1, maximo=12, ajuda="Em branco, o mês da cópia do SIP.")],
        ordem_padrao=("percentual_dias_afastados", True),
        carregar=F.carregar_af_absenteismo,
    ),
    Relatorio(
        "afastamentos-serie", AFAST, "Linha do tempo mensal",
        "Afastamentos iniciados, vínculos afastados e dias afastados mês a mês.",
        "agregado", PERM_PAINEL,
        colunas=[C("mes", "Mês"), C("afastamentos_iniciados", "Afastamentos iniciados", "numero"),
                 C("vinculos_afastados_no_mes", "Vínculos afastados no mês", "numero"),
                 C("vinculos_afastados_no_fim_do_mes", "Afastados no fim do mês", "numero"),
                 C("dias_afastados", "Dias afastados", "numero"),
                 C("mes_incompleto", "Mês incompleto", "sim_nao")],
        filtros=[Filtro("meses", "Meses", "numero", padrao=12, minimo=1, maximo=60),
                 Filtro("divisao", "Secretaria", "selecao", dominio="divisoes"), F_DATA_REF],
        ordem_padrao=("mes", False),
        carregar=F.carregar_af_serie,
    ),
    Relatorio(
        "afastamentos-tipos-esocial", AFAST, "Tipos com problema no eSocial",
        "Tipos de afastamento sem motivo eSocial válido configurado no SIP (ajuste com o RH e a Fiorilli).",
        "agregado", PERM_PAINEL,
        colunas=[C("reduzido", "Cód. tipo"), C("tipo", "Tipo de afastamento", busca=True),
                 C("problema", "Problema"), C("motivo_codigo", "Motivo eSocial", padrao=False),
                 C("motivo_descricao", "Descrição do motivo", padrao=False),
                 C("lancamentos_desde", "Lançamentos no período", "numero"),
                 C("ultimo_uso", "Último lançamento", "data")],
        filtros=[F_DESDE],
        ordem_padrao=("lancamentos_desde", True),
        carregar=F.carregar_af_tipos_problema,
    ),
]

POR_ID = {r.id: r for r in CATALOGO}
