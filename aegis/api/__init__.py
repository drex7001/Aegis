"""FastAPI application: OIDC auth, authorization gates, v1 routes, legacy UI (T11–T14)."""

def create_app():
    """Import lazily so authorization modules remain independently importable."""
    from aegis.api.app import create_app as factory

    return factory()

__all__ = ["create_app"]
