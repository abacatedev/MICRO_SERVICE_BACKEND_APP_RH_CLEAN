# Guia da API para construir o frontend do Pré-Censo

Este documento é a referência para quem vai construir um frontend sobre esta API, inclusive uma IA
de desenvolvimento. Ele descreve o modelo de autenticação adotado (cookie de sessão com proxy), cada
rota, os formatos de dados, as permissões e as regras de negócio que a interface precisa respeitar.

O contrato formal (OpenAPI 3) fica em `docs/openapi.json` e, com a API no ar, em
`http://localhost:8000/openapi.json`. A documentação interativa fica em `http://localhost:8000/docs`.
Quando este guia e o contrato divergirem, vale o contrato.

---

## 0. Instruções para a IA que for construir o frontend

Siga estas regras. Elas não são preferência de estilo; quebrá-las deixa o sistema inseguro ou quebrado.

1. **Autenticação por cookie de sessão com proxy.** O frontend nunca guarda token, senha ou segredo.
   Não use `localStorage`, `sessionStorage` nem cabeçalho `Authorization`. Não implemente login próprio,
   NextAuth, Auth0 ou similares.
2. **Todas as chamadas usam caminhos relativos** (`/rh/me`, `/rh/diagnostico`), nunca
   `http://localhost:8000/...`. A URL da API (`API_TARGET=http://localhost:8000`) fica só no
   `.env.local` e é lida só pelo `next.config.mjs`, que repassa esses caminhos para a API (seção 2.2).
3. **Entrar e sair são navegações, não `fetch`.** Use link ou `window.location.href` para `/rh/login` e
   `/rh/logout`.
4. **O frontend não guarda regra de negócio.** Títulos, descrições, gravidades, contagens e orientações
   das regras vêm da API. Não escreva no código a lista de regras, os limites de idade nem os textos.
5. **Mostre ou esconda telas pelas `permissions` do `/rh/me`**, nunca pelo nome do perfil. A API já
   bloqueia o que não é permitido; o frontend só evita mostrar o que daria 403.
6. **Toda consulta a dado nominal fica registrada na auditoria.** Não faça pré-carregamento,
   "prefetch" ou chamadas especulativas de fichas, dependentes ou listas nominais. Busque só quando a
   pessoa pedir.
7. **O `REGISTRO` é a chave que o RH usa no dia a dia.** Mostre-o sempre, em destaque, com os zeros
   à esquerda (`005895`).
8. **Dados pessoais.** Não registre respostas da API no console, em ferramentas de analytics ou em
   serviços de erro externos.
9. **Use `localhost`, nunca `127.0.0.1`** (seção 2.3).

---

## 1. Visão geral

| Item | Valor |
|---|---|
| API | FastAPI em `http://localhost:8000` (Docker Compose) |
| Frontend | Porta própria, por exemplo `http://localhost:3000` |
| Fonte dos dados | Cópia de análise do SIP (Firebird), **somente leitura** |
| Escopo | Empresa `001` (Prefeitura de Cáceres), vínculos ativos: situações `1` (Normal) e `3` (Afastado) |
| Autenticação | Google, só para e-mails pré-cadastrados; sessão de 8 horas em cookie HttpOnly |
| Idioma | Português do Brasil em textos, mensagens e nomes de campo |

A API não grava nada no SIP. As únicas escritas são no banco próprio do sistema: usuários, sessões e
auditoria (rotas `/rh/admin`).

---

## 2. Autenticação: cookie de sessão com proxy

### 2.1 A ideia

O navegador só conversa com o endereço do frontend. O servidor do frontend repassa (proxy) os caminhos
da API para `localhost:8000`. Para o navegador, frontend e API são o mesmo site, então:

- não há CORS;
- os cookies de sessão vão e voltam sozinhos;
- o frontend não precisa saber nada sobre tokens.

Caminhos que precisam passar pelo proxy: **`/rh`, `/auth`, `/oauth`, `/.well-known`**. Os quatro são
necessários: o login passa por `/rh/login` e em seguida por `/auth/google`.

### 2.2 URL da API e configuração do proxy

A API do RH está em:

```dotenv
API_TARGET=http://localhost:8000
```

| Ambiente | Valor de `API_TARGET` |
|---|---|
| Desenvolvimento em casa (frontend com `npm run dev`, API no Docker) | `http://localhost:8000` |
| Frontend em contêiner no mesmo Docker Compose da API | `http://api:8000` |
| Produção | Não se usa: o proxy reverso do domínio faz o papel (ver abaixo) |

Regras para essa variável:

1. Fica em `.env.local` na raiz do frontend. Esse arquivo **não** vai para o Git.
2. A mesma linha vai para `.env.example`, que vai para o Git, para quem clonar saber o que configurar.
3. É lida **somente** no arquivo de configuração do proxy (`next.config.mjs` ou `vite.config.ts`).
   Não use o prefixo `NEXT_PUBLIC_` nem `VITE_`: a URL da API não deve chegar ao navegador.
4. O código que roda no navegador **nunca** usa `http://localhost:8000`. Ele chama só caminhos
   relativos (`/rh/me`, `/rh/diagnostico`, `/rh/login?retorno=...`).
5. Depois de mudar o `.env.local`, reinicie o servidor de desenvolvimento (`npm run dev`). A
   configuração só é lida na partida.

Endereços da API úteis para quem desenvolve (não para o código do navegador):

| Endereço | Conteúdo |
|---|---|
| `http://localhost:8000/` | Saúde: `{"status":"ok"}` |
| `http://localhost:8000/docs` | Swagger |
| `http://localhost:8000/openapi.json` | Contrato OpenAPI 3 |

**Next.js 16** (`next.config.mjs`), o frontend oficial (`MICRO_SERVICE_FRONTEND_RH`):

```js
// next.config.mjs
// Repassa para a API os quatro caminhos do backend. O navegador só conhece localhost:3000.
const API_TARGET = process.env.API_TARGET ?? "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return ["rh", "auth", "oauth", ".well-known"].map((caminho) => ({
      source: `/${caminho}/:path*`,
      destination: `${API_TARGET}/${caminho}/:path*`,
    }));
  },
};

export default nextConfig;
```

Atenção: as páginas do frontend não podem usar `/rh`, `/auth`, `/oauth` nem `/.well-known` como
rota própria, porque esses caminhos pertencem à API. Use, por exemplo, `/painel`, `/regras/D01`,
`/servidores/001750`, `/admin/usuarios`.

**Vite** (`vite.config.ts`), usado pelo frontend antigo:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API = process.env.API_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: Object.fromEntries(
      ["/rh", "/auth", "/oauth", "/.well-known"].map((rota) => [rota, { target: API, changeOrigin: false }]),
    ),
  },
});
```

Em produção, o mesmo papel é feito por um proxy reverso (Nginx, Caddy, Traefik) que serve o frontend e
encaminha esses quatro caminhos para a API no mesmo domínio.

### 2.3 Configuração da API (`.env` do backend)

```dotenv
FRONTEND_URL=http://localhost:3000/
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

- `FRONTEND_URL`: para onde a pessoa volta depois do login, quando o frontend não informa `retorno`.
- `CORS_ORIGINS`: lista de frontends aceitos no parâmetro `retorno`. Com proxy não há CORS, mas a lista
  continua servindo para validar o retorno.

Depois de alterar: `docker compose up -d --force-recreate api`.

Por que `localhost` e não `127.0.0.1`: o retorno do Google chega em `localhost:8000` e a pessoa volta
para `localhost:3000`. Em `localhost`, o navegador compartilha os cookies entre as portas; entre
`localhost` e `127.0.0.1`, não.

### 2.4 Cookies (o frontend não lê nenhum deles)

| Cookie | Duração | Função |
|---|---|---|
| `rh_session` | até 8 h | Sessão. Expira também após 30 min sem uso, no logout ou se um admin a encerrar |
| `rh_token` | 15 min | Token de acesso. A API renova sozinha enquanto a sessão vale |
| `rh_state`, `rh_retorno`, `auth_session` | 10 min | Uso interno durante o login |

Todos são HttpOnly: o JavaScript não consegue lê-los, e não deve tentar.

### 2.5 Fluxo de login

```
Frontend            Proxy / API                         Google
   |  navega para /rh/login?retorno=...                    |
   |------------------------------------------------------>|
   |              302 para /auth/google  ->  302 para o Google
   |                                       login da pessoa |
   |              /auth/google/callback  <------------------|
   |              confere cadastro, perfil e acesso
   |              /rh/callback: cria a sessão (cookies)
   |  302 para o endereço de retorno                       |
   |<------------------------------------------------------|
   |  fetch("/rh/me") -> 200 com o usuário                 |
```

| Situação | O que o frontend faz |
|---|---|
| Entrar | `window.location.href = "/rh/login?retorno=" + encodeURIComponent(location.href)` |
| Voltou do login | Chama `GET /rh/me` |
| URL com `?acesso=negado` | Mostra: "Esta conta Google não tem acesso. Peça o cadastro do seu e-mail ao administrador." |
| Qualquer chamada devolve 401 | Mostra a tela de entrada (ou redireciona para o login) |
| Sair | `window.location.href = "/rh/logout?retorno=" + encodeURIComponent(location.origin + "/")` |

O `retorno` é opcional. Ele precisa começar por uma origem de `CORS_ORIGINS`; caso contrário a API
responde 400 ("Endereço de retorno não autorizado"). Sem ele, vale o `FRONTEND_URL`.

### 2.6 Cliente HTTP recomendado

```ts
// src/api/cliente.ts
export class NaoAutenticado extends Error {}
export class SemPermissao extends Error {}
export class NaoEncontrado extends Error {}

export async function api<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resposta = await fetch(caminho, {
    ...init,
    credentials: "same-origin",
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  if (resposta.status === 401) throw new NaoAutenticado();
  if (resposta.status === 403) throw new SemPermissao();
  if (resposta.status === 404) throw new NaoEncontrado();
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    const detalhe = typeof corpo?.detail === "string" ? corpo.detail : `Falha ${resposta.status}`;
    throw new Error(detalhe);
  }
  return resposta.json() as Promise<T>;
}

export const entrar = () =>
  (window.location.href = `/rh/login?retorno=${encodeURIComponent(window.location.href)}`);

export const sair = () =>
  (window.location.href = `/rh/logout?retorno=${encodeURIComponent(window.location.origin + "/")}`);
```

Com React Query, trate `NaoAutenticado` de forma global (sem novas tentativas) e leve a pessoa para a
tela de entrada. Não repita automaticamente chamadas que deram 401 ou 403.

---

## 3. Erros

| Código | Corpo | Quando | O que a interface faz |
|---|---|---|---|
| 401 | `{"detail": "Não autenticado"}` | Sem sessão | Tela de entrada |
| 401 | `{"detail": "Sessão expirada"}` | 8 h, 30 min sem uso, ou sessão encerrada por um admin | Aviso curto e tela de entrada |
| 403 | `{"detail": "Sem permissão"}` | O perfil não tem a permissão da rota | Mensagem; não deveria ocorrer se o menu respeita as permissões |
| 403 | `{"detail": "Acesso revogado"}` | Usuário desativado durante o uso | Tela de entrada com aviso |
| 404 | `{"detail": "..."}` | Registro, regra ou domínio inexistente | Mensagem na própria tela |
| 409 | `{"detail": "..."}` | Admin: e-mail já cadastrado, ou tentativa de remover o último admin | Mensagem no formulário |
| 422 | `{"detail": [ {"loc": [...], "msg": "...", "type": "..."} ]}` | Parâmetro ou corpo inválido | Erro ao lado do campo indicado em `loc` |
| 500 | texto ou JSON | Falha no SIP ou na API | "Não foi possível consultar o SIP agora. Tente de novo em instantes." |

Atenção: no 422, `detail` é uma lista; nos demais, um texto.

---

## 4. Permissões e telas

`GET /rh/me` devolve `permissions`. Monte o menu a partir delas:

| Permissão | Libera | Perfis |
|---|---|---|
| `rh:diagnostico:painel` | Painel (só contagens) e recorte por secretaria | admin, rh, consulta |
| `rh:diagnostico:listar` | Listas nominais, planilhas CSV e ficha de pendências | admin, rh |
| `rh:servidores:listar` | Busca de servidores e domínios (sem CPF para quem não detalha) | admin, rh, consulta |
| `rh:servidores:detalhar` | Dados completos do servidor (CPF, endereço, documentos) | admin, rh |
| `rh:dependentes:ler` | Dependentes de um registro | admin, rh |
| `rh:usuarios:gerenciar` | Usuários, perfis e sessões | admin |
| `rh:auditoria:ler` | Auditoria | admin |

Telas sugeridas e a permissão de cada uma:

| Tela | Rotas | Permissão |
|---|---|---|
| Entrada | `/rh/login` | pública |
| Painel | `/rh/diagnostico`, `/rh/diagnostico/por-divisao` | `rh:diagnostico:painel` |
| Lista de uma regra | `/rh/diagnostico/{codigo}` | `rh:diagnostico:listar` |
| Busca de servidores | `/rh/servidores`, `/rh/dominios/{nome}` | `rh:servidores:listar` |
| Ficha do servidor | `/rh/servidores/{registro}`, `.../dependentes`, `.../pendencias` | `rh:servidores:detalhar`, `rh:dependentes:ler`, `rh:diagnostico:listar` (cada bloco só aparece com a sua permissão) |
| Usuários | `/rh/admin/usuarios`, `/rh/admin/roles` | `rh:usuarios:gerenciar` |
| Sessões | `/rh/admin/sessoes` | `rh:usuarios:gerenciar` |
| Auditoria | `/rh/admin/auditoria` | `rh:auditoria:ler` |

No perfil `consulta`, o painel aparece, mas as regras não viram link.

---

## 5. Convenções dos dados

- **Nomes de campo.** Rotas que leem o SIP direto (`/rh/servidores...`, `/rh/dominios`) usam os nomes
  das colunas do SIP, em maiúsculas (`REGISTRO`, `NOME`, `DTADMISSAO`). As rotas do diagnóstico e de
  administração usam nomes próprios (minúsculas, ou maiúsculas já formatadas nas listas da regra).
- **Códigos e nomes.** Todo código do SIP vem acompanhado do nome com o sufixo `_NOME`:
  `SITUACAO: "1"` e `SITUACAO_NOME: "Normal"`. Mostre o nome; use o código só em filtros.
- **`REGISTRO`.** Texto de 6 dígitos com zeros à esquerda. Nas rotas, aceita `3` ou `000003`.
- **Matrícula.** Mostre como no SIP: `MATRICULA-CONTRATO` (por exemplo `207-1`).
- **Datas.** Rotas do SIP e de administração: ISO 8601 (`"2002-08-05"`, `"2026-10-06T23:34:13+00:00"`);
  formate para `dd/mm/aaaa`. Listas do diagnóstico: já vêm em `dd/mm/aaaa`.
- **Marcações.** Nas rotas do SIP, `"S"` e `"N"`. Nas listas do diagnóstico, já vêm como `"Sim"` e `"Não"`.
- **Vazios.** Campos ausentes vêm como `null` ou `""`. Mostre "Não informado".
- **CPF.** Rotas do SIP: só dígitos (aplique a máscara `000.000.000-00`). Listas do diagnóstico: já
  formatado.
- **Textos do SIP** podem vir em maiúsculas e sem acento em parte dos registros; não tente corrigir.

---

## 6. Referência das rotas

Parâmetros com `*` são obrigatórios. Todas as rotas abaixo, menos as de login, exigem sessão.
Os exemplos usam nomes, documentos e números fictícios.

### 6.1 Sessão e usuário

#### `GET /rh/login` · navegação
| Parâmetro | Tipo | Descrição |
|---|---|---|
| `retorno` | query, texto | Endereço para voltar após o login (origem em `CORS_ORIGINS`) |

Responde 302. Não use `fetch`.

#### `GET /rh/logout` · navegação
| Parâmetro | Tipo | Descrição |
|---|---|---|
| `retorno` | query, texto | Endereço para voltar após sair |

Encerra a sessão no servidor e apaga os cookies. Responde 302.

#### `GET /rh/me`
Quem está logado.

```json
{
  "sub": "1",
  "email": "servidora@exemplo.gov.br",
  "name": "Maria Exemplo",
  "roles": ["rh"],
  "permissions": ["rh:dependentes:ler", "rh:diagnostico:listar", "rh:diagnostico:painel",
                  "rh:servidores:detalhar", "rh:servidores:listar"],
  "exp": 1791345917,
  "sessao_expira_em": "2026-10-07T11:50:17+00:00"
}
```

`sessao_expira_em` é o fim máximo da sessão (8 h). Pode ser mostrado no menu do usuário.

#### `GET /rh/token`
Não é necessário com proxy. Existe para integrações que precisem de `Authorization: Bearer`.

### 6.2 Diagnóstico cadastral

O diagnóstico lê os vínculos ativos e seus dependentes, aplica as regras e guarda o resultado em
memória por 10 minutos. **A primeira chamada pode levar alguns segundos**: mostre um estado de
carregamento com o texto "Lendo o cadastro no SIP…".

#### `GET /rh/diagnostico` · `rh:diagnostico:painel`
| Parâmetro | Tipo | Descrição |
|---|---|---|
| `atualizar` | query, booleano, padrão `false` | `true` recalcula agora (botão "Atualizar leitura") |

```json
{
  "gerado_em": "2026-10-07T03:19:07+00:00",
  "universo": { "empresa": "001", "situacoes": ["1", "3"], "vinculos": 2463, "dependentes": 3150 },
  "resumo": { "vinculos": 2463, "com_erro": 1200, "com_alerta": 600, "sem_pendencia": 663 },
  "regras": [
    {
      "codigo": "D01",
      "titulo": "Dependente sem CPF",
      "tipo": "erro",
      "alvo": "dependente",
      "descricao": "O dependente está cadastrado sem CPF...",
      "orientacao": "Pedir o CPF ao servidor. No SIP: Cadastro de Trabalhadores, Dependentes, Alterar...",
      "servidores": 318,
      "ocorrencias": 512
    }
  ]
}
```

- `resumo`: cada vínculo entra em uma só categoria, pela pior pendência. `com_erro + com_alerta +
  sem_pendencia = vinculos`. Bom para uma barra de proporção.
- `regras`: já vem **ordenada** (erros primeiro, depois por quantidade). Mantenha a ordem.
- `servidores`: quantos vínculos têm a pendência. `ocorrencias`: quantas vezes ela aparece (um servidor
  pode ter vários dependentes na mesma regra).
- Uma regra com `servidores: 0` pode ser mostrada esmaecida e sem link.

**Agrupamento sugerido por `tipo`:**

| `tipo` | Grupo na tela | Significado |
|---|---|---|
| `erro` | Erros | Cadastro incorreto ou incompleto; precisa correção |
| `alerta` | Alertas | Vale conferir com o servidor |
| `recadastro` | Alertas | Dados existem em outro registro; o RH pode recadastrar |
| `conferencia` | Para acompanhar | Conferir, não é necessariamente erro |
| `indicador` | Para acompanhar | Informação para planejar o Censo |

Use cor só para gravidade (erro, alerta, recadastro) e sempre com o rótulo em texto ao lado.

#### `GET /rh/diagnostico/por-divisao` · `rh:diagnostico:painel`
Situação por secretaria, da que tem mais erros para a que tem menos.

```json
[
  { "divisao": "SECRETARIA MUNICIPAL DE SAÚDE", "vinculos": 610, "com_erro": 320, "com_alerta": 150, "sem_pendencia": 140 }
]
```

#### `GET /rh/indicadores/faixa-dependentes` · `rh:diagnostico:painel`
Dependentes dos vínculos ativos por faixa etária (gráfico "Faixa etária dos dependentes").

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `divisao` | query, texto | Secretaria: código (`000003` ou `3`) ou nome exato |
| `subdivisao` | query, texto | Subdivisão: código ou nome exato |
| `vinculo` | query, texto | Vínculo: código ou nome exato |
| `atualizar` | query, booleano | `true` relê o SIP |

```json
{
  "gerado_em": "2026-10-21T23:40:00+00:00",
  "filtros": { "divisao": null, "subdivisao": null, "vinculo": null },
  "vinculos_com_dependentes": 1450,
  "dependentes": 3150,
  "em_desconformidade": 980,
  "sem_data": 12,
  "faixas": [
    { "faixa": "21-23", "idade_minima": 21, "idade_maxima": 23, "exige_comprovacao": true,
      "dependentes": 210, "irrf": 150, "salario_familia": 40, "universitario": 8, "deficiente": 1,
      "irrf_fora_do_limite": 120, "salario_familia_fora_do_limite": 40, "em_desconformidade": 130 }
  ]
}
```

- `faixas` vem sempre com as oito faixas, na ordem: `0-13`, `14-17`, `18-20`, `21-23`, `24-29`,
  `30-39`, `40+`, `Sem data` (faixa vazia vem com zeros).
- `exige_comprovacao: true` (21 anos em diante e `Sem data`): pinte de laranja.
- `em_desconformidade`: dependente com IRRF ou salário-família marcado fora do limite de idade do
  vínculo (IRRF sai no ano seguinte ao que completa 21, ou 24 se universitário; salário-família a
  partir dos 14). Deficientes e cônjuges não entram.
- Só números, sem dados nominais. Resultado em cache por 10 minutos; os filtros não releem o SIP.

#### `GET /rh/diagnostico/{codigo}` · `rh:diagnostico:listar`
Lista nominal de uma regra.

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `codigo*` | caminho | Código da regra (`D01`, `S02`...); aceita minúsculas |
| `formato` | query, `json` ou `csv`, padrão `json` | `csv` baixa a planilha |
| `limite` | query, 1 a 1000, padrão 100 | Itens por página |
| `pagina` | query, a partir de 1 | Página |

```json
{
  "regra": { "codigo": "D03", "titulo": "...", "tipo": "erro", "alvo": "dependente",
             "descricao": "...", "orientacao": "..." },
  "gerado_em": "2026-10-07T03:19:07+00:00",
  "total": 512,
  "servidores": 318,
  "pagina": 1,
  "limite": 100,
  "itens": [
    {
      "REGISTRO": "001234", "MATRICULA": 207, "CONTRATO": 1,
      "SERVIDOR": "FULANO DE EXEMPLO", "CPF_SERVIDOR": "123.456.789-09", "ADMISSAO": "05/08/2002",
      "SITUACAO": "Normal", "VINCULO": "EFETIVO", "CARGO": "AGENTE ADMINISTRATIVO",
      "DIVISAO": "SECRETARIA MUNICIPAL DE SAÚDE", "LOCAL_TRABALHO": "UBS CENTRO",
      "CELULAR": "65999990000", "EMAIL": "fulano@exemplo.com",
      "ITEM": 1, "DEPENDENTE": "BELTRANO DE EXEMPLO",
      "PARENTESCO": "Filho(a) não emancipado menor de 21 Anos",
      "NASCIMENTO": "21/08/1990", "IDADE": 36, "CPF_DEPENDENTE": "",
      "DEPENDENTE_IRRF": "Sim", "SALARIO_FAMILIA": "Não", "FAIXA_IDADE": "Não",
      "UNIVERSITARIO": "Não", "DEFICIENTE": "Não",
      "DOCUMENTOS": "Nenhum", "DATA_ENTREGA": "01/02/2014", "NOME_MAE": "FULANA DE EXEMPLO",
      "DETALHE": "36 anos; limite de IRRF do vínculo: 21"
    }
  ]
}
```

- `regra.alvo` define as colunas: em `"servidor"`, os campos de `ITEM` a `NOME_MAE` não existem.
- `DETALHE` explica por que a linha entrou na regra. Mostre sempre.
- Para mostrar tudo de uma vez, busque as páginas em sequência até completar `total`.
- `PARENTESCO` é longo: mostre a parte inicial ("Filho(a)") e o texto completo em dica ou detalhe.
- Planilha: use um link comum, `<a href="/rh/diagnostico/D03?formato=csv">Baixar planilha</a>`. O arquivo
  vem separado por ponto e vírgula, em UTF-8 com BOM (abre direto no Excel) e com o nome
  `diagnostico_D03.csv`.

#### `GET /rh/servidores/{registro}/pendencias` · `rh:diagnostico:listar`
Tudo o que o diagnóstico encontrou para um vínculo ativo. 404 se o registro não for vínculo ativo.

```json
{
  "registro": "001234", "matricula": 207, "contrato": 1, "servidor": "FULANO DE EXEMPLO",
  "situacao": "Normal", "vinculo": "EFETIVO", "divisao": "SECRETARIA MUNICIPAL DE SAÚDE",
  "local_trabalho": "UBS CENTRO", "gerado_em": "2026-10-07T03:19:07+00:00", "total": 2,
  "pendencias": [
    {
      "codigo": "D03", "titulo": "IRRF marcado acima da idade, sem controle de faixa de idade",
      "tipo": "erro", "item": 2, "dependente": "BELTRANO DE EXEMPLO",
      "parentesco": "Filho(a) não emancipado menor de 21 Anos", "idade": 25,
      "detalhe": "25 anos; limite de IRRF do vínculo: 21",
      "dados": { "NASCIMENTO": "13/08/2001", "DEPENDENTE_IRRF": "Sim", "FAIXA_IDADE": "Não" }
    }
  ]
}
```

Pendências do servidor (regras `S`, `V`, `I`) vêm com `item`, `dependente`, `parentesco` e `idade` nulos.
Sugestão: agrupar as pendências por dependente na ficha.

### 6.3 Servidores e dependentes (leitura direta do SIP)

#### `GET /rh/servidores` · `rh:servidores:listar`
| Parâmetro | Tipo | Descrição |
|---|---|---|
| `nome` | query, mínimo 2 caracteres | Trecho do nome (sem diferenciar maiúsculas) |
| `situacao` | query, código | Código de `SITUACOES` (`1` Normal, `3` Afastado, `6` Desligado...) |
| `ativos` | query, booleano | `true` restringe a Normal e Afastado |
| `limite` | query, 1 a 200, padrão 50 | Itens por página |
| `pagina` | query, a partir de 1 | Página |

```json
{
  "total": 16, "pagina": 1, "limite": 50,
  "itens": [
    {
      "REGISTRO": "001234", "MATRICULA": 207, "CONTRATO": 1, "NOME": "FULANO DE EXEMPLO",
      "CPF": "12345678909",
      "SITUACAO": "1", "VINCULO": "02", "CARGOATUAL": "0058", "DIVISAO": "000003",
      "SUBDIVISAO": "003001", "LOCAL_TRABALHO": "000165",
      "DTADMISSAO": "2002-08-05", "DTDEMISSAO": null,
      "SITUACAO_NOME": "Normal", "VINCULO_NOME": "EFETIVO", "CARGOATUAL_NOME": "AGENTE ADMINISTRATIVO",
      "DIVISAO_NOME": "SECRETARIA MUNICIPAL DE SAÚDE", "SUBDIVISAO_NOME": "SAÚDE - ADMINISTRATIVO",
      "LOCAL_TRABALHO_NOME": "UBS CENTRO"
    }
  ]
}
```

- `CPF` só aparece para quem tem `rh:servidores:detalhar`.
- A mesma pessoa pode aparecer em vários registros (vínculos antigos e atuais). Mostre a situação de
  cada um e destaque os ativos.
- Ordem: alfabética por nome, depois registro. Faça a busca só depois que a pessoa digitar ou enviar,
  com espera de pelo menos 400 ms entre teclas.

#### `GET /rh/servidores/{registro}` · `rh:servidores:detalhar`
Dados completos de um registro. Campos: os da lista mais `CPF`, `SEXO`, `DTNASCIMENTO`, `ESTADOCIVIL`,
`INSTRUCAO`, `NOMEMAE`, `NOMEPAI`, `CEP`, `ENDERECO`, `NUMERO`, `BAIRRO`, `COMPL`, `CIDADE`, `UF`,
`TELEFONE`, `CELULAR`, `EMAIL`, `PIS`, `RG`, `RGORGAOEMISSOR`, `UFRG`, `DTRG`, `CTPS`, `SERIE`,
`UFCTPS`, `CLT_OU_ESTATUTO`, `HORASEMANAL`, `CAT_TRAB_ESOCIAL`, `STATUS_ESOCIAL`, `DH_ALTEROU`, e os
seis `_NOME`. `ESTADOCIVIL` e `INSTRUCAO` vêm só como código.

Sugestão de layout, na ordem da tela do SIP que o RH conhece: cabeçalho (registro, admissão, matrícula,
contrato, nome), dados pessoais, documentos, endereço e contato, dependentes, pendências.

#### `GET /rh/servidores/{registro}/dependentes` · `rh:dependentes:ler`
Lista de dependentes do registro, por `ITEM`:

```json
[
  {
    "ITEM": 1, "NOME": "BELTRANO DE EXEMPLO", "DTNASC": "2007-01-04", "IDADE": 19, "SEXO": "M",
    "PARENTESCO": "03", "PARENTESCO_NOME": "Filho(a) não emancipado menor de 21 Anos",
    "CPF": "", "NOMEMAE": "FULANA DE EXEMPLO",
    "IRRF": "S", "SALFAMILIA": "S", "DEFICIENTE": "N", "UNIVERSITARIO": "N", "DTOBITO": null,
    "INI_IRRF": null, "FIM_IRRF": null, "INI_SALFAM": null, "FIM_SALFAM": null
  }
]
```

`IDADE` vem do próprio SIP e pode estar desatualizada; para exibir, calcule pela `DTNASC`.

#### `GET /rh/dominios/{nome}` · `rh:servidores:listar`
Códigos e nomes para filtros e caixas de seleção. `nome` aceita: `situacoes`, `parentescos`,
`vinculos`, `cargos`, `divisoes`, `subdivisoes`, `locais_trabalho`.

```json
[ { "CODIGO": "1", "NOME": "Normal" }, { "CODIGO": "3", "NOME": "Afastado" } ]
```

Esses dados mudam pouco: guarde em cache por toda a sessão.

### 6.4 Administração (`rh:usuarios:gerenciar`)

#### `GET /rh/admin/roles`
Perfis e o que cada um pode. Use para montar o seletor de perfil.

```json
[ { "role": "consulta", "nome": "Consulta",
    "permissoes": [ { "slug": "rh:servidores:listar", "descricao": "Listar servidores..." } ] } ]
```

#### `GET /rh/admin/usuarios`
```json
[ { "id": 2, "email": "servidora@exemplo.gov.br", "nome": "Maria Exemplo", "role": "consulta",
    "ativo": true, "ja_entrou": false, "ultimo_login": null, "criado_em": "2026-10-06T23:09:30+00:00" } ]
```

`ja_entrou: false` indica pré-cadastro que ainda não fez o primeiro login.

#### `POST /rh/admin/usuarios`
Pré-cadastro. Corpo:

```json
{ "email": "fulano@gmail.com", "nome": "Fulano de Tal", "role": "consulta" }
```

- `email`: formato de e-mail, até 255 caracteres. A API grava em minúsculas.
- `nome`: 2 a 255 caracteres. Será substituído pelo nome da conta Google no primeiro login.
- `role`: `admin`, `rh` ou `consulta`.

Resposta 201 com o usuário. 409 se o e-mail já estiver cadastrado. A pessoa entra com a conta Google
desse e-mail; não há senha nem convite por e-mail.

#### `PATCH /rh/admin/usuarios/{user_id}`
Corpo com qualquer combinação dos campos:

```json
{ "nome": "Fulano de Tal", "role": "rh", "ativo": false }
```

- Desativar (`ativo: false`) encerra todas as sessões da pessoa na hora.
- 409 ao tentar desativar ou rebaixar o último administrador ativo.
- Não há exclusão: desativar preserva o histórico da auditoria. Peça confirmação antes de desativar.

#### `GET /rh/admin/sessoes`
| Parâmetro | Tipo | Descrição |
|---|---|---|
| `somente_ativas` | query, booleano, padrão `true` | `false` inclui as encerradas |
| `usuario_id` | query, inteiro | Filtra por usuário |

```json
[ { "id": 1, "usuario_id": 1, "usuario_email": "...", "usuario_nome": "...", "ativa": true,
    "criada_em": "...", "ultimo_uso": "...", "expira_em": "...", "encerrada_em": null,
    "ip": "172.26.0.1", "navegador": "Mozilla/5.0 ..." } ]
```

#### `DELETE /rh/admin/sessoes/{sessao_id}` e `DELETE /rh/admin/usuarios/{user_id}/sessoes`
Encerram uma sessão, ou todas de um usuário. Respondem `{ "encerradas": 1 }`. Peça confirmação.

### 6.5 Auditoria (`rh:auditoria:ler`)

#### `GET /rh/admin/auditoria`
| Parâmetro | Tipo | Descrição |
|---|---|---|
| `usuario_id` | query, inteiro | Quem fez |
| `acao` | query, texto | Ação ou prefixo (`usuarios.` traz todas de usuários) |
| `alvo` | query, texto | Registro do servidor (`3` ou `000003`) ou id do usuário |
| `de`, `ate` | query, data e hora ISO 8601 | Período |
| `limite` | query, 1 a 500, padrão 100 | Itens por página |
| `pagina` | query, a partir de 1 | Página |

```json
{ "total": 14, "pagina": 1, "limite": 100,
  "itens": [ { "id": 14, "quando": "2026-10-06T23:46:42+00:00", "usuario_id": 1,
               "usuario_email": "...", "acao": "servidores.detalhar", "alvo": "001234",
               "detalhe": { "encontrado": true }, "ip": "172.26.0.1" } ] }
```

Ações existentes, com rótulo sugerido:

| `acao` | Rótulo |
|---|---|
| `login.sucesso` | Entrou no sistema |
| `login.negado` | Tentativa de acesso negada |
| `logout` | Saiu |
| `servidores.listar` | Buscou servidores |
| `servidores.detalhar` | Abriu a ficha de um servidor |
| `dependentes.listar` | Consultou dependentes |
| `diagnostico.painel` | Abriu o painel |
| `diagnostico.listar` | Abriu ou baixou a lista de uma regra |
| `diagnostico.ficha` | Abriu a ficha de pendências |
| `usuarios.criar` | Cadastrou usuário |
| `usuarios.alterar` | Alterou usuário |
| `sessoes.encerrar` | Encerrou sessão |

### 6.6 Outras rotas

Não são usadas pelo frontend do RH: `GET /` (status), `GET /auth/google`, `GET /auth/google/callback`,
`POST /oauth/token`, `GET /.well-known/jwks.json` (serviço de autenticação para outras aplicações).

---

## 7. Regras do diagnóstico

A lista abaixo é só para entendimento. **O frontend lê as regras da API** (`GET /rh/diagnostico`); elas
podem mudar sem alteração no frontend. Os códigos são internos deste projeto, não vêm do SIP nem do
eSocial. Na tela, mostre o título; o código pode aparecer discreto, como referência.

| Código | Título | Tipo | Alvo |
|---|---|---|---|
| D01 | Dependente sem CPF | erro | dependente |
| D11 | Dependente sem nenhum documento | erro | dependente |
| D02 | CPF de dependente inválido, repetido ou igual ao do servidor | erro | dependente |
| D03 | IRRF marcado acima da idade, sem controle de faixa de idade | erro | dependente |
| D04 | Salário-família marcado acima da idade, sem controle de faixa de idade | erro | dependente |
| D13 | IRRF marcado acima da idade, com controle de faixa de idade | alerta | dependente |
| D14 | Salário-família marcado acima da idade, com controle de faixa de idade | alerta | dependente |
| D05 | Parentesco "menor de 21 anos" com 21 anos ou mais | alerta | dependente |
| D06 | Mais de um cônjuge ou companheiro no mesmo registro | alerta | dependente |
| D07 | Idade incoerente com o parentesco | alerta | dependente |
| D08 | PAI com sexo feminino ou MÃE com sexo masculino | alerta | dependente |
| D09 | Dependente duplicado no mesmo registro | alerta | dependente |
| D12 | Certidão de nascimento sem dados do cartório | indicador | dependente |
| D15 | Documentação do dependente entregue há mais de 5 anos | indicador | dependente |
| D10 | Parentesco "Outros" | indicador | dependente |
| S01 | Servidor sem celular | alerta | servidor |
| S02 | Servidor sem e-mail | alerta | servidor |
| S07 | Estado civil solteiro com cônjuge entre os dependentes | alerta | servidor |
| S03 | Título de eleitor ausente ou com preenchimento falso | alerta | servidor |
| S04 | PIS ausente ou com preenchimento falso | erro | servidor |
| S05 | Servidor sem nome da mãe | erro | servidor |
| S06 | CPF do servidor ausente ou inválido | erro | servidor |
| V01 | Vínculo ativo com data de término vencida | alerta | servidor |
| V02 | CPF com mais de um vínculo ativo | conferencia | servidor |
| I01 | Sem dependentes em nenhum registro | indicador | servidor |
| I02 | Sem dependentes no vínculo ativo, com dependentes em outro registro | recadastro | servidor |

Os pares D03/D13 e D04/D14 são a mesma situação dividida pela marcação "Considerar para Faixa de
Idade?" do SIP. Mostre os dois lados a lado: o RH vai decidir por qual começar.

Frases para a interface: os números medem o **cadastro**, não o que a folha paga ou deduz. Para D03 e
D04, use "possível dedução indevida" ou "possível pagamento indevido", nunca "indevido" sem a ressalva.

---

## 8. Tipos TypeScript

Para gerar os tipos a partir do contrato:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts
```

Versão escrita à mão, equivalente:

```ts
export type Tipo = "erro" | "alerta" | "recadastro" | "conferencia" | "indicador";
export type SimNao = "Sim" | "Não";

export interface Usuario {
  sub: string; email: string; name: string;
  roles: string[]; permissions: string[];
  exp: number; sessao_expira_em: string | null;
}

export interface Resumo { vinculos: number; com_erro: number; com_alerta: number; sem_pendencia: number }

export interface RegraBase {
  codigo: string; titulo: string; tipo: Tipo; alvo: "dependente" | "servidor";
  descricao: string; orientacao: string;
}
export interface RegraDoPainel extends RegraBase { servidores: number; ocorrencias: number }

export interface Painel {
  gerado_em: string;
  universo: { empresa: string; situacoes: string[]; vinculos: number; dependentes: number };
  resumo: Resumo;
  regras: RegraDoPainel[];
}

export interface ResumoDivisao extends Resumo { divisao: string }

export interface Ocorrencia {
  REGISTRO: string; MATRICULA: number | null; CONTRATO: number | null;
  SERVIDOR: string; CPF_SERVIDOR: string; ADMISSAO: string;
  SITUACAO: string | null; VINCULO: string | null; CARGO: string | null;
  DIVISAO: string | null; LOCAL_TRABALHO: string | null; CELULAR: string; EMAIL: string;
  ITEM?: number; DEPENDENTE?: string; PARENTESCO?: string; NASCIMENTO?: string; IDADE?: number | null;
  CPF_DEPENDENTE?: string; DEPENDENTE_IRRF?: SimNao; SALARIO_FAMILIA?: SimNao; FAIXA_IDADE?: SimNao;
  UNIVERSITARIO?: SimNao; DEFICIENTE?: SimNao; DOCUMENTOS?: string; DATA_ENTREGA?: string; NOME_MAE?: string;
  DETALHE: string;
}

export interface ListaDaRegra {
  regra: RegraBase; gerado_em: string; total: number; servidores: number;
  pagina: number; limite: number; itens: Ocorrencia[];
}

export interface Pendencia {
  codigo: string; titulo: string; tipo: Tipo; item: number | null; dependente: string | null;
  parentesco: string | null; idade: number | null; detalhe: string; dados: Record<string, unknown>;
}

export interface Ficha {
  registro: string; matricula: number | null; contrato: number | null; servidor: string;
  situacao: string | null; vinculo: string | null; divisao: string | null; local_trabalho: string | null;
  gerado_em: string; total: number; pendencias: Pendencia[];
}

export interface ListaServidores {
  total: number; pagina: number; limite: number;
  itens: Array<Record<string, string | number | null>>; // colunas do SIP + *_NOME
}

export interface Dominio { CODIGO: string; NOME: string }

export interface Perfil {
  role: "admin" | "rh" | "consulta"; nome: string;
  permissoes: { slug: string; descricao: string }[];
}

export interface UsuarioAdmin {
  id: number; email: string; nome: string; role: string | null; ativo: boolean;
  ja_entrou: boolean; ultimo_login: string | null; criado_em: string;
}

export interface Sessao {
  id: number; usuario_id: number; usuario_email: string; usuario_nome: string; ativa: boolean;
  criada_em: string; ultimo_uso: string; expira_em: string; encerrada_em: string | null;
  ip: string | null; navegador: string | null;
}

export interface RegistroAuditoria {
  id: number; quando: string; usuario_id: number | null; usuario_email: string | null;
  acao: string; alvo: string | null; detalhe: Record<string, unknown> | null; ip: string | null;
}

export interface Pagina<T> { total: number; pagina: number; limite: number; itens: T[] }
```

---

## 9. Experiência esperada pelo RH

- **Linguagem.** Português simples, sem termos técnicos ("vínculo ativo", não "SITUACAO 1"). Botões com
  verbo: "Baixar planilha", "Atualizar leitura", "Cadastrar usuário".
- **Referência ao SIP.** O RH trabalha com o SIP aberto ao lado. Registro, matrícula-contrato e nomes de
  campo iguais aos do SIP ("Dependente IRRF?", "Salário Família", "Considerar para Faixa de Idade?")
  ajudam a localizar o caso.
- **Orientação sempre visível.** Na lista de uma regra, mostre `descricao` e `orientacao` antes da tabela.
- **Busca local** nas listas da regra (nome, registro, matrícula, CPF, secretaria), sem nova chamada.
- **Impressão.** O painel deve ter uma versão de impressão limpa, para reuniões.
- **Acessibilidade.** Contraste adequado, foco visível no teclado, gravidade sempre com texto além da cor.
- **Telas pequenas.** Tabelas largas com rolagem horizontal; colunas principais (registro, nome) sempre visíveis.

---

## 10. Como testar a integração

1. API no ar (`docker compose up -d postgres firebird api`), `http://localhost:8000/` respondendo
   `{"status":"ok"}` e `FRONTEND_URL=http://localhost:3000/` no `.env` do backend.
2. Frontend com `API_TARGET=http://localhost:8000` no `.env.local` e no ar (`npm run dev`).
3. Abra `http://localhost:3000`, clique em entrar e faça login com uma conta cadastrada.
4. Confira no navegador (F12, Rede): as chamadas vão para `localhost:3000/rh/...`, sem erro de CORS,
   e `/rh/me` responde 200.
5. Entre com uma conta não cadastrada: deve voltar com `?acesso=negado`.
6. Entre com o perfil `consulta`: o painel aparece, as listas nominais não.
7. Clique em sair e recarregue: deve aparecer a tela de entrada.

### Problemas comuns

| Sintoma | Causa provável |
|---|---|
| Erro de CORS no console | O frontend está chamando `http://localhost:8000` em vez do caminho relativo |
| `/rh/me` dá 404 | O proxy não está ativo, ou falta `/rh` na lista |
| `/rh/me` dá 500 ou `ECONNREFUSED` no terminal do Next | API desligada, ou `API_TARGET` errado (`http://api:8000` fora do Docker) |
| Mudou o `.env.local` e nada mudou | Reinicie o `npm run dev` |
| Login cai em página de erro do frontend | Falta `/auth` no proxy |
| Depois do login, `/rh/me` dá 401 | Acesso por `127.0.0.1`, ou cookies bloqueados no navegador |
| Login volta para a porta errada | `FRONTEND_URL` antigo no `.env` da API, ou API não recriada |
| "Endereço de retorno não autorizado" | O `retorno` não está em `CORS_ORIGINS` |
| Painel demora na primeira vez | Normal: leitura do SIP. As seguintes vêm do cache por 10 minutos |
