"""
NetworkIntel - 查询引擎
核心IP情报查询逻辑，所有查询走此模块
支持：单IP、批量IP、CIDR块
"""

import ipaddress
import json
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from functools import lru_cache

from utils.ip_utils import ip_to_int, check_special_ip, normalize_ip, parse_ip_input
from utils.schema import get_connection
from utils.config_loader import get_config
from utils.logger import get_logger

logger = get_logger("networkintel")


# ── 风险等级计算 ──────────────────────────────────────────────

def calculate_risk(result: dict) -> str:
    """
    根据查询结果计算风险等级
    返回：critical / high / medium / low / info / clean
    """
    threats = result.get("threats", [])
    if not threats:
        pass
    else:
        severities = [t.get("severity", "medium") for t in threats]
        if "critical" in severities:
            return "critical"
        if "high" in severities:
            return "high"
        if "medium" in severities:
            return "medium"
        return "low"

    if result.get("is_tor"):
        return "high"
    if result.get("is_vpn"):
        return "medium"
    if result.get("rpki", {}).get("status") == "invalid":
        return "medium"
    if result.get("cloud_provider"):
        return "info"
    return "clean"


# ── 主查询函数 ────────────────────────────────────────────────

def query_ip(ip_str: str, db_path: str = None) -> dict:
    """
    查询单个IP的完整情报
    返回结构化字典，包含所有维度的信息
    """
    cfg = get_config()
    db = db_path or cfg.db_path
    ip_str = ip_str.strip()

    # 1. 验证IP
    normalized = normalize_ip(ip_str)
    if not normalized:
        return {"error": f"无效IP地址: {ip_str}", "ip": ip_str}

    # Check IP version
    from utils.ip_utils import get_ip_version
    is_ipv6 = (get_ip_version(normalized) == 6)

    # 2. 检查特殊IP
    special = check_special_ip(normalized)
    if special:
        return {
            "ip": normalized,
            "is_special": True,
            "special_category": special["category"],
            "special_description": special["description"],
            "special_network": special["network"],
            "risk_level": "clean",
            "queried_at": datetime.now().isoformat(),
        }

    conn = get_connection(db)

    try:
        result = {
            "ip": normalized,
            "is_special": False,
            "ip_version": 6 if is_ipv6 else 4,
            "queried_at": datetime.now().isoformat(),
        }

        if is_ipv6:
            import ipaddress
            ip_hex = f"{int(ipaddress.IPv6Address(normalized)):032x}"
            result["geoip"] = _query_geoip_v6(conn, ip_hex)
            result["asn"]   = _query_asn_v6(conn, ip_hex)
            result["rpki"]  = _query_rpki_v6(conn, ip_hex, result.get("asn", {}).get("asn") if result.get("asn") else None)
            result["rir"]   = _query_rir_v6(conn, ip_hex)
            result["cloud"] = _query_cloud_v6(conn, ip_hex)
            result["cloud_provider"] = result["cloud"]["provider"] if result["cloud"] else None
            tor_vpn = _query_tor_vpn_v6(conn, ip_hex)
            result["is_tor"] = tor_vpn["is_tor"]
            result["is_vpn"] = tor_vpn["is_vpn"]
            result["threats"] = _query_threats_v6(conn, ip_hex)
        else:
            ip_int = ip_to_int(normalized)
            result["geoip"] = _query_geoip(conn, ip_int)
            result["asn"] = _query_asn(conn, ip_int)
            result["rpki"] = _query_rpki(conn, ip_int, (result.get("asn") or {}).get("asn"))
            result["rir"] = _query_rir(conn, ip_int)
            result["cloud"] = _query_cloud(conn, ip_int)
            result["cloud_provider"] = result["cloud"]["provider"] if result["cloud"] else None
            tor_vpn = _query_tor_vpn(conn, ip_int)
            result["is_tor"] = tor_vpn["is_tor"]
            result["is_vpn"] = tor_vpn["is_vpn"]
            result["threats"] = _query_threats(conn, ip_int)

        # 10. PeeringDB（如果有ASN）
        asn_num = (result.get("asn") or {}).get("asn")
        if asn_num:
            result["peeringdb"] = _query_peeringdb(conn, asn_num)

        # 11. WHOIS缓存
        result["whois"] = _query_whois(conn, normalized)

        # 12. 风险等级
        result["risk_level"] = calculate_risk(result)

        # 13. 保存查询历史
        _save_history(conn, normalized, "single", result)

        return result

    finally:
        conn.close()


def query_batch(ip_list: List[str], db_path: str = None,
                progress_callback=None) -> List[dict]:
    """
    批量查询IP列表
    progress_callback(current: int, total: int) 可选进度回调
    """
    cfg = get_config()
    db = db_path or cfg.db_path
    results = []
    total = len(ip_list)
    cache = {}  # session内去重缓存

    for i, ip_str in enumerate(ip_list):
        if progress_callback:
            progress_callback(i + 1, total)

        ip_str = ip_str.strip()
        if not ip_str:
            continue

        # 缓存去重
        if ip_str in cache:
            results.append(cache[ip_str])
            continue

        result = query_ip(ip_str, db)
        cache[ip_str] = result
        results.append(result)

    return results


# ── 各维度子查询 ──────────────────────────────────────────────

def _query_geoip(conn: sqlite3.Connection, ip_int: int) -> Optional[dict]:
    row = conn.execute("""
        SELECT country_code, country_name, region, city,
               latitude, longitude, accuracy_radius, network, network_end_int
        FROM geoip
        WHERE network_start_int <= ?
        ORDER BY network_start_int DESC
        LIMIT 1
    """, (ip_int,)).fetchone()
    if row and row["network_end_int"] < ip_int:
        row = None

    if not row:
        return None
    return {
        "country_code":   row["country_code"],
        "country_name":   row["country_name"],
        "region":         row["region"],
        "city":           row["city"],
        "latitude":       row["latitude"],
        "longitude":      row["longitude"],
        "accuracy_radius": row["accuracy_radius"],
        "network":        row["network"],
    }


def _query_asn(conn: sqlite3.Connection, ip_int: int) -> Optional[dict]:
    row = conn.execute("""
        SELECT asn, as_name, country_code, network
        FROM asn_info
        WHERE network_start_int <= ? AND network_end_int >= ?
        ORDER BY (network_end_int - network_start_int) ASC
        LIMIT 1
    """, (ip_int, ip_int)).fetchone()

    if not row:
        return None
    return {
        "asn":          row["asn"],
        "as_name":      row["as_name"],
        "country_code": row["country_code"],
        "network":      row["network"],
    }


def _query_rpki(conn: sqlite3.Connection, ip_int: int,
                asn: Optional[int] = None) -> dict:
    """查询RPKI状态，匹配前缀+ASN"""
    row = conn.execute("""
        SELECT prefix, asn, max_length, status, ta
        FROM rpki
        WHERE network_start_int <= ? AND network_end_int >= ?
        ORDER BY (network_end_int - network_start_int) ASC
        LIMIT 1
    """, (ip_int, ip_int)).fetchone()

    if not row:
        return {"status": "not-found", "prefix": None, "asn": None}

    # 验证ASN是否匹配
    status = row["status"]
    if asn and row["asn"] != asn:
        status = "invalid"  # 前缀存在但ASN不匹配

    return {
        "status":     status,
        "prefix":     row["prefix"],
        "asn":        row["asn"],
        "max_length": row["max_length"],
        "ta":         row["ta"],
    }


def _query_rir(conn: sqlite3.Connection, ip_int: int) -> Optional[dict]:
    row = conn.execute("""
        SELECT rir, country_code, ip_type, network, status, date_allocated
        FROM rir_delegated
        WHERE network_start_int <= ? AND network_end_int >= ?
        ORDER BY (network_end_int - network_start_int) ASC
        LIMIT 1
    """, (ip_int, ip_int)).fetchone()

    if not row:
        return None
    return {
        "rir":            row["rir"].upper() if row["rir"] else "",
        "country_code":   row["country_code"],
        "ip_type":        row["ip_type"],
        "network":        row["network"],
        "status":         row["status"],
        "date_allocated": row["date_allocated"],
    }


def _query_cloud(conn: sqlite3.Connection, ip_int: int) -> Optional[dict]:
    row = conn.execute("""
        SELECT provider, network, region, service
        FROM cloud_ranges
        WHERE network_start_int <= ? AND network_end_int >= ?
        ORDER BY (network_end_int - network_start_int) ASC
        LIMIT 1
    """, (ip_int, ip_int)).fetchone()

    if not row:
        return None
    return {
        "provider": row["provider"],
        "network":  row["network"],
        "region":   row["region"],
        "service":  row["service"],
    }


def _query_tor_vpn(conn: sqlite3.Connection, ip_int: int) -> dict:
    rows = conn.execute("""
        SELECT threat_type, list_name
        FROM threat_intel
        WHERE network_start_int <= ? AND network_end_int >= ?
          AND threat_type IN ('tor', 'vpn')
    """, (ip_int, ip_int)).fetchall()

    is_tor = any(r["threat_type"] == "tor" for r in rows)
    is_vpn = any(r["threat_type"] == "vpn" for r in rows)
    return {"is_tor": is_tor, "is_vpn": is_vpn}


def _query_threats(conn: sqlite3.Connection, ip_int: int) -> List[dict]:
    rows = conn.execute("""
        SELECT threat_type, list_name, severity, snapshot_date
        FROM threat_intel
        WHERE network_start_int <= ? AND network_end_int >= ?
          AND threat_type NOT IN ('tor', 'vpn')
        ORDER BY severity DESC
    """, (ip_int, ip_int)).fetchall()

    return [
        {
            "threat_type": r["threat_type"],
            "list_name":   r["list_name"],
            "severity":    r["severity"],
            "date":        r["snapshot_date"],
        }
        for r in rows
    ]


def _query_peeringdb(conn: sqlite3.Connection, asn: int) -> Optional[dict]:
    row = conn.execute("""
        SELECT name, aka, website, info_type,
               info_prefixes4, info_prefixes6, policy_general, ix_list
        FROM peeringdb WHERE asn = ? LIMIT 1
    """, (asn,)).fetchone()

    if not row:
        return None
    try:
        ix_list = json.loads(row["ix_list"] or "[]")
    except Exception:
        ix_list = []
    return {
        "name":           row["name"],
        "aka":            row["aka"],
        "website":        row["website"],
        "info_type":      row["info_type"],
        "info_prefixes4": row["info_prefixes4"],
        "info_prefixes6": row["info_prefixes6"],
        "policy_general": row["policy_general"],
        "ix_list":        ix_list,
    }


def _query_whois(conn: sqlite3.Connection, ip_str: str) -> Optional[dict]:
    row = conn.execute("""
        SELECT org_name, country, abuse_email, registered_date, queried_at
        FROM whois_cache WHERE query = ? LIMIT 1
    """, (ip_str,)).fetchone()

    if not row:
        return None
    return {
        "org_name":        row["org_name"],
        "country":         row["country"],
        "abuse_email":     row["abuse_email"],
        "registered_date": row["registered_date"],
        "cached_at":       row["queried_at"],
    }


def _save_history(conn: sqlite3.Connection, ip: str,
                  query_type: str, result: dict) -> None:
    """保存查询记录到历史表"""
    summary = {
        "country": result.get("geoip", {}).get("country_code") if result.get("geoip") else None,
        "asn":     result.get("asn", {}).get("asn") if result.get("asn") else None,
        "cloud":   result.get("cloud_provider"),
        "is_tor":  result.get("is_tor", False),
        "is_vpn":  result.get("is_vpn", False),
        "threats": len(result.get("threats", [])),
    }
    try:
        conn.execute("""
            INSERT INTO query_history (query_input, query_type, result_summary, risk_level)
            VALUES (?, ?, ?, ?)
        """, (ip, query_type, json.dumps(summary), result.get("risk_level", "clean")))
        conn.commit()
    except Exception as e:
        # 历史记录写失败不影响主流程；但不再静默——记 debug 便于排查，
        # 并区分锁冲突（并发更新时该 INSERT 可能撞锁）与其它错误。
        from utils.schema import is_locked_error
        if is_locked_error(e):
            logger.debug(f"[query_history] 写历史撞锁（database is locked），已跳过: {e}")
        else:
            logger.debug(f"[query_history] 写历史失败，已跳过: {e}")




# ── IPv6 子查询函数 ──────────────────────────────────────────

def _query_geoip_v6(conn, ip_hex):
    row = conn.execute("""
        SELECT country_code, country_name, region, city, latitude, longitude,
               accuracy_radius, network
        FROM geoip_v6
        WHERE network_start_hex <= ? AND network_end_hex >= ?
        ORDER BY length(network_end_hex) - length(network_start_hex) ASC
        LIMIT 1
    """, (ip_hex, ip_hex)).fetchone()
    return dict(row) if row else None


def _query_asn_v6(conn, ip_hex):
    row = conn.execute("""
        SELECT asn, as_name, country_code, network
        FROM asn_info_v6
        WHERE network_start_hex <= ? AND network_end_hex >= ?
        LIMIT 1
    """, (ip_hex, ip_hex)).fetchone()
    return dict(row) if row else None


def _query_rpki_v6(conn, ip_hex, asn=None):
    row = conn.execute("""
        SELECT prefix, asn, max_length, status, ta
        FROM rpki_v6
        WHERE network_start_hex <= ? AND network_end_hex >= ?
        LIMIT 1
    """, (ip_hex, ip_hex)).fetchone()
    if not row:
        return {"status": "not-found", "prefix": None, "asn": None}
    status = row["status"]
    if asn and row["asn"] != asn:
        status = "invalid"
    return {"status": status, "prefix": row["prefix"], "asn": row["asn"],
            "max_length": row["max_length"], "ta": row["ta"]}


def _query_rir_v6(conn, ip_hex):
    row = conn.execute("""
        SELECT rir, country_code, network, status, date_allocated
        FROM rir_delegated_v6
        WHERE network_start_hex <= ? AND network_end_hex >= ?
        LIMIT 1
    """, (ip_hex, ip_hex)).fetchone()
    if not row:
        return None
    return {"rir": row["rir"].upper() if row["rir"] else "",
            "country_code": row["country_code"], "ip_type": "ipv6",
            "network": row["network"], "status": row["status"],
            "date_allocated": row["date_allocated"]}


def _query_cloud_v6(conn, ip_hex):
    row = conn.execute("""
        SELECT provider, network, region, service
        FROM cloud_ranges_v6
        WHERE network_start_hex <= ? AND network_end_hex >= ?
        LIMIT 1
    """, (ip_hex, ip_hex)).fetchone()
    return dict(row) if row else None


def _query_tor_vpn_v6(conn, ip_hex):
    rows = conn.execute("""
        SELECT threat_type FROM threat_intel_v6
        WHERE network_start_hex <= ? AND network_end_hex >= ?
          AND threat_type IN ('tor','vpn')
    """, (ip_hex, ip_hex)).fetchall()
    return {"is_tor": any(r["threat_type"] == "tor" for r in rows),
            "is_vpn": any(r["threat_type"] == "vpn" for r in rows)}


def _query_threats_v6(conn, ip_hex):
    rows = conn.execute("""
        SELECT threat_type, list_name, severity, snapshot_date
        FROM threat_intel_v6
        WHERE network_start_hex <= ? AND network_end_hex >= ?
          AND threat_type NOT IN ('tor','vpn')
        ORDER BY severity DESC
    """, (ip_hex, ip_hex)).fetchall()
    return [{"threat_type": r["threat_type"], "list_name": r["list_name"],
             "severity": r["severity"], "date": r["snapshot_date"]} for r in rows]

def get_source_status(db_path: str = None) -> List[dict]:
    """获取所有数据源状态（用于TUI数据源页）"""
    cfg = get_config()
    db = db_path or cfg.db_path
    conn = get_connection(db)
    try:
        rows = conn.execute("""
            SELECT source, description, last_updated, status,
                   record_count, error_message, schedule, enabled,
                   snapshot_category, updated_at
            FROM source_meta ORDER BY source
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_query_history(limit: int = 50, db_path: str = None) -> List[dict]:
    """获取查询历史"""
    cfg = get_config()
    db = db_path or cfg.db_path
    conn = get_connection(db)
    try:
        rows = conn.execute("""
            SELECT query_input, query_type, result_summary, risk_level, queried_at
            FROM query_history
            ORDER BY queried_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["result_summary"] = json.loads(item["result_summary"] or "{}")
            except Exception:
                item["result_summary"] = {}
            result.append(item)
        return result
    finally:
        conn.close()
