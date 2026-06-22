"""Authentification minimale SaaS (P1.1) : inscription, connexion, JWT, ownership.

Sans dépendance externe : hachage pbkdf2 (stdlib) + JWT HS256 (stdlib hmac). Un mode
DEMO_LOCAL (jamais actif en production) permet la démo sans authentification.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db

_PBKDF2_ROUNDS = 200_000


# ---------------------------------------------------------------- mots de passe
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, derived_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
        return hmac.compare_digest(derived, base64.b64decode(derived_b64))
    except Exception:
        return False


# --------------------------------------------------------------------- JWT
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def create_token(*, user_id: str, email: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "email": email, "exp": int(time.time()) + settings.jwt_expires_seconds}
    segment = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    signature = hmac.new(settings.jwt_secret.encode(), segment.encode(), hashlib.sha256).digest()
    return f"{segment}.{_b64url(signature)}"


def decode_token(token: str) -> dict | None:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        segment = f"{header_b64}.{payload_b64}"
        expected = hmac.new(settings.jwt_secret.encode(), segment.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


# ------------------------------------------------------------- utilisateurs
@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str


def _load_user_by_id(user_id: str, db: Session) -> AuthUser | None:
    row = (
        db.execute(text("SELECT id, email FROM users WHERE id = :id"), {"id": user_id}).mappings().first()
    )
    return AuthUser(id=row["id"], email=row["email"]) if row else None


def register_user(email: str, password: str, db: Session) -> AuthUser:
    email = email.strip().lower()
    if not email or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email and password are required")
    existing = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user_id = base64.urlsafe_b64encode(os.urandom(18)).decode()
    db.execute(
        text("INSERT INTO users (id, email, password_hash, created_at) VALUES (:id, :email, :pwd, NOW())"),
        {"id": user_id, "email": email, "pwd": hash_password(password)},
    )
    db.commit()
    return AuthUser(id=user_id, email=email)


def authenticate_user(email: str, password: str, db: Session) -> AuthUser:
    email = email.strip().lower()
    row = (
        db.execute(
            text("SELECT id, email, password_hash FROM users WHERE email = :email"), {"email": email}
        )
        .mappings()
        .first()
    )
    if row is None or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return AuthUser(id=row["id"], email=row["email"])


# --------------------------------------------------------------- dépendances
def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    return header[7:].strip()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> AuthUser | None:
    """Utilisateur courant. En DEMO_LOCAL : optionnel (None si pas de jeton)."""
    token = _bearer_token(request)
    if settings.demo_local_enabled:
        if token:
            payload = decode_token(token)
            if payload:
                return _load_user_by_id(str(payload.get("sub")), db)
        return None
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    payload = decode_token(token)
    user = _load_user_by_id(str(payload.get("sub")), db) if payload else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


def ensure_project_access(owner_id: str | None, current_user: AuthUser | None) -> None:
    """Vérifie la propriété d'un projet (ouverte en DEMO_LOCAL)."""
    if settings.demo_local_enabled:
        return
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project belongs to another user")


def authorized_project_user(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthUser | None:
    """Dépendance des routes projet : authentifie + vérifie la propriété (404/401/403)."""
    current_user = get_current_user(request, db)
    row = (
        db.execute(
            text("SELECT owner_id FROM projects WHERE id = :project_id"), {"project_id": project_id}
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    ensure_project_access(row.get("owner_id"), current_user)
    return current_user
