from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlencode, urlparse
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.application.security import ROLE_TECHNICIAN
from app.infrastructure.acumatica.oidc import OidcIdentity
from app.infrastructure.sql import (
    AuthSession,
    Base,
    SqlAuthSessionRepository,
    SqlUserIdentityRepository,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from app.server.oidc import OidcRuntime, oidc_session_auth_resolver


ISSUER = "https://identity.example.invalid"
COOKIE = "rp_test_session"


class FakeOidcClient:
    def __init__(self, identity: OidcIdentity) -> None:
        self.identity = identity
        self.last_verifier: str | None = None
        self.last_nonce: str | None = None

    async def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        self.last_verifier = code_verifier
        self.last_nonce = nonce
        return "https://identity.example.invalid/authorize?" + urlencode(
            {
                "state": state,
                "nonce": nonce,
                "code_challenge_method": "S256",
            }
        )

    async def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> OidcIdentity:
        if code != "valid-code":
            raise ValueError("invalid code")
        if code_verifier != self.last_verifier or nonce != self.last_nonce:
            raise ValueError("invalid transaction")
        return self.identity


class ServerOidcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "oidc.db"
        self.database_url = f"sqlite+pysqlite:///{self.database_path.as_posix()}"
        engine = create_sql_engine(self.database_url)
        Base.metadata.create_all(engine)
        self.factory = create_session_factory(engine)
        with self.factory.begin() as session:
            self.user = SqlUserIdentityRepository(session).upsert(
                issuer=ISSUER,
                subject="subject-1",
                display_name="Technicien OIDC",
                email=None,
                roles=(ROLE_TECHNICIAN,),
            )
        engine.dispose()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _app(self, fake_client: FakeOidcClient):
        runtime = OidcRuntime(
            client=fake_client,  # type: ignore[arg-type]
            cookie_name=COOKIE,
            session_hours=8,
            secure_cookie=False,
        )
        return create_api_app(
            self.database_url,
            auth_resolver=oidc_session_auth_resolver(COOKIE),
            oidc_runtime=runtime,
        )

    def test_login_callback_creates_opaque_session_then_logout_revokes_it(self) -> None:
        fake = FakeOidcClient(
            OidcIdentity(
                issuer=ISSUER,
                subject="subject-1",
                display_name="Nom fournisseur ignoré pour les rôles",
                email=None,
            )
        )
        app = self._app(fake)
        with TestClient(app) as client:
            before = client.get("/api/v1/auth/me")
            login = client.get("/api/v1/auth/login", follow_redirects=False)
            self.assertEqual(login.status_code, 302)
            state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

            callback = client.get(
                f"/api/v1/auth/callback?code=valid-code&state={state}",
                follow_redirects=False,
            )
            self.assertEqual(callback.status_code, 303)
            self.assertEqual(callback.headers["location"], "/")
            set_cookie = callback.headers["set-cookie"].lower()
            self.assertIn("httponly", set_cookie)
            self.assertIn("samesite=lax", set_cookie)

            session_token = client.cookies.get(COOKIE)
            self.assertIsNotNone(session_token)
            me = client.get("/api/v1/auth/me")
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["display_name"], "Technicien OIDC")
            self.assertEqual(me.json()["roles"], [ROLE_TECHNICIAN])
            self.assertEqual(me.json()["auth_mode"], "oidc")

            with app.state.session_factory.begin() as session:
                stored = session.scalar(select(AuthSession))
                self.assertIsNotNone(stored)
                assert stored is not None
                self.assertNotEqual(stored.token_hash, session_token)
                self.assertNotIn(session_token or "", stored.token_hash)

            logout = client.post("/api/v1/auth/logout")
            self.assertEqual(logout.status_code, 204)
            after = client.get("/api/v1/auth/me")

        self.assertEqual(before.status_code, 401)
        self.assertEqual(before.json()["error"]["code"], "authentication_required")
        self.assertEqual(after.status_code, 401)

    def test_callback_rejects_identity_not_registered_locally(self) -> None:
        fake = FakeOidcClient(
            OidcIdentity(
                issuer=ISSUER,
                subject="unknown-subject",
                display_name="Utilisateur inconnu",
                email=None,
            )
        )
        app = self._app(fake)
        with TestClient(app) as client:
            login = client.get("/api/v1/auth/login", follow_redirects=False)
            state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
            callback = client.get(
                f"/api/v1/auth/callback?code=valid-code&state={state}",
                follow_redirects=False,
            )

        self.assertEqual(callback.status_code, 403)
        self.assertEqual(callback.json()["error"]["code"], "oidc_user_not_registered")

    def test_login_state_is_one_time_use(self) -> None:
        fake = FakeOidcClient(
            OidcIdentity(
                issuer=ISSUER,
                subject="subject-1",
                display_name="Technicien OIDC",
                email=None,
            )
        )
        app = self._app(fake)
        with TestClient(app) as client:
            login = client.get("/api/v1/auth/login", follow_redirects=False)
            state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
            first = client.get(
                f"/api/v1/auth/callback?code=valid-code&state={state}",
                follow_redirects=False,
            )
            second = client.get(
                f"/api/v1/auth/callback?code=valid-code&state={state}",
                follow_redirects=False,
            )

        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json()["error"]["code"], "oidc_state_invalid")

    def test_expired_and_revoked_sessions_do_not_resolve(self) -> None:
        now = datetime.now(timezone.utc)
        with self.factory.begin() as session:
            repository = SqlAuthSessionRepository(session)
            repository.create_session(
                raw_token="expired-token",
                user_id=self.user.user_id,
                expires_at=now - timedelta(seconds=1),
            )
            repository.create_session(
                raw_token="revoked-token",
                user_id=self.user.user_id,
                expires_at=now + timedelta(hours=1),
            )
            repository.revoke_session("revoked-token")

        with self.factory.begin() as session:
            repository = SqlAuthSessionRepository(session)
            self.assertIsNone(repository.resolve_principal("expired-token"))
            self.assertIsNone(repository.resolve_principal("revoked-token"))


if __name__ == "__main__":
    unittest.main()
