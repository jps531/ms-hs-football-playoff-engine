"""Unit tests for backend.api.auth: session cookies, stored emails, the JWKS cache, and the Prefect gate."""

import asyncio
import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm
from starlette.requests import Request

from backend.api import auth
from backend.api.auth import (
    SESSION_SECRET_KEY,
    _decode_session_token,
    mint_session_token,
)


class TestMintAndDecodeSessionToken:
    """mint_session_token/_decode_session_token round-trip a signed, time-limited token."""

    def test_round_trip_preserves_claims(self):
        """A freshly minted token decodes back to the same db_id/role."""
        token = mint_session_token(db_id=7, role="moderator")
        claims = _decode_session_token(token)
        assert claims is not None
        assert claims["db_id"] == 7
        assert claims["role"] == "moderator"

    def test_expired_token_returns_none(self):
        """A token whose exp has already passed decodes to None, not an error."""
        expired_payload = {"db_id": 7, "role": "moderator", "exp": int(time.time()) - 60}
        token = jwt.encode(expired_payload, SESSION_SECRET_KEY, algorithm="HS256")
        assert _decode_session_token(token) is None

    def test_tampered_signature_returns_none(self):
        """A token signed with the wrong secret decodes to None, not an error."""
        token = jwt.encode(
            {"db_id": 7, "role": "moderator", "exp": int(time.time()) + 3600},
            "a-different-secret-at-least-32-bytes-long",
            algorithm="HS256",
        )
        assert _decode_session_token(token) is None

    def test_malformed_token_returns_none(self):
        """A non-JWT string decodes to None, not an error."""
        assert _decode_session_token("not-a-jwt") is None


# ------------------------------------------------------------ email, JWKS, Prefect gate


def test_only_a_verified_email_is_kept():
    """An address Auth0 hasn't verified is anyone's typing, so it isn't stored."""
    assert auth._verified_email({"email": "a@b.co", "email_verified": True}) == "a@b.co"
    assert auth._verified_email({"email": "a@b.co", "email_verified": False}) == ""
    assert auth._verified_email({"email": "a@b.co"}) == ""


def test_an_unknown_key_refetches_the_key_set_but_not_too_often(monkeypatch):
    """A forced refresh happens past _JWKS_MIN_REFRESH, never sooner."""
    fetched = []

    class Resp:
        """A urlopen response."""

        def __enter__(self):
            """Count the fetch."""
            fetched.append(1)
            return self

        def __exit__(self, *a):
            """Nothing to close."""

        def read(self, *a):
            """An empty key set."""
            return b'{"keys": []}'

    monkeypatch.setattr(auth.urllib.request, "urlopen", lambda *a, **k: Resp())
    now = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(auth, "_jwks_cache", None)
    auth._get_jwks()
    auth._get_jwks(force=True)  # just fetched: no refetch
    assert len(fetched) == 1
    now[0] += auth._JWKS_MIN_REFRESH + 1
    auth._get_jwks(force=True)
    assert len(fetched) == 2
    auth._get_jwks()  # within the TTL: cached
    assert len(fetched) == 2


_AUTH0_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_AUTH0_JWK = {**RSAAlgorithm.to_jwk(_AUTH0_KEY.public_key(), as_dict=True), "kid": "k1", "use": "sig"}


def _auth0_token(key=_AUTH0_KEY, algorithm="RS256", kid="k1", **claims) -> str:
    """An access token as Auth0 signs one, with these claims changed."""
    payload = {"sub": "auth0|1", "aud": auth.AUTH0_AUDIENCE, "iss": auth._ISSUER, "exp": int(time.time()) + 600}
    return jwt.encode({**payload, **claims}, key, algorithm=algorithm, headers={"kid": kid})


def _decode_auth0(monkeypatch, token):
    """``_decode_auth0_token`` against a key set holding just our test key."""
    monkeypatch.setattr(auth, "_get_jwks", lambda force=False: {"keys": [_AUTH0_JWK]})
    return asyncio.run(auth._decode_auth0_token(token))


def test_auth0_token_signed_with_the_key_set_decodes(monkeypatch):
    """A token Auth0 signed (RS256, a kid in the key set, our audience and issuer) gives its claims."""
    assert _decode_auth0(monkeypatch, _auth0_token())["sub"] == "auth0|1"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: _auth0_token(aud="someone-else"), id="wrong audience"),
        pytest.param(lambda: _auth0_token(iss="https://evil.example/"), id="wrong issuer"),
        pytest.param(lambda: _auth0_token(exp=int(time.time()) - 60), id="expired"),
        pytest.param(
            lambda: _auth0_token(key=rsa.generate_private_key(public_exponent=65537, key_size=2048)),
            id="another key",
        ),
        pytest.param(lambda: _auth0_token(kid="k2"), id="unknown kid"),
        pytest.param(lambda: "not-a-jwt", id="malformed"),
    ],
)
def test_auth0_token_that_isnt_ours_is_a_401(monkeypatch, token):
    """Every other token is refused with a 401."""
    with pytest.raises(HTTPException) as err:
        _decode_auth0(monkeypatch, token())
    assert err.value.status_code == 401


def test_auth0_token_forged_with_the_public_key_is_a_401(monkeypatch):
    """HS256 signed with the public key (which anyone can fetch) isn't accepted: only RS256 is."""

    def b64(data: bytes) -> str:
        """Base64url without padding, as in a JWT."""
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    claims = {"sub": "auth0|1", "aud": auth.AUTH0_AUDIENCE, "iss": auth._ISSUER, "exp": int(time.time()) + 600}
    signing_input = (
        f"{b64(json.dumps({'alg': 'HS256', 'typ': 'JWT', 'kid': 'k1'}).encode())}.{b64(json.dumps(claims).encode())}"
    )
    public_der = _AUTH0_KEY.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    forged = f"{signing_input}.{b64(hmac.new(public_der, signing_input.encode(), hashlib.sha256).digest())}"
    with pytest.raises(HTTPException) as err:
        _decode_auth0(monkeypatch, forged)
    assert err.value.status_code == 401


def _cookie_request(token: str | None) -> Request:
    """A request carrying the session cookie."""
    headers = [(b"cookie", f"{auth.SESSION_COOKIE_NAME}={token}".encode())] if token else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})


@pytest.mark.parametrize(("role_now", "allowed"), [("owner", True), ("moderator", False), (None, False)])
def test_prefect_gate_is_owner_only_and_rechecks_the_role(monkeypatch, role_now, allowed):
    """An owner's cookie still passes only if the account is the owner now (not demoted or deactivated)."""

    async def current_role(db_id):
        """The role in the users table today."""
        return role_now

    monkeypatch.setattr(auth, "_current_role", current_role)
    token = auth.mint_session_token(1, "owner")
    run = auth.get_owner_via_cookie_or_bearer(_cookie_request(token), None)
    if allowed:
        assert asyncio.run(run)["db_id"] == 1
    else:
        with pytest.raises(HTTPException) as err:
            asyncio.run(run)
        assert err.value.status_code == 401


def test_prefect_gate_refuses_a_moderator_bearer(monkeypatch):
    """A moderator's Auth0 token is a 403 at the Prefect gate."""

    async def moderator(token):
        """A valid moderator."""
        return {"db_id": 2, "role": "moderator"}

    monkeypatch.setattr(auth, "get_current_user", moderator)
    creds = auth.HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    with pytest.raises(HTTPException) as err:
        asyncio.run(auth.get_owner_via_cookie_or_bearer(_cookie_request(None), creds))
    assert err.value.status_code == 403
