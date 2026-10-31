from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from dataflow.modules.audit.infrastructure import AuditRecord
from dataflow.modules.identity.infrastructure import SessionRecord, UserRecord

PASSWORD = "Una-clave-de-pruebas-1234"


def register(client: TestClient, email: str = "alex@example.com") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register", json={"name": "Alex", "email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    return {"x-csrf-token": response.json()["csrf_token"]}


def test_cookie_authentication_logout_and_password_hash(client: TestClient, db: Session) -> None:
    assert client.get("/api/v1/projects").status_code == 401
    headers = register(client)
    raw_token = client.cookies["dataflow_session"]
    assert client.get("/api/v1/auth/me").json()["user"]["email"] == "alex@example.com"
    user = db.scalar(select(UserRecord))
    assert (
        user and user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash
    )
    stored = db.scalar(select(SessionRecord))
    assert stored and stored.token_hash != raw_token
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    client.cookies.set("dataflow_session", raw_token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_generic_errors_and_expiration(client: TestClient, db: Session) -> None:
    register(client)
    client.cookies.clear()
    for email in ["alex@example.com", "unknown@example.com"]:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_CREDENTIALS"
    response = client.post(
        "/api/v1/auth/login", json={"email": "ALEX@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    db.execute(update(SessionRecord).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_origin_and_input_validation(client: TestClient) -> None:
    headers = register(client)
    payload = {"name": "Proyecto correcto"}
    assert client.post("/api/v1/projects", json=payload).status_code == 403
    assert (
        client.post(
            "/api/v1/projects", json=payload, headers={**headers, "Origin": "https://otro.example"}
        ).status_code
        == 403
    )
    invalid = client.post("/api/v1/projects", json={"name": "   "}, headers=headers)
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"
    assert "input" not in str(invalid.json())
    assert "x-correlation-id" in invalid.headers


def test_projects_pagination_edit_archive_and_audit(client: TestClient, db: Session) -> None:
    headers = register(client)
    first = client.post(
        "/api/v1/projects", json={"name": "Ventas 100%", "description": "Original"}, headers=headers
    )
    assert first.status_code == 201
    project = first.json()
    assert project["revision"] == 1
    client.post("/api/v1/projects", json={"name": "Ventas 1000"}, headers=headers)
    page = client.get("/api/v1/projects", params={"q": "100%", "limit": 1}).json()
    assert page["total"] == 1 and page["items"][0]["id"] == project["id"]
    assert client.get("/api/v1/projects", params={"offset": 1, "limit": 1}).json()["total"] == 2
    endpoint = "/api/v1/projects/" + project["id"]
    edited = client.patch(
        endpoint,
        json={"name": "Ventas editadas", "description": "Actualizada", "expected_revision": 1},
        headers=headers,
    )
    assert edited.status_code == 200 and edited.json()["revision"] == 2
    assert (
        client.patch(
            endpoint, json={"name": "Cambio obsoleto", "expected_revision": 1}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(endpoint + "/archive", json={"expected_revision": 2}, headers=headers).json()[
            "status"
        ]
        == "archived"
    )
    assert (
        client.patch(
            endpoint, json={"name": "No editable", "expected_revision": 3}, headers=headers
        ).status_code
        == 409
    )
    assert client.get("/api/v1/projects", params={"status": "archived"}).json()["total"] == 1
    actions = list(
        db.scalars(select(AuditRecord.action).where(AuditRecord.entity_id == project["id"]))
    )
    assert actions == ["project.created", "project.updated", "project.archived"]


def test_cross_account_isolation(client: TestClient) -> None:
    headers = register(client, "owner@example.com")
    project_id = client.post(
        "/api/v1/projects", json={"name": "Proyecto privado"}, headers=headers
    ).json()["id"]
    client.cookies.clear()
    other = register(client, "other@example.com")
    assert client.get("/api/v1/projects").json()["total"] == 0
    path = "/api/v1/projects/" + project_id
    assert client.get(path).status_code == 404
    assert (
        client.patch(
            path, json={"name": "Intento ajeno", "expected_revision": 1}, headers=other
        ).status_code
        == 404
    )
    assert (
        client.post(path + "/archive", json={"expected_revision": 1}, headers=other).status_code
        == 404
    )
    assert client.get("/api/v1/projects/" + str(uuid4())).status_code == 404


def test_rate_limit_persists_failed_attempts(client: TestClient, db: Session) -> None:
    for _ in range(15):
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": "locked@example.com", "password": "wrong"}
            ).status_code
            == 401
        )
    response = client.post(
        "/api/v1/auth/login", json={"email": "locked@example.com", "password": "wrong"}
    )
    assert response.status_code == 429
    assert db.scalar(select(func.count()).select_from(UserRecord)) == 0
