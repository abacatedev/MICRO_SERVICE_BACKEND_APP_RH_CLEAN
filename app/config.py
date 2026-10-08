from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/rh_auth"
    base_url: str = "http://localhost:8000"
    jwt_issuer: str = "http://localhost:8000"
    session_secret: str
    frontend_url: str = "/rh/me"  # para onde o login volta por padrão; ex.: http://localhost:3000/
    # Frontends autorizados a chamar a API pelo navegador (CORS) e a receber o retorno do login
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def origens(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    google_client_id: str = ""
    google_client_secret: str = ""

    jwt_private_key_path: str = "keys/private.pem"
    jwt_public_key_path: str = "keys/public.pem"
    access_token_seconds: int = 900
    auth_code_seconds: int = 60
    session_hours: int = 8  # duração máxima da sessão do navegador
    session_idle_minutes: int = 30  # encerra por inatividade; 0 desliga

    rh_client_id: str = "rh"
    rh_client_secret: str = ""

    # mesmos nomes do .env do projeto anterior
    sip_db_host: str = "firebird"
    sip_db_port: int = 3050
    sip_db_database: str = "/firebird/data/SIP_ANALISE_2.FDB"
    sip_db_user: str = "SIPANALISE"
    sip_db_password: str = ""
    sip_db_charset: str = "WIN1252"
    sip_db_dialect: int = 3
    sip_db_sysdba_password: str = ""  # usado só para recriar o usuário de leitura
    sip_empresa: str = "001"
    sip_situacoes_ativas: str = "1,3"  # universo do diagnóstico: Normal e Afastado
    diagnostico_cache_minutes: int = 10

    @property
    def situacoes_ativas(self) -> list[str]:
        return [x.strip() for x in self.sip_situacoes_ativas.split(",") if x.strip()]


settings = Settings()
