"""Shared FastAPI dependencies."""

import secrets

from fastapi import Header, HTTPException, Request

from app.services import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Optional protection: enforced only when SERVICE_API_KEY is set."""
    expected = request.app.state.services.settings.service_api_key
    if expected is None:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected.get_secret_value()):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")
