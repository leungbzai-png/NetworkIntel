"""
在线缓存测试（独立 SQLite，临时路径，可控时钟；不联网）：
  - set / get 正常
  - 过期不命中（include_expired 可取回并 is_expired=True）
  - purge_expired
  - stats
"""
import os
import tempfile

import _bootstrap  # noqa: F401

from providers.cache import OnlineCache


def _cache(tmpdir, clock):
    return OnlineCache(db_path=os.path.join(tmpdir, "oc.sqlite"), now=lambda: clock[0])


def test_set_and_get():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        c = _cache(d, clock)
        assert c.set("bgpview", "ip", "8.8.8.8",
                     normalized={"asn": 15169}, raw={"x": 1}, ttl_seconds=100) is True
        e = c.get("bgpview", "ip", "8.8.8.8")
        assert e is not None
        assert e.normalized == {"asn": 15169}
        assert e.status == "ok"
        assert e.is_expired(clock[0]) is False


def test_expired_not_hit():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        c = _cache(d, clock)
        c.set("ipinfo", "ip", "1.1.1.1", normalized={"a": 1}, ttl_seconds=10)
        clock[0] = 1000.0 + 11        # 过期
        assert c.get("ipinfo", "ip", "1.1.1.1") is None
        stale = c.get("ipinfo", "ip", "1.1.1.1", include_expired=True)
        assert stale is not None and stale.is_expired(clock[0]) is True


def test_purge_expired():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        c = _cache(d, clock)
        c.set("bgpview", "ip", "a", normalized={}, ttl_seconds=10)
        c.set("bgpview", "ip", "b", normalized={}, ttl_seconds=10000)
        clock[0] = 1000.0 + 50
        removed = c.purge_expired()
        assert removed == 1
        assert c.get("bgpview", "ip", "b") is not None


def test_stats():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        c = _cache(d, clock)
        c.set("bgpview", "ip", "a", normalized={}, ttl_seconds=10)
        c.set("ipinfo", "ip", "b", normalized={}, ttl_seconds=10)
        clock[0] = 1000.0 + 50
        s = c.stats()
        assert s["total"] == 2
        assert s["expired"] == 2
        assert s["by_provider"].get("bgpview") == 1


def test_upsert_overwrites():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        c = _cache(d, clock)
        c.set("bgpview", "ip", "x", normalized={"v": 1}, ttl_seconds=100)
        c.set("bgpview", "ip", "x", normalized={"v": 2}, ttl_seconds=100)
        assert c.get("bgpview", "ip", "x").normalized == {"v": 2}
        assert c.stats()["total"] == 1
