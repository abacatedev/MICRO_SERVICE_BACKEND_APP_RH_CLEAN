"""Documentação da API (Swagger em /docs, ReDoc em /redoc, contrato em /openapi.json).

Tudo o que o Swagger mostra além do código das rotas fica aqui: descrição geral,
grupos, esquemas de autenticação, permissão exigida e formato da resposta de
cada rota. Os modelos abaixo documentam as respostas; não alteram o que a API devolve.
"""
from datetime import datetime
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from pydantic.json_schema import models_json_schema

DESCRICAO = """
Diagnóstico cadastral dos servidores e dependentes da Prefeitura de Cáceres (Pré-Censo),
a partir de uma cópia de análise do SIP. **A API só lê o SIP.**

## Como autenticar

**Pelo navegador (recomendado para frontends).** Envie a pessoa para
`GET /rh/login?retorno=http://localhost:3000/`. Depois do Google, ela volta para o seu
frontend com a sessão aberta em cookie HttpOnly (8 horas). Nas chamadas, use
`fetch(url, { credentials: "include" })`.

**Por token.** Com a sessão aberta, `GET /rh/token` devolve um JWT RS256 de 15 minutos.
Envie em `Authorization: Bearer <token>`. Quando vencer, peça outro na mesma rota.

**Neste Swagger.** Entre antes por [/rh/login](/rh/login) na mesma janela; as rotas passam a
responder com o seu usuário. O botão **Authorize** aceita um token de `GET /rh/token`.

## Respostas de erro

| Código | Significado |
|---|---|
| 401 | Sem sessão ou token, ou sessão expirada. Refaça o login. |
| 403 | Autenticado, mas sem a permissão da rota, ou acesso revogado. |
| 404 | Registro, regra ou domínio inexistente. |
| 422 | Parâmetro inválido. |

O `registro` aceita `3` ou `000003`. Datas vêm em ISO 8601; nas listas do diagnóstico, já em `dd/mm/aaaa`.
"""

GRUPOS = [
    {"name": "rh", "description": "Login do RH, usuário atual, servidores, dependentes e domínios."},
    {"name": "rh-diagnostico", "description": "Painel, listas nominais por regra, planilhas e ficha de pendências."},
    {"name": "rh-admin", "description": "Usuários, sessões e auditoria. Só para o perfil `admin`."},
    {"name": "auth", "description": "Serviço de autenticação: Google, código de autorização, token e JWKS."},
    {"name": "infra", "description": "Verificação de funcionamento."},
]


# ---------- modelos das respostas ----------

class Erro(BaseModel):
    detail: str = Field(examples=["Sem permissão"])


class Status(BaseModel):
    status: str = Field(examples=["ok"])


class Usuario(BaseModel):
    sub: str = Field(description="Id do usuário", examples=["1"])
    email: str
    name: str
    roles: list[str] = Field(examples=[["rh"]])
    permissions: list[str] = Field(examples=[["rh:diagnostico:painel", "rh:servidores:listar"]])
    exp: int = Field(description="Validade do token atual (epoch, em segundos)")
    sessao_expira_em: datetime | None = Field(description="Fim da sessão; nulo quando o acesso é só por token")


class Token(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = Field(examples=[900])


class Dominio(BaseModel):
    CODIGO: str
    NOME: str


class ListaServidores(BaseModel):
    total: int
    pagina: int
    limite: int
    itens: list[dict[str, Any]] = Field(
        description="Colunas do SIP em maiúsculas (REGISTRO, MATRICULA, CONTRATO, NOME, SITUACAO...) "
        "e os nomes traduzidos com o sufixo _NOME. CPF só para quem pode ver a ficha."
    )


Tipo = Literal["erro", "alerta", "recadastro", "conferencia", "indicador"]


class Resumo(BaseModel):
    vinculos: int
    com_erro: int
    com_alerta: int
    sem_pendencia: int


class ResumoDivisao(Resumo):
    divisao: str


class Universo(BaseModel):
    empresa: str
    situacoes: list[str]
    vinculos: int
    dependentes: int


class RegraBase(BaseModel):
    codigo: str = Field(examples=["D03"])
    titulo: str
    tipo: Tipo
    alvo: Literal["dependente", "servidor"]
    descricao: str
    orientacao: str


class RegraDoPainel(RegraBase):
    servidores: int = Field(description="Vínculos com a pendência")
    ocorrencias: int = Field(description="Quantas vezes a pendência aparece")


class Painel(BaseModel):
    gerado_em: datetime
    universo: Universo
    resumo: Resumo
    regras: list[RegraDoPainel] = Field(description="Já ordenadas por gravidade e quantidade")


class Ocorrencia(BaseModel):
    REGISTRO: str
    MATRICULA: int | None
    CONTRATO: int | None
    SERVIDOR: str
    CPF_SERVIDOR: str
    ADMISSAO: str
    SITUACAO: str | None
    VINCULO: str | None
    CARGO: str | None
    DIVISAO: str | None
    LOCAL_TRABALHO: str | None
    CELULAR: str
    EMAIL: str
    ITEM: int | None = Field(None, description="Daqui até NOME_MAE: só nas regras de dependente")
    DEPENDENTE: str | None = None
    PARENTESCO: str | None = None
    NASCIMENTO: str | None = None
    IDADE: int | None = None
    CPF_DEPENDENTE: str | None = None
    DEPENDENTE_IRRF: Literal["Sim", "Não"] | None = None
    SALARIO_FAMILIA: Literal["Sim", "Não"] | None = None
    FAIXA_IDADE: Literal["Sim", "Não"] | None = None
    UNIVERSITARIO: Literal["Sim", "Não"] | None = None
    DEFICIENTE: Literal["Sim", "Não"] | None = None
    DOCUMENTOS: str | None = None
    DATA_ENTREGA: str | None = None
    NOME_MAE: str | None = None
    DETALHE: str


class ListaDaRegra(BaseModel):
    regra: RegraBase
    gerado_em: datetime
    total: int
    servidores: int
    pagina: int
    limite: int
    itens: list[Ocorrencia]


class Pendencia(BaseModel):
    codigo: str
    titulo: str
    tipo: Tipo
    item: int | None
    dependente: str | None
    parentesco: str | None
    idade: int | None
    detalhe: str
    dados: dict[str, Any] = Field(description="Demais campos do dependente, quando houver")


class Ficha(BaseModel):
    registro: str
    matricula: int | None
    contrato: int | None
    servidor: str
    situacao: str | None
    vinculo: str | None
    divisao: str | None
    local_trabalho: str | None
    gerado_em: datetime
    total: int
    pendencias: list[Pendencia]


class PermissaoDoPerfil(BaseModel):
    slug: str
    descricao: str


class Perfil(BaseModel):
    role: Literal["admin", "rh", "consulta"]
    nome: str
    permissoes: list[PermissaoDoPerfil]


class UsuarioAdmin(BaseModel):
    id: int
    email: str
    nome: str
    role: str | None
    ativo: bool
    ja_entrou: bool
    ultimo_login: datetime | None
    criado_em: datetime


class Sessao(BaseModel):
    id: int
    usuario_id: int
    usuario_email: str
    usuario_nome: str
    ativa: bool
    criada_em: datetime
    ultimo_uso: datetime
    expira_em: datetime
    encerrada_em: datetime | None
    ip: str | None
    navegador: str | None


class Encerradas(BaseModel):
    encerradas: int


class RegistroAuditoria(BaseModel):
    id: int
    quando: datetime
    usuario_id: int | None
    usuario_email: str | None
    acao: str = Field(examples=["servidores.detalhar"])
    alvo: str | None
    detalhe: dict[str, Any] | None
    ip: str | None


class Auditoria(BaseModel):
    total: int
    pagina: int
    limite: int
    itens: list[RegistroAuditoria]


MODELOS = [
    Erro, Status, Usuario, Token, Dominio, ListaServidores, Painel, ResumoDivisao, ListaDaRegra,
    Ficha, Perfil, UsuarioAdmin, Sessao, Encerradas, Auditoria,
]

PUBLICA, AUTENTICADO = "pública", "qualquer usuário autenticado"
Lista = lambda modelo: ("lista", modelo)  # noqa: E731

# (método, caminho) -> (resumo, permissão, modelo da resposta 200)
ROTAS: dict[tuple[str, str], tuple[str, str, Any]] = {
    ("get", "/"): ("Verificar se a API está no ar", PUBLICA, Status),
    ("get", "/auth/google"): ("Iniciar o login no Google para uma aplicação cliente", PUBLICA, None),
    ("get", "/auth/google/callback"): ("Retorno do Google (uso interno do fluxo)", PUBLICA, None),
    ("post", "/oauth/token"): ("Trocar o código de autorização por um JWT", "client_secret da aplicação", Token),
    ("get", "/.well-known/jwks.json"): ("Chave pública para validar os tokens", PUBLICA, None),
    ("get", "/rh/login"): ("Entrar com o Google", PUBLICA, None),
    ("get", "/rh/callback"): ("Retorno do login (uso interno do fluxo)", PUBLICA, None),
    ("get", "/rh/logout"): ("Sair e encerrar a sessão", PUBLICA, None),
    ("get", "/rh/me"): ("Usuário atual, perfis e permissões", AUTENTICADO, Usuario),
    ("get", "/rh/token"): ("Obter um token de acesso a partir da sessão", AUTENTICADO, Token),
    ("get", "/rh/dominios/{nome}"): ("Códigos e nomes para filtros", "rh:servidores:listar", Lista(Dominio)),
    ("get", "/rh/servidores"): ("Buscar servidores", "rh:servidores:listar", ListaServidores),
    ("get", "/rh/servidores/{registro}"): ("Dados de um servidor", "rh:servidores:detalhar", None),
    ("get", "/rh/servidores/{registro}/dependentes"): ("Dependentes de um registro", "rh:dependentes:ler", None),
    ("get", "/rh/diagnostico"): ("Painel do diagnóstico", "rh:diagnostico:painel", Painel),
    ("get", "/rh/diagnostico/por-divisao"): ("Situação dos vínculos por secretaria", "rh:diagnostico:painel", Lista(ResumoDivisao)),
    ("get", "/rh/diagnostico/por-divisao/perfil"): ("Perfil dos vínculos por secretaria (Raio-X)", "rh:diagnostico:painel", None),
    ("get", "/rh/diagnostico/por-divisao/regras"): ("Regras do diagnóstico por secretaria (Raio-X)", "rh:diagnostico:painel", None),
    ("get", "/rh/diagnostico/{codigo}"): ("Lista nominal de uma regra (JSON ou CSV)", "rh:diagnostico:listar", ListaDaRegra),
    ("get", "/rh/servidores/{registro}/pendencias"): ("Ficha de pendências de um vínculo", "rh:diagnostico:listar", Ficha),
    ("get", "/rh/admin/roles"): ("Perfis e o que cada um pode", "rh:usuarios:gerenciar", Lista(Perfil)),
    ("get", "/rh/admin/usuarios"): ("Listar usuários", "rh:usuarios:gerenciar", Lista(UsuarioAdmin)),
    ("post", "/rh/admin/usuarios"): ("Pré-cadastrar um usuário pelo e-mail", "rh:usuarios:gerenciar", UsuarioAdmin),
    ("patch", "/rh/admin/usuarios/{user_id}"): ("Alterar nome, perfil ou situação", "rh:usuarios:gerenciar", UsuarioAdmin),
    ("get", "/rh/admin/sessoes"): ("Sessões abertas", "rh:usuarios:gerenciar", Lista(Sessao)),
    ("delete", "/rh/admin/sessoes/{sessao_id}"): ("Encerrar uma sessão", "rh:usuarios:gerenciar", Encerradas),
    ("delete", "/rh/admin/usuarios/{user_id}/sessoes"): ("Encerrar todas as sessões de um usuário", "rh:usuarios:gerenciar", Encerradas),
    ("get", "/rh/admin/auditoria"): ("Consultar a auditoria", "rh:auditoria:ler", Auditoria),
    ("get", "/rh/indicadores/faixa-dependentes"): ("Dependentes por faixa etária", "rh:diagnostico:painel", None),
}
REDIRECIONA = {
    ("get", "/auth/google"), ("get", "/auth/google/callback"),
    ("get", "/rh/login"), ("get", "/rh/callback"), ("get", "/rh/logout"),
}


def _ref(modelo) -> dict:
    return {"$ref": f"#/components/schemas/{modelo.__name__}"}


def configurar(app: FastAPI) -> None:
    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        spec = get_openapi(
            title=app.title, version=app.version, description=DESCRICAO, routes=app.routes, tags=GRUPOS,
        )
        componentes = spec.setdefault("components", {})
        _, definicoes = models_json_schema(
            [(m, "serialization") for m in MODELOS], ref_template="#/components/schemas/{model}"
        )
        componentes.setdefault("schemas", {}).update(definicoes.get("$defs", {}))
        componentes["securitySchemes"] = {
            "sessao": {
                "type": "apiKey", "in": "cookie", "name": "rh_session",
                "description": "Cookie criado por /rh/login. O navegador envia sozinho.",
            },
            "bearer": {
                "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
                "description": "Token de GET /rh/token (15 minutos).",
            },
        }
        erro = {"application/json": {"schema": _ref(Erro)}}
        for caminho, operacoes in spec["paths"].items():
            for metodo, op in operacoes.items():
                resumo, permissao, modelo = ROTAS.get((metodo, caminho), (None, None, None))
                if resumo is None:
                    continue
                op["summary"] = resumo
                nota = f"**Permissão:** `{permissao}`" if ":" in permissao else f"**Acesso:** {permissao}"
                op["description"] = f"{nota}\n\n{op.get('description', '')}".strip()
                respostas = op.setdefault("responses", {})
                if (metodo, caminho) in REDIRECIONA:
                    respostas.pop("200", None)
                    respostas["302"] = {"description": "Redireciona. Abra no navegador; não use fetch nem o Try it out."}
                elif modelo is not None:
                    esquema = (
                        {"type": "array", "items": _ref(modelo[1])} if isinstance(modelo, tuple) else _ref(modelo)
                    )
                    respostas["200"] = {
                        "description": "Sucesso", "content": {"application/json": {"schema": esquema}},
                    }
                if permissao not in (PUBLICA,) and not permissao.startswith("client_secret"):
                    op["security"] = [{"sessao": []}, {"bearer": []}]
                    respostas["401"] = {"description": "Não autenticado ou sessão expirada", "content": erro}
                    if ":" in permissao:
                        respostas["403"] = {"description": "Sem permissão", "content": erro}
        csv = spec["paths"]["/rh/diagnostico/{codigo}"]["get"]["responses"]["200"]["content"]
        csv["text/csv"] = {"schema": {"type": "string", "description": "Com formato=csv: planilha separada por ponto e vírgula"}}
        app.openapi_schema = spec
        return spec

    app.openapi = openapi
