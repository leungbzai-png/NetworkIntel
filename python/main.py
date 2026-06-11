"""
NetworkIntel - Textual TUI 主程序
全可视化界面，支持深色/浅色/跟随系统主题
"""

import os
import sys
import threading
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding

from textual.widgets import (
    Header, Footer, TabbedContent, TabPane,
    Input, Button, Label, DataTable, ProgressBar,
    Static, Switch, Select, RichLog, Markdown
)
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual import work, on
from textual.screen import ModalScreen
from textual.message import Message
from rich.text import Text
from rich.panel import Panel


# ── 颜色和标签常量 ────────────────────────────────────────────
RISK_STYLE = {
    "critical": "bold red",
    "high":     "bold #ff8c00",
    "medium":   "bold yellow",
    "low":      "bold green",
    "info":     "bold blue",
    "clean":    "bold green",
}
RISK_LABEL = {
    "critical": "🔴 严重",
    "high":     "🟠 高危",
    "medium":   "🟡 中危",
    "low":      "🟢 低危",
    "info":     "🔵 注意",
    "clean":    "✅ 正常",
}
CLOUD_ICON = {
    "aws":        "☁ AWS",
    "azure":      "☁ Azure",
    "gcp":        "☁ GCP",
    "cloudflare": "🟠 CF",
    "hetzner":    "☁ Hetzner",
    "vultr":      "☁ Vultr",
}


# ── 自定义消息 ─────────────────────────────────────────────────
class QueryResult(Message):
    def __init__(self, result: dict):
        super().__init__()
        self.result = result

class BatchProgress(Message):
    def __init__(self, current: int, total: int):
        super().__init__()
        self.current = current
        self.total = total

class BatchDone(Message):
    def __init__(self, results: list, report_paths: dict):
        super().__init__()
        self.results = results
        self.report_paths = report_paths

class SchedulerStatus(Message):
    def __init__(self, source: str, status: str, message: str):
        super().__init__()
        self.source = source
        self.status = status
        self.message = message


# ── 结果展示组件 ──────────────────────────────────────────────

class ResultCard(Static):
    """IP查询结果卡片"""

    DEFAULT_CSS = """
    ResultCard {
        border: solid $accent;
        border-radius: 1;
        padding: 1 2;
        margin: 1 0;
        background: $surface;
    }
    ResultCard .card-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    ResultCard .row-label {
        color: $text-muted;
        width: 14;
    }
    ResultCard .section-head {
        text-style: bold;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, result: dict):
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        r = self.result
        ip = r.get("ip", "")

        if r.get("error"):
            yield Label(f"[red]❌ {ip}[/red]\n错误: {r['error']}")
            return

        risk = r.get("risk_level", "clean")
        risk_style = RISK_STYLE.get(risk, "")
        risk_label = RISK_LABEL.get(risk, risk)

        if r.get("is_special"):
            yield Label(f"[bold cyan]{ip}[/bold cyan]  [{risk_style}]{risk_label}[/]")
            yield Label(f"[dim]🔒 {r.get('special_description', '特殊地址')}[/dim]")
            return

        # IP标题行
        yield Label(f"[bold cyan]{ip}[/bold cyan]  [{risk_style}]{risk_label}[/]",
                    classes="card-title")

        # 基础信息区
        yield Label("[dim]── 基础信息 ──────────────────────────────[/dim]",
                    classes="section-head")
        yield from self._geo_rows(r)
        yield from self._asn_rows(r)

        # 网络情报区
        yield Label("[dim]── 网络情报 ──────────────────────────────[/dim]",
                    classes="section-head")
        yield from self._network_rows(r)

        # 威胁情报区
        yield Label("[dim]── 威胁情报 ──────────────────────────────[/dim]",
                    classes="section-head")
        yield from self._threat_rows(r)

    def _geo_rows(self, r):
        geo = r.get("geoip") or {}
        if geo:
            location = " / ".join(filter(None, [
                geo.get("city"), geo.get("region"), geo.get("country_name")
            ])) or "—"
            cc = geo.get("country_code", "")
            yield self._row("🌍 地理位置", f"{cc} {location}")
        else:
            yield self._row("🌍 地理位置", "[dim]无数据[/dim]")

    def _asn_rows(self, r):
        asn = r.get("asn") or {}
        rir = r.get("rir") or {}
        if asn:
            yield self._row("🏢 ASN", f"AS{asn.get('asn','')} [dim]{asn.get('as_name','')}[/dim]")
            yield self._row("📡 BGP前缀", f"[cyan]{asn.get('network','—')}[/cyan]")
        if rir:
            yield self._row("🗂  RIR", f"{rir.get('rir','')} [dim]({rir.get('status','')})[/dim]")

    def _network_rows(self, r):
        rpki = r.get("rpki") or {}
        cloud = r.get("cloud") or {}
        pdb = r.get("peeringdb") or {}
        whois = r.get("whois") or {}

        status = rpki.get("status", "not-found")
        rpki_icons = {"valid": "✅ Valid", "invalid": "❌ Invalid", "not-found": "— 未找到"}
        rpki_color = {"valid": "green", "invalid": "red", "not-found": "dim"}
        yield self._row("🔐 RPKI",
            f"[{rpki_color.get(status,'dim')}]{rpki_icons.get(status, status)}[/]")

        if cloud:
            prov = cloud.get("provider", "")
            region = cloud.get("region", "")
            svc = cloud.get("service", "")
            icon = CLOUD_ICON.get(prov, f"☁ {prov}")
            extra = " / ".join(filter(None, [region, svc]))
            yield self._row("☁  云服务商", f"{icon} [dim]{extra}[/dim]")
        else:
            yield self._row("☁  云服务商", "[dim]—[/dim]")

        if pdb:
            ixps = pdb.get("ix_list", [])
            ixp_str = ", ".join(ixps[:3]) + ("..." if len(ixps) > 3 else "") if ixps else "—"
            yield self._row("🔗 IXP", ixp_str)

        if whois:
            yield self._row("📋 WHOIS", f"[dim]{whois.get('org_name','—')} (缓存: {whois.get('cached_at','')[:10]})[/dim]")

    def _threat_rows(self, r):
        threats = r.get("threats", [])
        is_tor = r.get("is_tor", False)
        is_vpn = r.get("is_vpn", False)

        tor_color = "red" if is_tor else "green"
        vpn_color = "yellow" if is_vpn else "green"
        yield self._row("🧅 Tor出口",
            f"[{tor_color}]{'✓ 是' if is_tor else '✗ 否'}[/]")
        yield self._row("🔒 VPN",
            f"[{vpn_color}]{'✓ 是' if is_vpn else '✗ 否'}[/]")

        if threats:
            tags = " ".join(
                f"[on red][white] {t['list_name']} [/white][/on red]"
                for t in threats[:5]
            )
            if len(threats) > 5:
                tags += f" [dim]+{len(threats)-5}条[/dim]"
            yield self._row("⚠  威胁情报", tags)
        else:
            yield self._row("⚠  威胁情报", "[green]✗ 未命中[/green]")

    def _row(self, label: str, value: str) -> Label:
        return Label(f"[dim]{label}[/dim]  {value}")


# ── 主页：查询面板 ─────────────────────────────────────────────

class QueryScreen(Container):
    """主查询页：左侧历史，右侧结果"""

    DEFAULT_CSS = """
    QueryScreen {
        layout: horizontal;
        height: 1fr;
    }
    #history-panel {
        width: 30;
        border-right: solid $accent-darken-2;
        padding: 0 1;
    }
    #result-panel {
        width: 1fr;
        padding: 0 1;
    }
    #input-row {
        height: 3;
        layout: horizontal;
        margin-bottom: 1;
    }
    #ip-input {
        width: 1fr;
    }
    #query-btn {
        width: 10;
        margin-left: 1;
    }
    #history-title {
        text-style: bold;
        color: $text-muted;
        margin-bottom: 1;
        padding: 1 0 0 0;
    }
    .history-item {
        height: 2;
        padding: 0 1;
        border-bottom: solid $background-darken-1;
    }
    .history-item:hover {
        background: $surface-lighten-1;
    }
    .history-item.risk-critical { border-left: solid red; }
    .history-item.risk-high     { border-left: solid darkorange; }
    .history-item.risk-medium   { border-left: solid yellow; }
    .history-item.risk-clean    { border-left: solid green; }
    .history-item.risk-info     { border-left: solid blue; }
    """

    history: reactive = reactive([])
    current_result: reactive = reactive(None)

    def compose(self) -> ComposeResult:
        with Vertical(id="history-panel"):
            yield Label("📋 查询历史", id="history-title")
            yield ScrollableContainer(id="history-list")

        with Vertical(id="result-panel"):
            with Horizontal(id="input-row"):
                yield Input(
                    placeholder="输入 IP 地址，如 1.1.1.1",
                    id="ip-input",
                )
                yield Button("🔍 查询", variant="primary", id="query-btn")
            yield ScrollableContainer(id="result-container")

    @on(Button.Pressed, "#query-btn")
    def on_query_button(self) -> None:
        ip_input = self.query_one("#ip-input", Input)
        self._do_query(ip_input.value.strip())

    @on(Input.Submitted, "#ip-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_query(event.value.strip())

    @work(thread=True)
    def _do_query(self, ip_str: str) -> None:
        if not ip_str:
            return
        try:
            from query.engine import query_ip
            result = query_ip(ip_str)
        except Exception as e:
            result = {"ip": ip_str, "error": str(e)}
        # Schedule UI update on main thread
        self.app.call_from_thread(self._display_result, result)

    def _display_result(self, result: dict) -> None:
        """在主线程中更新UI"""
        try:
            container = self.query_one("#result-container", ScrollableContainer)
            container.remove_children()
            container.mount(ResultCard(result))

            from query.engine import get_query_history
            history = get_query_history(limit=30)
            self._update_history(history)
        except Exception as e:
            self.notify(f"显示结果错误: {e}", severity="error")

    def on_query_result(self, msg: QueryResult) -> None:
        # Kept for compat but no longer used
        self._display_result(msg.result)

    def _update_history(self, history: list) -> None:
        hist_list = self.query_one("#history-list", ScrollableContainer)
        hist_list.remove_children()
        for item in history:
            ip = item.get("query_input", "")
            risk = item.get("risk_level", "clean")
            risk_label = RISK_LABEL.get(risk, risk)
            time_str = item.get("queried_at", "")[:16]
            lbl = Label(f"[bold]{ip}[/bold]\n[dim]{risk_label} {time_str}[/dim]")
            lbl.classes = f"history-item risk-{risk}"
            hist_list.mount(lbl)

    def on_mount(self) -> None:
        """页面挂载时加载历史"""
        try:
            from query.engine import get_query_history
            self._update_history(get_query_history(30))
        except Exception:
            pass


# ── 批量查询页 ─────────────────────────────────────────────────

class BatchScreen(Container):
    """批量查询页"""

    DEFAULT_CSS = """
    BatchScreen {
        padding: 1 2;
    }
    #batch-input {
        height: 8;
        margin-bottom: 1;
    }
    #batch-progress-bar {
        margin: 1 0;
    }
    #batch-status {
        color: $text-muted;
        margin-bottom: 1;
    }
    .batch-btn { margin-right: 1; }
    #batch-log {
        height: 1fr;
        border: solid $accent-darken-2;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold]批量IP查询[/bold]\n[dim]每行一个IP，或输入文件路径（.txt）[/dim]",
                    markup=True)
        yield Input(
            placeholder="粘贴多个IP（每行一个），或输入文件路径如 E:\\ips.txt",
            id="batch-input",
        )
        with Horizontal():
            yield Button("▶ 开始查询", variant="primary",   id="btn-batch-run",   classes="batch-btn")
            yield Button("📂 浏览文件", variant="default",  id="btn-batch-file",  classes="batch-btn")
            yield Button("📊 导出HTML", variant="success",  id="btn-export-html", classes="batch-btn")
            yield Button("📋 导出CSV",  variant="default",  id="btn-export-csv",  classes="batch-btn")
        yield ProgressBar(id="batch-progress-bar", show_eta=True)
        yield Label("", id="batch-status")
        yield RichLog(id="batch-log", highlight=True, markup=True)

        self._results: list = []
        self._report_paths: dict = {}

    @on(Button.Pressed, "#btn-batch-run")
    def run_batch(self) -> None:
        inp = self.query_one("#batch-input", Input).value.strip()
        if not inp:
            return

        # 判断是文件路径还是直接粘贴的IP
        if os.path.isfile(inp):
            with open(inp, "r", encoding="utf-8") as f:
                raw = f.read()
        else:
            raw = inp

        from utils.ip_utils import parse_ip_input
        ips, errors = parse_ip_input(raw)

        if not ips:
            log = self.query_one("#batch-log", RichLog)
            log.write("[red]未找到有效IP地址[/red]")
            return

        log = self.query_one("#batch-log", RichLog)
        log.clear()
        log.write(f"[green]共 {len(ips)} 个IP，开始查询...[/green]")
        if errors:
            for e in errors[:5]:
                log.write(f"[yellow]⚠ {e}[/yellow]")

        pb = self.query_one("#batch-progress-bar", ProgressBar)
        pb.update(total=len(ips), progress=0)

        self._do_batch(ips)

    @work(thread=True)
    def _do_batch(self, ips: list) -> None:
        from query.engine import query_batch
        total = len(ips)

        def progress_cb(current, total):
            self.app.post_message(BatchProgress(current, total))

        results = query_batch(ips, progress_callback=progress_cb)
        self.app.post_message(BatchDone(results, {}))

    def on_batch_progress(self, msg: BatchProgress) -> None:
        pb = self.query_one("#batch-progress-bar", ProgressBar)
        status = self.query_one("#batch-status", Label)
        pb.update(progress=msg.current)
        status.update(f"进度: {msg.current}/{msg.total}")

        log = self.query_one("#batch-log", RichLog)
        if msg.current % 10 == 0 or msg.current == msg.total:
            log.write(f"[dim]已处理 {msg.current}/{msg.total}[/dim]")

    def on_batch_done(self, msg: BatchDone) -> None:
        self._results = msg.results
        status = self.query_one("#batch-status", Label)
        risk_counts = {}
        for r in self._results:
            risk = r.get("risk_level", "clean")
            risk_counts[risk] = risk_counts.get(risk, 0) + 1

        summary = " | ".join(f"{RISK_LABEL.get(k,k)}: {v}" for k, v in risk_counts.items())
        status.update(f"[green]查询完成[/green] — {summary}")

        log = self.query_one("#batch-log", RichLog)
        log.write(f"[bold green]✓ 查询完成，{len(self._results)} 个IP[/bold green]")
        log.write(f"统计: {summary}")
        log.write("点击 [bold]导出HTML[/bold] 或 [bold]导出CSV[/bold] 保存报告")

        # 自动生成报告
        self._export(auto_open=True)

    @on(Button.Pressed, "#btn-export-html")
    def export_html(self) -> None:
        if self._results:
            self._export(auto_open=True)

    @on(Button.Pressed, "#btn-export-csv")
    def export_csv(self) -> None:
        if self._results and self._report_paths.get("csv_path"):
            import webbrowser
            webbrowser.open(f"file:///{self._report_paths['csv_path'].replace(os.sep, '/')}")

    def _export(self, auto_open: bool = False) -> None:
        try:
            from reports.generator import generate_reports
            paths = generate_reports(self._results, auto_open=auto_open)
            self._report_paths = paths
            log = self.query_one("#batch-log", RichLog)
            log.write(f"[green]HTML报告: {paths['html_path']}[/green]")
            log.write(f"[green]CSV报告:  {paths['csv_path']}[/green]")
        except Exception as e:
            log = self.query_one("#batch-log", RichLog)
            log.write(f"[red]导出失败: {e}[/red]")


# ── 数据源状态页 ──────────────────────────────────────────────

class SourcesScreen(Container):
    """数据源状态页"""

    DEFAULT_CSS = """
    SourcesScreen { padding: 1 2; }
    #sources-table { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold]数据源状态[/bold]  [dim]双击行手动触发更新[/dim]")
        yield DataTable(id="sources-table", cursor_type="row")
        yield Button("🔄 全部更新", variant="primary", id="btn-update-all")

    def on_mount(self) -> None:
        self.call_after_refresh(self._setup)

    def _setup(self) -> None:
        table = self.query_one("#sources-table", DataTable)
        table.add_columns(
            "数据源", "状态", "上次更新", "下次更新",
            "记录数", "调度频率", "说明"
        )
        self._refresh_table()

    def _refresh_table(self) -> None:
        try:
            from query.engine import get_source_status
            from scheduler.scheduler import get_scheduler
            sched = get_scheduler()
            statuses = get_source_status()

            table = self.query_one("#sources-table", DataTable)
            table.clear()

            for s in statuses:
                status_map = {
                    "ok":    Text("✅ 正常", style="green"),
                    "error": Text("❌ 错误", style="red"),
                    "never": Text("⭕ 未初始化", style="dim"),
                    "stale": Text("⚠️ 过期", style="yellow"),
                }
                st = status_map.get(s.get("status", "never"),
                                    Text(s.get("status", ""), style="dim"))
                last = (s.get("last_updated") or "")[:16]
                nxt = sched.get_next_run(s["source"]) or "—"
                cnt = f"{s.get('record_count', 0):,}"
                sch = s.get("schedule", "")
                desc = s.get("description", "")[:30]
                table.add_row(s["source"], st, last, nxt, cnt, sch, desc)
        except Exception:
            pass

    @on(Button.Pressed, "#btn-update-all")
    def update_all(self) -> None:
        from scheduler.scheduler import get_scheduler
        get_scheduler().trigger_all()
        self.notify("已触发所有数据源更新")

    @on(DataTable.RowSelected, "#sources-table")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        try:
            source = str(event.data_table.get_cell_at((event.cursor_row, 0)))
            from scheduler.scheduler import get_scheduler
            get_scheduler().trigger_now(source)
            self.notify(f"已触发 {source} 更新")
        except Exception:
            pass


# ── 调度管理页 ────────────────────────────────────────────────

class SchedulerScreen(Container):
    """调度任务管理页"""

    DEFAULT_CSS = """
    SchedulerScreen { padding: 1 2; }
    #sched-table { height: 1fr; }
    .sched-form { height: 5; margin: 1 0; layout: horizontal; }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold]调度任务管理[/bold]\n[dim]选择行后可修改调度频率（cron表达式）[/dim]")
        yield DataTable(id="sched-table", cursor_type="row")
        with Horizontal(classes="sched-form"):
            yield Label("修改频率 →", classes="row-label")
            yield Input(placeholder="cron: 分 时 日 月 周", id="cron-input")
            yield Button("✓ 应用", variant="primary", id="btn-apply-cron")
            yield Button("▶ 立即触发", id="btn-trigger-now")
        yield RichLog(id="sched-log", highlight=True)

    def on_mount(self) -> None:
        self.call_after_refresh(self._setup)

    def _setup(self) -> None:
        table = self.query_one("#sched-table", DataTable)
        table.add_columns("数据源", "状态", "调度频率", "下次运行", "上次消息")
        self._refresh()

    def _refresh(self) -> None:
        try:
            from scheduler.scheduler import get_scheduler
            jobs = get_scheduler().get_all_jobs_info()
            table = self.query_one("#sched-table", DataTable)
            table.clear()
            for j in jobs:
                enabled = "✅" if j.get("enabled") else "⭕"
                status_colors = {"running": "yellow", "ok": "green", "error": "red",
                                 "idle": "dim", "never": "dim"}
                st = Text(j.get("status","idle"),
                          style=status_colors.get(j.get("status","idle"), "dim"))
                table.add_row(
                    j["source"], st, j.get("schedule",""),
                    j.get("next_run","—"), j.get("message","")[:40]
                )
        except Exception:
            pass

    @on(Button.Pressed, "#btn-apply-cron")
    def apply_cron(self) -> None:
        table = self.query_one("#sched-table", DataTable)
        if table.cursor_row < 0:
            return
        source = str(table.get_cell_at((table.cursor_row, 0)))
        cron = self.query_one("#cron-input", Input).value.strip()
        if not cron:
            return
        try:
            from scheduler.scheduler import get_scheduler
            get_scheduler().update_schedule(source, cron)
            log = self.query_one("#sched-log", RichLog)
            log.write(f"[green]✓ {source} 调度已更新: {cron}[/green]")
            self._refresh()
        except Exception as e:
            self.query_one("#sched-log", RichLog).write(f"[red]错误: {e}[/red]")

    @on(Button.Pressed, "#btn-trigger-now")
    def trigger_now(self) -> None:
        table = self.query_one("#sched-table", DataTable)
        if table.cursor_row < 0:
            return
        source = str(table.get_cell_at((table.cursor_row, 0)))
        from scheduler.scheduler import get_scheduler
        get_scheduler().trigger_now(source)
        log = self.query_one("#sched-log", RichLog)
        log.write(f"[yellow]▶ 已触发 {source} 更新[/yellow]")


# ── 设置页 ────────────────────────────────────────────────────

class SettingsScreen(Container):
    """设置页"""

    DEFAULT_CSS = """
    SettingsScreen { padding: 1 2; }
    .setting-row { height: 3; layout: horizontal; margin-bottom: 1; }
    .setting-label { width: 22; padding-top: 1; }
    .setting-input { width: 40; }
    """

    def compose(self) -> ComposeResult:
        from utils.config_loader import get_config
        cfg = get_config()

        yield Label("[bold]⚙ 系统设置[/bold]\n", markup=True)

        yield Label("[dim]── 主题 ─────────────────────────────────[/dim]")
        with Horizontal(classes="setting-row"):
            yield Label("界面主题:", classes="setting-label")
            yield Select(
                [("跟随系统", "system"), ("深色", "dark"), ("浅色", "light")],
                value=cfg.theme,
                id="sel-theme",
            )

        yield Label("\n[dim]── MaxMind GeoLite2 ──────────────────────[/dim]")
        with Horizontal(classes="setting-row"):
            yield Label("License Key:", classes="setting-label")
            yield Input(
                value=(cfg.get_source("geoip") or {}).get("license_key", ""),
                placeholder="YOUR_MAXMIND_LICENSE_KEY_HERE",
                id="inp-maxmind",
                password=True,
            )

        yield Label("\n[dim]── 路径配置 ──────────────────────────────[/dim]")
        with Horizontal(classes="setting-row"):
            yield Label("项目根目录:", classes="setting-label")
            yield Input(value=cfg.base_dir, id="inp-basedir")
        with Horizontal(classes="setting-row"):
            yield Label("GDrive同步目录:", classes="setting-label")
            yield Input(value=cfg.gdrive_sync_dir, id="inp-gdrive")

        yield Button("💾 保存设置", variant="primary", id="btn-save-settings")

    @on(Select.Changed, "#sel-theme")
    def theme_changed(self, event: Select.Changed) -> None:
        theme = event.value
        app = self.app
        if theme == "dark":
            app.dark = True
        elif theme == "light":
            app.dark = False
        else:
            import darkdetect
            try:
                app.dark = darkdetect.isDark()
            except Exception:
                app.dark = True

    @on(Button.Pressed, "#btn-save-settings")
    def save_settings(self) -> None:
        try:
            from utils.config_loader import get_config
            cfg = get_config()

            maxmind = self.query_one("#inp-maxmind", Input).value.strip()
            if maxmind:
                cfg.set_maxmind_key(maxmind)

            self.notify("✅ 设置已保存")
        except Exception as e:
            self.notify(f"❌ 保存失败: {e}", severity="error")


# ── 报告历史页 ────────────────────────────────────────────────

class ReportsScreen(Container):
    """历史报告列表页"""

    DEFAULT_CSS = """
    ReportsScreen { padding: 1 2; }
    #reports-table { height: 1fr; }
    """


    def compose(self) -> ComposeResult:
        yield Label("[bold]📊 历史报告[/bold]  [dim]双击打开[/dim]")
        yield DataTable(id="reports-table", cursor_type="row")
        yield Button("🔄 刷新", id="btn-refresh-reports")

    def on_mount(self) -> None:
        self.call_after_refresh(self._setup)

    def _setup(self) -> None:
        table = self.query_one("#reports-table", DataTable)
        table.add_columns("文件名", "类型", "大小", "时间", "路径")
        self._refresh()

    def _refresh(self) -> None:
        from utils.config_loader import get_config
        cfg = get_config()
        reports_dir = os.path.join(cfg.base_dir, "reports")
        table = self.query_one("#reports-table", DataTable)
        table.clear()

        if not os.path.exists(reports_dir):
            return

        files = []
        for f in os.listdir(reports_dir):
            fp = os.path.join(reports_dir, f)
            if os.path.isfile(fp):
                stat = os.stat(fp)
                files.append((f, fp, stat.st_size, stat.st_mtime))

        files.sort(key=lambda x: x[3], reverse=True)
        for fname, fpath, size, mtime in files[:50]:
            ext = fname.split(".")[-1].upper()
            size_str = f"{size/1024:.1f} KB"
            time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            table.add_row(fname, ext, size_str, time_str, fpath)

    @on(DataTable.RowSelected, "#reports-table")
    def open_report(self, event: DataTable.RowSelected) -> None:
        try:
            path = str(event.data_table.get_cell_at((event.cursor_row, 4)))
            import webbrowser
            webbrowser.open(f"file:///{path.replace(os.sep, '/')}")
        except Exception:
            pass

    @on(Button.Pressed, "#btn-refresh-reports")
    def on_refresh_clicked(self) -> None:
        self._refresh()


# ── 主 App ────────────────────────────────────────────────────

class NetworkIntelApp(App):
    """NetworkIntel 主程序"""

    TITLE = "🌐 NetworkIntel"
    CSS = """
    Screen {
        background: $background;
    }
    Header {
        background: $primary-darken-3;
    }
    TabbedContent {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "退出"),
        Binding("f1", "show_tab('query')",    "查询",    show=True),
        Binding("f2", "show_tab('batch')",    "批量",    show=True),
        Binding("f3", "show_tab('sources')",  "数据源",  show=True),
        Binding("f4", "show_tab('scheduler')", "调度",   show=True),
        Binding("f5", "show_tab('reports')",  "报告",    show=True),
        Binding("f6", "show_tab('settings')", "设置",    show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="query", id="tabs"):
            with TabPane("🔍 查询 [F1]", id="query"):
                yield QueryScreen()
            with TabPane("📦 批量 [F2]", id="batch"):
                yield BatchScreen()
            with TabPane("🗄 数据源 [F3]", id="sources"):
                yield SourcesScreen()
            with TabPane("⏰ 调度 [F4]", id="scheduler"):
                yield SchedulerScreen()
            with TabPane("📊 报告 [F5]", id="reports"):
                yield ReportsScreen()
            with TabPane("⚙ 设置 [F6]", id="settings"):
                yield SettingsScreen()
        yield Footer()

    def on_mount(self) -> None:
        """程序启动：初始化数据库，启动调度器，检查数据健康"""
        self._init_app()

    @work(thread=True)
    def _init_app(self) -> None:
        try:
            from utils.config_loader import get_config
            from utils.schema import init_db
            from scheduler.scheduler import get_scheduler

            cfg = get_config()
            init_db(cfg.db_path)

            # 检查数据库是否为空，给出提示
            from query.engine import get_source_status
            statuses = get_source_status()
            never_inited = [s for s in statuses if s.get("status") == "never"]
            if len(never_inited) == len(statuses) or not statuses:
                self.notify(
                    "⚠️ 数据库为空！请点击「数据源」页面的「全部更新」初始化数据。",
                    severity="warning",
                    timeout=10,
                )

            # 启动调度器
            sched = get_scheduler()
            sched.start()

            # 注册调度状态回调
            from scheduler.scheduler import register_update_callback
            register_update_callback(self._on_scheduler_update)

        except Exception as e:
            self.notify(f"初始化错误: {e}", severity="error")

    def _on_scheduler_update(self, source: str, status: str, message: str) -> None:
        self.post_message(SchedulerStatus(source, status, message))

    def on_scheduler_status(self, msg: SchedulerStatus) -> None:
        if msg.status == "ok":
            self.notify(f"✅ {msg.source} 更新完成", timeout=3)
        elif msg.status == "error":
            self.notify(f"❌ {msg.source} 更新失败: {msg.message}",
                        severity="error", timeout=5)

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab_id

    def _detect_theme(self) -> bool:
        """检测系统主题，返回 True = 深色"""
        try:
            import darkdetect
            return darkdetect.isDark()
        except Exception:
            return True

    def on_load(self) -> None:
        from utils.config_loader import get_config
        cfg = get_config()
        if cfg.theme == "dark":
            self.dark = True
        elif cfg.theme == "light":
            self.dark = False
        else:
            self.dark = self._detect_theme()


def main():
    """程序入口"""
    # 确保工作目录正确
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    os.chdir(script_dir)

    app = NetworkIntelApp()
    app.run()


if __name__ == "__main__":
    main()
