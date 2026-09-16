"""Connection lifetime is what Neon actually bills.

Neon suspends a compute only at ZERO open connections, so a pool that holds
connections open bills 24h/day of idle-awake time against a free allowance
worth 13.3h/day. Two things keep that from silently coming back:

  * the engine must use NullPool, so a closed Session really disconnects;
  * the URL must reach Neon's `-pooler` host, so paying a fresh handshake per
    session stays cheap.

Both are one-line regressions to make and invisible in production until the
month's compute budget is gone, which is why they are pinned here.
"""

from sqlalchemy.pool import NullPool

from backend.database.db import _pooler_url, engine


DIRECT = "postgresql://u:p@ep-foo-123.us-east-2.aws.neon.tech/db?sslmode=require"
POOLED = "postgresql://u:p@ep-foo-123-pooler.us-east-2.aws.neon.tech/db?sslmode=require"


class TestPoolerURL:
    def test_neon_host_gains_the_pooler_label(self):
        assert _pooler_url(DIRECT) == POOLED

    def test_already_pooled_url_is_untouched(self):
        assert _pooler_url(POOLED) == POOLED

    def test_non_neon_host_is_untouched(self):
        url = "postgresql://u:p@db.example.com/db"
        assert _pooler_url(url) == url

    def test_sqlite_url_is_untouched(self):
        assert _pooler_url("sqlite:///tmp/test.db") == "sqlite:///tmp/test.db"

    def test_password_containing_an_at_sign_survives(self):
        # rsplit, not split: a password with "@" used to truncate the host.
        url = "postgresql://u:pa@ss@ep-foo-123.us-east-2.aws.neon.tech/db"
        assert _pooler_url(url) == (
            "postgresql://u:pa@ss@ep-foo-123-pooler.us-east-2.aws.neon.tech/db"
        )

    def test_explicit_port_is_preserved(self):
        url = "postgresql://u:p@ep-foo-123.us-east-2.aws.neon.tech:5432/db"
        assert "-pooler.us-east-2.aws.neon.tech:5432/db" in _pooler_url(url)

    def test_url_with_no_path_still_rewrites(self):
        url = "postgresql://u:p@ep-foo-123.us-east-2.aws.neon.tech"
        assert _pooler_url(url).endswith("-pooler.us-east-2.aws.neon.tech")


class TestEngineHoldsNoConnections:
    def test_engine_uses_nullpool(self):
        # QueuePool here means the compute never sleeps again.
        assert isinstance(engine.pool, NullPool)
