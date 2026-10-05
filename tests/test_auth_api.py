from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def legacy_auth():
    spec = importlib.util.spec_from_file_location("legacy_auth", "app/auth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "entered,expected,result",
    [
        ("пароль", "пароль", True),
        (" пароль", "пароль", False),
        ("", "пароль", False),
        ("é", "e", False),
    ],
)
def test_legacy_matches(entered, expected, result):
    assert legacy_auth()._matches(entered, expected) is result


@pytest.mark.parametrize(
    "value,expected", [(None, None), ("   ", None), ("  пароль ", "пароль"), (123, "123")]
)
def test_legacy_configuration(monkeypatch, value, expected):
    auth = legacy_auth()
    monkeypatch.delenv("PPD_APP_PASSWORD", raising=False)
    monkeypatch.setattr(auth, "st", SimpleNamespace(secrets={"app_password": value}))
    assert auth.configured_password() == expected


@pytest.fixture
def client(monkeypatch, tmp_path):
    from ppd_audit.api.auth_routes import AuthenticationMiddleware, router

    monkeypatch.setenv("PPD_APP_PASSWORD", "пароль")
    monkeypatch.setenv("PPD_SESSION_SECRET", "a" * 40)
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(AuthenticationMiddleware)

    @app.get("/private")
    def private():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return TestClient(app)


def test_login_logout_and_guard(client):
    assert client.get("/auth/session").json() == {
        "authentication_required": True,
        "authenticated": False,
    }
    assert client.get("/private").status_code == 401
    assert client.get("/docs").status_code == 401
    assert client.get("/health").status_code == 200
    assert client.post("/auth/login", json={"password": "нет"}).status_code == 401
    response = client.post("/auth/login", json={"password": "пароль"})
    assert response.json()["authenticated"] is True
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert client.get("/private").status_code == 200
    assert client.post("/auth/logout").json()["authenticated"] is False
    assert client.get("/private").status_code == 401


def test_no_password_gate(client, monkeypatch):
    monkeypatch.setenv("PPD_APP_PASSWORD", "   ")
    assert client.get("/private").status_code == 200
    assert client.get("/auth/session").json() == {
        "authentication_required": False,
        "authenticated": True,
    }


def test_tampered_expired_rotated_sessions(client, monkeypatch):
    from ppd_audit.services import authentication

    client.post("/auth/login", json={"password": "пароль"})
    token = client.cookies.get("ppd_session")
    client.cookies.clear()
    client.cookies.set("ppd_session", token + "x")
    assert client.get("/private").status_code == 401
    client.cookies.set("ppd_session", token)
    monkeypatch.setattr(authentication.time, "time", lambda: 10**12)
    assert client.get("/private").status_code == 401
    monkeypatch.undo()
    monkeypatch.setenv("PPD_APP_PASSWORD", "другой пароль")
    assert client.get("/private").status_code == 401


def test_origin_guard(client):
    assert (
        client.post(
            "/auth/login", json={"password": "пароль"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/auth/login", json={"password": "пароль"}, headers={"Origin": "http://testserver"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/logout",
            headers={"Origin": "http://127.0.0.1:5173", "X-Forwarded-Host": "127.0.0.1:5173"},
        ).status_code
        == 200
    )


def test_environment_and_file_configuration(monkeypatch, tmp_path):
    from ppd_audit.services.authentication import configured_password

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PPD_APP_PASSWORD", raising=False)
    assert configured_password() is None
    Path(".streamlit").mkdir()
    Path(".streamlit/secrets.toml").write_text('app_password = " file-password "')
    assert configured_password() == "file-password"
    monkeypatch.setenv("PPD_APP_PASSWORD", " env-password ")
    assert configured_password() == "env-password"


def test_malformed_origin_is_rejected(client):
    response = client.post(
        "/auth/login", json={"password": "пароль"}, headers={"Origin": "http://["}
    )
    assert response.status_code == 403


def test_secure_cookie_and_signing_secret_rotation(client, monkeypatch):
    monkeypatch.setenv("PPD_COOKIE_SECURE", "1")
    response = client.post("/auth/login", json={"password": "пароль"})
    assert "Secure" in response.headers["set-cookie"]
    token = client.cookies.get("ppd_session")
    client.cookies.clear()
    client.cookies.set("ppd_session", token)
    monkeypatch.setenv("PPD_SESSION_SECRET", "b" * 40)
    assert client.get("/private").status_code == 401


def test_shared_matching_is_identical_to_legacy():
    from ppd_audit.services.authentication import matches

    assert matches("пароль", "пароль")
    assert not matches(" пароль", "пароль")
