"""Seam to the EduPage client.

The real thing is the synchronous `edupage_api.Edupage`; tests swap in a fake via
:func:`set_client_factory` so the whole API surface can be exercised offline.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol


class EduPageClient(Protocol):
    subdomain: str
    username: str
    session: Any

    def login(self, username: str, password: str, subdomain: str) -> Any: ...


ClientFactory = Callable[[], EduPageClient]

_factory: ClientFactory | None = None

try:  # pragma: no cover - trivial import guard
    from edupage_api import Edupage as _Edupage

    LIBRARY_AVAILABLE = True
except Exception:  # pragma: no cover
    _Edupage = None  # type: ignore[assignment]
    LIBRARY_AVAILABLE = False


def _default_factory() -> EduPageClient:
    if _Edupage is None:
        raise RuntimeError("edupage-api library is not installed")
    return _Edupage()  # type: ignore[return-value]


def set_client_factory(factory: ClientFactory | None) -> None:
    """Install a client factory (tests) or restore the default with ``None``."""
    global _factory
    _factory = factory


def new_client() -> EduPageClient:
    return (_factory or _default_factory)()
