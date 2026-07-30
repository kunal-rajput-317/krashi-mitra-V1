"""Auth primitives: password hashing, JWTs, OTP lifecycle.

The invariants here are the ones where a regression is silent and serious —
a verify that raises instead of returning False took /login to a 500 for
every passwordless row, and a token that decodes without checking expiry
would let an old session live forever.
"""

from datetime import datetime, timedelta

import pytest

from backend.utils import auth_utils


class TestPasswordHashing:
    def test_hash_then_verify_round_trip(self):
        hashed = auth_utils.hash_password("KisanBhai@2026")
        assert hashed != "KisanBhai@2026"
        assert auth_utils.verify_password("KisanBhai@2026", hashed) is True

    def test_wrong_password_is_rejected(self):
        hashed = auth_utils.hash_password("KisanBhai@2026")
        assert auth_utils.verify_password("kisanbhai@2026", hashed) is False

    def test_salt_makes_each_hash_unique(self):
        a = auth_utils.hash_password("same-password")
        b = auth_utils.hash_password("same-password")
        assert a != b, "identical hashes mean the salt is not being applied"

    @pytest.mark.parametrize("bad_hash", [None, "", "   ", "not-a-bcrypt-hash"])
    def test_missing_or_corrupt_hash_fails_closed(self, bad_hash):
        """Must return False, never raise.

        Legacy and re-imported rows can carry a NULL hashed_password; the old
        code did None.encode() and surfaced an AttributeError as a 500 on
        /login. A passwordless account must fail closed.
        """
        assert auth_utils.verify_password("anything", bad_hash) is False

    def test_password_longer_than_bcrypt_limit_is_handled(self):
        """bcrypt silently truncates past 72 bytes; hashing must not raise."""
        long_password = "क" * 200
        hashed = auth_utils.hash_password(long_password)
        assert auth_utils.verify_password(long_password, hashed) is True


class TestPasswordStrength:
    def test_a_strong_password_passes(self):
        assert auth_utils.validate_password_strength("KisanBhai@2026") is None

    @pytest.mark.parametrize("weak", ["", "abc", "12345"])
    def test_short_passwords_are_rejected_with_a_reason(self, weak):
        error = auth_utils.validate_password_strength(weak)
        assert isinstance(error, str) and error.strip()


class TestAccessTokens:
    def test_round_trip_preserves_identity(self):
        token = auth_utils.create_access_token(user_id=42, email="a@b.com")
        payload = auth_utils.decode_access_token(token)
        assert payload is not None
        assert str(payload.get("sub")) == "42" or payload.get("user_id") == 42
        assert payload.get("email") == "a@b.com"

    def test_garbage_token_returns_none_not_an_exception(self):
        assert auth_utils.decode_access_token("not.a.jwt") is None
        assert auth_utils.decode_access_token("") is None

    def test_token_signed_with_another_secret_is_rejected(self):
        """The whole point of JWT_SECRET: a forged token must not decode."""
        from jose import jwt

        forged = jwt.encode(
            {"sub": "1", "email": "attacker@example.com",
             "exp": datetime.utcnow() + timedelta(hours=1)},
            "a-different-secret",
            algorithm="HS256",
        )
        assert auth_utils.decode_access_token(forged) is None

    def test_expired_token_is_rejected(self):
        from jose import jwt

        expired = jwt.encode(
            {"sub": "1", "email": "a@b.com",
             "exp": datetime.utcnow() - timedelta(hours=1)},
            auth_utils.JWT_SECRET,
            algorithm="HS256",
        )
        assert auth_utils.decode_access_token(expired) is None


class TestOtp:
    def test_otp_is_six_digits(self):
        otp = auth_utils.generate_otp()
        assert otp.isdigit() and len(otp) == 6

    def test_otps_are_not_constant(self):
        assert len({auth_utils.generate_otp() for _ in range(30)}) > 1

    def test_fresh_expiry_is_in_the_future(self):
        assert auth_utils.is_otp_expired(auth_utils.otp_expiry_time()) is False

    def test_past_expiry_is_expired(self):
        assert auth_utils.is_otp_expired(datetime.utcnow() - timedelta(minutes=1)) is True

    def test_missing_expiry_counts_as_expired(self):
        """A NULL otp_expiry must not be treated as 'still valid'."""
        assert auth_utils.is_otp_expired(None) is True
