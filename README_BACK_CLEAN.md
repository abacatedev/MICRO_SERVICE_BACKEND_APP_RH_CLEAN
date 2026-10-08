# MICRO_SERVICE_BACKEND_RH

Diagnóstico cadastral dos servidores e dependentes da Prefeitura de Cáceres, feito a partir de uma
cópia de análise da base do SIP (Fiorilli, Firebird 2.5). É a etapa de **Pré-Censo**: mostra ao RH
onde o cadastro está incompleto ou desatualizado, antes do Censo dos Servidores e dos envios ao eSocial.

O sistema **só lê** o SIP. Nenhuma rota altera dados da folha.

> Repositório privado. Contém a estrutura do cadastro de pessoal; não publique nem compartilhe fora da CTI.

## Sumário

1. [O que o sistema faz](#o-que-o-sistema-faz)
2. [Arquitetura](#arquitetura)
3. [Estrutura de pastas](#estrutura-de-pastas)
4. [Instalação na prefeitura (Windows)](#instalação-na-prefeitura-windows)
5. [Instalação em casa (Linux)](#instalação-em-casa-linux)
6. [Variáveis do `.env`](#variáveis-do-env)
7. [Perfis e permissões](#perfis-e-permissões)
8. [Diagnóstico cadastral](#diagnóstico-cadastral)
9. [Rotas da API](#rotas-da-api)
10. [Autenticação e sessão](#autenticação-e-sessão)
11. [Auditoria](#auditoria)
12. [Frontend](#frontend)
13. [Comandos do dia a dia](#comandos-do-dia-a-dia)
14. [Problemas conhecidos](#problemas-conhecidos)
15. [Segurança e dados pessoais](#segurança-e-dados-pessoais)
16. [Pendências](#pendências)

## O que o sistema faz

- **Painel:** quantos vínculos ativos têm erro, alerta ou nenhuma pendência, por regra e por secretaria.
- **Lista nominal:** para cada regra, quem são os servidores e dependentes, com registro, matrícula,
  lotação, marcações do SIP e orientação de onde corrigir. Exporta planilha CSV.
- **Ficha de pendências:** tudo o que foi encontrado para um vínculo.
- **Consulta de servidores e dependentes**, com os códigos traduzidos (situação, vínculo, cargo, lotação).
- **Controle de acesso:** login com Google, só para e-mails cadastrados, com três perfis.
- **Auditoria:** registro de quem consultou o quê, quando e de onde.

## Arquitetura

| Serviço | Tecnologia | Porta | Função |
|---|---|---|---|
| `api` | FastAPI (Python 3.12, uv) | 8000 | Autenticação, diagnóstico e leitura do SIP |
| `web` | React + Vite + TypeScript | 5173 | Interface do RH |
| `postgres` | PostgreSQL 18 | interna | Usuários, perfis, sessões e auditoria |
| `firebird` | Firebird 2.5 | interna | Só em casa; na prefeitura usa-se o servidor da rede |

O frontend repassa `/rh`, `/auth`, `/oauth` e `/.well-known` para a API. Navegador, frontend e API ficam
na mesma origem, e o cookie de sessão funciona sem configuração extra.

Os diagramas (arquitetura, fluxo de login, token, sessão) estão em `docs/DIAGRAMAS.md`, quando presentes.

## Estrutura de pastas

```
app/
  main.py            inicialização, sessão temporária do login, rotas
  config.py          leitura do .env
  database.py        conexão com o PostgreSQL
  models.py          tabelas: usuários, aplicações, perfis, códigos, sessões, auditoria
  security.py        hash, JWT RS256, JWKS
  docs.py            Swagger: descrição, autenticação, permissões e modelos das respostas
  audit.py           gravação da auditoria
  auth/              login Google, checagem de acesso, código de autorização, /oauth/token, perfis
  rh/
    routes.py        login do RH, servidores, dependentes, domínios
    deps.py          proteção das rotas: sessão, token e permissões
    sessions.py      sessão de 8 horas
    firebird.py      acesso somente leitura ao SIP
    regras.py        as regras do diagnóstico (funções puras, sem banco)
    diagnostico.py   painel, lista nominal, CSV e ficha
    admin.py         usuários, sessões e auditoria
scripts/
  gerar_chaves.py    cria o par de chaves RS256
  seed.py            cria a aplicação RH e cadastra um usuário
tests/               testes automáticos (não precisam de Google nem de Firebird)
web/                 frontend
docker-compose.yml             ambiente de casa (com contêiner Firebird)
docker-compose.prefeitura.yml  ambiente da prefeitura (Firebird da rede)
```

## Instalação na prefeitura (Windows)

Pré-requisitos: Docker Desktop em execução, Git, e acesso de rede ao servidor Firebird `172.16.0.21:3050`.
Todos os comandos são no PowerShell.

**1. Baixar o projeto**

```powershell
cd "C:\Users\T.I Prefeitura\Documents\DEV\TI_PREFEITURA"
git clone https://github.com/abacatedev/MICRO_SERVICE_BACKEND_RH.git
cd MICRO_SERVICE_BACKEND_RH
```

**2. Criar o `.env`**

```powershell
copy .env.example .env
notepad .env
```

Preencha conforme a tabela de [variáveis](#variáveis-do-env). Na prefeitura:

```dotenv
SIP_DB_HOST=172.16.0.21
SIP_DB_PORT=3050
SIP_DB_DATABASE=(caminho do SIP_ANALISE_2.FDB no servidor, o mesmo do projeto APP_CENSO)
SIP_DB_USER=SIPANALISE
SIP_DB_PASSWORD=(senha do SIPANALISE no servidor)
FRONTEND_URL=http://localhost:5173/
```

Deixe **de fora** `SIP_DB_HOST_FILE` e `SIP_DB_SYSDBA_PASSWORD`: só servem para o contêiner de casa.
Salve o arquivo antes de continuar.

**3. Subir os contêineres**

```powershell
docker compose -f docker-compose.prefeitura.yml up -d --build
```

**4. Gerar as chaves e cadastrar o primeiro administrador**

```powershell
docker compose -f docker-compose.prefeitura.yml exec api python -m scripts.gerar_chaves
docker compose -f docker-compose.prefeitura.yml exec api python -m scripts.seed seu.email@gmail.com "Seu Nome"
```

O `seed` imprime uma linha `RH_CLIENT_SECRET=...` **uma única vez**. Copie para o `.env`, salve e recarregue:

```powershell
docker compose -f docker-compose.prefeitura.yml up -d
```

**5. Google Cloud**

Na credencial OAuth (APIs e serviços, Credenciais), o redirecionamento autorizado precisa conter exatamente:

```
http://localhost:8000/auth/google/callback
```

**6. Testar**

Abra `http://localhost:5173` e entre com o Google. A primeira subida do frontend leva um ou dois minutos,
enquanto instala as dependências (`docker compose -f docker-compose.prefeitura.yml logs -f web`).

Na prefeitura, usuários, sessões e auditoria começam do zero: ficam no PostgreSQL de cada máquina.

## Instalação em casa (Linux)

Em casa não há servidor Firebird: o banco é um arquivo `.FDB` aberto por um contêiner.

```bash
git clone https://github.com/abacatedev/MICRO_SERVICE_BACKEND_RH.git
cd MICRO_SERVICE_BACKEND_RH
cp .env.example .env        # preencher; ver a tabela de variáveis
docker-compose up -d --build
docker-compose exec api python -m scripts.gerar_chaves
docker-compose exec api python -m scripts.seed seu.email@gmail.com "Seu Nome"
# copiar RH_CLIENT_SECRET para o .env
docker-compose up -d
```

Particularidades de casa:

- `SIP_DB_HOST=firebird` e `SIP_DB_DATABASE=/firebird/data/SIP_ANALISE_2.FDB`.
- `SIP_DB_HOST_FILE` aponta para o arquivo na máquina (com aspas, se o caminho tiver espaço).
  O disco precisa estar montado antes do `up`.
- `SIP_DB_SYSDBA_PASSWORD` é a senha do SYSDBA **do contêiner**. Com ela, a API recria sozinha o usuário
  de leitura quando o contêiner do Firebird é recriado.
- Nunca suba dois contêineres Firebird apontando para o mesmo arquivo `.FDB`.

## Variáveis do `.env`

O `.env` nunca vai para o Git. Use o `.env.example` como modelo.

| Variável | Para que serve | Exemplo |
|---|---|---|
| `DATABASE_URL` | PostgreSQL do sistema. O host é o nome do serviço, não `localhost` | `postgresql+psycopg://postgres:postgres@postgres:5432/rh_auth` |
| `BASE_URL` | Endereço público da API | `http://localhost:8000` |
| `JWT_ISSUER` | Emissor gravado nos tokens | `http://localhost:8000` |
| `FRONTEND_URL` | Para onde o login volta por padrão | `http://localhost:3000/` |
| `CORS_ORIGINS` | Frontends autorizados a chamar a API e a receber o retorno do login | `http://localhost:3000,http://localhost:5173` |
| `SESSION_SECRET` | Segredo do cookie temporário do login | gerar com `openssl rand -hex 32` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Credencial OAuth do Google | |
| `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH` | Chaves RS256 | `keys/private.pem`, `keys/public.pem` |
| `ACCESS_TOKEN_SECONDS` | Validade do token | `900` |
| `AUTH_CODE_SECONDS` | Validade do código de autorização | `60` |
| `SESSION_HOURS` | Duração máxima da sessão | `8` |
| `SESSION_IDLE_MINUTES` | Encerra por inatividade; `0` desliga | `30` |
| `RH_CLIENT_ID` | Identificador da aplicação RH | `rh` |
| `RH_CLIENT_SECRET` | Segredo impresso pelo `seed` | |
| `SIP_DB_HOST`, `SIP_DB_PORT` | Servidor Firebird | `172.16.0.21`, `3050` |
| `SIP_DB_DATABASE` | Caminho do banco como o servidor o enxerga | |
| `SIP_DB_USER`, `SIP_DB_PASSWORD` | Usuário de leitura | `SIPANALISE` |
| `SIP_DB_DIALECT`, `SIP_DB_CHARSET` | Parâmetros da conexão | `3`, `WIN1252` |
| `SIP_EMPRESA` | Empresa analisada | `001` |
| `SIP_SITUACOES_ATIVAS` | Situações que contam como vínculo ativo | `1,3` |
| `DIAGNOSTICO_CACHE_MINUTES` | Tempo em memória do resultado | `10` |
| `SIP_DB_HOST_FILE` | Só em casa: caminho do `.FDB` na máquina | |
| `SIP_DB_SYSDBA_PASSWORD` | Só em casa: SYSDBA do contêiner | |

Depois de alterar o `.env`, **salve** e recrie a API. Um `restart` não relê o arquivo:

```bash
docker compose up -d --force-recreate api
```

## Perfis e permissões

| Perfil | Pode |
|---|---|
| `admin` | Tudo, inclusive usuários, sessões e auditoria |
| `rh` | Painel, listas nominais, planilhas, fichas, servidores e dependentes |
| `consulta` | Painel (só contagens) e lista de servidores sem CPF |

Perfis e permissões ficam em `app/auth/rbac.py` e são sincronizados com o banco a cada subida.
O acesso é conferido no banco a cada requisição: desativar alguém ou trocar o perfil vale na hora.

O primeiro administrador é criado pelo `seed`. Os demais, pela rota `POST /rh/admin/usuarios`
(em `http://localhost:8000/docs`, enquanto não há tela). Quem não está cadastrado recebe acesso negado.

## Diagnóstico cadastral

**Universo:** empresa 001, vínculos nas situações de `SIP_SITUACOES_ATIVAS` (1 = Normal, 3 = Afastado)
e os dependentes presos a esses registros. Dependente que ficou em registro antigo não conta.
Quem tem dois vínculos ativos aparece duas vezes, uma por registro.

**Como funciona:** a API busca o universo com três consultas e aplica as regras em Python, em
`app/rh/regras.py`. O resultado fica em memória por 10 minutos; "Atualizar leitura" recalcula.

**Os códigos das regras** (D, S, V, I) são etiquetas internas deste projeto. Não vêm do SIP nem do
eSocial. Critérios, gravidades e textos de orientação são propostas da CTI, a validar com o RH.

| Código | Regra | Tipo |
|---|---|---|
| D01 | Dependente sem CPF | erro |
| D11 | Dependente sem nenhum documento | erro |
| D02 | CPF de dependente inválido, repetido ou igual ao do servidor | erro |
| D03 | IRRF marcado acima da idade, sem controle de faixa de idade | erro |
| D04 | Salário-família marcado acima da idade, sem controle de faixa de idade | erro |
| D13 | IRRF marcado acima da idade, com controle de faixa de idade | alerta |
| D14 | Salário-família marcado acima da idade, com controle de faixa de idade | alerta |
| D05 | Parentesco "menor de 21 anos" com 21 anos ou mais | alerta |
| D06 | Mais de um cônjuge ou companheiro no mesmo registro | alerta |
| D07 | Idade incoerente com o parentesco | alerta |
| D08 | PAI com sexo feminino ou MÃE com sexo masculino | alerta |
| D09 | Dependente duplicado no mesmo registro | alerta |
| D12 | Certidão de nascimento sem dados do cartório | indicador |
| D15 | Documentação do dependente entregue há mais de 5 anos | indicador |
| D10 | Parentesco "Outros" | indicador |
| S01 | Servidor sem celular | alerta |
| S02 | Servidor sem e-mail | alerta |
| S07 | Estado civil solteiro com cônjuge entre os dependentes | alerta |
| S03 | Título de eleitor ausente ou com preenchimento falso | alerta |
| S04 | PIS ausente ou com preenchimento falso | erro |
| S05 | Servidor sem nome da mãe | erro |
| S06 | CPF do servidor ausente ou inválido | erro |
| V01 | Vínculo ativo com data de término vencida | alerta |
| V02 | CPF com mais de um vínculo ativo | conferência |
| I01 | Sem dependentes em nenhum registro | indicador |
| I02 | Sem dependentes no vínculo ativo, com dependentes em outro registro | recadastro |

**Pontos de atenção**

- Os limites de idade (IRRF, universitário, salário-família) são lidos da tabela `VINCULO` do SIP.
- Preenchimento falso (só zeros, só noves) conta como informação ausente.
- A leitura da marcação "Considerar para Faixa de Idade?" (regras D03/D13 e D04/D14) é uma hipótese
  ainda não confirmada com a Fiorilli.
- O diagnóstico mede o **cadastro**, não o que a folha paga ou deduz.

## Rotas da API

Documentação interativa em `http://localhost:8000/docs`.

| Rota | Função | Permissão |
|---|---|---|
| `GET /auth/google` | Valida o cliente e envia ao Google | pública |
| `GET /auth/google/callback` | Identidade, acesso, código, volta ao cliente | pública |
| `POST /oauth/token` | Código + segredo → JWT RS256 | `client_secret` |
| `GET /.well-known/jwks.json` | Chave pública | pública |
| `GET /rh/login`, `/rh/callback`, `/rh/logout` | Login e saída do RH | pública |
| `GET /rh/me` | Usuário, perfis, permissões e fim da sessão | autenticado |
| `GET /rh/token` | Token de acesso (JWT) a partir da sessão | autenticado |
| `GET /rh/diagnostico` | Painel: resumo e contagem por regra | `rh:diagnostico:painel` |
| `GET /rh/diagnostico/por-divisao` | Situação dos vínculos por secretaria | `rh:diagnostico:painel` |
| `GET /rh/diagnostico/{codigo}` | Lista nominal; `?formato=csv` baixa a planilha | `rh:diagnostico:listar` |
| `GET /rh/servidores/{registro}/pendencias` | Ficha de pendências do vínculo | `rh:diagnostico:listar` |
| `GET /rh/servidores` | Busca por `nome`, `situacao`, `ativos` | `rh:servidores:listar` |
| `GET /rh/servidores/{registro}` | Dados do servidor | `rh:servidores:detalhar` |
| `GET /rh/servidores/{registro}/dependentes` | Dependentes do registro | `rh:dependentes:ler` |
| `GET /rh/dominios/{nome}` | Códigos e nomes para filtros | `rh:servidores:listar` |
| `GET /rh/admin/roles` | Perfis e o que cada um pode | `rh:usuarios:gerenciar` |
| `GET`, `POST /rh/admin/usuarios` | Listar e pré-cadastrar por e-mail | `rh:usuarios:gerenciar` |
| `PATCH /rh/admin/usuarios/{id}` | Nome, perfil, ativar ou desativar | `rh:usuarios:gerenciar` |
| `GET /rh/admin/sessoes` | Sessões abertas | `rh:usuarios:gerenciar` |
| `DELETE /rh/admin/sessoes/{id}` | Encerrar uma sessão | `rh:usuarios:gerenciar` |
| `DELETE /rh/admin/usuarios/{id}/sessoes` | Encerrar todas as sessões da pessoa | `rh:usuarios:gerenciar` |
| `GET /rh/admin/auditoria` | Registro de auditoria, com filtros | `rh:auditoria:ler` |

O `registro` aceita `3` ou `000003`. Domínios disponíveis: `situacoes`, `parentescos`, `vinculos`,
`cargos`, `divisoes`, `subdivisoes`, `locais_trabalho`.

## Autenticação e sessão

1. O usuário entra com o Google. Só passa quem tem o e-mail pré-cadastrado, com e-mail verificado.
2. A API confere usuário ativo, vínculo com a aplicação e perfil ativo.
3. É emitido um código de autorização de uso único (60 s), trocado por um JWT RS256 de 15 minutos.
4. É criada uma sessão de 8 horas em cookie HttpOnly. Quando o token vence, a sessão emite outro
   sem novo login no Google.

A sessão termina no logout, após 8 horas, após 30 minutos sem uso, quando o administrador a encerra
ou quando o usuário é desativado. Clientes de API usam `Authorization: Bearer` com o JWT, sem sessão.

## Auditoria

Tabela `audit_logs`, consultada em `GET /rh/admin/auditoria`. Ações registradas:

`login.sucesso`, `login.negado`, `logout`, `servidores.listar`, `servidores.detalhar`,
`dependentes.listar`, `diagnostico.painel`, `diagnostico.listar`, `diagnostico.ficha`,
`usuarios.criar`, `usuarios.alterar`, `sessoes.encerrar`.

Cada registro guarda usuário, alvo (registro do servidor ou id do usuário), detalhe, data e IP.
Em Docker local, o IP gravado é o do gateway do Docker; atrás de um proxy reverso isso precisa de ajuste.

## Frontend

Pasta `web/`. Telas: entrada, painel (com impressão) e lista nominal por regra, com busca,
quadro "Ver tudo" e planilha. O frontend não guarda regra de negócio: títulos, gravidades,
descrições e números vêm da API.

Fora do Docker: `cd web && npm install && npm run dev`. Para publicar: `npm run build` gera `web/dist`.

## Usar com outro frontend

A API aceita frontends em outra porta (por exemplo `http://localhost:3000`): CORS com credenciais para
as origens de `CORS_ORIGINS`, login com `GET /rh/login?retorno=<endereço do frontend>` e, para quem
prefere token, `GET /rh/token`. O passo a passo, com exemplos de código, está em
`docs/INTEGRACAO_FRONTEND.md`. O contrato fica em `/openapi.json` e em `docs/openapi.json`.

O Swagger (`/docs`) traz, em cada rota, o resumo, a permissão exigida, o formato da resposta e os erros.
Esses textos e modelos ficam em `app/docs.py`.

## Comandos do dia a dia

Na prefeitura, acrescente `-f docker-compose.prefeitura.yml` depois de `docker compose`.

| Tarefa | Comando |
|---|---|
| Subir | `docker compose up -d` |
| Parar | `docker compose down` |
| Ver logs da API | `docker compose logs --tail 50 api` |
| Recriar a API após mudar o `.env` | `docker compose up -d --force-recreate api` |
| Cadastrar usuário pelo terminal | `docker compose exec api python -m scripts.seed email "Nome" rh` |
| Rodar os testes | `uv sync && uv run pytest -q` |
| Nova dependência Python | `uv add pacote` e `docker compose up -d --build` |
| Enviar alterações | `git add .`, `git commit -m "..."`, `git push` |
| Receber alterações | `git pull` |

## Problemas conhecidos

| Sintoma | Causa | Solução |
|---|---|---|
| `connection refused` em `localhost:5432` | `DATABASE_URL` com `localhost` | Usar o host `postgres` |
| `Could not parse SQLAlchemy URL` | Aspas, espaço ou quebra de linha na `DATABASE_URL` | Redigitar a linha sem aspas |
| `redirect_uri_mismatch` no Google | Redirecionamento não cadastrado | Adicionar `http://localhost:8000/auth/google/callback` |
| Login volta para `/rh/me` | `FRONTEND_URL` ausente ou `.env` não salvo | Salvar o `.env` e recriar a API |
| `access_denied` | Conta Google não cadastrada | Cadastrar o e-mail |
| `Your user name and password are not defined` | Usuário de leitura inexistente no Firebird | Em casa, conferir `SIP_DB_SYSDBA_PASSWORD`; na prefeitura, conferir usuário e senha |
| `deadlock` ao conectar | Consulta pesada aberta no `isql` | Encerrar o `isql`; em casa, `docker compose restart firebird` |
| Números do painel não mudam | Resultado em memória | "Atualizar leitura" |
| "Sessão expirada" | 8 horas, 30 minutos sem uso ou sessão encerrada | Entrar de novo |

No `isql`, use só `SELECT` e consultas leves. Cruzamentos pesados devem ser feitos pela API.

## Segurança e dados pessoais

- O sistema trata dados pessoais de servidores e dependentes (CPF, endereço, documentos).
- `.env`, chaves em `keys/` e arquivos de banco ficam fora do Git.
- A coluna `SENHAWEB` do SIP nunca é lida.
- Só entra quem foi cadastrado, e todo acesso a dado nominal fica na auditoria.
- Usuários são desativados, não apagados, para preservar o histórico.

## Pendências

- Validação das regras, gravidades e orientações pelo RH (memorando enviado).
- Confirmar com a Fiorilli o efeito da marcação "Considerar para Faixa de Idade?".
- Telas de servidores, ficha completa, administração e relatórios no frontend.
- Antes de sair do `localhost`: HTTPS com proxy reverso, IP real na auditoria, restrição de domínio
  de e-mail e migrations no lugar da criação automática de tabelas.
