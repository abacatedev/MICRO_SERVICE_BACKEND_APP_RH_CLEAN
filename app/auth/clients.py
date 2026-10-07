"""Limite de tentativas de client_secret errado (em memória; simples)."""
import time
from collections import defaultdict, deque
from threading import Lock

WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 5

_failures: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def register_failure(key: str) -> bool:
    """Registra a falha e devolve True quando o cliente passou do limite."""
    now = time.monotonic()
    with _lock:
        q = _failures[key]
        while q and now - q[0] > WINDOW_SECONDS:
            q.popleft()
        q.append(now)
        return len(q) > MAX_FAILURES


def reset() -> None:
    with _lock:
        _failures.clear()
