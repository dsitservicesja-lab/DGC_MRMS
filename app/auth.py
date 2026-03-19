import hashlib
from fastapi import Request
from .config import (
    ADMIN_USERNAME,
    ADMIN_SALT,
    ADMIN_PASSWORD_HASH,
    ADMIN_PASSWORD,
    SUPERADMIN_USERNAME,
    SUPERADMIN_SALT,
    SUPERADMIN_PASSWORD_HASH,
    SUPERADMIN_PASSWORD,
)

def _matches(password: str, plain: str, salt: str, digest: str) -> bool:
    if plain:
        return password == plain
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return h == digest


def authenticate_user(username: str, password: str) -> str | None:
    u = username.strip()
    if u == SUPERADMIN_USERNAME and _matches(password, SUPERADMIN_PASSWORD, SUPERADMIN_SALT, SUPERADMIN_PASSWORD_HASH):
        return "superadmin"
    if u == ADMIN_USERNAME and _matches(password, ADMIN_PASSWORD, ADMIN_SALT, ADMIN_PASSWORD_HASH):
        return "admin"
    return None


def current_role(request: Request) -> str:
    return str(request.session.get("role") or "")


def is_superadmin(request: Request) -> bool:
    return current_role(request) == "superadmin"


def can_view_requests(request: Request) -> bool:
    return current_role(request) in {"admin", "superadmin"}


def is_admin(request: Request) -> bool:
    return can_view_requests(request)
