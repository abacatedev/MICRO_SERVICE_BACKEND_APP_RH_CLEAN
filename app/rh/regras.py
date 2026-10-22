"""Regras do diagnóstico cadastral (Pré-Censo).

Funções puras: recebem os servidores e dependentes do universo e devolvem as
ocorrências de cada regra. Não acessam banco, então são fáceis de ler, testar
e validar com o RH. Para mudar um critério, altere só este arquivo.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime

# Códigos de SIPREV_TIPODEPEN
COM_LIMITE_IDADE = {"03", "06", "08", "10", "15", "17"}  # filho, irmão, enteado, tutelado, neto, guarda
MENOR_DE_21 = {"03", "06", "08", "10"}                    # o próprio nome do tipo diz "menor de 21"
CONJUGE = {"01", "02"}
DESCENDENTE = {"03", "04", "08", "09", "15"}
ASCENDENTE = {"05", "12", "13"}
COM_CERTIDAO = {"03", "04", "08", "09", "10", "11", "15", "17"}  # de quem se espera certidão de nascimento
DIFERENCA_MINIMA_ANOS = 12  # entre servidor e filho, ou entre pai/mãe e servidor
ANOS_SEM_REVISAO = 5        # data de entrega da documentação mais antiga que isso
SOLTEIRO = "1"              # código de ESTADOCIVIL no SIP

ONDE_DEP = "No SIP: Cadastro de Trabalhadores, Dependentes, Alterar"


@dataclass(frozen=True)
class Regra:
    codigo: str
    titulo: str
    tipo: str   # erro | alerta | indicador | recadastro | conferencia
    alvo: str   # dependente | servidor
    descricao: str = ""    # o que a regra encontra, em linguagem do RH
    orientacao: str = ""   # o que fazer (rascunho; o RH deve revisar)


REGRAS = [
    Regra("D01", "Dependente sem CPF", "erro", "dependente",
          "O dependente está cadastrado sem CPF, ou com o campo vazio. O eSocial exige o CPF do dependente.",
          f"Pedir o CPF ao servidor. {ONDE_DEP}, aba Outros Documentos."),
    Regra("D16", "Dependente sem data de nascimento válida", "erro", "dependente",
          "A data de nascimento do dependente está vazia, é falsa (01/01/1900 ou anterior) ou está no futuro. "
          "O eSocial exige a data, e sem ela o sistema não controla os limites de idade do IRRF e do salário-família.",
          f"Pedir ao servidor a certidão ou um documento com a data. {ONDE_DEP}, aba Informações Gerais."),
    Regra("D11", "Dependente sem nenhum documento", "erro", "dependente",
          "O dependente só tem nome e nascimento: sem CPF, sem RG, sem outro documento e sem dados de certidão.",
          f"Pedir os documentos ao servidor. {ONDE_DEP}, abas Informações Gerais e Outros Documentos."),
    Regra("D02", "CPF de dependente inválido, repetido no servidor ou igual ao do servidor", "erro", "dependente",
          "O CPF do dependente não passa na conferência dos dígitos, repete o de outro dependente ou é o do próprio servidor.",
          f"Conferir o documento e corrigir o número. {ONDE_DEP}, aba Outros Documentos."),
    Regra("D03", "IRRF marcado acima da idade, sem controle de faixa de idade", "erro", "dependente",
          "Dependente IRRF = Sim, já no ano seguinte ao que completou a idade limite do vínculo (21, ou 24 se "
          "universitário), e 'Considerar para Faixa de Idade' = Não. "
          "Sem esse controle, o sistema pode continuar deduzindo o imposto (a confirmar com a Fiorilli ou em um holerite).",
          f"Confirmar se o dependente ainda se enquadra; se não, desmarcar. {ONDE_DEP}, aba Dados para Cálculo."),
    Regra("D04", "Salário-família marcado acima da idade, sem controle de faixa de idade", "erro", "dependente",
          "Salário Família = Sim, com a idade limite do vínculo já completada, e 'Considerar para Faixa de Idade' = Não.",
          f"Desmarcar o salário-família. {ONDE_DEP}, aba Dados para Cálculo."),
    Regra("D13", "IRRF marcado acima da idade, com controle de faixa de idade", "alerta", "dependente",
          "Dependente IRRF = Sim, já no ano seguinte ao que completou a idade limite, mas "
          "'Considerar para Faixa de Idade' = Sim. "
          "O sistema deve estar aplicando o limite sozinho; o cadastro é que ficou desatualizado.",
          f"Atualizar o cadastro quando o servidor for chamado no Censo. {ONDE_DEP}, aba Dados para Cálculo."),
    Regra("D14", "Salário-família marcado acima da idade, com controle de faixa de idade", "alerta", "dependente",
          "Salário Família = Sim com a idade limite já completada, mas 'Considerar para Faixa de Idade' = Sim.",
          f"Atualizar o cadastro quando o servidor for chamado no Censo. {ONDE_DEP}, aba Dados para Cálculo."),
    Regra("D05", "Parentesco 'menor de 21 anos' com 21 anos ou mais", "alerta", "dependente",
          "O tipo de parentesco diz 'menor de 21 anos', mas o dependente já tem 21 ou mais.",
          f"Atualizar o parentesco ou encerrar a dependência. {ONDE_DEP}, aba Informações Gerais."),
    Regra("D06", "Mais de um cônjuge ou companheiro no mesmo registro", "alerta", "dependente",
          "O mesmo registro tem mais de um cônjuge ou companheiro cadastrado.",
          "Confirmar a situação atual com o servidor e manter apenas o vínculo vigente."),
    Regra("D07", "Idade incoerente com o parentesco", "alerta", "dependente",
          "A diferença de idade entre servidor e dependente não combina com o parentesco informado.",
          "Conferir a data de nascimento e o parentesco do dependente."),
    Regra("D08", "PAI com sexo feminino ou MÃE com sexo masculino", "alerta", "dependente",
          "O parentesco é PAI com sexo feminino, ou MÃE com sexo masculino.",
          "Corrigir o sexo ou o parentesco do dependente."),
    Regra("D09", "Dependente duplicado no mesmo registro", "alerta", "dependente",
          "O mesmo dependente (nome e nascimento) aparece mais de uma vez no registro.",
          "Excluir o cadastro repetido."),
    Regra("D12", "Certidão de nascimento sem dados do cartório", "indicador", "dependente",
          "Filho, enteado, neto ou menor sob guarda sem cartório, livro, folha, registro nem matrícula da certidão.",
          f"Pedir a certidão no Censo. {ONDE_DEP}, aba Informações Gerais."),
    Regra("D15", f"Documentação do dependente entregue há mais de {ANOS_SEM_REVISAO} anos", "indicador", "dependente",
          f"A data de entrega registrada tem mais de {ANOS_SEM_REVISAO} anos: o cadastro provavelmente nunca foi revisado.",
          "Priorizar estes servidores na chamada do Censo."),
    Regra("D10", "Parentesco 'Outros'", "indicador", "dependente",
          "O dependente está com o parentesco 'Outros', que não diz qual é a relação.",
          "Informar o parentesco correto."),
    Regra("S01", "Servidor sem celular", "alerta", "servidor",
          "O servidor não tem celular cadastrado.",
          "Coletar o celular; ele será usado para os avisos do Censo."),
    Regra("S02", "Servidor sem e-mail", "alerta", "servidor",
          "O servidor não tem e-mail cadastrado.",
          "Coletar o e-mail; ele será usado para os avisos do Censo."),
    Regra("S07", "Estado civil solteiro com cônjuge entre os dependentes", "alerta", "servidor",
          "O servidor está como Solteiro, mas tem um dependente cadastrado como Cônjuge.",
          "Confirmar com o servidor e corrigir o estado civil ou o parentesco."),
    Regra("S03", "Título de eleitor ausente ou com preenchimento falso", "alerta", "servidor",
          "O título de eleitor está vazio ou preenchido só com zeros.",
          "Pedir o número do título ao servidor."),
    Regra("S04", "PIS ausente ou com preenchimento falso", "erro", "servidor",
          "O PIS está vazio ou preenchido só com zeros ou noves.",
          "Pedir o número do PIS/PASEP/NIT ao servidor."),
    Regra("S05", "Servidor sem nome da mãe", "erro", "servidor",
          "O nome da mãe do servidor não está preenchido.",
          "Completar o nome da mãe conforme o documento."),
    Regra("S06", "CPF do servidor ausente ou inválido", "erro", "servidor",
          "O CPF do servidor está vazio ou não passa na conferência dos dígitos.",
          "Conferir o documento e corrigir o CPF."),
    Regra("V01", "Vínculo ativo com data de término vencida", "alerta", "servidor",
          "O vínculo está ativo, mas a data de término já passou.",
          "Verificar se o contrato foi prorrogado ou se falta registrar o desligamento."),
    Regra("V02", "CPF com mais de um vínculo ativo", "conferencia", "servidor",
          "A mesma pessoa tem mais de um vínculo ativo.",
          "Conferir se os dois vínculos estão de fato vigentes."),
    Regra("I01", "Sem dependentes em nenhum registro", "indicador", "servidor",
          "O servidor não tem dependentes em nenhum registro. Pode ser que não tenha, ou que nunca tenham sido cadastrados.",
          "Nada a fazer agora; o Censo vai perguntar ao servidor."),
    Regra("I02", "Sem dependentes no vínculo ativo, com dependentes em outro registro", "recadastro", "servidor",
          "O vínculo ativo está sem dependentes, mas a pessoa tem dependentes cadastrados em outro registro.",
          "Recadastrar os dependentes no vínculo ativo, depois de confirmar com o servidor."),
]
POR_CODIGO = {r.codigo: r for r in REGRAS}

_SERVIDOR = [
    "REGISTRO", "MATRICULA", "CONTRATO", "SERVIDOR", "CPF_SERVIDOR", "ADMISSAO", "SITUACAO", "VINCULO",
    "CARGO", "DIVISAO", "LOCAL_TRABALHO", "CELULAR", "EMAIL",
]
COLUNAS_SERVIDOR = _SERVIDOR + ["DETALHE"]
COLUNAS_DEPENDENTE = _SERVIDOR + [
    "ITEM", "DEPENDENTE", "PARENTESCO", "NASCIMENTO", "IDADE", "CPF_DEPENDENTE",
    "DEPENDENTE_IRRF", "SALARIO_FAMILIA", "FAIXA_IDADE", "UNIVERSITARIO", "DEFICIENTE",
    "DOCUMENTOS", "DATA_ENTREGA", "NOME_MAE", "DETALHE",
]


# ---------- utilitários ----------

def so_digitos(valor) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def vazio(valor) -> bool:
    return not str(valor if valor is not None else "").strip()


def ausente(valor) -> bool:
    """Nulo, vazio ou preenchimento falso (0, 00000000000, 99999999999...)."""
    texto = str(valor or "").strip()
    if not texto:
        return True
    digitos = so_digitos(texto)
    return bool(digitos) and digitos == texto and len(set(digitos)) == 1


def cpf_valido(valor) -> bool:
    cpf = so_digitos(valor)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if (soma * 10) % 11 % 10 != int(cpf[tamanho]):
            return False
    return True


def cpf_formatado(valor) -> str:
    cpf = so_digitos(valor)
    if len(cpf) != 11:
        return str(valor or "").strip()
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def _data(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    return valor if isinstance(valor, date) else None


DATA_MINIMA_NASCIMENTO = date(1900, 1, 2)  # 01/01/1900 e anteriores são preenchimento falso


def nascimento_valido(valor, hoje: date) -> date | None:
    """Data de nascimento utilizável: None se vazia, falsa (até 01/01/1900) ou no futuro."""
    d = _data(valor)
    if d is None or d < DATA_MINIMA_NASCIMENTO or d > hoje:
        return None
    return d


def data_br(valor) -> str:
    d = _data(valor)
    return d.strftime("%d/%m/%Y") if d else ""


def anos_entre(inicio, fim) -> int | None:
    """Anos completos de `inicio` até `fim` (negativo se `fim` for anterior)."""
    inicio, fim = _data(inicio), _data(fim)
    if inicio is None or fim is None:
        return None
    if fim < inicio:
        return -anos_entre(fim, inicio)
    return fim.year - inicio.year - ((fim.month, fim.day) < (inicio.month, inicio.day))


def _sim(valor) -> bool:
    return str(valor or "").strip().upper() == "S"


def _sim_nao(valor) -> str:
    return "Sim" if _sim(valor) else "Não"


def _nome(valor) -> str:
    return " ".join(str(valor or "").upper().split())


def documentos_do_dependente(d: dict) -> list[str]:
    """Quais documentos o dependente tem preenchidos (aba Outros Documentos e certidão)."""
    tem = []
    if not ausente(d.get("CPF")):
        tem.append("CPF")
    if not ausente(d.get("RG")):
        tem.append("RG")
    if not ausente(d.get("PIS")):
        tem.append("PIS")
    if not vazio(d.get("TIPODOC")) or not vazio(d.get("NUMDOC")):
        tem.append("Outro documento")
    if tem_certidao(d):
        tem.append("Certidão")
    return tem


def tem_certidao(d: dict) -> bool:
    campos = ("NOMECARTORIO", "NUMLIVRO", "NUMREGISTRO", "NUMFOLHA", "CERTIDAO_MATRICULA")
    return any(not vazio(d.get(c)) for c in campos)


# ---------- avaliação ----------

def avaliar(servidores: list[dict], dependentes: list[dict], cpfs_com_dep_fora: set[str], hoje: date) -> dict:
    """Devolve {codigo: [ocorrências]} para todas as regras."""
    out: dict[str, list[dict]] = {r.codigo: [] for r in REGRAS}

    deps_por_registro: dict[str, list[dict]] = defaultdict(list)
    for d in dependentes:
        deps_por_registro[d["REGISTRO"]].append(d)

    vinculos_por_cpf = Counter(so_digitos(s.get("CPF")) for s in servidores if not ausente(s.get("CPF")))
    cpfs_com_dep_no_universo: dict[str, set[str]] = defaultdict(set)
    for s in servidores:
        if deps_por_registro.get(s["REGISTRO"]):
            cpfs_com_dep_no_universo[so_digitos(s.get("CPF"))].add(s["REGISTRO"])
    cpfs_com_dep_fora = {so_digitos(c) for c in cpfs_com_dep_fora}

    for s in sorted(servidores, key=lambda x: (_nome(x.get("NOME")), x["REGISTRO"])):
        base = {
            "REGISTRO": s["REGISTRO"],
            "MATRICULA": s.get("MATRICULA"),
            "CONTRATO": s.get("CONTRATO"),
            "SERVIDOR": s.get("NOME"),
            "CPF_SERVIDOR": cpf_formatado(s.get("CPF")),
            "ADMISSAO": data_br(s.get("DTADMISSAO")),
            "SITUACAO": s.get("SITUACAO_NOME"),
            "VINCULO": s.get("VINCULO_NOME"),
            "CARGO": s.get("CARGOATUAL_NOME"),
            "DIVISAO": s.get("DIVISAO_NOME"),
            "LOCAL_TRABALHO": s.get("LOCAL_TRABALHO_NOME"),
            "CELULAR": str(s.get("CELULAR") or "").strip(),
            "EMAIL": str(s.get("EMAIL") or "").strip(),
        }

        def do_servidor(codigo: str, detalhe: str = "") -> None:
            out[codigo].append({**base, "DETALHE": detalhe})

        cpf = so_digitos(s.get("CPF"))
        if vazio(s.get("CELULAR")):
            do_servidor("S01")
        if vazio(s.get("EMAIL")):
            do_servidor("S02")
        if ausente(s.get("ELEITOR")):
            do_servidor("S03")
        if ausente(s.get("PIS")):
            do_servidor("S04")
        if vazio(s.get("NOMEMAE")):
            do_servidor("S05")
        if ausente(s.get("CPF")):
            do_servidor("S06", "CPF ausente")
        elif not cpf_valido(cpf):
            do_servidor("S06", "CPF inválido")
        termino = _data(s.get("DTTERMINO"))
        if termino is not None and termino < hoje:
            do_servidor("V01", f"Término em {data_br(termino)}")
        if cpf and vinculos_por_cpf[cpf] > 1:
            do_servidor("V02", f"{vinculos_por_cpf[cpf]} vínculos ativos")

        deps = sorted(deps_por_registro.get(s["REGISTRO"], []), key=lambda d: d.get("ITEM") or 0)
        if not deps:
            em_outro_ativo = cpfs_com_dep_no_universo.get(cpf, set()) - {s["REGISTRO"]}
            if cpf and (cpf in cpfs_com_dep_fora or em_outro_ativo):
                do_servidor("I02", "Dependentes cadastrados em outro registro do mesmo CPF")
            else:
                do_servidor("I01")
            continue

        cpfs_validos = Counter(so_digitos(d.get("CPF")) for d in deps if cpf_valido(d.get("CPF")))
        conjuges = [d for d in deps if d.get("PARENTESCO") in CONJUGE]
        repetidos = Counter((_nome(d.get("NOME")), _data(d.get("DTNASC"))) for d in deps)

        casados_com = [d.get("NOME") for d in deps if str(d.get("PARENTESCO") or "").strip() == "01"]
        if str(s.get("ESTADOCIVIL") or "").strip() == SOLTEIRO and casados_com:
            do_servidor("S07", f"Cônjuge cadastrado: {casados_com[0]}")

        for d in deps:
            parentesco = str(d.get("PARENTESCO") or "").strip()
            nascimento = nascimento_valido(d.get("DTNASC"), hoje)  # data falsa não gera idade
            idade = anos_entre(nascimento, hoje)
            documentos = documentos_do_dependente(d)
            linha = {
                **base,
                "ITEM": d.get("ITEM"),
                "DEPENDENTE": d.get("NOME"),
                "PARENTESCO": d.get("PARENTESCO_NOME") or parentesco,
                "NASCIMENTO": data_br(d.get("DTNASC")),
                "IDADE": idade,
                "CPF_DEPENDENTE": "" if ausente(d.get("CPF")) else cpf_formatado(d.get("CPF")),
                "DEPENDENTE_IRRF": _sim_nao(d.get("IRRF")),
                "SALARIO_FAMILIA": _sim_nao(d.get("SALFAMILIA")),
                "FAIXA_IDADE": _sim_nao(d.get("FAIXA_IDADE")),
                "UNIVERSITARIO": _sim_nao(d.get("UNIVERSITARIO")),
                "DEFICIENTE": _sim_nao(d.get("DEFICIENTE")),
                "DOCUMENTOS": ", ".join(documentos) or "Nenhum",
                "DATA_ENTREGA": data_br(d.get("DTENTREGA")),
                "NOME_MAE": str(d.get("NOMEMAE") or "").strip(),
            }

            def do_dependente(codigo: str, detalhe: str = "") -> None:
                out[codigo].append({**linha, "DETALHE": detalhe})

            cpf_dep = so_digitos(d.get("CPF"))
            if ausente(d.get("CPF")):
                do_dependente("D01")
            elif not cpf_valido(cpf_dep):
                do_dependente("D02", "CPF inválido")
            elif cpf_dep == cpf:
                do_dependente("D02", "Igual ao CPF do servidor")
            elif cpfs_validos[cpf_dep] > 1:
                do_dependente("D02", "CPF repetido no mesmo servidor")
            if not documentos:
                do_dependente("D11", "Só nome e nascimento cadastrados")
            if nascimento is None:
                bruta = _data(d.get("DTNASC"))
                do_dependente("D16", "Data vazia" if bruta is None else f"Data inválida: {data_br(bruta)}")

            feminino = str(d.get("SEXO") or "").strip().upper() == "F"
            controla_faixa = _sim(d.get("FAIXA_IDADE"))
            if idade is not None and parentesco in COM_LIMITE_IDADE and not _sim(d.get("DEFICIENTE")):
                lim_irrf = s.get("IDADE_IRRF_FEMI") if feminino else s.get("IDADE_IRRF_MASC")
                if _sim(d.get("UNIVERSITARIO")) and s.get("IDADE_IRRF_UNIVERSITARIO") is not None:
                    lim_irrf, rotulo = s["IDADE_IRRF_UNIVERSITARIO"], "universitário"
                else:
                    rotulo = "IRRF"
                # Regra da Receita: o dependente perde a condição no ano SEGUINTE ao que completa
                # o limite (21, ou 24 se universitário/técnico). Então conta o ano, não a idade de hoje.
                idade_no_ano = hoje.year - nascimento.year  # idade que completa no ano corrente
                if _sim(d.get("IRRF")) and lim_irrf is not None and idade_no_ano > lim_irrf:
                    do_dependente(
                        "D13" if controla_faixa else "D03",
                        f"{idade} anos; completou {lim_irrf} em {nascimento.year + lim_irrf} "
                        f"(limite de {rotulo} do vínculo: {lim_irrf})",
                    )
                lim_sf = s.get("IDADESALFAMFEM") if feminino else s.get("IDADESALFAMMASC")
                if _sim(d.get("SALFAMILIA")) and lim_sf is not None and idade >= lim_sf:
                    do_dependente(
                        "D14" if controla_faixa else "D04",
                        f"{idade} anos; salário-família até {lim_sf}",
                    )

            if idade is not None and parentesco in MENOR_DE_21 and idade >= 21:
                do_dependente("D05", f"{idade} anos")
            if parentesco in CONJUGE and len(conjuges) > 1:
                do_dependente("D06", f"{len(conjuges)} cônjuges ou companheiros")

            if parentesco in DESCENDENTE:
                diferenca = anos_entre(s.get("DTNASCIMENTO"), nascimento)
                if diferenca is not None and diferenca < DIFERENCA_MINIMA_ANOS:
                    do_dependente("D07", f"Servidor apenas {diferenca} anos mais velho")
            elif parentesco in ASCENDENTE:
                diferenca = anos_entre(nascimento, s.get("DTNASCIMENTO"))
                if diferenca is not None and diferenca < DIFERENCA_MINIMA_ANOS:
                    do_dependente("D07", f"Apenas {diferenca} anos mais velho que o servidor")

            if (parentesco == "12" and feminino) or (parentesco == "13" and not feminino and d.get("SEXO")):
                do_dependente("D08", f"Sexo cadastrado: {d.get('SEXO')}")
            if repetidos[(_nome(d.get("NOME")), _data(d.get("DTNASC")))] > 1:
                do_dependente("D09")
            if parentesco in COM_CERTIDAO and not tem_certidao(d):
                do_dependente("D12")
            entrega = anos_entre(d.get("DTENTREGA"), hoje)
            if entrega is not None and entrega >= ANOS_SEM_REVISAO:
                do_dependente("D15", f"Entregue em {data_br(d.get('DTENTREGA'))}, há {entrega} anos")
            if parentesco == "00":
                do_dependente("D10")

    return out
