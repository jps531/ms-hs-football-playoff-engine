"""Unit tests for backend.api.auth's session cookie helpers."""

import time

from jose import jwt

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
        token = jwt.encode({"db_id": 7, "role": "moderator", "exp": int(time.time()) + 3600}, "wrong-secret", algorithm="HS256")
        assert _decode_session_token(token) is None

    def test_malformed_token_returns_none(self):
        """A non-JWT string decodes to None, not an error."""
        assert _decode_session_token("not-a-jwt") is None
