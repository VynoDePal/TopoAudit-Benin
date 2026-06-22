"""Tests de l'authentification minimale SaaS (P1.1)."""

import pytest
from fastapi.testclient import TestClient

from app.auth import create_token, decode_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.main import app


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeAuthSession:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.projects: dict[str, dict] = {}

    def execute(self, statement, params):
        sql = str(statement)
        if "INSERT INTO users" in sql:
            self.users[params["email"]] = {
                "id": params["id"],
                "email": params["email"],
                "password_hash": params["pwd"],
            }
            return FakeResult(None)
        if "SELECT id FROM users WHERE email" in sql:
            user = self.users.get(params["email"])
            return FakeResult({"id": user["id"]} if user else None)
        if "password_hash FROM users WHERE email" in sql:
            return FakeResult(self.users.get(params["email"]))
        if "SELECT id, email FROM users WHERE id" in sql:
            user = next((u for u in self.users.values() if u["id"] == params["id"]), None)
            return FakeResult({"id": user["id"], "email": user["email"]} if user else None)
        if "FROM projects" in sql:
            return FakeResult(self.projects.get(params["project_id"]))
        return FakeResult(None)

    def commit(self):
        pass


def _client(session):
    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


# ---------------------------------------------------------------- unités
def test_password_hash_roundtrip():
    stored = hash_password("s3cret-passw0rd")
    assert stored != "s3cret-passw0rd"
    assert verify_password("s3cret-passw0rd", stored)
    assert not verify_password("wrong", stored)


def test_token_roundtrip_and_tamper_detection():
    token = create_token(user_id="u1", email="a@b.bj")
    payload = decode_token(token)
    assert payload is not None and payload["sub"] == "u1"
    assert decode_token(token + "x") is None  # signature invalide
    assert decode_token("not.a.jwt") is None


# ------------------------------------------------------------- endpoints
def test_register_then_login_returns_token():
    session = FakeAuthSession()
    client = _client(session)

    reg = client.post("/api/auth/register", json={"email": "Arp@Example.bj", "password": "motdepasse1"})
    assert reg.status_code == 201
    assert reg.json()["email"] == "arp@example.bj"
    assert decode_token(reg.json()["token"]) is not None

    dup = client.post("/api/auth/register", json={"email": "arp@example.bj", "password": "motdepasse1"})
    assert dup.status_code == 409

    login = client.post("/api/auth/login", json={"email": "arp@example.bj", "password": "motdepasse1"})
    assert login.status_code == 200
    assert login.json()["user_id"] == reg.json()["user_id"]

    bad = client.post("/api/auth/login", json={"email": "arp@example.bj", "password": "mauvais!!"})
    assert bad.status_code == 401


def test_ownership_enforced_when_demo_disabled(monkeypatch):
    monkeypatch.setattr(settings, "demo_local", False)
    session = FakeAuthSession()
    session.users["owner@x.bj"] = {"id": "owner-1", "email": "owner@x.bj", "password_hash": hash_password("pw")}
    session.users["other@x.bj"] = {"id": "other-2", "email": "other@x.bj", "password_hash": hash_password("pw")}
    session.projects["proj-1"] = {"id": "proj-1", "owner_id": "owner-1", "status": "AUDITED"}
    client = _client(session)

    owner_token = create_token(user_id="owner-1", email="owner@x.bj")
    other_token = create_token(user_id="other-2", email="other@x.bj")

    # Sans jeton → 401.
    assert client.get("/api/projects/proj-1/workflow").status_code == 401
    # Propriétaire → autorisé.
    ok = client.get("/api/projects/proj-1/workflow", headers={"Authorization": f"Bearer {owner_token}"})
    assert ok.status_code == 200
    # Autre utilisateur → 403.
    forbidden = client.get("/api/projects/proj-1/workflow", headers={"Authorization": f"Bearer {other_token}"})
    assert forbidden.status_code == 403


def test_demo_local_allows_access_without_token(monkeypatch):
    monkeypatch.setattr(settings, "demo_local", True)
    monkeypatch.setattr(settings, "app_env", "local")
    session = FakeAuthSession()
    session.projects["proj-demo"] = {"id": "proj-demo", "owner_id": None, "status": "AUDITED"}
    client = _client(session)

    assert client.get("/api/projects/proj-demo/workflow").status_code == 200
