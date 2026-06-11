# -*- coding: utf-8 -*-
"""
NetworkIntel - GUI 扩展模块
新增功能：
  - DashboardBar      :  查询页顶部数据库统计条
  - NetworkPage       :  网络页（ASN 反查 / 国家统计 / CIDR 段查询）
  - ThreatLibraryPage :  威胁库浏览页

设计原则：
  - 与 main_gui.py 解耦，作为可插拔扩展加载
  - 后端零改动：只读 SQLite（utils.schema.get_connection）+ 读 config
"""
from __future__ import annotations

import csv
import ipaddress
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFrame, QTabWidget, QComboBox, QMessageBox, QFileDialog, QSpinBox,
    QPlainTextEdit, QSizePolicy
)

# 后端
from utils.schema import get_connection
from utils.config_loader import get_config


# ── 风险颜色（与 main_gui 一致） ──────────────────────────────
RISK_COLORS = {
    "critical": "#DC2626",
    "high":     "#EA580C",
    "medium":   "#D97706",
    "low":      "#2563EB",
    "info":     "#2563EB",
    "clean":    "#16A34A",
}
ACCENT = "#2563EB"


# ╔════════════════════════════════════════════════════════════╗
# ║                      工具函数                              ║
# ╚════════════════════════════════════════════════════════════╝

def db_conn() -> sqlite3.Connection:
    return get_connection(get_config().db_path)


def ip_range_from_cidr(cidr: str) -> tuple[int, int, int]:
    """CIDR -> (start_int, end_int, version)。失败抛 ValueError。"""
    net = ipaddress.ip_network(cidr.strip(), strict=False)
    return int(net.network_address), int(net.broadcast_address), net.version


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def make_card(title: str, parent=None) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame(parent)
    card.setObjectName("Card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 14, 18, 14)
    lay.setSpacing(8)
    if title:
        t = QLabel(title.upper())
        t.setObjectName("CardTitle")
        lay.addWidget(t)
    return card, lay


# ╔════════════════════════════════════════════════════════════╗
# ║                    DashboardBar                            ║
# ║      查询页顶部的数据库统计小条                            ║
# ╚════════════════════════════════════════════════════════════╝

class DashboardWorker(QThread):
    """异步统计：避免首次打开查询页时卡住"""
    done = Signal(dict)

    def run(self):
        stats = {"asn": 0, "geoip": 0, "threats": 0, "cloud": 0, "rpki": 0}
        try:
            conn = db_conn()
            try:
                for key, sql in [
                    ("asn",     "SELECT COUNT(*) FROM asn_info"),
                    ("geoip",   "SELECT COUNT(*) FROM geoip"),
                    ("threats", "SELECT COUNT(*) FROM threat_intel"),
                    ("cloud",   "SELECT COUNT(*) FROM cloud_ranges"),
                    ("rpki",    "SELECT COUNT(*) FROM rpki"),
                ]:
                    try:
                        stats[key] = conn.execute(sql).fetchone()[0] or 0
                    except sqlite3.OperationalError:
                        stats[key] = 0
            finally:
                conn.close()
        except Exception:
            pass
        self.done.emit(stats)


class DashboardBar(QFrame):
    """紧凑的数据库统计条，挂在 QueryPage 顶部"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMaximumHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 10, 18, 10)
        lay.setSpacing(28)

        self.cells: dict[str, tuple[QLabel, QLabel]] = {}
        for key, label in [
            ("asn", "ASN 记录"),
            ("geoip", "地理段"),
            ("rpki", "RPKI"),
            ("cloud", "云段"),
            ("threats", "威胁"),
        ]:
            box = QVBoxLayout()
            box.setSpacing(0)
            t = QLabel(label.upper())
            t.setObjectName("CardTitle")
            t.setStyleSheet("color:#9CA3AF; font-size:10px; font-weight:600; letter-spacing:0.5px;")
            v = QLabel("—")
            v.setStyleSheet(f"color:{ACCENT}; font-size:18px; font-weight:600;")
            box.addWidget(t)
            box.addWidget(v)
            wrap = QWidget()
            wrap.setLayout(box)
            lay.addWidget(wrap)
            self.cells[key] = (t, v)

        lay.addStretch(1)
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setMinimumWidth(64)
        self.refresh_btn.setMaximumWidth(64)
        self.refresh_btn.setText('⟳ 刷新')
        self.refresh_btn.setToolTip("刷新统计")
        self.refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(self.refresh_btn)

        self._worker: Optional[DashboardWorker] = None
        # 启动延迟刷新（避免阻塞窗口显示）
        QTimer.singleShot(500, self.refresh)

    def refresh(self):
        if self._worker and self._worker.isRunning():
            return
        self._worker = DashboardWorker()
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, stats: dict):
        for key, (_, v) in self.cells.items():
            v.setText(fmt_int(stats.get(key, 0)))


# ╔════════════════════════════════════════════════════════════╗
# ║                   ASN 反查 子页                            ║
# ╚════════════════════════════════════════════════════════════╝

class ASNLookupWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, asn: int):
        super().__init__()
        self.asn = asn

    def run(self):
        try:
            conn = db_conn()
            try:
                # 基本信息（取最新快照）
                meta_row = conn.execute("""
                    SELECT as_name, country_code, COUNT(*) AS prefix_count,
                           SUM(network_end_int - network_start_int + 1) AS ip_count,
                           MAX(snapshot_date) AS snap
                    FROM asn_info WHERE asn = ?
                    GROUP BY asn
                """, (self.asn,)).fetchone()

                # 前缀列表
                prefixes = conn.execute("""
                    SELECT network, network_start_int, network_end_int, country_code, snapshot_date
                    FROM asn_info WHERE asn = ?
                    ORDER BY network_start_int
                    LIMIT 5000
                """, (self.asn,)).fetchall()

                # PeeringDB（如果存在）
                pdb = None
                try:
                    pdb = conn.execute("""
                        SELECT name, aka, website, info_type, info_prefixes4, info_prefixes6, policy_general
                        FROM peeringdb WHERE asn = ? LIMIT 1
                    """, (self.asn,)).fetchone()
                except sqlite3.OperationalError:
                    pass

                # 该 ASN 关联的 RPKI ROA 数量
                rpki_count = 0
                try:
                    rpki_count = conn.execute(
                        "SELECT COUNT(*) FROM rpki WHERE asn = ?", (self.asn,)
                    ).fetchone()[0]
                except sqlite3.OperationalError:
                    pass

                # 该 ASN 下被威胁标记的前缀数（粗略统计：与威胁段有重叠的 ASN 前缀）
                threat_overlap = 0
                try:
                    threat_overlap = conn.execute("""
                        SELECT COUNT(DISTINCT a.id)
                        FROM asn_info a
                        JOIN threat_intel t
                          ON t.network_start_int <= a.network_end_int
                         AND t.network_end_int   >= a.network_start_int
                        WHERE a.asn = ?
                    """, (self.asn,)).fetchone()[0] or 0
                except Exception:
                    pass

                self.done.emit({
                    "asn":   self.asn,
                    "meta":  dict(meta_row) if meta_row else None,
                    "prefixes": [dict(r) for r in prefixes],
                    "peeringdb": dict(pdb) if pdb else None,
                    "rpki_count": rpki_count,
                    "threat_overlap": threat_overlap,
                })
            finally:
                conn.close()
        except Exception as e:
            self.failed.emit(f"{e}\n{traceback.format_exc()}")


class ASNLookupTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: Optional[ASNLookupWorker] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 14, 0, 0)
        root.setSpacing(12)

        # 输入行
        row = QHBoxLayout()
        row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setObjectName("BigInput")
        self.input.setPlaceholderText("输入 ASN，例如  13335  或  AS13335")
        self.input.returnPressed.connect(self._run)
        self.btn = QPushButton("反查")
        self.btn.setObjectName("Primary")
        self.btn.setMinimumHeight(44)
        self.btn.setMinimumWidth(100)
        self.btn.clicked.connect(self._run)
        row.addWidget(self.input, 1)
        row.addWidget(self.btn)
        root.addLayout(row)

        # 摘要卡
        self.meta_card, self.meta_layout = make_card("ASN 摘要", self)
        self.meta_value = QLabel("请输入 ASN 后开始查询")
        self.meta_value.setStyleSheet("color:#6B7280; font-size:13px;")
        self.meta_value.setWordWrap(True)
        self.meta_layout.addWidget(self.meta_value)
        root.addWidget(self.meta_card)

        # 前缀表
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["前缀", "起始 IP", "结束 IP", "IP 数"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 160)
        root.addWidget(self.table, 1)

        # 导出
        bar = QHBoxLayout()
        self.btn_export = QPushButton("导出前缀为 CSV")
        self.btn_export.clicked.connect(self._export)
        self.btn_export.setEnabled(False)
        bar.addStretch(1)
        bar.addWidget(self.btn_export)
        root.addLayout(bar)

        self._current_asn: Optional[int] = None
        self._current_prefixes: list = []

    def _parse_asn(self, s: str) -> Optional[int]:
        s = s.strip().upper().lstrip("AS").lstrip()
        if not s.isdigit():
            return None
        return int(s)

    def _run(self):
        asn = self._parse_asn(self.input.text())
        if asn is None:
            QMessageBox.warning(self, "格式错误", "请输入数字 ASN，例如 13335")
            return
        if self.worker and self.worker.isRunning():
            return
        self.btn.setEnabled(False)
        self.btn.setText("查询中…")
        self.meta_value.setText(f"查询 AS{asn} …")
        self.table.setRowCount(0)
        self.btn_export.setEnabled(False)

        self.worker = ASNLookupWorker(asn)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_done(self, data: dict):
        self.btn.setEnabled(True)
        self.btn.setText("反查")
        asn = data["asn"]
        meta = data["meta"]
        prefixes = data["prefixes"]
        pdb = data["peeringdb"]
        self._current_asn = asn
        self._current_prefixes = prefixes

        if not meta:
            self.meta_value.setText(
                f"未在本地库找到 AS{asn} 的记录。\n请确认 ip2asn 数据源已更新。"
            )
            return

        lines = [
            f"<b>AS{asn}</b>  ·  {meta.get('as_name') or '—'}",
            f"国家: {meta.get('country_code') or '—'}  "
            f"·  前缀数: <b>{fmt_int(meta.get('prefix_count'))}</b>  "
            f"·  IP 总数: <b>{fmt_int(meta.get('ip_count'))}</b>",
            f"快照日期: {meta.get('snap') or '—'}  "
            f"·  RPKI ROA: {fmt_int(data.get('rpki_count', 0))}  "
            f"·  与威胁库重叠前缀: <span style='color:#DC2626;'>{fmt_int(data.get('threat_overlap', 0))}</span>",
        ]
        if pdb:
            lines.append(
                f"<span style='color:#6B7280;'>PeeringDB:</span> "
                f"{pdb.get('name') or ''} "
                f"<span style='color:#6B7280;'>· {pdb.get('info_type') or ''} "
                f"· prefix4={pdb.get('info_prefixes4') or 0} "
                f"prefix6={pdb.get('info_prefixes6') or 0}</span>"
            )
        self.meta_value.setText("<br>".join(lines))
        self.meta_value.setTextFormat(Qt.RichText)

        # 填表
        self.table.setRowCount(len(prefixes))
        for i, p in enumerate(prefixes):
            s_int, e_int = p["network_start_int"], p["network_end_int"]
            try:
                start_ip = str(ipaddress.ip_address(s_int))
                end_ip = str(ipaddress.ip_address(e_int))
            except Exception:
                start_ip = end_ip = "—"
            ip_cnt = e_int - s_int + 1
            self.table.setItem(i, 0, QTableWidgetItem(p["network"] or "—"))
            self.table.setItem(i, 1, QTableWidgetItem(start_ip))
            self.table.setItem(i, 2, QTableWidgetItem(end_ip))
            self.table.setItem(i, 3, QTableWidgetItem(fmt_int(ip_cnt)))
        self.btn_export.setEnabled(bool(prefixes))

    def _on_fail(self, err: str):
        self.btn.setEnabled(True)
        self.btn.setText("反查")
        QMessageBox.critical(self, "查询失败", err)

    def _export(self):
        if not self._current_prefixes:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出前缀", f"AS{self._current_asn}_prefixes.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["network", "start_ip", "end_ip", "ip_count", "country", "snapshot"])
                for p in self._current_prefixes:
                    s_int, e_int = p["network_start_int"], p["network_end_int"]
                    try:
                        s_ip = str(ipaddress.ip_address(s_int))
                        e_ip = str(ipaddress.ip_address(e_int))
                    except Exception:
                        s_ip = e_ip = ""
                    w.writerow([p["network"], s_ip, e_ip, e_int - s_int + 1,
                                p.get("country_code") or "", p.get("snapshot_date") or ""])
            QMessageBox.information(self, "完成", f"已导出：{path}")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))


# ╔════════════════════════════════════════════════════════════╗
# ║                  国家统计 子页                             ║
# ╚════════════════════════════════════════════════════════════╝

class CountryStatsWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, country: str):
        super().__init__()
        self.country = country.upper()

    def run(self):
        try:
            conn = db_conn()
            try:
                cc = self.country
                geo_total = conn.execute(
                    "SELECT COUNT(*) FROM geoip WHERE country_code = ?", (cc,)
                ).fetchone()[0] or 0

                top_cities = conn.execute("""
                    SELECT city, COUNT(*) AS c
                    FROM geoip WHERE country_code = ? AND city IS NOT NULL AND city != ''
                    GROUP BY city ORDER BY c DESC LIMIT 15
                """, (cc,)).fetchall()

                top_asns = conn.execute("""
                    SELECT asn, as_name, COUNT(*) AS prefix_count,
                           SUM(network_end_int - network_start_int + 1) AS ip_count
                    FROM asn_info WHERE country_code = ?
                    GROUP BY asn ORDER BY ip_count DESC LIMIT 30
                """, (cc,)).fetchall()

                rir_breakdown = []
                try:
                    rir_breakdown = conn.execute("""
                        SELECT rir, COUNT(*) AS c, SUM(value) AS total_ips
                        FROM rir_delegated WHERE country_code = ?
                        GROUP BY rir ORDER BY total_ips DESC
                    """, (cc,)).fetchall()
                except sqlite3.OperationalError:
                    pass

                threat_count = 0
                try:
                    # 与 geoip 段重叠的威胁数（估算）
                    threat_count = conn.execute("""
                        SELECT COUNT(DISTINCT t.id) FROM threat_intel t
                        JOIN geoip g
                          ON t.network_start_int <= g.network_end_int
                         AND t.network_end_int   >= g.network_start_int
                        WHERE g.country_code = ?
                    """, (cc,)).fetchone()[0] or 0
                except Exception:
                    pass

                self.done.emit({
                    "country": cc,
                    "geo_total": geo_total,
                    "cities": [dict(r) for r in top_cities],
                    "asns": [dict(r) for r in top_asns],
                    "rir": [dict(r) for r in rir_breakdown],
                    "threat_count": threat_count,
                })
            finally:
                conn.close()
        except Exception as e:
            self.failed.emit(f"{e}\n{traceback.format_exc()}")


class CountryStatsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: Optional[CountryStatsWorker] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 14, 0, 0)
        root.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setObjectName("BigInput")
        self.input.setPlaceholderText("两位国家代码，例如  CN  /  US  /  JP  /  DE")
        self.input.setMaxLength(2)
        self.input.returnPressed.connect(self._run)
        self.btn = QPushButton("统计")
        self.btn.setObjectName("Primary")
        self.btn.setMinimumHeight(44)
        self.btn.setMinimumWidth(100)
        self.btn.clicked.connect(self._run)
        row.addWidget(self.input, 1)
        row.addWidget(self.btn)
        root.addLayout(row)

        # 摘要
        self.summary_card, self.summary_layout = make_card("国家概览", self)
        self.summary_label = QLabel("请输入国家代码")
        self.summary_label.setStyleSheet("color:#6B7280; font-size:13px;")
        self.summary_label.setWordWrap(True)
        self.summary_layout.addWidget(self.summary_label)
        root.addWidget(self.summary_card)

        # 两个表横向：城市 / ASN
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(12)

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("城市分布 TOP 15"))
        self.city_table = QTableWidget(0, 2)
        self.city_table.setHorizontalHeaderLabels(["城市", "段数"])
        self.city_table.horizontalHeader().setStretchLastSection(True)
        self.city_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.city_table.setColumnWidth(0, 200)
        left_box.addWidget(self.city_table)

        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("主要 ASN（按 IP 数）TOP 30"))
        self.asn_table = QTableWidget(0, 4)
        self.asn_table.setHorizontalHeaderLabels(["ASN", "组织", "前缀数", "IP 数"])
        self.asn_table.horizontalHeader().setStretchLastSection(True)
        self.asn_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.asn_table.setColumnWidth(0, 80)
        self.asn_table.setColumnWidth(1, 240)
        self.asn_table.setColumnWidth(2, 80)
        right_box.addWidget(self.asn_table)

        lw = QWidget(); lw.setLayout(left_box)
        rw = QWidget(); rw.setLayout(right_box)
        tabs_row.addWidget(lw, 1)
        tabs_row.addWidget(rw, 2)
        wrap = QWidget(); wrap.setLayout(tabs_row)
        root.addWidget(wrap, 1)

    def _run(self):
        cc = self.input.text().strip().upper()
        if len(cc) != 2:
            QMessageBox.warning(self, "格式错误", "请输入两位国家代码，例如 CN、US")
            return
        if self.worker and self.worker.isRunning():
            return
        self.btn.setEnabled(False)
        self.btn.setText("统计中…")
        self.summary_label.setText(f"统计 {cc} …")
        self.city_table.setRowCount(0)
        self.asn_table.setRowCount(0)
        self.worker = CountryStatsWorker(cc)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_done(self, data: dict):
        self.btn.setEnabled(True)
        self.btn.setText("统计")
        cc = data["country"]
        if not data["geo_total"] and not data["asns"]:
            self.summary_label.setText(
                f"未找到 {cc} 的数据。请确认 geoip / ip2asn 已更新。"
            )
            return

        rir_str = ""
        if data["rir"]:
            parts = [f"{r['rir'].upper()}: {fmt_int(r['c'])} 段" for r in data["rir"]]
            rir_str = "  ·  ".join(parts)
        self.summary_label.setText(
            f"<b>{cc}</b>  ·  GeoIP 段数: <b>{fmt_int(data['geo_total'])}</b>  "
            f"·  威胁条目（与该国 IP 重叠）: <span style='color:#DC2626;'>"
            f"{fmt_int(data['threat_count'])}</span><br>"
            f"<span style='color:#6B7280;'>RIR 分布：{rir_str or '—'}</span>"
        )
        self.summary_label.setTextFormat(Qt.RichText)

        # 城市
        cities = data["cities"]
        self.city_table.setRowCount(len(cities))
        for i, r in enumerate(cities):
            self.city_table.setItem(i, 0, QTableWidgetItem(r["city"]))
            self.city_table.setItem(i, 1, QTableWidgetItem(fmt_int(r["c"])))

        # ASN
        asns = data["asns"]
        self.asn_table.setRowCount(len(asns))
        for i, r in enumerate(asns):
            self.asn_table.setItem(i, 0, QTableWidgetItem(f"AS{r['asn']}"))
            self.asn_table.setItem(i, 1, QTableWidgetItem(r["as_name"] or "—"))
            self.asn_table.setItem(i, 2, QTableWidgetItem(fmt_int(r["prefix_count"])))
            self.asn_table.setItem(i, 3, QTableWidgetItem(fmt_int(r["ip_count"] or 0)))

    def _on_fail(self, err: str):
        self.btn.setEnabled(True)
        self.btn.setText("统计")
        QMessageBox.critical(self, "查询失败", err)


# ╔════════════════════════════════════════════════════════════╗
# ║                  CIDR 段查询 子页                          ║
# ╚════════════════════════════════════════════════════════════╝

class CIDRWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, cidr: str):
        super().__init__()
        self.cidr = cidr

    def run(self):
        try:
            s_int, e_int, ver = ip_range_from_cidr(self.cidr)
            conn = db_conn()
            try:
                # ASN 覆盖（一段可能跨多个 ASN）
                asns = conn.execute("""
                    SELECT asn, as_name, country_code, network,
                           network_start_int, network_end_int
                    FROM asn_info
                    WHERE network_start_int <= ? AND network_end_int >= ?
                    ORDER BY (network_end_int - network_start_int) ASC
                    LIMIT 50
                """, (e_int, s_int)).fetchall()

                # 地理覆盖
                geos = conn.execute("""
                    SELECT country_code, country_name, COUNT(*) AS c
                    FROM geoip
                    WHERE network_start_int <= ? AND network_end_int >= ?
                    GROUP BY country_code ORDER BY c DESC LIMIT 10
                """, (e_int, s_int)).fetchall()

                # 威胁条目
                threats = conn.execute("""
                    SELECT network, threat_type, list_name, severity, snapshot_date
                    FROM threat_intel
                    WHERE network_start_int <= ? AND network_end_int >= ?
                    LIMIT 500
                """, (e_int, s_int)).fetchall()

                # 云段
                clouds = conn.execute("""
                    SELECT provider, network, region, service
                    FROM cloud_ranges
                    WHERE network_start_int <= ? AND network_end_int >= ?
                    LIMIT 100
                """, (e_int, s_int)).fetchall()

                self.done.emit({
                    "cidr": self.cidr,
                    "version": ver,
                    "start_int": s_int,
                    "end_int": e_int,
                    "ip_count": e_int - s_int + 1,
                    "asns":   [dict(r) for r in asns],
                    "geos":   [dict(r) for r in geos],
                    "threats":[dict(r) for r in threats],
                    "clouds": [dict(r) for r in clouds],
                })
            finally:
                conn.close()
        except ValueError as e:
            self.failed.emit(f"CIDR 格式错误：{e}")
        except Exception as e:
            self.failed.emit(f"{e}\n{traceback.format_exc()}")


class CIDRTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: Optional[CIDRWorker] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 14, 0, 0)
        root.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setObjectName("BigInput")
        self.input.setPlaceholderText("CIDR，例如  1.1.1.0/24   或   2606:4700::/32")
        self.input.returnPressed.connect(self._run)
        self.btn = QPushButton("查询")
        self.btn.setObjectName("Primary")
        self.btn.setMinimumHeight(44)
        self.btn.setMinimumWidth(100)
        self.btn.clicked.connect(self._run)
        row.addWidget(self.input, 1)
        row.addWidget(self.btn)
        root.addLayout(row)

        # 摘要
        self.summary_card, self.summary_layout = make_card("段摘要", self)
        self.summary_label = QLabel("输入 CIDR 段开始查询")
        self.summary_label.setStyleSheet("color:#6B7280; font-size:13px;")
        self.summary_label.setWordWrap(True)
        self.summary_layout.addWidget(self.summary_label)
        root.addWidget(self.summary_card)

        # 三个表纵向：ASN / 威胁 / 云
        self.asn_table = QTableWidget(0, 4)
        self.asn_table.setHorizontalHeaderLabels(["ASN", "组织", "国家", "网络"])
        self.asn_table.horizontalHeader().setStretchLastSection(True)
        self.asn_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.asn_table.setMaximumHeight(180)
        root.addWidget(QLabel("ASN 覆盖"))
        root.addWidget(self.asn_table)

        self.threat_table = QTableWidget(0, 5)
        self.threat_table.setHorizontalHeaderLabels(["网络", "类型", "来源", "严重度", "快照"])
        self.threat_table.horizontalHeader().setStretchLastSection(True)
        self.threat_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(QLabel("段内威胁条目（最多 500）"))
        root.addWidget(self.threat_table, 1)

        self.cloud_table = QTableWidget(0, 4)
        self.cloud_table.setHorizontalHeaderLabels(["云", "网络", "区域", "服务"])
        self.cloud_table.horizontalHeader().setStretchLastSection(True)
        self.cloud_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cloud_table.setMaximumHeight(140)
        root.addWidget(QLabel("段内云服务商"))
        root.addWidget(self.cloud_table)

    def _run(self):
        cidr = self.input.text().strip()
        if "/" not in cidr:
            QMessageBox.warning(self, "格式错误", "请输入带前缀长度的 CIDR，例如 1.1.1.0/24")
            return
        if self.worker and self.worker.isRunning():
            return
        self.btn.setEnabled(False)
        self.btn.setText("查询中…")
        self.summary_label.setText(f"查询 {cidr} …")
        for t in (self.asn_table, self.threat_table, self.cloud_table):
            t.setRowCount(0)
        self.worker = CIDRWorker(cidr)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_done(self, data: dict):
        self.btn.setEnabled(True)
        self.btn.setText("查询")

        geo_str = "—"
        if data["geos"]:
            geo_str = "  ".join(
                f"{g['country_code']}({fmt_int(g['c'])})" for g in data["geos"][:5]
            )
        threat_n = len(data["threats"])
        threat_color = "#DC2626" if threat_n > 0 else "#16A34A"

        self.summary_label.setText(
            f"<b>{data['cidr']}</b>  ·  IPv{data['version']}  ·  "
            f"IP 数: <b>{fmt_int(data['ip_count'])}</b><br>"
            f"地理覆盖: {geo_str}<br>"
            f"ASN 数: {fmt_int(len(data['asns']))}  ·  "
            f"威胁条目: <span style='color:{threat_color}; font-weight:600;'>"
            f"{fmt_int(threat_n)}</span>  ·  "
            f"云段: {fmt_int(len(data['clouds']))}"
        )
        self.summary_label.setTextFormat(Qt.RichText)

        # ASN
        self.asn_table.setRowCount(len(data["asns"]))
        for i, r in enumerate(data["asns"]):
            self.asn_table.setItem(i, 0, QTableWidgetItem(f"AS{r['asn']}"))
            self.asn_table.setItem(i, 1, QTableWidgetItem(r["as_name"] or "—"))
            self.asn_table.setItem(i, 2, QTableWidgetItem(r["country_code"] or "—"))
            self.asn_table.setItem(i, 3, QTableWidgetItem(r["network"] or "—"))

        # 威胁
        self.threat_table.setRowCount(len(data["threats"]))
        for i, r in enumerate(data["threats"]):
            self.threat_table.setItem(i, 0, QTableWidgetItem(r["network"]))
            self.threat_table.setItem(i, 1, QTableWidgetItem(r["threat_type"] or "—"))
            self.threat_table.setItem(i, 2, QTableWidgetItem(r["list_name"] or "—"))
            sev = r["severity"] or "medium"
            sev_item = QTableWidgetItem(sev)
            sev_item.setForeground(QColor(RISK_COLORS.get(sev, "#6B7280")))
            self.threat_table.setItem(i, 3, sev_item)
            self.threat_table.setItem(i, 4, QTableWidgetItem(r["snapshot_date"] or "—"))

        # 云
        self.cloud_table.setRowCount(len(data["clouds"]))
        for i, r in enumerate(data["clouds"]):
            self.cloud_table.setItem(i, 0, QTableWidgetItem(r["provider"] or "—"))
            self.cloud_table.setItem(i, 1, QTableWidgetItem(r["network"] or "—"))
            self.cloud_table.setItem(i, 2, QTableWidgetItem(r["region"] or "—"))
            self.cloud_table.setItem(i, 3, QTableWidgetItem(r["service"] or "—"))

    def _on_fail(self, err: str):
        self.btn.setEnabled(True)
        self.btn.setText("查询")
        QMessageBox.critical(self, "失败", err)


# ╔════════════════════════════════════════════════════════════╗
# ║                    NetworkPage（合并）                     ║
# ╚════════════════════════════════════════════════════════════╝

class NetworkPage(QWidget):
    """网络页：ASN 反查 / 国家统计 / CIDR 段查询  3 个 Tab"""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(10)

        title = QLabel("网络")
        title.setObjectName("PageTitle")
        sub = QLabel("基于本地数据库的 ASN / 国家 / CIDR 段离线分析")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(ASNLookupTab(),   "ASN 反查")
        self.tabs.addTab(CountryStatsTab(), "国家统计")
        self.tabs.addTab(CIDRTab(),        "CIDR 段查询")
        root.addWidget(self.tabs, 1)


# ╔════════════════════════════════════════════════════════════╗
# ║                  威胁库浏览页                              ║
# ╚════════════════════════════════════════════════════════════╝

class ThreatBrowseWorker(QThread):
    done = Signal(list, int)   # rows, total_count
    failed = Signal(str)

    def __init__(self, filters: dict, page: int, page_size: int):
        super().__init__()
        self.filters = filters
        self.page = page
        self.page_size = page_size

    def run(self):
        try:
            where, params = ["1=1"], []
            f = self.filters
            if f.get("list_name"):
                where.append("list_name = ?"); params.append(f["list_name"])
            if f.get("threat_type"):
                where.append("threat_type = ?"); params.append(f["threat_type"])
            if f.get("severity"):
                where.append("severity = ?"); params.append(f["severity"])
            if f.get("search"):
                where.append("network LIKE ?"); params.append(f"%{f['search']}%")

            where_sql = " AND ".join(where)

            conn = db_conn()
            try:
                total = conn.execute(
                    f"SELECT COUNT(*) FROM threat_intel WHERE {where_sql}", params
                ).fetchone()[0] or 0

                offset = (self.page - 1) * self.page_size
                rows = conn.execute(f"""
                    SELECT network, threat_type, list_name, severity, source,
                           snapshot_date, network_start_int, network_end_int
                    FROM threat_intel WHERE {where_sql}
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                """, params + [self.page_size, offset]).fetchall()

                self.done.emit([dict(r) for r in rows], total)
            finally:
                conn.close()
        except Exception as e:
            self.failed.emit(f"{e}\n{traceback.format_exc()}")


class ThreatLibraryPage(QWidget):
    """威胁库浏览：筛选 / 搜索 / 分页 / 导出"""

    PAGE_SIZE = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: Optional[ThreatBrowseWorker] = None
        self.page = 1
        self.total = 0
        self.last_rows: list = []
        self._build()
        self._load_filter_options()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(12)

        title = QLabel("威胁库")
        title.setObjectName("PageTitle")
        sub = QLabel("浏览所有威胁情报条目，可按来源 / 类型 / 严重度筛选")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        # 筛选行
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.list_combo = QComboBox()
        self.list_combo.addItem("全部来源", "")
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部类型", "")
        self.sev_combo = QComboBox()
        self.sev_combo.addItem("全部严重度", "")
        for s in ["critical", "high", "medium", "low"]:
            self.sev_combo.addItem(s, s)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索网络/IP，如 1.1.1")
        self.search_input.returnPressed.connect(self._on_filter)

        self.btn_apply = QPushButton("筛选")
        self.btn_apply.setObjectName("Primary")
        self.btn_apply.clicked.connect(self._on_filter)
        self.btn_reset = QPushButton("重置")
        self.btn_reset.clicked.connect(self._on_reset)

        for w in (self.list_combo, self.type_combo, self.sev_combo):
            w.setMinimumWidth(140)
        self.list_combo.currentIndexChanged.connect(self._on_filter)
        self.type_combo.currentIndexChanged.connect(self._on_filter)
        self.sev_combo.currentIndexChanged.connect(self._on_filter)

        bar.addWidget(self.list_combo)
        bar.addWidget(self.type_combo)
        bar.addWidget(self.sev_combo)
        bar.addWidget(self.search_input, 1)
        bar.addWidget(self.btn_apply)
        bar.addWidget(self.btn_reset)
        root.addLayout(bar)

        # 状态
        self.stat_label = QLabel("加载中…")
        self.stat_label.setObjectName("PageSubtitle")
        root.addWidget(self.stat_label)

        # 表
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["网络", "类型", "来源列表", "严重度", "数据源", "快照"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 110)
        root.addWidget(self.table, 1)

        # 翻页 / 导出
        pager = QHBoxLayout()
        self.btn_prev = QPushButton("上一页")
        self.btn_prev.clicked.connect(self._prev)
        self.btn_next = QPushButton("下一页")
        self.btn_next.clicked.connect(self._next)
        self.page_label = QLabel("第 1 页")
        self.page_label.setStyleSheet("color:#6B7280;")
        self.btn_export = QPushButton("导出当前筛选为 CSV")
        self.btn_export.clicked.connect(self._export)

        pager.addWidget(self.btn_prev)
        pager.addWidget(self.btn_next)
        pager.addWidget(self.page_label)
        pager.addStretch(1)
        pager.addWidget(self.btn_export)
        root.addLayout(pager)

    def _load_filter_options(self):
        """读取库中现有的 list_name / threat_type 填充下拉"""
        try:
            conn = db_conn()
            try:
                lists = conn.execute(
                    "SELECT DISTINCT list_name FROM threat_intel "
                    "WHERE list_name IS NOT NULL ORDER BY list_name"
                ).fetchall()
                for r in lists:
                    self.list_combo.addItem(r["list_name"], r["list_name"])
                types = conn.execute(
                    "SELECT DISTINCT threat_type FROM threat_intel "
                    "WHERE threat_type IS NOT NULL ORDER BY threat_type"
                ).fetchall()
                for r in types:
                    self.type_combo.addItem(r["threat_type"], r["threat_type"])
            finally:
                conn.close()
        except Exception as e:
            print("[ThreatLibraryPage._load_filter_options]", e)

    def _filters(self) -> dict:
        return {
            "list_name":   self.list_combo.currentData() or "",
            "threat_type": self.type_combo.currentData() or "",
            "severity":    self.sev_combo.currentData() or "",
            "search":      self.search_input.text().strip(),
        }

    def _on_filter(self):
        self.page = 1
        self.refresh()

    def _on_reset(self):
        self.list_combo.setCurrentIndex(0)
        self.type_combo.setCurrentIndex(0)
        self.sev_combo.setCurrentIndex(0)
        self.search_input.clear()
        self.page = 1
        self.refresh()

    def refresh(self):
        if self.worker and self.worker.isRunning():
            return
        self.stat_label.setText("加载中…")
        self.worker = ThreatBrowseWorker(self._filters(), self.page, self.PAGE_SIZE)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_done(self, rows: list, total: int):
        self.total = total
        self.last_rows = rows
        total_pages = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.stat_label.setText(f"共 {fmt_int(total)} 条匹配  ·  当前 {len(rows)} 行")
        self.page_label.setText(f"第 {self.page} / {total_pages} 页")
        self.btn_prev.setEnabled(self.page > 1)
        self.btn_next.setEnabled(self.page < total_pages)

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["network"] or "—"))
            self.table.setItem(i, 1, QTableWidgetItem(r["threat_type"] or "—"))
            self.table.setItem(i, 2, QTableWidgetItem(r["list_name"] or "—"))
            sev = r["severity"] or "medium"
            sev_item = QTableWidgetItem(sev)
            sev_item.setForeground(QColor(RISK_COLORS.get(sev, "#6B7280")))
            self.table.setItem(i, 3, sev_item)
            self.table.setItem(i, 4, QTableWidgetItem(r["source"] or "—"))
            self.table.setItem(i, 5, QTableWidgetItem(r["snapshot_date"] or "—"))

    def _on_fail(self, err: str):
        self.stat_label.setText("加载失败")
        QMessageBox.critical(self, "失败", err)

    def _prev(self):
        if self.page > 1:
            self.page -= 1
            self.refresh()

    def _next(self):
        self.page += 1
        self.refresh()

    def _export(self):
        """导出当前筛选条件下的全部记录（不止当前页）"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出威胁条目",
            f"threats_{datetime.now():%Y%m%d_%H%M%S}.csv",
            "CSV (*.csv)"
        )
        if not path:
            return
        try:
            f = self._filters()
            where, params = ["1=1"], []
            if f["list_name"]:
                where.append("list_name = ?"); params.append(f["list_name"])
            if f["threat_type"]:
                where.append("threat_type = ?"); params.append(f["threat_type"])
            if f["severity"]:
                where.append("severity = ?"); params.append(f["severity"])
            if f["search"]:
                where.append("network LIKE ?"); params.append(f"%{f['search']}%")
            where_sql = " AND ".join(where)

            conn = db_conn()
            try:
                cur = conn.execute(
                    f"SELECT network, threat_type, list_name, severity, "
                    f"source, snapshot_date FROM threat_intel WHERE {where_sql}",
                    params
                )
                with open(path, "w", encoding="utf-8-sig", newline="") as fp:
                    w = csv.writer(fp)
                    w.writerow(["network", "threat_type", "list_name", "severity",
                                "source", "snapshot_date"])
                    n = 0
                    for row in cur:
                        w.writerow([row["network"], row["threat_type"], row["list_name"],
                                    row["severity"], row["source"], row["snapshot_date"]])
                        n += 1
            finally:
                conn.close()
            QMessageBox.information(self, "导出完成", f"已写入 {fmt_int(n)} 条到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
