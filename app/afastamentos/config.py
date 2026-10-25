"""
Configuração do módulo de afastamentos (Pré-Censo / RH).

Fonte: SIP/Fiorilli (Firebird 2.5), SOMENTE LEITURA.

Tudo que foi CONFIRMADO por consulta ao catálogo está marcado [OK].
O que ainda precisa ser conferido está marcado [CONFIRMAR] — rode
sql/verificar_colunas_afastamentos.sql e ajuste aqui se necessário.
"""
from datetime import date

# --------------------------------------------------------------------------
# Escopo
# --------------------------------------------------------------------------
EMPRESA = "001"                 # [OK] 001 = Prefeitura (002 = terceirizados, fora do escopo)
SITUACOES_ATIVAS = (1, 3)       # [OK] 1 Normal, 3 Afastado (3 não é usado hoje no TRABALHADOR)
SITUACAO_DESLIGADO = 6          # [OK]

NOMES_SITUACAO = {              # [OK] tabela SITUACOES
    0: "Cálculo Desativado", 1: "Normal", 2: "Desligamento sem rescisão",
    3: "Afastado", 4: "Aviso Indenizado", 5: "Aviso Trabalhado", 6: "Desligado",
}

# --------------------------------------------------------------------------
# O que é "afastamento temporário"
# Regra: tipo (SEFIPREDUZIDO) com código SEFIP de retorno (SEFIPENT) preenchido.
# Rescisões, falecimento e transferências não têm retorno e ficam de fora.
# Exceções que não têm SEFIPENT mas são afastamentos:
# --------------------------------------------------------------------------
TIPOS_TEMPORARIOS_EXTRAS = (1220,)   # 1220 = afastamento para exercer cargo eletivo

# --------------------------------------------------------------------------
# Convenção de datas
# Dedução (não confirmada com o RH): no SIP, DTFIM é o DIA DO RETORNO,
# porque PK_ESOCIAL_FIM = DTFIM - 1 nos registros de amostra.
# Se o RH disser que DTFIM é o último dia afastado, troque para False:
# todas as contagens se ajustam sozinhas.
# --------------------------------------------------------------------------
DTFIM_E_DIA_DO_RETORNO = True

# --------------------------------------------------------------------------
# Parâmetros das regras
# --------------------------------------------------------------------------
DESDE_PADRAO = date(2025, 1, 1)       # início padrão das análises de lançamento/eSocial
DIAS_LONGO_PADRAO = 60                # "afastamento longo"
DIAS_TIPO_DESCONTINUADO = 365         # tipo sem lançamento novo há mais que isso
TOLERANCIA_EMENDA_DIAS = 1            # até 1 dia entre afastamentos: mesmo episódio
TOLERANCIA_RENOVACAO_DIAS = 3         # até 3 dias (fim de semana) se o anterior durou RENOVACAO_MIN_DIAS ou mais
RENOVACAO_MIN_DIAS = 15               # licença longa renovada
CAUSA_SEM_REMUNERACAO = "97"          # [OK] CAUSAS 97 = afastamento sem vencimento

CAUSAS_SAUDE = ("91", "92", "93", "94")  # [OK] CAUSAS: acidente típico, de trajeto, doença do trabalho, doença comum
RECORRENTES_MIN_PADRAO = 4            # episódios de afastamento de saúde no ano
EPISODIO_CURTO_DIAS = 2               # "falta curta" no alerta de recorrentes
PERFIL_FREQUENTE_PROPORCAO = 0.5      # metade ou mais dos episódios são curtos -> faltas frequentes
PERFIL_PROLONGADO_DIAS = 60           # algum episódio com 60 dias ou mais -> afastamento prolongado
MESES_SERIE_PADRAO = 12               # linha do tempo mensal

TIPOS_MATERNIDADE = (168, 226)        # [OK] licença maternidade / salário maternidade INSS
TIPOS_PATERNIDADE = (10,)             # [OK] licença paternidade art. 109
JANELA_NASCIMENTO_ANTES_DIAS = 120    # aceita filho nascido até 120 dias antes do início

# --------------------------------------------------------------------------
# Nomes de colunas
# --------------------------------------------------------------------------
COL_TRAB_MATRICULA = "MATRICULA"      # [OK] UNIQUE (EMPRESA, MATRICULA, CONTRATO)
COL_TRAB_NOME = "NOME"                # [OK]
COL_TRAB_CPF = "CPF"                  # [OK]
COL_TRAB_DIVISAO = "DIVISAO"          # [OK] FK (EMPRESA, DIVISAO) -> DIVISAO
COL_TRAB_CARGO = "CARGOATUAL"        # [OK] FK (EMPRESA, CARGOATUAL) -> CARGOS
COL_DEP_NASCIMENTO = "DTNASC"        # [OK]

# --------------------------------------------------------------------------
# Quem pode ver — permissões que JÁ EXISTEM no backend do RH (nada novo no Postgres)
# Resumos (só números) x listas nominais (nome, CPF, REGISTRO).
# Nenhuma rota deste módulo expõe CID ou médico.
# --------------------------------------------------------------------------
PERM_RESUMO = "rh:diagnostico:painel"      # contagens e gráficos
PERM_NOMINAL = "rh:diagnostico:listar"     # listas com nome, CPF e REGISTRO
PERM_SERVIDOR = "rh:servidores:detalhar"   # histórico de um vínculo
