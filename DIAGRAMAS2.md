# MICRO_SERVICE_BACKEND_RH: diagramas

Diagramas do backend FastAPI (Auth Service + RH) como está implementado hoje, incluindo perfis, auditoria e sessão.
Sugestão: salvar este arquivo em `docs/DIAGRAMAS.md`; o GitHub renderiza os blocos Mermaid.

## 1. Visão geral da arquitetura

```mermaid
flowchart TB
    U["Navegador do RH"]
    G["Google OAuth"]
    EXT["Outras aplicações<br/>Censo, Turismo"]

    subgraph COMPOSE["Docker Compose"]
        subgraph API["api: FastAPI, porta 8000"]
            AUTH["Módulo Auth<br/>/auth/google, /oauth/token, JWKS"]
            RH["Módulo RH<br/>/rh/login, /rh/me, /rh/servidores"]
            KEYS["keys/<br/>private.pem e public.pem"]
        end
        subgraph PG["postgres: banco rh_auth"]
            T1["users"]
            T2["applications"]
            T3["roles"]
            T4["permissions"]
            T5["role_permissions"]
            T6["user_applications"]
            T7["user_roles"]
            T8["oauth_authorization_codes"]
        end
        subgraph FB["firebird 2.5: SIP somente leitura"]
            F1["TRABALHADOR"]
            F2["DEPENDENTES"]
        end
    end

    DISCO["/media/ademar/Novo volume/<br/>SIP_ANALISE_2.FDB"]

    U -->|"HTTP"| RH
    U -->|"login"| AUTH
    AUTH <-->|"identidade"| G
    RH -->|"troca code por JWT"| AUTH
    AUTH -->|"SQLAlchemy"| PG
    AUTH -->|"assina RS256"| KEYS
    RH -->|"valida RS256"| KEYS
    RH -->|"fdb, EMPRESA 001"| FB
    FB --- DISCO
    EXT -->|"chave pública via JWKS"| AUTH
```

## 2. Componentes do Auth Service

```mermaid
flowchart TB
    CLIENTE["Aplicação cliente"]

    subgraph APP["app/"]
        MAIN["main.py<br/>SessionMiddleware e handler de OAuthError"]
        CONFIG["config.py<br/>variáveis do .env"]

        subgraph AUTHPKG["auth/"]
            ROUTES["routes.py<br/>/auth/google, callback, /oauth/token, JWKS"]
            GOOGLE["google.py<br/>URL de autorização e perfil via httpx"]
            ACCESS["access.py<br/>check_access"]
            TOKEN["token.py<br/>create_code e exchange_code"]
            CLIENTS["clients.py<br/>limite de tentativas do client_secret"]
            ERRORS["errors.py<br/>OAuthError"]
        end

        SECURITY["security.py<br/>SHA-256, JWT RS256, kid, JWKS"]
        MODELS["models.py e database.py<br/>SQLAlchemy"]

        subgraph RHPKG["rh/"]
            RHROUTES["routes.py<br/>login, callback, me, servidores"]
            DEPS["deps.py<br/>current_user e require_role"]
            FIREBIRD["firebird.py<br/>query e garantir_usuario"]
        end
    end

    GAPI["Google"]
    PG[("PostgreSQL rh_auth")]
    FB[("Firebird SIP")]
    KEYS["keys/*.pem"]

    CLIENTE --> MAIN
    MAIN --> ROUTES
    MAIN --> RHROUTES
    ROUTES --> GOOGLE
    ROUTES --> ACCESS
    ROUTES --> TOKEN
    ROUTES --> SECURITY
    TOKEN --> ACCESS
    TOKEN --> CLIENTS
    TOKEN --> ERRORS
    TOKEN --> SECURITY
    GOOGLE --> GAPI
    ACCESS --> MODELS
    TOKEN --> MODELS
    MODELS --> PG
    SECURITY --> KEYS
    RHROUTES --> TOKEN
    RHROUTES --> DEPS
    RHROUTES --> FIREBIRD
    DEPS --> SECURITY
    FIREBIRD --> FB
    CONFIG -.-> ROUTES
    CONFIG -.-> SECURITY
    CONFIG -.-> FIREBIRD
```

## 3. Fluxo completo: Google OAuth, Authorization Code e JWT

```mermaid
flowchart LR
    USR["Usuário"]
    RHC["RH<br/>/rh/login e /rh/callback"]
    AUTH["Auth<br/>/auth/google e callback"]
    GOOGLE["Google"]
    CODE["Authorization Code<br/>hash, uso único, 60 s"]
    TOKEN["exchange_code<br/>POST /oauth/token"]
    JWT["JWT RS256<br/>15 min"]
    API["Rotas /rh/*"]
    JWKS["/.well-known/jwks.json"]

    USR -->|"1. Abre /rh/login"| RHC
    RHC -->|"2. /auth/google com client_id=rh, redirect_uri e state"| AUTH
    AUTH -->|"3. Valida cliente e redireciona"| GOOGLE
    GOOGLE -->|"4. Usuário se autentica"| USR
    GOOGLE -->|"5. Callback com code do Google"| AUTH
    AUTH -->|"6. Verifica usuário, aplicação e roles"| AUTH
    AUTH -->|"7. Gera"| CODE
    AUTH -->|"8. Redirect com code e state"| RHC
    RHC -->|"9. client_id, client_secret, code, redirect_uri"| TOKEN
    TOKEN -->|"10. Valida client_secret"| TOKEN
    TOKEN -->|"11. Valida e consome"| CODE
    TOKEN -->|"12. Emite"| JWT
    JWT -->|"13. Cookie HttpOnly rh_token"| RHC
    RHC -->|"14. Requisição autenticada"| API
    API -->|"15. Valida RS256 com a chave pública"| JWT
    JWKS -.->|"16. Mesma chave para outras aplicações"| API
```

## 4. Sequência detalhada do login

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuário
    participant RH as RH (/rh)
    participant A as Auth (/auth)
    participant G as Google
    participant DB as PostgreSQL
    participant T as exchange_code

    U->>RH: GET /rh/login
    RH-->>U: 302 /auth/google + cookie rh_state
    U->>A: GET /auth/google?client_id=rh, redirect_uri, state
    A->>DB: Busca aplicação pelo client_id
    DB-->>A: Aplicação ativa e redirect_uri cadastrado
    A-->>U: 302 Google + sessão temporária com google_state
    U->>G: Login e consentimento
    G-->>U: 302 /auth/google/callback com code e state
    U->>A: GET /auth/google/callback
    A->>A: Confere google_state e descarta a sessão temporária
    A->>G: Troca o code pelo access_token
    G-->>A: access_token
    A->>G: GET userinfo
    G-->>A: sub, email, email_verified, name
    A->>DB: Busca usuário por google_id ou e-mail pré-cadastrado
    A->>DB: check_access: user_application e roles ativas
    alt Acesso negado
        A->>DB: Auditoria login.negado
        A-->>U: 302 /rh/callback?error=access_denied
        U->>RH: GET /rh/callback
        RH-->>U: 403 Acesso negado
    else Acesso autorizado
        A->>DB: Atualiza nome e last_login_at
        A->>DB: Auditoria login.sucesso
        A->>DB: Grava hash do Authorization Code (60 s)
        A-->>U: 302 /rh/callback com code e state
        U->>RH: GET /rh/callback
        RH->>RH: Confere o cookie rh_state
        RH->>T: client_id, client_secret, code, redirect_uri
        T->>DB: Valida cliente, código e acesso
        T->>DB: UPDATE atômico marca used_at
        T-->>RH: access_token JWT RS256, expires_in 900
        RH->>DB: Cria a sessão de 8 h (só o hash)
        RH-->>U: 302 /rh/me + cookies rh_token (15 min) e rh_session (8 h)
        U->>RH: GET /rh/me
        RH-->>U: sub, email, name, roles, permissions, sessao_expira_em
    end
```

## 5. Fluxograma de autorização (callback do Google)

```mermaid
flowchart TD
    START(["GET /auth/google/callback"])
    S1{"Sessão existe e<br/>state confere?"}
    E400["400 invalid_state"]
    S2{"Google devolveu code?"}
    S3{"Perfil obtido no Google?"}
    S4{"email_verified<br/>é verdadeiro?"}
    S5{"Usuário com este<br/>google_id?"}
    S6{"E-mail pré-cadastrado<br/>sem google_id?"}
    LINK["Vincula o google_id ao usuário"]
    S7{"Usuário está ativo?"}
    S8{"Aplicação existe<br/>e está ativa?"}
    S9{"Existe user_application<br/>ativa?"}
    S10{"Existe pelo menos<br/>uma role ativa?"}
    DENY["ACESSO NEGADO<br/>redirect com error=access_denied"]
    OK["ACESSO AUTORIZADO<br/>atualiza nome e last_login_at"]
    CODE["Gera Authorization Code<br/>redirect com code e state"]

    START --> S1
    S1 -->|"Não"| E400
    S1 -->|"Sim"| S2
    S2 -->|"Não"| DENY
    S2 -->|"Sim"| S3
    S3 -->|"Não"| DENY
    S3 -->|"Sim"| S4
    S4 -->|"Não"| DENY
    S4 -->|"Sim"| S5
    S5 -->|"Sim"| S7
    S5 -->|"Não"| S6
    S6 -->|"Não"| DENY
    S6 -->|"Sim"| LINK
    LINK --> S7
    S7 -->|"Não"| DENY
    S7 -->|"Sim"| S8
    S8 -->|"Não"| DENY
    S8 -->|"Sim"| S9
    S9 -->|"Não"| DENY
    S9 -->|"Sim"| S10
    S10 -->|"Não"| DENY
    S10 -->|"Sim"| OK
    OK --> CODE
```

## 6. Fluxograma do `/oauth/token`

```mermaid
flowchart TD
    START(["POST /oauth/token"])
    P1{"Todos os parâmetros<br/>foram enviados?"}
    P2{"grant_type é<br/>authorization_code?"}
    C1{"Aplicação existe, está ativa<br/>e tem client_secret?"}
    C2{"client_secret confere?<br/>SHA-256 em tempo constante"}
    RL{"Mais de 5 erros<br/>em 15 minutos?"}
    K1{"Código existe para<br/>esta aplicação?"}
    K2{"redirect_uri<br/>corresponde?"}
    K3{"Código expirou?"}
    K4{"Código já foi<br/>utilizado?"}
    A1{"check_access:<br/>usuário ativo, acesso e role?"}
    UPD{"UPDATE atômico<br/>marcou used_at?"}
    JWT["Gera JWT RS256<br/>sub, email, name, roles, jti, iss, aud"]
    OK["200 OK<br/>access_token, token_type, expires_in<br/>Cache-Control: no-store"]

    E400R["400 invalid_request"]
    E400G["400 unsupported_grant_type"]
    E401["401 invalid_client"]
    E429["429 rate_limit_exceeded"]
    E400["400 invalid_grant"]

    START --> P1
    P1 -->|"Não"| E400R
    P1 -->|"Sim"| P2
    P2 -->|"Não"| E400G
    P2 -->|"Sim"| C1
    C1 -->|"Não"| E401
    C1 -->|"Sim"| C2
    C2 -->|"Inválido"| RL
    RL -->|"Não"| E401
    RL -->|"Sim"| E429
    C2 -->|"Válido"| K1
    K1 -->|"Não"| E400
    K1 -->|"Sim"| K2
    K2 -->|"Não"| E400
    K2 -->|"Sim"| K3
    K3 -->|"Expirado"| E400
    K3 -->|"Válido"| K4
    K4 -->|"Já usado"| E400
    K4 -->|"Disponível"| A1
    A1 -->|"Negado"| E400
    A1 -->|"OK"| UPD
    UPD -->|"Não, outra requisição venceu"| E400
    UPD -->|"Sim"| JWT
    JWT --> OK
```

## 7. Validação do JWT e uso do JWKS

```mermaid
flowchart TD
    START(["Requisição a uma rota protegida"])
    T1{"Token no header<br/>Authorization: Bearer?"}
    T2{"Token no cookie<br/>rh_token?"}
    ORIGEM{"Quem está validando?"}
    LOCAL["Módulo RH<br/>lê keys/public.pem"]
    JWKS["Outra aplicação<br/>GET /.well-known/jwks.json<br/>cache de 1 hora"]
    KID{"Existe chave com o<br/>kid do cabeçalho?"}
    V1{"alg é RS256 e a<br/>assinatura confere?"}
    V2{"iss é o Auth Service?"}
    V3{"aud é o client_id<br/>desta aplicação?"}
    V4{"exp ainda não passou e<br/>claims obrigatórias presentes?"}
    R1{"Usuário tem a role<br/>exigida pela rota?"}
    OK["Acesso liberado<br/>consulta ao SIP"]
    E401["401 Não autenticado<br/>ou token inválido"]
    E403["403 Sem permissão"]

    START --> T1
    T1 -->|"Sim"| ORIGEM
    T1 -->|"Não"| T2
    T2 -->|"Não"| E401
    T2 -->|"Sim"| ORIGEM
    ORIGEM -->|"RH, mesmo processo"| LOCAL
    ORIGEM -->|"Censo, Turismo"| JWKS
    JWKS --> KID
    KID -->|"Não"| E401
    KID -->|"Sim"| V1
    LOCAL --> V1
    V1 -->|"Não"| E401
    V1 -->|"Sim"| V2
    V2 -->|"Não"| E401
    V2 -->|"Sim"| V3
    V3 -->|"Não"| E401
    V3 -->|"Sim"| V4
    V4 -->|"Não"| E401
    V4 -->|"Sim"| R1
    R1 -->|"Não"| E403
    R1 -->|"Sim"| OK
```

## 8. Sessão de 8 horas e renovação do token

```mermaid
flowchart TD
    START(["Requisição a uma rota /rh/*"])
    H{"Header Authorization:<br/>Bearer presente?"}
    HB{"JWT do header<br/>é válido?"}
    S1{"Cookie rh_session<br/>presente?"}
    S2{"Sessão existe e<br/>não foi encerrada?"}
    S3{"Menos de 8 h<br/>desde o login?"}
    S4{"Usada nos últimos<br/>30 minutos?"}
    ACC{"check_access no banco:<br/>usuário ativo, acesso e role?"}
    REV["Encerra a sessão"]
    T1{"Cookie rh_token<br/>válido e do mesmo usuário?"}
    NEW["Emite novo JWT RS256<br/>e grava o cookie rh_token<br/>sem passar pelo Google"]
    TOUCH["Atualiza o último uso da sessão"]
    PERM{"Usuário tem a permissão<br/>exigida pela rota?"}
    OK["Acesso liberado<br/>e registrado na auditoria"]
    E401A["401 Não autenticado"]
    E401T["401 Token inválido ou expirado"]
    E401S["401 Sessão expirada"]
    E403R["403 Acesso revogado"]
    E403P["403 Sem permissão"]

    START --> H
    H -->|"Sim, cliente de API"| HB
    HB -->|"Não"| E401T
    HB -->|"Sim"| ACC
    H -->|"Não, navegador"| S1
    S1 -->|"Não"| E401A
    S1 -->|"Sim"| S2
    S2 -->|"Não"| E401S
    S2 -->|"Sim"| S3
    S3 -->|"Não"| E401S
    S3 -->|"Sim"| S4
    S4 -->|"Não"| E401S
    S4 -->|"Sim"| ACC
    ACC -->|"Negado"| REV
    REV --> E403R
    ACC -->|"OK, com sessão"| T1
    ACC -->|"OK, com Bearer"| PERM
    T1 -->|"Não"| NEW
    T1 -->|"Sim"| TOUCH
    NEW --> TOUCH
    TOUCH --> PERM
    PERM -->|"Não"| E403P
    PERM -->|"Sim"| OK
```

A sessão também termina no logout, quando o administrador a encerra em `/rh/admin/sessoes`
ou quando o usuário é desativado.
