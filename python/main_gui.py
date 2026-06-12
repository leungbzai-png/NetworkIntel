# -*- coding: utf-8 -*-
"""
NetworkIntel - PySide6 桌面 GUI
极简风格（Linear / Raycast / SSH Terminal 参考）
后端零改动，仅调用 query.engine / scheduler.scheduler / reports.generator / utils.config_loader

启动：python main_gui.py
"""
from __future__ import annotations

import os
import sys
import csv
import json
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    Qt, QSize, QThread, Signal, QObject, QTimer, QSettings, QPoint
)
from PySide6.QtGui import (
    QIcon, QFont, QFontDatabase, QPalette, QColor, QAction, QKeySequence,
    QShortcut, QGuiApplication, QPixmap, QPainter, QPen
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QLineEdit, QTextEdit, QPlainTextEdit, QFrame, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QProgressBar, QListWidget, QListWidgetItem, QSplitter, QSizePolicy,
    QScrollArea, QGridLayout, QComboBox, QCheckBox, QStyleFactory,
    QAbstractItemView, QSpacerItem, QToolButton, QTabWidget,
    QDialog, QRadioButton, QButtonGroup
)

# ── 后端接口 ──────────────────────────────────────────────────
# 允许从项目根目录运行
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

APP_VERSION = "1.2.0"
APP_BUILD = "2026-06-05"

try:
    from query.engine import query_ip, query_batch, calculate_risk
    from scheduler.scheduler import get_scheduler, register_update_callback
    from reports.generator import generate_reports
    from utils.config_loader import get_config, reload_config
    from utils.schema import get_connection
    from utils.ip_utils import get_ip_version, normalize_ip
    from datasources import setup_profiles
    BACKEND_OK = True
    BACKEND_ERR = ""
except Exception as e:
    BACKEND_OK = False
    BACKEND_ERR = f"{e}\n{traceback.format_exc()}"

# 扩展模块（DashboardBar / NetworkPage / ThreatLibraryPage）
try:
    from gui_extensions import DashboardBar, NetworkPage, ThreatLibraryPage
    EXT_OK = True
except Exception as _e:
    print("[gui_extensions] 加载失败:", _e)
    EXT_OK = False

# 地图模块（可选，需要 QtWebEngine）
try:
    from gui_map import MapWidget, is_map_available
    MAP_OK = is_map_available()
except Exception as _e:
    print("[gui_map] 加载失败:", _e)
    MAP_OK = False
    MapWidget = None  # type: ignore


# ╔════════════════════════════════════════════════════════════╗
# ║                       主题 / 样式                          ║
# ╚════════════════════════════════════════════════════════════╝

ACCENT = "#2563EB"

LIGHT_QSS = f"""
* {{
    font-family: -apple-system, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
}}

QMainWindow, QWidget {{
    background-color: #FFFFFF;
    color: #111827;
}}

#Sidebar {{
    background-color: #FAFAFA;
    border-right: 1px solid #E5E7EB;
}}

#SidebarTitle {{
    color: #111827;
    font-size: 17px;
    font-weight: 600;
    padding: 22px 20px 6px 20px;
}}

#SidebarSubtitle {{
    color: #9CA3AF;
    font-size: 11px;
    padding: 0 20px 18px 20px;
    letter-spacing: 0.5px;
}}

QPushButton#NavButton {{
    background-color: transparent;
    color: #4B5563;
    border: none;
    text-align: left;
    padding: 10px 20px;
    font-size: 13px;
    border-radius: 0px;
}}
QPushButton#NavButton:hover {{
    background-color: #F3F4F6;
    color: #111827;
}}
QPushButton#NavButton:checked {{
    background-color: #EFF6FF;
    color: {ACCENT};
    font-weight: 600;
    border-left: 3px solid {ACCENT};
    padding-left: 17px;
}}

#PageTitle {{
    font-size: 26px;
    font-weight: 600;
    color: #111827;
}}
#PageSubtitle {{
    font-size: 13px;
    color: #6B7280;
}}
#SectionTitle {{
    font-size: 13px;
    font-weight: 600;
    color: #6B7280;
    letter-spacing: 0.4px;
}}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 9px 12px;
    font-size: 14px;
    color: #111827;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}

QLineEdit#BigInput {{
    font-size: 16px;
    padding: 14px 16px;
    border-radius: 10px;
}}

QPushButton {{
    background-color: #F3F4F6;
    color: #111827;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
}}
QPushButton:hover {{ background-color: #E5E7EB; }}
QPushButton:pressed {{ background-color: #D1D5DB; }}

QPushButton#Primary {{
    background-color: {ACCENT};
    color: #FFFFFF;
    border: 1px solid {ACCENT};
    font-weight: 500;
}}
QPushButton#Primary:hover {{ background-color: #1D4ED8; }}
QPushButton#Primary:pressed {{ background-color: #1E40AF; }}
QPushButton#Primary:disabled {{ background-color: #93C5FD; border-color:#93C5FD; }}

#Card {{
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
}}
#CardTitle {{
    color: #6B7280;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
#CardValue {{
    color: #111827;
    font-size: 15px;
}}
#CardValueBig {{
    color: #111827;
    font-size: 20px;
    font-weight: 600;
}}

QTableWidget {{
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    gridline-color: #F3F4F6;
    font-size: 13px;
}}
QTableWidget::item {{ padding: 6px; }}
QTableWidget::item:selected {{ background-color: #EFF6FF; color: #111827; }}
QHeaderView::section {{
    background-color: #F9FAFB;
    color: #6B7280;
    border: none;
    border-bottom: 1px solid #E5E7EB;
    padding: 8px;
    font-size: 12px;
    font-weight: 600;
}}

QProgressBar {{
    background-color: #F3F4F6;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 4px; }}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #D1D5DB; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #9CA3AF; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height:10px; margin:0; }}
QScrollBar::handle:horizontal {{ background:#D1D5DB; border-radius:5px; min-width:30px; }}
QScrollBar::handle:horizontal:hover {{ background:#9CA3AF; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}

#StatusBar {{
    background-color: #FAFAFA;
    border-top: 1px solid #E5E7EB;
    color: #6B7280;
    font-size: 12px;
}}

#Badge {{
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
    color: #FFFFFF;
}}

#Separator {{
    background-color: #E5E7EB;
    max-height: 1px;
    min-height: 1px;
}}
"""

DARK_QSS = f"""
* {{
    font-family: -apple-system, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
}}

QMainWindow, QWidget {{ background-color: #0F1115; color: #E5E7EB; }}

#Sidebar {{ background-color: #0B0D11; border-right: 1px solid #1F2330; }}
#SidebarTitle {{ color: #F3F4F6; font-size: 17px; font-weight: 600; padding: 22px 20px 6px 20px; }}
#SidebarSubtitle {{ color: #6B7280; font-size: 11px; padding: 0 20px 18px 20px; letter-spacing: 0.5px; }}

QPushButton#NavButton {{
    background-color: transparent; color: #9CA3AF; border: none;
    text-align: left; padding: 10px 20px; font-size: 13px;
}}
QPushButton#NavButton:hover {{ background-color: #161B26; color: #F3F4F6; }}
QPushButton#NavButton:checked {{
    background-color: #1A2235; color: #60A5FA; font-weight: 600;
    border-left: 3px solid {ACCENT}; padding-left: 17px;
}}

#PageTitle {{ font-size: 26px; font-weight: 600; color: #F9FAFB; }}
#PageSubtitle {{ font-size: 13px; color: #9CA3AF; }}
#SectionTitle {{ font-size: 13px; font-weight: 600; color: #9CA3AF; letter-spacing: 0.4px; }}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
    background-color: #161B26; border: 1px solid #262C3A; border-radius: 8px;
    padding: 9px 12px; font-size: 14px; color: #F3F4F6;
    selection-background-color: {ACCENT}; selection-color: #FFFFFF;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit#BigInput {{ font-size: 16px; padding: 14px 16px; border-radius: 10px; }}

QPushButton {{
    background-color: #1B2130; color: #E5E7EB; border: 1px solid #262C3A;
    border-radius: 8px; padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background-color: #232A3B; }}
QPushButton:pressed {{ background-color: #2C3447; }}
QPushButton#Primary {{ background-color: {ACCENT}; color:#FFFFFF; border:1px solid {ACCENT}; font-weight:500; }}
QPushButton#Primary:hover {{ background-color: #1D4ED8; }}
QPushButton#Primary:disabled {{ background-color:#1E3A8A; border-color:#1E3A8A; color:#9CA3AF; }}

#Card {{ background-color: #131722; border: 1px solid #1F2330; border-radius: 12px; }}
#CardTitle {{ color: #9CA3AF; font-size: 12px; font-weight: 600; letter-spacing:0.5px; }}
#CardValue {{ color: #F3F4F6; font-size: 15px; }}
#CardValueBig {{ color: #F9FAFB; font-size: 20px; font-weight: 600; }}

QTableWidget {{
    background-color: #131722; border: 1px solid #1F2330; border-radius: 8px;
    gridline-color: #1F2330; font-size: 13px; color: #E5E7EB;
}}
QTableWidget::item {{ padding: 6px; }}
QTableWidget::item:selected {{ background-color: #1E2A44; color: #F9FAFB; }}
QHeaderView::section {{
    background-color: #0F1320; color: #9CA3AF; border: none;
    border-bottom: 1px solid #1F2330; padding: 8px; font-size: 12px; font-weight: 600;
}}

QProgressBar {{ background-color:#1B2130; border:none; border-radius:4px; height:6px; text-align:center; color: transparent; }}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius:4px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2C3447; border-radius:5px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background: #3B445C; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height:10px; margin:0; }}
QScrollBar::handle:horizontal {{ background:#2C3447; border-radius:5px; min-width:30px; }}

#StatusBar {{ background-color:#0B0D11; border-top: 1px solid #1F2330; color:#9CA3AF; font-size:12px; }}
#Badge {{ border-radius: 10px; padding: 2px 10px; font-size: 11px; font-weight: 600; color:#FFFFFF; }}
#Separator {{ background-color: #1F2330; max-height: 1px; min-height: 1px; }}
"""

RISK_COLORS = {
    "critical": "#DC2626",
    "high":     "#EA580C",
    "medium":   "#D97706",
    "low":      "#2563EB",
    "info":     "#2563EB",
    "clean":    "#16A34A",
}
RISK_LABELS = {
    "critical": "严重",
    "high":     "高危",
    "medium":   "中危",
    "low":      "低危",
    "info":     "注意",
    "clean":    "正常",
}


# ╔════════════════════════════════════════════════════════════╗
# ║                       工作线程                             ║
# ╚════════════════════════════════════════════════════════════╝

class SingleQueryWorker(QThread):
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, ip: str):
        super().__init__()
        self.ip = ip

    def run(self):
        try:
            r = query_ip(self.ip)
            self.finished_ok.emit(r)
        except Exception as e:
            self.failed.emit(f"{e}\n{traceback.format_exc()}")


class BatchQueryWorker(QThread):
    progress = Signal(int, int)        # current, total
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, ip_list):
        super().__init__()
        self.ip_list = ip_list
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            results = []
            total = len(self.ip_list)
            for i, ip in enumerate(self.ip_list):
                if self._cancel:
                    break
                self.progress.emit(i + 1, total)
                if not ip.strip():
                    continue
                try:
                    results.append(query_ip(ip.strip()))
                except Exception as e:
                    results.append({"ip": ip, "error": str(e)})
            self.finished_ok.emit(results)
        except Exception as e:
            self.failed.emit(f"{e}\n{traceback.format_exc()}")


class SourceUpdateWorker(QThread):
    """直接触发调度器的 trigger_now（其内部已有线程，这里只是确保不阻塞）"""
    done = Signal(str)

    def __init__(self, source_name: str):
        super().__init__()
        self.source_name = source_name

    def run(self):
        try:
            sched = get_scheduler()
            sched.trigger_now(self.source_name)
            self.done.emit(self.source_name)
        except Exception as e:
            self.done.emit(f"ERR:{e}")


class ReportGenWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, results, auto_open=True):
        super().__init__()
        self.results = results
        self.auto_open = auto_open

    def run(self):
        try:
            paths = generate_reports(self.results, auto_open=self.auto_open)
            self.done.emit(paths)
        except Exception as e:
            self.failed.emit(str(e))


# ╔════════════════════════════════════════════════════════════╗
# ║                     可复用 UI 组件                         ║
# ╚════════════════════════════════════════════════════════════╝

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


def risk_badge(risk: str) -> QLabel:
    lbl = QLabel(f"  {RISK_LABELS.get(risk, risk)}  ")
    lbl.setObjectName("Badge")
    color = RISK_COLORS.get(risk, "#6B7280")
    lbl.setStyleSheet(f"background-color:{color}; color:#FFFFFF; border-radius:10px; "
                      f"padding:3px 12px; font-size:11px; font-weight:600;")
    lbl.setAlignment(Qt.AlignCenter)
    return lbl


def kv_row(parent_layout: QVBoxLayout, key: str, value: str):
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    k = QLabel(key)
    k.setStyleSheet("color:#6B7280; font-size:12px;")
    k.setMinimumWidth(96)
    v = QLabel(value if value not in (None, "") else "—")
    v.setObjectName("CardValue")
    v.setWordWrap(True)
    v.setTextInteractionFlags(Qt.TextSelectableByMouse)
    h.addWidget(k, 0, Qt.AlignTop)
    h.addWidget(v, 1)
    parent_layout.addLayout(h)


# ╔════════════════════════════════════════════════════════════╗
# ║                       页面：查询                           ║
# ╚════════════════════════════════════════════════════════════╝

class QueryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: SingleQueryWorker | None = None
        self.history: list[dict] = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(18)

        # 标题
        title = QLabel("IP 情报查询")
        title.setObjectName("PageTitle")
        sub = QLabel("输入 IPv4 / IPv6 地址，离线获取完整情报")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        # 数据库统计仪表盘（来自 gui_extensions）
        if EXT_OK:
            try:
                self.dashboard = DashboardBar(self)
                root.addWidget(self.dashboard)
            except Exception as _e:
                print("[DashboardBar]", _e)

        # 输入区
        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.ip_input = QLineEdit()
        self.ip_input.setObjectName("BigInput")
        self.ip_input.setPlaceholderText("例如  1.1.1.1   或   2606:4700:4700::1111")
        self.ip_input.returnPressed.connect(self.do_query)
        self.btn_query = QPushButton("查询")
        self.btn_query.setObjectName("Primary")
        self.btn_query.setMinimumHeight(46)
        self.btn_query.setMinimumWidth(110)
        self.btn_query.clicked.connect(self.do_query)
        input_row.addWidget(self.ip_input, 1)
        input_row.addWidget(self.btn_query)
        root.addLayout(input_row)

        # 状态行
        self.status_label = QLabel("")
        self.status_label.setObjectName("PageSubtitle")
        root.addWidget(self.status_label)

        # 结果滚动区
        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_scroll.setFrameShape(QFrame.NoFrame)
        self.result_container = QWidget()
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        self.result_layout.setSpacing(14)
        self.result_layout.addStretch(1)
        self.result_scroll.setWidget(self.result_container)
        root.addWidget(self.result_scroll, 1)

        # 历史
        h_title = QLabel("最近查询")
        h_title.setObjectName("SectionTitle")
        root.addWidget(h_title)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(120)
        self.history_list.setStyleSheet("border:1px solid transparent;")
        self.history_list.itemDoubleClicked.connect(self._reuse_history)
        root.addWidget(self.history_list)

    def do_query(self):
        ip = self.ip_input.text().strip()
        if not ip:
            return
        if self.worker and self.worker.isRunning():
            return
        self.btn_query.setEnabled(False)
        self.btn_query.setText("查询中…")
        self.status_label.setText(f"查询 {ip} …")
        self._clear_results()
        self.worker = SingleQueryWorker(ip)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_done(self, result: dict):
        self.btn_query.setEnabled(True)
        self.btn_query.setText("查询")
        ip = result.get("ip", "?")
        if "error" in result:
            self.status_label.setText(f"错误：{result['error']}")
            return
        self.status_label.setText(f"已完成 · {ip}")
        self._render_result(result)

        # 历史
        rec = {
            "ip": ip,
            "risk": result.get("risk_level", "clean"),
            "country": (result.get("geoip") or {}).get("country_name") or "",
            "ts": datetime.now().strftime("%H:%M:%S"),
        }
        self.history.insert(0, rec)
        self.history = self.history[:50]
        self._refresh_history()

    def _on_fail(self, err: str):
        self.btn_query.setEnabled(True)
        self.btn_query.setText("查询")
        self.status_label.setText("查询失败")
        QMessageBox.critical(self, "查询失败", err)

    def _clear_results(self):
        while self.result_layout.count() > 1:
            item = self.result_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render_result(self, r: dict):
        ipver = r.get("ip_version", 4)
        # 头部摘要卡
        head, hlay = make_card("", self)
        hlay.setSpacing(10)
        top = QHBoxLayout()
        ip_lbl = QLabel(r.get("ip", "—"))
        ip_lbl.setStyleSheet("font-size:24px; font-weight:600; font-family: ui-monospace, Menlo, Consolas, monospace;")
        ip_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ver = QLabel(f"IPv{ipver}")
        ver.setStyleSheet(f"color:{ACCENT}; font-size:12px; font-weight:600; "
                          f"background:rgba(37,99,235,0.10); border-radius:6px; padding:3px 8px;")
        top.addWidget(ip_lbl)
        top.addWidget(ver)
        top.addStretch(1)
        top.addWidget(risk_badge(r.get("risk_level", "clean")))
        hlay.addLayout(top)

        if r.get("is_special"):
            kv_row(hlay, "类别", r.get("special_category", ""))
            kv_row(hlay, "说明", r.get("special_description", ""))
            kv_row(hlay, "网段", r.get("special_network", ""))
            self.result_layout.insertWidget(self.result_layout.count() - 1, head)
            return

        self.result_layout.insertWidget(self.result_layout.count() - 1, head)

        # 网格：地理 / ASN / RPKI / 云 / Tor·VPN / 威胁 / WHOIS
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        cards = []

        # 地理
        geo = r.get("geoip") or {}
        c, l = make_card("地理位置", self)
        kv_row(l, "国家", f"{geo.get('country_name','')} ({geo.get('country_code','')})" if geo else "—")
        kv_row(l, "地区", geo.get("region", "") if geo else "—")
        kv_row(l, "城市", geo.get("city", "") if geo else "—")
        if geo and geo.get("latitude") is not None:
            kv_row(l, "经纬度", f"{geo.get('latitude')}, {geo.get('longitude')}")
        kv_row(l, "网段", geo.get("network", "") if geo else "—")
        cards.append(c)

        # ASN
        asn = r.get("asn") or {}
        c, l = make_card("ASN / BGP", self)
        if asn:
            kv_row(l, "ASN", f"AS{asn.get('asn')}" if asn.get("asn") else "—")
            kv_row(l, "组织", asn.get("as_name") or asn.get("description") or "—")
            kv_row(l, "国家", asn.get("country_code") or "—")
            kv_row(l, "前缀", asn.get("prefix") or asn.get("network") or "—")
        else:
            kv_row(l, "状态", "无 ASN 数据")
        cards.append(c)

        # RPKI
        rpki = r.get("rpki") or {}
        c, l = make_card("RPKI", self)
        status = (rpki.get("status") or "unknown") if rpki else "unknown"
        kv_row(l, "状态", status)
        if rpki:
            kv_row(l, "最大长度", str(rpki.get("max_length", "—")))
            kv_row(l, "前缀", rpki.get("prefix", "—"))
        cards.append(c)

        # 云
        cloud = r.get("cloud") or {}
        c, l = make_card("云服务商", self)
        if cloud:
            kv_row(l, "提供商", cloud.get("provider", "—"))
            kv_row(l, "区域", cloud.get("region", "—"))
            kv_row(l, "服务", cloud.get("service", "—"))
        else:
            kv_row(l, "状态", "非云 IP")
        cards.append(c)

        # Tor / VPN
        c, l = make_card("匿名网络", self)
        kv_row(l, "Tor 出口", "是 ⚠" if r.get("is_tor") else "否")
        kv_row(l, "已知 VPN", "是 ⚠" if r.get("is_vpn") else "否")
        cards.append(c)

        # 威胁
        threats = r.get("threats") or []
        c, l = make_card("威胁情报", self)
        if not threats:
            kv_row(l, "状态", "未发现")
        else:
            for t in threats[:8]:
                sev = t.get("severity", "medium")
                color = RISK_COLORS.get(sev, "#6B7280")
                line = QLabel(
                    f"<span style='color:{color}; font-weight:600;'>● {sev.upper()}</span> "
                    f"<span style='color:#6B7280;'>{t.get('list_name','')}</span> "
                    f"· {t.get('threat_type','')}"
                )
                line.setTextFormat(Qt.RichText)
                l.addWidget(line)
            if len(threats) > 8:
                more = QLabel(f"…还有 {len(threats)-8} 条")
                more.setStyleSheet("color:#9CA3AF; font-size:12px;")
                l.addWidget(more)
        cards.append(c)

        # WHOIS / RIR
        whois = r.get("whois") or {}
        rir = r.get("rir") or {}
        c, l = make_card("WHOIS / RIR", self)
        if rir:
            kv_row(l, "RIR", rir.get("registry", "—"))
            kv_row(l, "国家", rir.get("country_code", "—"))
            kv_row(l, "分配日期", rir.get("date", "—"))
        if whois:
            kv_row(l, "Org", whois.get("org") or whois.get("organization") or "—")
            kv_row(l, "Net", whois.get("netname") or "—")
        if not rir and not whois:
            kv_row(l, "状态", "无数据")
        cards.append(c)

        # PeeringDB
        pdb = r.get("peeringdb") or {}
        if pdb:
            c, l = make_card("PeeringDB", self)
            kv_row(l, "名称", pdb.get("name", "—"))
            kv_row(l, "类型", pdb.get("info_type", "—"))
            kv_row(l, "Traffic", pdb.get("info_traffic", "—"))
            cards.append(c)

        # 摆放：每行两列
        cols = 2
        for i, card in enumerate(cards):
            grid.addWidget(card, i // cols, i % cols)
        for col in range(cols):
            grid.setColumnStretch(col, 1)

        self.result_layout.insertWidget(self.result_layout.count() - 1, grid_w)

    def _refresh_history(self):
        self.history_list.clear()
        for h in self.history:
            txt = f"{h['ts']}   {h['ip']:<40}   {RISK_LABELS.get(h['risk'],'')}   {h['country']}"
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, h["ip"])
            color = RISK_COLORS.get(h["risk"])
            if color:
                item.setForeground(QColor(color))
            self.history_list.addItem(item)

    def _reuse_history(self, item: QListWidgetItem):
        ip = item.data(Qt.UserRole)
        if ip:
            self.ip_input.setText(ip)
            self.do_query()


# ╔════════════════════════════════════════════════════════════╗
# ║                       页面：批量                           ║
# ╚════════════════════════════════════════════════════════════╝

class BatchPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: BatchQueryWorker | None = None
        self.report_worker: ReportGenWorker | None = None
        self.results: list[dict] = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        title = QLabel("批量查询")
        title.setObjectName("PageTitle")
        sub = QLabel("每行一个 IP，或从文本文件导入")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        # 工具栏
        toolbar = QHBoxLayout()
        self.btn_load = QPushButton("从文件导入…")
        self.btn_load.clicked.connect(self._load_file)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.clicked.connect(lambda: self.input_box.clear())
        self.btn_run = QPushButton("开始批量查询")
        self.btn_run.setObjectName("Primary")
        self.btn_run.clicked.connect(self._run)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setEnabled(False)
        toolbar.addWidget(self.btn_load)
        toolbar.addWidget(self.btn_clear)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_cancel)
        toolbar.addWidget(self.btn_run)
        root.addLayout(toolbar)

        # 输入与结果分栏
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText("1.1.1.1\n8.8.8.8\n2606:4700:4700::1111\n…")
        splitter.addWidget(self.input_box)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        rl.addWidget(self.progress)
        self.progress_label = QLabel("就绪")
        self.progress_label.setObjectName("PageSubtitle")
        rl.addWidget(self.progress_label)

        self.result_table = QTableWidget(0, 6)
        self.result_table.setHorizontalHeaderLabels(["IP", "版本", "风险", "国家", "ASN", "威胁"])
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.setColumnWidth(0, 220)
        self.result_table.setColumnWidth(1, 60)
        self.result_table.setColumnWidth(2, 70)
        self.result_table.setColumnWidth(3, 130)
        self.result_table.setColumnWidth(4, 90)

        # 结果区：Tab（表格 / 地图）
        self.result_tabs = QTabWidget()
        self.result_tabs.setDocumentMode(True)
        self.result_tabs.addTab(self.result_table, "表格")
        if MAP_OK and MapWidget is not None:
            try:
                self.map_widget = MapWidget()
                self.result_tabs.addTab(self.map_widget, "地图")
            except Exception as _e:
                print("[BatchPage MapWidget]", _e)
                self.map_widget = None
        else:
            self.map_widget = None
        rl.addWidget(self.result_tabs, 1)

        export_row = QHBoxLayout()
        self.btn_html = QPushButton("生成 HTML 报告并打开")
        self.btn_html.setObjectName("Primary")
        self.btn_html.clicked.connect(lambda: self._export(open_html=True))
        self.btn_csv = QPushButton("仅导出 CSV")
        self.btn_csv.clicked.connect(self._export_csv_only)
        self.btn_html.setEnabled(False)
        self.btn_csv.setEnabled(False)
        export_row.addStretch(1)
        export_row.addWidget(self.btn_csv)
        export_row.addWidget(self.btn_html)
        rl.addLayout(export_row)

        splitter.addWidget(right)
        splitter.setSizes([350, 700])
        root.addWidget(splitter, 1)

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 IP 列表文件", "",
                                              "文本文件 (*.txt *.csv);;所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                self.input_box.setPlainText(f.read())
        except Exception as e:
            QMessageBox.critical(self, "读取失败", str(e))

    def _run(self):
        text = self.input_box.toPlainText().strip()
        if not text:
            return
        ips = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not ips:
            return
        self.result_table.setRowCount(0)
        self.results = []
        self.progress.setMaximum(len(ips))
        self.progress.setValue(0)
        self.progress_label.setText(f"开始 · 共 {len(ips)} 个 IP")
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_html.setEnabled(False)
        self.btn_csv.setEnabled(False)

        self.worker = BatchQueryWorker(ips)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.progress_label.setText("已取消")

    def _on_progress(self, cur: int, total: int):
        self.progress.setValue(cur)
        self.progress_label.setText(f"查询中  {cur} / {total}")

    def _on_done(self, results: list):
        self.results = results
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_html.setEnabled(bool(results))
        self.btn_csv.setEnabled(bool(results))
        self.progress_label.setText(f"完成 · {len(results)} 条")
        self._fill_table(results)
        # 推送数据到地图
        if self.map_widget is not None:
            try:
                self.map_widget.set_points(results)
            except Exception as _e:
                print("[map.set_points]", _e)

    def _on_fail(self, err: str):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "批量查询失败", err)

    def _fill_table(self, results: list):
        self.result_table.setRowCount(len(results))
        for i, r in enumerate(results):
            ip = r.get("ip", "—")
            ver = r.get("ip_version", "")
            risk = r.get("risk_level", "")
            country = (r.get("geoip") or {}).get("country_name", "") or ""
            asn = (r.get("asn") or {}).get("asn", "")
            threats = r.get("threats") or []
            threats_txt = f"{len(threats)} 条" if threats else "—"

            items = [
                QTableWidgetItem(str(ip)),
                QTableWidgetItem(f"v{ver}" if ver else "—"),
                QTableWidgetItem(RISK_LABELS.get(risk, "")),
                QTableWidgetItem(country),
                QTableWidgetItem(f"AS{asn}" if asn else "—"),
                QTableWidgetItem(threats_txt),
            ]
            if risk in RISK_COLORS:
                items[2].setForeground(QColor(RISK_COLORS[risk]))
            for col, it in enumerate(items):
                self.result_table.setItem(i, col, it)

    def _export(self, open_html: bool):
        if not self.results:
            return
        self.btn_html.setEnabled(False)
        self.report_worker = ReportGenWorker(self.results, auto_open=open_html)
        self.report_worker.done.connect(self._on_report_done)
        self.report_worker.failed.connect(self._on_report_fail)
        self.report_worker.start()

    def _on_report_done(self, paths: dict):
        self.btn_html.setEnabled(True)
        self.progress_label.setText(f"报告已生成：{paths.get('html_path','')}")

    def _on_report_fail(self, err: str):
        self.btn_html.setEnabled(True)
        QMessageBox.critical(self, "报告生成失败", err)

    def _export_csv_only(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 CSV", f"networkintel_{datetime.now():%Y%m%d_%H%M%S}.csv",
            "CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["IP", "Version", "Risk", "Country", "City", "ASN",
                            "ASN Name", "Cloud", "Tor", "VPN", "Threats", "RPKI"])
                for r in self.results:
                    geo = r.get("geoip") or {}
                    asn = r.get("asn") or {}
                    cloud = r.get("cloud") or {}
                    rpki = r.get("rpki") or {}
                    w.writerow([
                        r.get("ip", ""),
                        r.get("ip_version", ""),
                        r.get("risk_level", ""),
                        geo.get("country_name", ""),
                        geo.get("city", ""),
                        asn.get("asn", ""),
                        asn.get("as_name") or asn.get("description") or "",
                        cloud.get("provider", ""),
                        "yes" if r.get("is_tor") else "",
                        "yes" if r.get("is_vpn") else "",
                        len(r.get("threats") or []),
                        rpki.get("status", ""),
                    ])
            self.progress_label.setText(f"CSV 已保存：{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))


# ╔════════════════════════════════════════════════════════════╗
# ║                     页面：数据源                           ║
# ╚════════════════════════════════════════════════════════════╝

class SourcesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.refresh()
        # 注册调度器回调，实时刷新
        try:
            register_update_callback(self._on_sched_event)
        except Exception:
            pass
        # 定时刷新（避免回调跨线程问题，UI 端轮询）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(3000)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        title = QLabel("数据源")
        title.setObjectName("PageTitle")
        sub = QLabel("双击行可立即触发该数据源更新")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        # 工具栏
        bar = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_setup = QPushButton("数据初始化…")
        self.btn_setup.setToolTip("选择数据源并串行下载（首次使用 / 重建数据库）")
        self.btn_setup.clicked.connect(self._open_setup)
        self.btn_update_all = QPushButton("全部更新")
        self.btn_update_all.setObjectName("Primary")
        self.btn_update_all.clicked.connect(self._update_all)
        bar.addWidget(self.btn_refresh)
        bar.addWidget(self.btn_setup)
        bar.addStretch(1)
        bar.addWidget(self.btn_update_all)
        root.addLayout(bar)

    def _open_setup(self):
        try:
            dlg = FirstRunSetupDialog(self.window())
            dlg.exec()
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "无法打开数据初始化", str(e))

        # 表
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["数据源", "说明", "启用", "最后更新", "记录数", "状态", "消息"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 90)
        self.table.doubleClicked.connect(self._on_double_click)
        root.addWidget(self.table, 1)

    def _on_sched_event(self, *args, **kwargs):
        # 跨线程：仅触发 UI 端轮询变更（通过 QTimer 已经轮询，故无操作）
        pass

    def refresh(self):
        try:
            cfg = get_config()
            sources = cfg.get_all_sources()
            # 从 source_meta 拉最新状态
            meta = {}
            try:
                conn = get_connection(cfg.db_path)
                try:
                    rows = conn.execute(
                        "SELECT source, last_updated, record_count, status, error_message "
                        "FROM source_meta"
                    ).fetchall()
                    for row in rows:
                        meta[row["source"]] = dict(row)
                finally:
                    conn.close()
            except Exception:
                pass

            # 调度器实时状态
            try:
                live = get_scheduler().get_job_status()
            except Exception:
                live = {}

            self.table.setRowCount(len(sources))
            for i, (name, scfg) in enumerate(sources.items()):
                m = meta.get(name, {})
                ls = live.get(name, {})

                last = m.get("last_updated") or ""
                if last:
                    last = last.replace("T", " ").split(".")[0]
                rec_count = m.get("record_count") or ls.get("record_count") or 0
                status = ls.get("status") or m.get("status") or "never"
                msg = ls.get("message") or m.get("error_message") or ""

                self.table.setItem(i, 0, QTableWidgetItem(name))
                self.table.setItem(i, 1, QTableWidgetItem(scfg.get("description", "")))
                self.table.setItem(i, 2, QTableWidgetItem("✓" if scfg.get("enabled", True) else "—"))
                self.table.setItem(i, 3, QTableWidgetItem(last or "—"))
                self.table.setItem(i, 4, QTableWidgetItem(f"{rec_count:,}" if rec_count else "—"))

                st_item = QTableWidgetItem(status)
                color = {"ok": "#16A34A", "running": "#2563EB", "error": "#DC2626",
                         "stale": "#D97706", "never": "#9CA3AF", "idle": "#9CA3AF"}.get(status, "#6B7280")
                st_item.setForeground(QColor(color))
                self.table.setItem(i, 5, st_item)
                self.table.setItem(i, 6, QTableWidgetItem(msg))
                self.table.item(i, 0).setData(Qt.UserRole, name)
        except Exception as e:
            print("[SourcesPage.refresh]", e)

    def _on_double_click(self, idx):
        row = idx.row()
        item = self.table.item(row, 0)
        if not item:
            return
        name = item.data(Qt.UserRole) or item.text()
        if QMessageBox.question(
            self, "确认", f"立即触发数据源更新：\n\n{name}\n\n该操作将在后台执行。",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                get_scheduler().trigger_now(name)
            except Exception as e:
                QMessageBox.critical(self, "失败", str(e))
            self.refresh()

    def _update_all(self):
        if QMessageBox.question(
            self, "全部更新", "确定立即触发所有已启用数据源的更新？\n（在后台执行，可能耗时较长）",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        try:
            get_scheduler().trigger_all()
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))
        self.refresh()


# ╔════════════════════════════════════════════════════════════╗
# ║                     页面：调度                             ║
# ╚════════════════════════════════════════════════════════════╝

class SchedulePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        title = QLabel("调度")
        title.setObjectName("PageTitle")
        sub = QLabel("cron 格式：分 时 日 月 周    例：0 3 * * * 表示每天凌晨 3 点")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["数据源", "启用", "cron", "下次执行", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 170)
        self.table.itemSelectionChanged.connect(self._on_select)
        root.addWidget(self.table, 1)

        # 编辑区
        edit = QHBoxLayout()
        edit.setSpacing(10)
        self.cron_input = QLineEdit()
        self.cron_input.setPlaceholderText("0 3 * * *")
        self.cron_input.setMaximumWidth(220)
        self.enable_chk = QCheckBox("启用")
        self.btn_apply = QPushButton("应用")
        self.btn_apply.setObjectName("Primary")
        self.btn_apply.clicked.connect(self._apply)
        self.btn_trigger = QPushButton("立即执行")
        self.btn_trigger.clicked.connect(self._trigger)
        self.current_label = QLabel("（选择上方一行进行编辑）")
        self.current_label.setObjectName("PageSubtitle")
        edit.addWidget(QLabel("当前选中："))
        edit.addWidget(self.current_label)
        edit.addStretch(1)
        edit.addWidget(self.enable_chk)
        edit.addWidget(self.cron_input)
        edit.addWidget(self.btn_trigger)
        edit.addWidget(self.btn_apply)
        root.addLayout(edit)

        self._current: str | None = None

    def refresh(self):
        try:
            jobs = get_scheduler().get_all_jobs_info()
        except Exception as e:
            print("[SchedulePage]", e)
            jobs = []
        self.table.setRowCount(len(jobs))
        for i, j in enumerate(jobs):
            self.table.setItem(i, 0, QTableWidgetItem(j["source"]))
            self.table.setItem(i, 1, QTableWidgetItem("✓" if j["enabled"] else "—"))
            self.table.setItem(i, 2, QTableWidgetItem(j["schedule"]))
            self.table.setItem(i, 3, QTableWidgetItem(j["next_run"] or "—"))
            st = QTableWidgetItem(j["status"])
            color = {"ok": "#16A34A", "running": "#2563EB", "error": "#DC2626",
                     "idle": "#9CA3AF"}.get(j["status"], "#6B7280")
            st.setForeground(QColor(color))
            self.table.setItem(i, 4, st)
            self.table.item(i, 0).setData(Qt.UserRole, j)

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        item = self.table.item(r, 0)
        j = item.data(Qt.UserRole) or {}
        self._current = j.get("source")
        self.current_label.setText(self._current or "—")
        self.cron_input.setText(j.get("schedule", ""))
        self.enable_chk.setChecked(bool(j.get("enabled", True)))

    def _apply(self):
        if not self._current:
            return
        new_cron = self.cron_input.text().strip()
        if not new_cron or len(new_cron.split()) != 5:
            QMessageBox.warning(self, "无效", "cron 表达式必须包含 5 段：分 时 日 月 周")
            return
        try:
            get_scheduler().update_schedule(self._current, new_cron)
            get_config().set_source_enabled(self._current, self.enable_chk.isChecked())
            QMessageBox.information(self, "已应用", f"{self._current} 调度已更新")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))
        self.refresh()

    def _trigger(self):
        if not self._current:
            return
        try:
            get_scheduler().trigger_now(self._current)
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))


# ╔════════════════════════════════════════════════════════════╗
# ║                       页面：报告                           ║
# ╚════════════════════════════════════════════════════════════╝

class ReportsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        title = QLabel("历史报告")
        title.setObjectName("PageTitle")
        sub = QLabel("双击报告以默认浏览器打开 HTML / CSV")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        bar = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_open_dir = QPushButton("打开报告目录")
        self.btn_open_dir.clicked.connect(self._open_dir)
        bar.addWidget(self.btn_refresh)
        bar.addWidget(self.btn_open_dir)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["文件名", "类型", "大小", "修改时间"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setColumnWidth(0, 360)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 110)
        self.table.doubleClicked.connect(self._open)
        root.addWidget(self.table, 1)

    def _reports_dir(self) -> Path:
        try:
            base = get_config().base_dir
        except Exception:
            base = "."
        d = Path(base) / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def refresh(self):
        d = self._reports_dir()
        files = []
        for p in sorted(d.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_file() and p.suffix.lower() in (".html", ".csv"):
                files.append(p)
        self.table.setRowCount(len(files))
        for i, p in enumerate(files):
            st = p.stat()
            size_kb = st.st_size / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            mt = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            self.table.setItem(i, 0, QTableWidgetItem(p.name))
            self.table.setItem(i, 1, QTableWidgetItem(p.suffix.lstrip(".").upper()))
            self.table.setItem(i, 2, QTableWidgetItem(size_str))
            self.table.setItem(i, 3, QTableWidgetItem(mt))
            self.table.item(i, 0).setData(Qt.UserRole, str(p))

    def _open(self, idx):
        r = idx.row()
        path = self.table.item(r, 0).data(Qt.UserRole)
        if path:
            self._open_path(path)

    def _open_dir(self):
        self._open_path(str(self._reports_dir()))

    @staticmethod
    def _open_path(path: str):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as e:
            QMessageBox.critical(None, "打开失败", str(e))


# ╔════════════════════════════════════════════════════════════╗
# ║                       页面：设置                           ║
# ╚════════════════════════════════════════════════════════════╝

class SettingsPage(QWidget):
    theme_changed = Signal(str)  # "system" / "light" / "dark"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._load()

    def _build(self):
        # 整页可滚动：低分辨率 / 小窗口下，多张卡片不会被纵向挤压（输入框压成一条线）。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        root = QVBoxLayout(content)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(18)

        title = QLabel("设置")
        title.setObjectName("PageTitle")
        sub = QLabel("修改后点击保存生效")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        # Provider Key 管理（全部保存到 .env，不写入 sources.yaml 明文）
        self.KEY_FIELDS = [
            ("MAXMIND_LICENSE_KEY", "MaxMind Key",
             "注册：https://www.maxmind.com/en/geolite2/signup"),
            ("IPINFO_TOKEN", "ipinfo",
             "https://ipinfo.io/account/token"),
            ("IP2LOCATION_API_KEY", "ip2location",
             "https://www.ip2location.io/"),
            ("ABUSEIPDB_API_KEY", "AbuseIPDB",
             "https://www.abuseipdb.com/account/api"),
        ]
        self.key_inputs: dict[str, QLineEdit] = {}
        self.key_status: dict[str, QLabel] = {}

        c, l = make_card("API KEY", self)
        intro = QLabel("Key 保存到 .env（不写入 sources.yaml）。留空表示不修改。")
        intro.setStyleSheet("color:#6B7280; font-size:12px;")
        l.addWidget(intro)

        for env_var, label, tip_text in self.KEY_FIELDS:
            head = QHBoxLayout()
            head.addWidget(QLabel(label))
            status = QLabel("未配置")
            status.setStyleSheet("color:#9CA3AF; font-size:12px;")
            head.addStretch(1)
            head.addWidget(status)
            l.addLayout(head)
            self.key_status[env_var] = status

            row = QHBoxLayout()
            inp = QLineEdit()
            inp.setEchoMode(QLineEdit.Password)
            inp.setMinimumHeight(30)
            inp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            inp.setPlaceholderText("输入新 Key 以更新（留空保持不变）")
            toggle = QToolButton()
            toggle.setCheckable(True)
            toggle.setMinimumHeight(30)
            toggle.setText("显示")
            toggle.toggled.connect(
                lambda checked, e=env_var, b=None: self._toggle_key_echo(e, checked))
            # 绑定按钮文本切换
            toggle.toggled.connect(
                lambda checked, t=toggle: t.setText("隐藏" if checked else "显示"))
            row.addWidget(inp, 1)
            row.addWidget(toggle)
            l.addLayout(row)
            self.key_inputs[env_var] = inp

            tip = QLabel(tip_text)
            tip.setStyleSheet("color:#6B7280; font-size:11px;")
            tip.setOpenExternalLinks(True)
            l.addWidget(tip)

        self.btn_save_keys = QPushButton("保存 Key")
        self.btn_save_keys.setObjectName("Primary")
        self.btn_save_keys.clicked.connect(self._save_keys)
        l.addWidget(self.btn_save_keys)
        root.addWidget(c)

        # 主题
        c, l = make_card("外观", self)
        l.addWidget(QLabel("主题"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["跟随系统 (system)", "浅色 (light)", "深色 (dark)"])
        self.theme_combo.currentIndexChanged.connect(self._on_theme_change)
        l.addWidget(self.theme_combo)
        root.addWidget(c)

        # 数据目录模式（Portable / Custom）
        c, l = make_card("数据目录模式", self)
        self.home_input = QLineEdit(); self.home_input.setReadOnly(True)
        self.home_input.setMinimumHeight(30)
        l.addWidget(QLabel("程序根目录 (home)")); l.addWidget(self.home_input)

        l.addWidget(QLabel("模式"))
        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumHeight(30)
        self.mode_combo.addItems(["Portable（数据跟随程序目录）", "Custom（自定义数据目录）"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_change)
        l.addWidget(self.mode_combo)

        l.addWidget(QLabel("数据目录 (data_dir)"))
        drow = QHBoxLayout()
        self.data_dir_input = QLineEdit(); self.data_dir_input.setReadOnly(True)
        self.data_dir_input.setMinimumHeight(30)
        self.btn_pick_data = QPushButton("选择目录…")
        self.btn_pick_data.clicked.connect(self._pick_data_dir)
        drow.addWidget(self.data_dir_input, 1)
        drow.addWidget(self.btn_pick_data)
        l.addLayout(drow)

        self.btn_save_datadir = QPushButton("保存数据目录设置")
        self.btn_save_datadir.setObjectName("Primary")
        self.btn_save_datadir.clicked.connect(self._save_data_mode)
        l.addWidget(self.btn_save_datadir)
        dhint = QLabel("切换数据目录后需重启程序生效；不会自动搬迁旧数据。")
        dhint.setStyleSheet("color:#6B7280; font-size:12px;")
        l.addWidget(dhint)
        root.addWidget(c)

        # 路径（只读展示）
        c, l = make_card("当前路径", self)
        self.base_dir_input = QLineEdit()
        self.base_dir_input.setReadOnly(True)
        self.db_path_input = QLineEdit()
        self.db_path_input.setReadOnly(True)
        self.reports_dir_input = QLineEdit()
        self.reports_dir_input.setReadOnly(True)
        l.addWidget(QLabel("项目根目录")); l.addWidget(self.base_dir_input)
        l.addWidget(QLabel("数据库")); l.addWidget(self.db_path_input)
        l.addWidget(QLabel("报告目录")); l.addWidget(self.reports_dir_input)
        root.addWidget(c)

        # 底部操作（各卡片已自带保存按钮）
        bar = QHBoxLayout()
        self.btn_reload = QPushButton("重新加载配置")
        self.btn_reload.clicked.connect(self._reload)
        bar.addWidget(self.btn_reload)
        bar.addStretch(1)
        root.addLayout(bar)
        root.addStretch(1)

    def _load(self):
        try:
            from utils import paths
            cfg = get_config()
            # Key 状态（绝不回填真实 key 到输入框）
            status = cfg.get_key_status()
            for env_var, label, _tip in self.KEY_FIELDS:
                ok = status.get(env_var, False)
                lbl = self.key_status[env_var]
                lbl.setText("已配置" if ok else "未配置")
                lbl.setStyleSheet(
                    "color:#16A34A; font-size:12px;" if ok
                    else "color:#9CA3AF; font-size:12px;")
            # 数据目录模式
            self.home_input.setText(str(paths.get_home_dir()))
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(1 if paths.get_data_mode() == "custom" else 0)
            self.mode_combo.blockSignals(False)
            self.data_dir_input.setText(str(paths.get_data_dir()))
            self.btn_pick_data.setEnabled(paths.get_data_mode() == "custom")
            # 当前路径
            self.base_dir_input.setText(cfg.base_dir)
            self.db_path_input.setText(cfg.db_path)
            self.reports_dir_input.setText(cfg.reports_dir)
            # 主题
            theme = cfg.theme or "system"
            idx = {"system": 0, "light": 1, "dark": 2}.get(theme, 0)
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(idx)
            self.theme_combo.blockSignals(False)
        except Exception as e:
            QMessageBox.warning(self, "加载配置失败", str(e))

    def _toggle_key_echo(self, env_var: str, show: bool):
        inp = self.key_inputs.get(env_var)
        if inp:
            inp.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)

    def _on_theme_change(self, idx: int):
        theme = ["system", "light", "dark"][idx]
        try:
            get_config().set_theme(theme)
        except Exception:
            pass
        self.theme_changed.emit(theme)

    def _save_keys(self):
        try:
            cfg = get_config()
            saved = []
            for env_var, label, _tip in self.KEY_FIELDS:
                val = self.key_inputs[env_var].text().strip()
                if not val:
                    continue  # 留空 = 不修改
                if env_var == "MAXMIND_LICENSE_KEY":
                    cfg.set_maxmind_key(val)
                else:
                    cfg.set_provider_key(env_var, val)
                self.key_inputs[env_var].clear()
                saved.append(label)
            self._load()
            if saved:
                QMessageBox.information(
                    self, "已保存",
                    "已更新：" + "、".join(saved) + "\n\n"
                    "· MaxMind Key 用于下载 GeoIP 本地数据库。\n"
                    "· 在线 Provider key 仅用于旁路增强，不影响离线查询。")
            else:
                QMessageBox.information(self, "未修改", "未输入任何新 Key。")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _on_mode_change(self, idx: int):
        self.btn_pick_data.setEnabled(idx == 1)

    def _pick_data_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择自定义数据目录")
        if d:
            self.data_dir_input.setText(d)

    def _save_data_mode(self):
        try:
            from utils import paths
            from utils.config_loader import upsert_env
            mode = "custom" if self.mode_combo.currentIndex() == 1 else "portable"
            env_path = paths.get_env_path()
            upsert_env(env_path, "NETWORKINTEL_DATA_MODE", mode)
            if mode == "custom":
                data_dir = self.data_dir_input.text().strip()
                if not data_dir:
                    QMessageBox.warning(self, "未选择目录", "Custom 模式需选择数据目录。")
                    return
                upsert_env(env_path, "NETWORKINTEL_DATA_DIR", data_dir)
                # 立即在自定义目录下创建运行时子目录
                from pathlib import Path as _P
                for sub in ("live", "cache", "logs", "reports",
                            "snapshots", "backups", "gdrive_sync"):
                    (_P(data_dir) / sub).mkdir(parents=True, exist_ok=True)
            else:
                # 切回 portable：忽略 DATA_DIR（置空）
                upsert_env(env_path, "NETWORKINTEL_DATA_DIR", "")
            QMessageBox.information(
                self, "已保存",
                f"数据目录模式：{mode}\n\n请重启程序以使新数据目录生效。")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _reload(self):
        try:
            reload_config()
            self._load()
            QMessageBox.information(self, "已重载", "配置已重新加载")
        except Exception as e:
            QMessageBox.critical(self, "重载失败", str(e))


# ╔════════════════════════════════════════════════════════════╗
# ║              首次初始化 / 数据源选择下载（Phase 2）        ║
# ╚════════════════════════════════════════════════════════════╝

class SetupDownloadWorker(QThread):
    """
    后台串行下载工作线程。
    复用 datasources.setup_profiles.download_sources（逐个执行，绝不并发，
    与 do_update.py 的串行 CLI 路径一致，规避空库并发写的 database is locked 风险）。
    """
    progress = Signal(dict)   # 转发 download_sources 的 event
    finished_summary = Signal(dict)

    def __init__(self, names: list, parent=None):
        super().__init__(parent)
        self._names = list(names)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            # 首次下载前确保库与表结构存在（空库直接 load 会 no such table）
            setup_profiles.prepare_database()
            summary = setup_profiles.download_sources(
                self._names,
                on_progress=lambda ev: self.progress.emit(ev),
                should_cancel=lambda: self._cancel,
            )
        except Exception as e:  # 兜底，绝不让线程崩溃
            summary = {"total": len(self._names), "ok": 0,
                       "failed": len(self._names), "cancelled": False,
                       "results": [], "error": str(e)}
        self.finished_summary.emit(summary)


class FirstRunSetupDialog(QDialog):
    """
    数据初始化向导：选择数据源（最小/推荐/完整/自定义）并串行下载。
    可随时关闭（「稍后」）；不强制、不阻断程序使用。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据初始化 / 数据源下载")
        self.setMinimumSize(640, 600)
        self.worker: "SetupDownloadWorker | None" = None
        self._available_keys = setup_profiles.configured_keys()
        self._custom_checks: dict[str, QCheckBox] = {}
        self._build()
        self._refresh_summary()

    # ── UI ──
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)

        title = QLabel("数据初始化")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        intro = QLabel(
            "选择要下载的离线数据源。下载将**逐个串行**执行（避免并发写库冲突），"
            "可能耗时较长，失败的源会跳过并在结尾汇总。\n"
            "geoip 需要 MaxMind Key —— 未配置时会自动跳过，可稍后在设置页填写后再下载。")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#6B7280; font-size:12px;")
        root.addWidget(intro)

        # 预设单选
        self.btn_group = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}
        rc, rl = make_card("下载方案", self)
        for key in (*setup_profiles.PROFILE_ORDER, "custom"):
            rb = QRadioButton(
                f"{setup_profiles.PROFILE_LABELS[key]} — "
                f"{setup_profiles.PROFILE_DESCRIPTIONS[key]}")
            rb.toggled.connect(self._on_profile_toggle)
            self.btn_group.addButton(rb)
            self.radios[key] = rb
            rl.addWidget(rb)
        root.addWidget(rc)

        # 自定义勾选区（默认隐藏）
        self.custom_card, ccl = make_card("自定义数据源", self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(220)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setSpacing(4)
        for item in setup_profiles.source_catalog():
            name = item["name"]
            label = name
            if item["description"]:
                label += f" — {item['description']}"
            cb = QCheckBox(label)
            cb.setChecked(item["in_recommended"])
            req = item["requires_key"]
            if req and req not in self._available_keys:
                cb.setChecked(False)
                cb.setEnabled(False)
                cb.setText(label + f"  （需要 {req}，请先在设置页填写）")
            cb.toggled.connect(self._refresh_summary)
            self._custom_checks[name] = cb
            hl.addWidget(cb)
        hl.addStretch(1)
        scroll.setWidget(holder)
        ccl.addWidget(scroll)
        self.custom_card.setVisible(False)
        root.addWidget(self.custom_card)

        # 摘要
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color:#374151; font-size:12px;")
        root.addWidget(self.summary_label)

        # 进度区（默认隐藏）
        self.progress_box = QWidget()
        pv = QVBoxLayout(self.progress_box)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(6)
        self.overall_label = QLabel("准备中…")
        self.overall_label.setStyleSheet("font-size:12px; color:#374151;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.current_label = QLabel("")
        self.current_label.setStyleSheet("font-size:11px; color:#6B7280;")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)
        pv.addWidget(self.overall_label)
        pv.addWidget(self.progress_bar)
        pv.addWidget(self.current_label)
        pv.addWidget(self.log)
        self.progress_box.setVisible(False)
        root.addWidget(self.progress_box, 1)

        # 按钮栏
        bar = QHBoxLayout()
        self.btn_start = QPushButton("开始下载")
        self.btn_start.setObjectName("Primary")
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton("取消下载")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setVisible(False)
        self.btn_close = QPushButton("稍后")
        self.btn_close.clicked.connect(self.reject)
        bar.addStretch(1)
        bar.addWidget(self.btn_cancel)
        bar.addWidget(self.btn_close)
        bar.addWidget(self.btn_start)
        root.addLayout(bar)

        # 默认方案：全部子控件就绪后再勾选，避免 toggled 提前触发空引用
        self.radios["recommended"].setChecked(True)

    # ── 选择逻辑 ──
    def _current_profile(self) -> str:
        for key, rb in self.radios.items():
            if rb.isChecked():
                return key
        return "recommended"

    def _selection(self) -> dict:
        profile = self._current_profile()
        custom = None
        if profile == "custom":
            custom = [n for n, cb in self._custom_checks.items() if cb.isChecked()]
        return setup_profiles.resolve_selection(
            profile, custom=custom, available_keys=self._available_keys)

    def _on_profile_toggle(self):
        if not hasattr(self, "custom_card"):
            return  # 构建期间提前触发，忽略
        self.custom_card.setVisible(self._current_profile() == "custom")
        self._refresh_summary()

    def _refresh_summary(self):
        sel = self._selection()
        n = len(sel["selected"])
        parts = [f"将下载 <b>{n}</b> 个数据源"]
        if sel["selected"]:
            parts.append("：" + "、".join(sel["selected"]))
        text = "".join(parts)
        if sel["skipped"]:
            names = "、".join(s["name"] for s in sel["skipped"])
            text += (f"<br><span style='color:#D97706;'>跳过（缺 Key）：{names}</span>")
        if n == 0:
            text = "<span style='color:#DC2626;'>未选择任何可下载的数据源。</span>"
        self.summary_label.setTextFormat(Qt.RichText)
        self.summary_label.setText(text)
        if self.worker is None or not self.worker.isRunning():
            self.btn_start.setEnabled(n > 0)

    # ── 下载流程 ──
    def _start(self):
        sel = self._selection()
        names = sel["selected"]
        if not names:
            QMessageBox.warning(self, "未选择", "请至少选择一个可下载的数据源。")
            return
        msg = f"即将串行下载 {len(names)} 个数据源：\n\n" + "、".join(names)
        if sel["skipped"]:
            msg += "\n\n跳过（缺 Key）：" + "、".join(s["name"] for s in sel["skipped"])
        msg += "\n\n确认开始？"
        if QMessageBox.question(self, "确认下载", msg,
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        # 锁定选择 UI，展示进度
        for rb in self.radios.values():
            rb.setEnabled(False)
        self.custom_card.setEnabled(False)
        self.btn_start.setVisible(False)
        self.btn_close.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.progress_box.setVisible(True)
        self._total = len(names)
        self._done = 0
        self.progress_bar.setValue(0)
        self.overall_label.setText(f"0 / {self._total} 完成")
        self.log.clear()

        self.worker = SetupDownloadWorker(names, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_summary.connect(self._on_finished)
        self.worker.start()

    def _cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.current_label.setText("已请求取消，等待当前数据源完成…")

    def _on_progress(self, ev: dict):
        phase = ev.get("phase")
        if phase == "source_start":
            self.current_label.setText(f"开始：{ev['name']} …")
        elif phase == "source_progress":
            self.current_label.setText(
                f"{ev['name']}：{ev.get('step', '')} ({ev.get('pct', 0)}%)")
        elif phase == "source_done":
            self._done += 1
            r = ev["result"]
            if r["success"]:
                self.log.appendPlainText(
                    f"[OK]   {r['name']}  ·  {r['record_count']:,} 条")
            else:
                self.log.appendPlainText(
                    f"[FAIL] {r['name']}  ·  {r.get('error') or '未知错误'}")
            pct = int(self._done / max(1, self._total) * 100)
            self.progress_bar.setValue(pct)
            self.overall_label.setText(f"{self._done} / {self._total} 完成")

    def _on_finished(self, summary: dict):
        self.btn_cancel.setVisible(False)
        self.btn_close.setEnabled(True)
        self.btn_close.setText("完成")
        self.current_label.setText("")
        if summary.get("error"):
            self.log.appendPlainText(f"[异常] {summary['error']}")
        tail = "（已取消剩余）" if summary.get("cancelled") else ""
        self.overall_label.setText(
            f"完成：成功 {summary['ok']}，失败 {summary['failed']}，"
            f"共 {summary['total']} {tail}")
        # 通知主窗口刷新状态
        p = self.parent()
        if p is not None and hasattr(p, "refresh_after_setup"):
            try:
                p.refresh_after_setup()
            except Exception:
                pass

    def closeEvent(self, ev):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(
                self, "下载进行中", "下载仍在进行，确定关闭？\n（当前数据源会继续完成，但不再下载后续源）",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                ev.ignore()
                return
            self.worker.cancel()
        ev.accept()


# ╔════════════════════════════════════════════════════════════╗
# ║                        主窗口                              ║
# ╚════════════════════════════════════════════════════════════╝

class MainWindow(QMainWindow):
    PAGES = [
        ("查询",   "F1"),
        ("批量",   "F2"),
        ("网络",   "F3"),
        ("威胁库", "F4"),
        ("数据源", "F5"),
        ("调度",   "F6"),
        ("报告",   "F7"),
        ("设置",   "F8"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetworkIntel")
        self.resize(1200, 760)
        self.setMinimumSize(960, 600)

        self._theme_mode = "system"  # system / light / dark
        self._needs_setup = False
        self._setup_prompted = False
        # 路径初始化完成后、构建任何读库页面之前，先确保数据库与全部基础表存在。
        # 否则全新 / 空 portable 目录下，统计条 / 威胁库 / 查询页在构造时直接读表，
        # 会触发 sqlite3.OperationalError: no such table（只建表、不下载、不改 needs_setup）。
        self._ensure_database_ready()
        self._build_ui()
        self._apply_theme()

        # 启动调度器
        if BACKEND_OK:
            try:
                sched = get_scheduler()
                sched.start()
            except Exception as e:
                print("[scheduler.start]", e)

        # 首次运行：缺库/空库时主动弹出数据初始化向导（可关闭，不强制）
        if BACKEND_OK and getattr(self, "_needs_setup", False):
            QTimer.singleShot(700, self._maybe_prompt_setup)

    def _ensure_database_ready(self):
        """
        启动期幂等建库：保证空库首次运行时任何读表路径都不崩溃。
        只建表、不下载数据、不改变 needs_setup 判断；任何失败都降级，绝不阻断启动。
        """
        if not BACKEND_OK:
            return
        try:
            setup_profiles.ensure_runtime_database(get_config().db_path)
        except Exception as e:
            print("[ensure_database_ready]", e)

    # ────── UI ──────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # 左侧边栏
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(240)
        sv = QVBoxLayout(self.sidebar)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)

        title = QLabel("NetworkIntel")
        title.setObjectName("SidebarTitle")
        sub = QLabel("OFFLINE IP INTELLIGENCE")
        sub.setObjectName("SidebarSubtitle")
        sv.addWidget(title)
        sv.addWidget(sub)

        self.nav_buttons: list[QPushButton] = []
        for i, (name, key) in enumerate(self.PAGES):
            btn = QPushButton(f"  {name}")
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self._go(idx))
            sv.addWidget(btn)
            self.nav_buttons.append(btn)
            QShortcut(QKeySequence(key), self, activated=lambda idx=i: self._go(idx))

        sv.addStretch(1)

        # 主题切换按钮
        self.theme_toggle = QPushButton("  切换主题")
        self.theme_toggle.setObjectName("NavButton")
        self.theme_toggle.setCursor(Qt.PointingHandCursor)
        self.theme_toggle.clicked.connect(self._toggle_theme)
        sv.addWidget(self.theme_toggle)

        version = QLabel(f"  v{APP_VERSION}")
        version.setStyleSheet("color:#9CA3AF; font-size:11px; padding:14px 20px;")
        sv.addWidget(version)

        h.addWidget(self.sidebar)

        # 右侧主区
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        self.stack = QStackedWidget()
        self.page_query = QueryPage()
        self.page_batch = BatchPage()
        # 新增扩展页面（容错：如果加载失败用占位页）
        if EXT_OK:
            self.page_network = NetworkPage()
            self.page_threats = ThreatLibraryPage()
        else:
            self.page_network = self._placeholder_page("网络", "扩展模块加载失败")
            self.page_threats = self._placeholder_page("威胁库", "扩展模块加载失败")
        self.page_sources = SourcesPage()
        self.page_schedule = SchedulePage()
        self.page_reports = ReportsPage()
        self.page_settings = SettingsPage()
        self.page_settings.theme_changed.connect(self._set_theme)
        for p in [self.page_query, self.page_batch,
                  self.page_network, self.page_threats,
                  self.page_sources, self.page_schedule,
                  self.page_reports, self.page_settings]:
            self.stack.addWidget(p)

        rv.addWidget(self.stack, 1)

        # 状态栏
        sb = QWidget()
        sb.setObjectName("StatusBar")
        sb.setFixedHeight(28)
        sbl = QHBoxLayout(sb)
        sbl.setContentsMargins(16, 0, 16, 0)
        if not BACKEND_OK:
            self.status_text = QLabel(f"⚠ 后端加载失败：{BACKEND_ERR.splitlines()[0]}")
            self.status_text.setStyleSheet("color:#DC2626;")
        else:
            map_info = "" if MAP_OK else "  ·  地图不可用"
            self._needs_setup = False
            try:
                self._needs_setup = setup_profiles.needs_setup(get_config().db_path)
            except Exception:
                pass
            if self._needs_setup:
                self.status_text = QLabel(
                    "⚠ 数据库未初始化 · 请到「数据源」页点击「数据初始化…」选择并下载数据源")
                self.status_text.setStyleSheet("color:#D97706;")
            else:
                self.status_text = QLabel(f"就绪 · 调度器已启动{map_info}")
        sbl.addWidget(self.status_text)
        sbl.addStretch(1)
        self.cfg_label = QLabel("")
        try:
            cfg = get_config()
            self.cfg_label.setText(f"v{APP_VERSION}  ·  DB: {cfg.db_path}")
        except Exception:
            self.cfg_label.setText(f"v{APP_VERSION}")
        sbl.addWidget(self.cfg_label)
        rv.addWidget(sb)

        h.addWidget(right, 1)

        self._go(0)

        # 退出快捷键
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)

    def _go(self, idx: int):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == idx)

    def _maybe_prompt_setup(self):
        """首次运行时弹出数据初始化向导（仅一次，可被用户关闭）。"""
        if self._setup_prompted:
            return
        self._setup_prompted = True
        try:
            dlg = FirstRunSetupDialog(self)
            dlg.exec()
            self.refresh_after_setup()
        except Exception as e:
            print("[first-run setup]", e)

    def refresh_after_setup(self):
        """数据下载/初始化后刷新状态栏与数据源页。"""
        try:
            self._needs_setup = setup_profiles.needs_setup(get_config().db_path)
        except Exception:
            self._needs_setup = False
        try:
            if not self._needs_setup:
                map_info = "" if MAP_OK else "  ·  地图不可用"
                self.status_text.setText(f"就绪 · 调度器已启动{map_info}")
                self.status_text.setStyleSheet("")
        except Exception:
            pass
        try:
            self.page_sources.refresh()
        except Exception:
            pass

    def _placeholder_page(self, title: str, msg: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 28, 32, 24)
        t = QLabel(title); t.setObjectName("PageTitle")
        m = QLabel(msg); m.setObjectName("PageSubtitle")
        v.addWidget(t); v.addWidget(m); v.addStretch(1)
        return w

    # ────── 主题 ──────
    def _set_theme(self, theme: str):
        self._theme_mode = theme
        try:
            get_config().set_theme(theme)
        except Exception:
            pass
        self._apply_theme()

    def _toggle_theme(self):
        order = ["light", "dark", "system"]
        cur = self._theme_mode if self._theme_mode in order else "system"
        nxt = order[(order.index(cur) + 1) % len(order)]
        self._set_theme(nxt)

    def _detect_system_dark(self) -> bool:
        try:
            sh = QGuiApplication.styleHints()
            cs = getattr(sh, "colorScheme", None)
            if callable(cs):
                v = cs()
                return str(v).lower().endswith("dark")
        except Exception:
            pass
        # fallback: 看 palette 亮度
        c = QApplication.palette().color(QPalette.Window)
        return (c.red() + c.green() + c.blue()) / 3 < 128

    def _apply_theme(self):
        # 读配置
        try:
            cfg_theme = get_config().theme
            if self._theme_mode == "system" and cfg_theme in ("light", "dark", "system"):
                self._theme_mode = cfg_theme
        except Exception:
            pass

        mode = self._theme_mode
        if mode == "system":
            dark = self._detect_system_dark()
        else:
            dark = (mode == "dark")
        self.setStyleSheet(DARK_QSS if dark else LIGHT_QSS)

    def closeEvent(self, ev):
        try:
            get_scheduler().stop()
        except Exception:
            pass
        ev.accept()


# ╔════════════════════════════════════════════════════════════╗
# ║                          入口                              ║
# ╚════════════════════════════════════════════════════════════╝

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("NetworkIntel")
    app.setOrganizationName("NetworkIntel")

    if not BACKEND_OK:
        QMessageBox.critical(
            None, "后端加载失败",
            "无法加载后端模块。请确认从项目根目录运行，且 requirements.txt 已安装。\n\n"
            + BACKEND_ERR
        )

    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
