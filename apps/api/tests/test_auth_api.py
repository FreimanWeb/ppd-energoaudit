"""HTTP-аутентификация API и env-only конфигурация общего пароля."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "entered,expected,result",
    [
        ("пароль", "пароль", True),
        (" пароль", "пароль", False),
        ("", "пароль", False),
        ("é", "e", False),
    ],
)
def test_matches(entered, expected, result):
    from ppd_audit.services.authentication import matches

    assert matches(entered, expected) is result


@pytest.mark.parametrize("value,expected", [(None, None), ("   ", None), ("  пароль ", "пароль")])
def test_configured_password_env_only(monkeypatch, value, expected):
    from ppd_audit.services.authentication import configured_password

    if value is None:
        monkeypatch.delenv("PPD_APP_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("PPD_APP_PASSWORD", value)
    assert configured_password() == expected


def test_secrets_toml_is_not_a_password_source(monkeypatch, tmp_path):
    """После удаления Streamlit пароль берётся только из PPD_APP_PASSWORD."""
    from ppd_audit.services.authentication import configured_password

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PPD_APP_PASSWORD", raising=False)
    Path(".streamlit").mkdir()
    Path(".streamlit/secrets.toml").write_text('app_password = "file-password"')
    assert configured_password() is None
    monkeypatch.setenv("PPD_APP_PASSWORD", " env-password ")
    assert configured_password() == "env-password"


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

    response = client.post("/auth/login", json={"password": "пароль"})
    assert response.status_code == 200
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
