"""
NetworkIntel - SQLite Schema
所有表含 source / valid_from / valid_until / snapshot_date 标准字段
新增数据源只需在对应插件里调用已有表或创建新表，不需要改此文件核心结构
"""

import os
import sqlite3

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-64000;
PRAGMA temp_store=MEMORY;
PRAGMA foreign_keys=ON;

-- ============================================================
-- 元数据：数据源状态追踪
-- ============================================================
CREATE TABLE IF NOT EXISTS source_meta (
    source          TEXT PRIMARY KEY,
    description     TEXT,
    last_updated    TEXT,          -- ISO8601
    next_update     TEXT,          -- ISO8601
    record_count    INTEGER DEFAULT 0,
    file_size_bytes INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'never',  -- never/ok/error/stale
    error_message   TEXT,
    schedule        TEXT,
    enabled         INTEGER DEFAULT 1,
    snapshot_category TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- GeoIP：城市级地理信息
-- ============================================================
CREATE TABLE IF NOT EXISTS geoip (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    network         TEXT NOT NULL,      -- CIDR，如 1.1.1.0/24
    network_start   TEXT NOT NULL,      -- 起始IP（点分十进制，便于范围查询）
    network_end     TEXT NOT NULL,      -- 结束IP
    network_start_int INTEGER NOT NULL, -- 起始IP整数（快速范围查询）
    network_end_int   INTEGER NOT NULL,
    country_code    TEXT,
    country_name    TEXT,
    region          TEXT,
    city            TEXT,
    latitude        REAL,
    longitude       REAL,
    accuracy_radius INTEGER,
    -- 标准字段
    source          TEXT NOT NULL DEFAULT 'geoip',
    valid_from      TEXT,
    valid_until     TEXT,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_geoip_range ON geoip(network_start_int, network_end_int);
CREATE INDEX IF NOT EXISTS idx_geoip_country ON geoip(country_code);
CREATE INDEX IF NOT EXISTS idx_geoip_snapshot ON geoip(snapshot_date);

-- ============================================================
-- ASN：自治系统信息
-- ============================================================
CREATE TABLE IF NOT EXISTS asn_info (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asn             INTEGER NOT NULL,
    as_name         TEXT,
    country_code    TEXT,
    network         TEXT,
    network_start_int INTEGER NOT NULL,
    network_end_int   INTEGER NOT NULL,
    -- 标准字段
    source          TEXT NOT NULL DEFAULT 'ip2asn',
    valid_from      TEXT,
    valid_until     TEXT,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_asn_range ON asn_info(network_start_int, network_end_int);
CREATE INDEX IF NOT EXISTS idx_asn_number ON asn_info(asn);
CREATE INDEX IF NOT EXISTS idx_asn_snapshot ON asn_info(snapshot_date);

-- ============================================================
-- RPKI：路由起源验证
-- ============================================================
CREATE TABLE IF NOT EXISTS rpki (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prefix          TEXT NOT NULL,
    asn             INTEGER NOT NULL,
    max_length      INTEGER,
    status          TEXT NOT NULL,   -- valid / invalid / not-found
    ta              TEXT,            -- Trust Anchor，如 apnic
    network_start_int INTEGER NOT NULL,
    network_end_int   INTEGER NOT NULL,
    -- 标准字段
    source          TEXT NOT NULL DEFAULT 'rpki',
    valid_from      TEXT,
    valid_until     TEXT,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rpki_range ON rpki(network_start_int, network_end_int);
CREATE INDEX IF NOT EXISTS idx_rpki_asn ON rpki(asn);
CREATE INDEX IF NOT EXISTS idx_rpki_status ON rpki(status);

-- ============================================================
-- RIR：地区互联网注册机构分配记录
-- ============================================================
CREATE TABLE IF NOT EXISTS rir_delegated (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rir             TEXT NOT NULL,   -- arin/ripe/apnic/lacnic/afrinic
    country_code    TEXT,
    ip_type         TEXT,            -- ipv4 / ipv6
    network         TEXT NOT NULL,
    network_start_int INTEGER NOT NULL,
    network_end_int   INTEGER NOT NULL,
    prefix_length   INTEGER,
    value           INTEGER,         -- 地址数量
    date_allocated  TEXT,
    status          TEXT,            -- allocated/assigned/available/reserved
    -- 标准字段
    source          TEXT NOT NULL DEFAULT 'rir_delegated',
    valid_from      TEXT,
    valid_until     TEXT,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rir_range ON rir_delegated(network_start_int, network_end_int);
CREATE INDEX IF NOT EXISTS idx_rir_country ON rir_delegated(country_code);
CREATE INDEX IF NOT EXISTS idx_rir_rir ON rir_delegated(rir);

-- ============================================================
-- 云服务商 IP 段
-- ============================================================
CREATE TABLE IF NOT EXISTS cloud_ranges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL,   -- aws/azure/gcp/cloudflare/hetzner/vultr
    network         TEXT NOT NULL,
    network_start_int INTEGER NOT NULL,
    network_end_int   INTEGER NOT NULL,
    region          TEXT,
    service         TEXT,            -- EC2/S3等AWS服务名
    -- 标准字段
    source          TEXT NOT NULL,
    valid_from      TEXT,
    valid_until     TEXT,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cloud_range ON cloud_ranges(network_start_int, network_end_int);
CREATE INDEX IF NOT EXISTS idx_cloud_provider ON cloud_ranges(provider);

-- ============================================================
-- 威胁情报：统一表（Tor/VPN/Spamhaus/FireHOL/Abuse/ET）
-- ============================================================
CREATE TABLE IF NOT EXISTS threat_intel (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    network         TEXT NOT NULL,   -- 单IP或CIDR
    network_start_int INTEGER NOT NULL,
    network_end_int   INTEGER NOT NULL,
    threat_type     TEXT NOT NULL,   -- tor/vpn/spam/botnet/malware/scanner/etc
    list_name       TEXT NOT NULL,   -- 来源列表名，如 spamhaus_drop
    severity        TEXT DEFAULT 'medium',  -- low/medium/high/critical
    -- 标准字段
    source          TEXT NOT NULL,
    valid_from      TEXT,
    valid_until     TEXT,
    snapshot_date   TEXT NOT NULL,
    extra_json      TEXT             -- 预留扩展字段，存JSON
);
CREATE INDEX IF NOT EXISTS idx_threat_range ON threat_intel(network_start_int, network_end_int);
CREATE INDEX IF NOT EXISTS idx_threat_type ON threat_intel(threat_type);
CREATE INDEX IF NOT EXISTS idx_threat_list ON threat_intel(list_name);
CREATE INDEX IF NOT EXISTS idx_threat_snapshot ON threat_intel(snapshot_date);

-- ============================================================
-- WHOIS 本地缓存
-- ============================================================
CREATE TABLE IF NOT EXISTS whois_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query           TEXT NOT NULL UNIQUE,  -- IP或ASN
    raw_text        TEXT,
    org_name        TEXT,
    country         TEXT,
    abuse_email     TEXT,
    registered_date TEXT,
    queried_at      TEXT NOT NULL,
    -- 标准字段
    source          TEXT NOT NULL DEFAULT 'whois',
    valid_from      TEXT,
    valid_until     TEXT,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_whois_query ON whois_cache(query);

-- ============================================================
-- PeeringDB（可选插件）
-- ============================================================
CREATE TABLE IF NOT EXISTS peeringdb (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asn             INTEGER NOT NULL,
    name            TEXT,
    aka             TEXT,
    website         TEXT,
    info_type       TEXT,            -- Content/NSP/Enterprise等
    info_prefixes4  INTEGER,
    info_prefixes6  INTEGER,
    policy_general  TEXT,
    ix_list         TEXT,            -- JSON：接入的IXP列表
    -- 标准字段
    source          TEXT NOT NULL DEFAULT 'peeringdb',
    valid_from      TEXT,
    valid_until     TEXT,
    snapshot_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_peeringdb_asn ON peeringdb(asn);

-- ============================================================
-- 查询历史（本地持久化）
-- ============================================================
CREATE TABLE IF NOT EXISTS query_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_input     TEXT NOT NULL,
    query_type      TEXT NOT NULL,   -- single/batch
    result_summary  TEXT,            -- JSON摘要
    risk_level      TEXT,
    queried_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_queried ON query_history(queried_at DESC);

-- ============================================================
-- 批量查询任务记录
-- ============================================================
CREATE TABLE IF NOT EXISTS batch_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL UNIQUE,
    input_file      TEXT,
    total_ips       INTEGER DEFAULT 0,
    processed_ips   INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'pending',  -- pending/running/done/error
    html_report     TEXT,
    csv_report      TEXT,
    started_at      TEXT,
    finished_at     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# ============================================================
# 统一连接策略（v0.3.0 SQLite 写入串行化）
# ============================================================
# 所有主库连接都必须经过下面的工厂获取，统一应用：
#   - timeout / PRAGMA busy_timeout：锁冲突时等待重试而非立即失败
#   - PRAGMA journal_mode=WAL：读写分离（失败时优雅回退，不阻断启动）
#   - PRAGMA synchronous=NORMAL / foreign_keys=ON
# 读连接与写连接分开：写连接 isolation_level=None（autocommit），
# 以便由调用方显式 `BEGIN IMMEDIATE ... COMMIT/ROLLBACK` 控制事务边界。
# 连接**不跨线程共享**：每个线程各自 connect / close。

# busy_timeout（毫秒）：写者遇锁最多等待这么久再放弃。可用环境变量覆盖（便于测试）。
# 以下取值走函数动态读取环境变量，使测试可在 import 之后临时收紧超时，无需关心导入顺序。
_DEFAULT_BUSY_TIMEOUT_MS = 30000
_DEFAULT_LOCK_RETRIES = 3
_DEFAULT_LOCK_BACKOFF_S = 0.5


def busy_timeout_ms() -> int:
    return int(os.environ.get("NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS",
                              str(_DEFAULT_BUSY_TIMEOUT_MS)))


def connect_timeout_s() -> float:
    return max(0.2, busy_timeout_ms() / 1000.0)


def lock_retries() -> int:
    return int(os.environ.get("NETWORKINTEL_SQLITE_LOCK_RETRIES",
                              str(_DEFAULT_LOCK_RETRIES)))


def lock_backoff_s() -> float:
    return float(os.environ.get("NETWORKINTEL_SQLITE_LOCK_BACKOFF_S",
                                str(_DEFAULT_LOCK_BACKOFF_S)))


# 向后兼容常量（评估一次）；动态路径请用上面的函数。
BUSY_TIMEOUT_MS = busy_timeout_ms()
CONNECT_TIMEOUT_S = connect_timeout_s()


def is_locked_error(exc: BaseException) -> bool:
    """判断异常是否为 SQLite 锁冲突（database is locked / busy）。"""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return "database is locked" in msg or "database is busy" in msg


def _apply_common_pragmas(conn) -> None:
    """应用所有连接共用的 PRAGMA；WAL 失败时优雅回退并告警。"""
    conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms()}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    # WAL 通过返回值判断是否生效（PRAGMA 不抛异常而是返回实际模式）。
    try:
        row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        mode = (row[0] if row else "") or ""
        if str(mode).lower() != "wal":
            _warn_wal_fallback(str(mode))
    except sqlite3.OperationalError as e:
        # 极端情况下（如某些网络盘）设置 WAL 会抛错：记录告警但不阻断，
        # busy_timeout 仍已生效，退回默认 journal 模式继续工作。
        _warn_wal_fallback(f"error: {e}")


def _warn_wal_fallback(mode: str) -> None:
    try:
        from utils.logger import get_logger
        get_logger("networkintel").warning(
            f"[sqlite] WAL 未生效，已回退到 journal_mode={mode}；"
            f"busy_timeout={BUSY_TIMEOUT_MS}ms 仍已应用。"
        )
    except Exception:
        pass


def init_db(db_path: str) -> None:
    """初始化数据库，创建所有表和索引"""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=connect_timeout_s())
    try:
        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms()}")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def connect_read(db_path: str):
    """只读/一般查询连接。带 busy_timeout 与 WAL，row_factory=Row。"""
    conn = sqlite3.connect(db_path, timeout=connect_timeout_s(),
                           check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _apply_common_pragmas(conn)
    return conn


def connect_write(db_path: str):
    """
    写连接：isolation_level=None（autocommit）以便调用方显式控制事务
    （BEGIN IMMEDIATE ... COMMIT/ROLLBACK）。带 busy_timeout 与 WAL。
    """
    conn = sqlite3.connect(db_path, timeout=connect_timeout_s(),
                           check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    _apply_common_pragmas(conn)
    return conn


def get_connection(db_path: str):
    """向后兼容别名：只读/一般查询连接（等价 connect_read）。"""
    return connect_read(db_path)
