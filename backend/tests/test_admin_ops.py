"""The backup heartbeat the admin inbox reads.

The deployment runs Postgres on the same box as the app to save $15/month,
which is only a reasonable trade while the nightly dump is genuinely running.
These tests cover the thing that makes it reasonable: that a stopped backup
shows up as `stale`, and that an absent one is reported as `unknown` rather
than quietly passing for healthy.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.routers import admin


@pytest.fixture
def heartbeat(tmp_path, monkeypatch):
    path = tmp_path / "last-success"
    monkeypatch.setattr(admin, "BACKUP_HEARTBEAT", path)
    return path


def _written(hours_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat().replace(
        "+00:00", "Z"
    )


async def test_absent_heartbeat_is_unknown_not_ok(
    client: AsyncClient, admin_headers, heartbeat
) -> None:
    """The dangerous bug would be reporting healthy when nothing has ever run."""
    body = (await client.get("/api/admin/ops", headers=admin_headers)).json()["backup"]
    assert body["state"] == "unknown"
    assert body["last_success"] is None


async def test_recent_backup_is_ok(
    client: AsyncClient, admin_headers, heartbeat
) -> None:
    heartbeat.write_text(_written(5))
    body = (await client.get("/api/admin/ops", headers=admin_headers)).json()["backup"]
    assert body["state"] == "ok"
    assert 4.5 < body["age_hours"] < 5.5


async def test_two_missed_nights_is_stale(
    client: AsyncClient, admin_headers, heartbeat
) -> None:
    heartbeat.write_text(_written(40))
    body = (await client.get("/api/admin/ops", headers=admin_headers)).json()["backup"]
    assert body["state"] == "stale"


async def test_one_slow_night_does_not_cry_wolf(
    client: AsyncClient, admin_headers, heartbeat
) -> None:
    """A nightly job plus a slow upload plus a restart must not alarm; 36h is
    chosen so one late run is tolerated and two missed ones are not."""
    heartbeat.write_text(_written(30))
    body = (await client.get("/api/admin/ops", headers=admin_headers)).json()["backup"]
    assert body["state"] == "ok"


async def test_garbage_heartbeat_is_unknown(
    client: AsyncClient, admin_headers, heartbeat
) -> None:
    """A half-written file must not parse as a fresh backup."""
    heartbeat.write_text("not a timestamp")
    body = (await client.get("/api/admin/ops", headers=admin_headers)).json()["backup"]
    assert body["state"] == "unknown"


async def test_ops_requires_a_token(client: AsyncClient, heartbeat) -> None:
    assert (await client.get("/api/admin/ops")).status_code == 401
