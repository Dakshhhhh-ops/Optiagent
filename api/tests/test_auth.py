import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

import optiagent_api.auth as auth
from optiagent_api.auth import AuthError, verify_token
from optiagent_api.datasets import DatasetStore
from optiagent_api.main import app
from optiagent_api.projects import ProjectStore
from optiagent_api.routers.datasets import get_store
from optiagent_api.routers.projects import get_projects
from optiagent_api.settings import Settings, get_settings

ISSUER = "https://example.clerk.accounts.dev"
ORIGIN = "http://localhost:3000"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeKeys:
    """Stands in for Clerk's JWKS endpoint."""

    class _Key:
        key = PRIVATE_KEY.public_key()

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return self._Key()


def token(sub: str = "user_alice", **overrides: Any) -> str:
    now = int(time.time())
    claims = {"sub": sub, "iss": ISSUER, "iat": now, "nbf": now, "exp": now + 60, "azp": ORIGIN}
    claims.update(overrides)
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256")


def verify(t: str) -> str:
    return verify_token(t, issuer=ISSUER, authorized_parties=[ORIGIN], keys=FakeKeys())


# --------------------------------------------------------------------------- token checks


def test_valid_token_gives_the_user() -> None:
    assert verify(token()) == "user_alice"


@pytest.mark.parametrize(
    "bad",
    [
        {"exp": int(time.time()) - 120},  # expired (beyond the 30 s leeway)
        {"iss": "https://evil.example"},  # another issuer
        {"azp": "https://evil.example"},  # issued for another site
    ],
)
def test_rejected_tokens(bad: dict[str, Any]) -> None:
    with pytest.raises(AuthError):
        verify(token(**bad))


def test_tampered_token_is_rejected() -> None:
    header, _payload, signature = token().split(".")
    forged = jwt.encode({"sub": "user_admin"}, "x", algorithm="HS256").split(".")[1]
    with pytest.raises(AuthError):
        verify(f"{header}.{forged}.{signature}")


def test_token_signed_by_another_key_is_rejected() -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    forged = jwt.encode(
        {"sub": "user_alice", "iss": ISSUER, "iat": now, "exp": now + 60}, other, algorithm="RS256"
    )
    with pytest.raises(AuthError):
        verify(forged)


# --------------------------------------------------------------------------- endpoints


@pytest.fixture
def secured(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = Settings(auth_issuer=ISSUER, cors_origins=[ORIGIN])
    monkeypatch.setattr(auth, "jwks_client", lambda issuer: FakeKeys())
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_projects] = lambda: ProjectStore(engine)
    app.dependency_overrides[get_store] = lambda: DatasetStore(engine, 100_000, 5)
    yield TestClient(app)
    app.dependency_overrides.clear()


def as_user(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(sub)}"}


def test_private_endpoints_need_sign_in(secured: TestClient) -> None:
    assert secured.get("/api/v1/projects").status_code == 401
    assert secured.post("/api/v1/datasets/samples/sunray").status_code == 401
    assert secured.post("/api/v1/agent/analyze", json={"text": "x"}).status_code == 401
    bad = secured.get("/api/v1/projects", headers={"Authorization": "Bearer not-a-token"})
    assert bad.status_code == 401


def test_public_endpoints_stay_open(secured: TestClient) -> None:
    assert secured.get("/api/v1/examples").status_code == 200
    assert secured.get("/api/v1/datasets/samples").status_code == 200
    assert secured.get("/health").status_code == 200


def test_users_only_see_their_own_data(secured: TestClient) -> None:
    problem = secured.get("/api/v1/examples/t1_two_by_two").json()["problem"]
    created = secured.post(
        "/api/v1/projects", json={"problem": problem, "source": "manual"}, headers=as_user("alice")
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    assert [p["id"] for p in secured.get("/api/v1/projects", headers=as_user("alice")).json()] == [
        project_id
    ]
    assert secured.get("/api/v1/projects", headers=as_user("bob")).json() == []
    for method, path in [
        ("GET", f"/api/v1/projects/{project_id}"),
        ("DELETE", f"/api/v1/projects/{project_id}"),
    ]:
        assert secured.request(method, path, headers=as_user("bob")).status_code == 404

    dataset = secured.post("/api/v1/datasets/samples/sunray", headers=as_user("alice")).json()
    dataset_id = dataset["meta"]["id"]
    assert (
        secured.get(f"/api/v1/datasets/{dataset_id}", headers=as_user("alice")).status_code == 200
    )
    assert secured.get(f"/api/v1/datasets/{dataset_id}", headers=as_user("bob")).status_code == 404
