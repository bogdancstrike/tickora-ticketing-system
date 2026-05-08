import time

from src.iam.models import User
from src.iam.principal import ROLE_DISTRIBUTOR
from src.iam import service as iam_service
from src.iam import token_verifier


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.ttls[key] = ttl
        self.values[key] = value


def test_token_cache_key_is_stable_sha256():
    key1 = token_verifier._token_cache_key("same-token")
    key2 = token_verifier._token_cache_key("same-token")
    key3 = token_verifier._token_cache_key("other-token")

    assert key1 == key2
    assert key1 != key3
    assert key1.startswith("tickora:jwt:tok:")


def test_principal_from_claims_uses_redis_until_token_expiry(monkeypatch):
    redis = FakeRedis()
    calls = {"count": 0}

    def fake_get_or_create(claims):
        calls["count"] += 1
        return User(
            id="user-1",
            keycloak_subject=claims["sub"],
            username="alice",
            email="alice@example.test",
            first_name="Alice",
            last_name="User",
            user_type="internal",
            is_active=True,
        )

    monkeypatch.setattr(iam_service, "get_redis", lambda: redis)
    monkeypatch.setattr(iam_service, "get_or_create_user_from_claims", fake_get_or_create)

    claims = {
        "sub": "kc-sub-1",
        "jti": "token-1",
        "exp": int(time.time()) + 120,
        "realm_access": {"roles": [ROLE_DISTRIBUTOR]},
        "groups": ["/tickora/sectors/s10/members"],
    }

    first = iam_service.principal_from_claims(claims)
    second = iam_service.principal_from_claims(claims)

    assert calls["count"] == 1
    assert first == second
    assert second.is_distributor
    assert second.is_member_of("s10")
    assert next(iter(redis.ttls.values())) <= 120
