FROM python:3.12-slim-bookworm

# Biblioteca cliente do Firebird (o cliente 3.0 conversa com servidor 2.5)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libfbclient2 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
ENV PATH="/srv/.venv/bin:$PATH"

COPY app ./app
COPY scripts ./scripts

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
