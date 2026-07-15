"""
NetworkIntel - IPv6 Schema 扩展
新增表使用 TEXT 存储16字节hex字符串（如 '20010db8000000000000000000000001'）
这样字符串比较等价于数值比较，可用范围查询
"""

SCHEMA_V6_SQL = """
-- ============================================================
-- GeoIP IPv6
-- ============================================================
CREATE TABLE IF NOT EXISTS geoip_v6 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    network         TEXT NOT NULL,
    network_start_hex TEXT NOT NULL,  -- 32-char hex (16 bytes)
    network_end_hex   TEXT NOT NULL,
    country_code    TEXT,
    country_name    TEXT,
    region          TEXT,
    city            TEXT,
    latitude        REAL,
    longitude       REAL,
    accuracy_radius INTEGER,
    source          TEXT NOT NULL DEFAULT 'geoip',
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_geoip_v6_range ON geoip_v6(network_start_hex, network_end_hex);

-- ============================================================
-- ASN IPv6
-- ============================================================
CREATE TABLE IF NOT EXISTS asn_info_v6 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asn             INTEGER NOT NULL,
    as_name         TEXT,
    country_code    TEXT,
    network         TEXT,
    network_start_hex TEXT NOT NULL,
    network_end_hex   TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'ip2asn_v6',
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_asn_v6_range ON asn_info_v6(network_start_hex, network_end_hex);
CREATE INDEX IF NOT EXISTS idx_asn_v6_number ON asn_info_v6(asn);

-- ============================================================
-- RPKI IPv6
-- ============================================================
CREATE TABLE IF NOT EXISTS rpki_v6 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prefix          TEXT NOT NULL,
    asn             INTEGER NOT NULL,
    max_length      INTEGER,
    status          TEXT NOT NULL,
    ta              TEXT,
    network_start_hex TEXT NOT NULL,
    network_end_hex   TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'rpki',
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rpki_v6_range ON rpki_v6(network_start_hex, network_end_hex);

-- ============================================================
-- Cloud Ranges IPv6
-- ============================================================
CREATE TABLE IF NOT EXISTS cloud_ranges_v6 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL,
    network         TEXT NOT NULL,
    network_start_hex TEXT NOT NULL,
    network_end_hex   TEXT NOT NULL,
    region          TEXT,
    service         TEXT,
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cloud_v6_range ON cloud_ranges_v6(network_start_hex, network_end_hex);

-- ============================================================
-- Threat Intel IPv6
-- ============================================================
CREATE TABLE IF NOT EXISTS threat_intel_v6 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    network         TEXT NOT NULL,
    network_start_hex TEXT NOT NULL,
    network_end_hex   TEXT NOT NULL,
    threat_type     TEXT NOT NULL,
    list_name       TEXT NOT NULL,
    severity        TEXT DEFAULT 'medium',
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threat_v6_range ON threat_intel_v6(network_start_hex, network_end_hex);
CREATE INDEX IF NOT EXISTS idx_threat_v6_type ON threat_intel_v6(threat_type);

-- ============================================================
-- RIR IPv6 (separate from IPv4 to keep clean)
-- ============================================================
CREATE TABLE IF NOT EXISTS rir_delegated_v6 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rir             TEXT NOT NULL,
    country_code    TEXT,
    network         TEXT NOT NULL,
    network_start_hex TEXT NOT NULL,
    network_end_hex   TEXT NOT NULL,
    prefix_length   INTEGER,
    date_allocated  TEXT,
    status          TEXT,
    source          TEXT NOT NULL DEFAULT 'rir_delegated',
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rir_v6_range ON rir_delegated_v6(network_start_hex, network_end_hex);
"""


def init_v6_tables(db_path: str) -> None:
    """初始化IPv6相关表"""
    import sqlite3, os
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    from utils.schema import BUSY_TIMEOUT_MS, CONNECT_TIMEOUT_S
    conn = sqlite3.connect(db_path, timeout=CONNECT_TIMEOUT_S)
    try:
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.executescript(SCHEMA_V6_SQL)
        conn.commit()
    finally:
        conn.close()


def ipv6_to_hex(ip_str: str) -> str:
    """IPv6地址转32字符hex（左补0）"""
    import ipaddress
    addr = ipaddress.IPv6Address(ip_str)
    return f"{int(addr):032x}"


def ipv6_network_to_hex_range(cidr: str) -> tuple:
    """IPv6 CIDR -> (start_hex, end_hex)"""
    import ipaddress
    net = ipaddress.IPv6Network(cidr, strict=False)
    return (
        f"{int(net.network_address):032x}",
        f"{int(net.broadcast_address):032x}",
    )
