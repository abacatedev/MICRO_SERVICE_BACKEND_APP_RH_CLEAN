class OAuthError(Exception):
    """Erro padronizado do /oauth/token, sem detalhar a causa."""

    def __init__(self, status_code: int, error: str):
        self.status_code = status_code
        self.error = error
