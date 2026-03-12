import hashlib
from fastapi import Request
from .config import ADMIN_USERNAME, ADMIN_SALT, ADMIN_PASSWORD_HASH

def verify_password(username: str, password: str) -> bool:
    if username != ADMIN_USERNAME:
        return False
    h = hashlib.sha256((ADMIN_SALT + password).encode()).hexdigest()
    return h == ADMIN_PASSWORD_HASH

def is_admin(request: Request) -> bool:
    return request.session.get("role") == "admin"
