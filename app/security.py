"""Hash, segredos, JWT RS256 e JWKS."""
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization

from app.config import settings
from app.models import utcnow


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_secret() -> str:
    return secrets.token_urlsafe(32)


@lru_cache
def _private_pem() -> bytes:
    return Path(settings.jwt_private_key_path).read_bytes()


@lru_cache
def _public_pem() -> bytes:
    return Path(settings.jwt_public_key_path).read_bytes()


@lru_cache
def key_id() -> str:
    pub = serialization.load_pem_public_key(_public_pem())
    der = pub.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest()[:16]


def create_access_token(*, user_id: int, email: str, name: str, roles: list[str], client_id: str) -> str:
    now = utcnow()
    payload = {
        "iss": settings.jwt_issuer,
        "aud": client_id,
        "sub": str(user_id),
        "email": email,
        "name": name,
        "roles": roles,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_seconds),
    }
    return jwt.encode(payload, _private_pem(), algorithm="RS256", headers={"kid": key_id()})


def decode_access_token(token: str, audience: str) -> dict:
    return jwt.decode(
        token,
        _public_pem(),
        algorithms=["RS256"],  # nunca aceitar HS256 com a chave pública
        audience=audience,
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "aud", "iss"]},
    )


@lru_cache
def jwks() -> dict:
    pub = serialization.load_pem_public_key(_public_pem())
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(pub)
    if isinstance(jwk, str):
        jwk = json.loads(jwk)
    jwk.update({"kid": key_id(), "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}
