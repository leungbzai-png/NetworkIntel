# -*- coding: utf-8 -*-
"""
NetworkIntel - 地图可视化模块
基于 Leaflet + OpenStreetMap (国际版 tile)，QtWebEngine 渲染。

设计要点：
  - OSM 国际版 tile，对所有国家/地区中性显示
  - 国旗使用 flagcdn.com（ISO 3166-1 alpha-2，TW 即青天白日满地红）
  - 数据库中的 country_code 已经是 ISO 标准（CN/TW/HK 各自独立）
  - 整个模块可选加载，QtWebEngine 缺失时优雅降级
"""
from __future__ import annotations

import json
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout

# QtWebEngine 是可选依赖，加载失败的话 MapWidget = None
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    WEBENGINE_OK = True
    WEBENGINE_ERR = ""
except Exception as _e:
    WEBENGINE_OK = False
    WEBENGINE_ERR = str(_e)


# ── 内嵌的 Leaflet 地图 HTML ──────────────────────────────────
# 注意：
#   - tile 用 OSM 国际版（tile.openstreetmap.org）
#   - 国旗从 flagcdn.com 加载（CDN，离线时会显示文字代码）
#   - 风险等级颜色与 main_gui.py 同步
MAP_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>NetworkIntel Map</title>
<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  html, body { margin:0; padding:0; height:100%; width:100%;
               font-family: -apple-system, "Segoe UI", "PingFang SC",
                            "Microsoft YaHei", sans-serif; }
  #map { height: 100%; width: 100%; }
  .legend { background:rgba(255,255,255,0.92); padding:8px 10px;
            border-radius:8px; font-size:12px; line-height:1.6;
            box-shadow:0 2px 8px rgba(0,0,0,0.15); }
  .legend .dot { display:inline-block; width:10px; height:10px;
                 border-radius:50%; margin-right:6px; vertical-align:middle; }
  .popup-ip { font-family: ui-monospace, Menlo, Consolas, monospace;
              font-size:13px; font-weight:600; }
  .popup-row { font-size:12px; margin-top:3px; color:#374151; }
  .popup-flag { width:22px; height:14px; vertical-align:middle;
                margin-right:5px; border:1px solid #ddd; }
  .popup-risk { display:inline-block; padding:1px 8px; border-radius:4px;
                color:#fff; font-size:11px; font-weight:600; }
  .empty-hint { position:absolute; top:50%; left:50%;
                transform:translate(-50%,-50%);
                color:#9CA3AF; font-size:14px; pointer-events:none; }
</style>
</head>
<body>
<div id="map"></div>
<div id="hint" class="empty-hint">暂无可定位的查询结果（需要有地理位置数据）</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const RISK_COLORS = {
  critical: "#DC2626",
  high:     "#EA580C",
  medium:   "#D97706",
  low:      "#2563EB",
  info:     "#2563EB",
  clean:    "#16A34A",
};
const RISK_LABELS = {
  critical: "严重", high: "高危", medium: "中危",
  low: "低危", info: "注意", clean: "正常"
};

const map = L.map('map', {
  worldCopyJump: true,
  minZoom: 2,
}).setView([20, 10], 2);

L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18,
  attribution: '© OpenStreetMap',
}).addTo(map);

// 图例
const legend = L.control({ position: 'bottomleft' });
legend.onAdd = function() {
  const div = L.DomUtil.create('div', 'legend');
  let html = '<b>风险等级</b><br/>';
  for (const k of ['critical','high','medium','low','clean']) {
    html += `<span class="dot" style="background:${RISK_COLORS[k]}"></span>${RISK_LABELS[k]}<br/>`;
  }
  div.innerHTML = html;
  return div;
};
legend.addTo(map);

let markerGroup = L.layerGroup().addTo(map);

function safeText(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[<>&"]/g, c => ({
    '<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'
  }[c]));
}

window.updateMarkers = function(points) {
  markerGroup.clearLayers();

  const hint = document.getElementById('hint');
  if (!points || points.length === 0) {
    hint.style.display = 'block';
    return;
  }
  hint.style.display = 'none';

  const bounds = [];
  // 按 lat,lng 微小抖动避免重叠
  const seen = {};
  for (const p of points) {
    if (typeof p.lat !== 'number' || typeof p.lng !== 'number') continue;
    let lat = p.lat, lng = p.lng;
    const key = lat.toFixed(2)+','+lng.toFixed(2);
    seen[key] = (seen[key] || 0) + 1;
    if (seen[key] > 1) {
      // 圆形偏移避免完全重叠
      const angle = (seen[key] * 0.7);
      lat += 0.15 * Math.cos(angle);
      lng += 0.15 * Math.sin(angle);
    }

    const color = RISK_COLORS[p.risk] || '#6B7280';
    const marker = L.circleMarker([lat, lng], {
      radius: 7,
      color: '#fff',
      weight: 1.5,
      fillColor: color,
      fillOpacity: 0.85,
    });

    const cc = (p.country_code || '').toLowerCase();
    const flagHtml = cc && cc.length === 2
      ? `<img class="popup-flag" src="https://flagcdn.com/24x18/${cc}.png" alt="${cc}" onerror="this.style.display='none'"/>`
      : '';
    const riskBg = RISK_COLORS[p.risk] || '#6B7280';
    const riskLbl = RISK_LABELS[p.risk] || (p.risk || '');

    const popup = `
      <div class="popup-ip">${safeText(p.ip)}</div>
      <div class="popup-row">
        ${flagHtml}
        ${safeText(p.country_code || '')} ${safeText(p.country_name || '')}
        ${p.city ? ' · ' + safeText(p.city) : ''}
      </div>
      <div class="popup-row">
        <span class="popup-risk" style="background:${riskBg}">${safeText(riskLbl)}</span>
        ${p.asn ? '· AS' + safeText(p.asn) : ''}
        ${p.as_name ? ' · ' + safeText(p.as_name) : ''}
      </div>
      ${p.threats > 0 ? `<div class="popup-row" style="color:#DC2626">⚠ ${p.threats} 条威胁</div>` : ''}
    `;
    marker.bindPopup(popup);
    markerGroup.addLayer(marker);
    bounds.push([lat, lng]);
  }

  if (bounds.length > 0) {
    if (bounds.length === 1) {
      map.setView(bounds[0], 6);
    } else {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 6 });
    }
  }
};

// 主题切换接口（暂时只切换图例背景）
window.setDarkMode = function(dark) {
  document.body.style.background = dark ? '#0F1115' : '#fff';
};

// 通知 Python：地图已就绪
window.mapReady = true;
</script>
</body>
</html>
"""


# ╔════════════════════════════════════════════════════════════╗
# ║                       MapWidget                            ║
# ╚════════════════════════════════════════════════════════════╝

class MapPlaceholder(QWidget):
    """QtWebEngine 不可用时的占位"""
    def __init__(self, msg: str, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 40, 40, 40)
        title = QLabel("地图功能不可用")
        title.setStyleSheet("font-size:18px; font-weight:600; color:#DC2626;")
        info = QLabel(
            "需要安装 QtWebEngine 才能使用地图功能：\n\n"
            "    pip install PySide6-Addons\n\n"
            "通常 PySide6 完整安装包已含此组件。\n"
            f"加载错误: {msg}"
        )
        info.setStyleSheet("color:#6B7280; font-size:13px;")
        info.setWordWrap(True)
        v.addWidget(title)
        v.addWidget(info)
        v.addStretch(1)


if WEBENGINE_OK:

    class MapWidget(QWidget):
        """Leaflet 地图组件，通过 setHtml 加载内嵌 HTML，调用 updateMarkers 推数据"""

        def __init__(self, parent=None):
            super().__init__(parent)
            v = QVBoxLayout(self)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(6)

            # 工具栏
            bar = QHBoxLayout()
            bar.setContentsMargins(6, 6, 6, 0)
            self.info_label = QLabel("地图视图  ·  需要联网加载 tile / 国旗")
            self.info_label.setStyleSheet("color:#6B7280; font-size:12px;")
            self.btn_reload = QPushButton("⟳ 重新加载")
            self.btn_reload.setMaximumWidth(110)
            self.btn_reload.clicked.connect(self._reload)
            bar.addWidget(self.info_label, 1)
            bar.addWidget(self.btn_reload)
            v.addLayout(bar)

            # WebEngine
            self.view = QWebEngineView()
            try:
                s = self.view.settings()
                s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
                s.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
            except Exception:
                pass
            v.addWidget(self.view, 1)

            self._pending_points: Optional[list] = None
            self._ready = False
            # 页面加载完成后才能调 JS
            self.view.loadFinished.connect(self._on_loaded)
            self.view.setHtml(MAP_HTML, QUrl("https://localhost/"))

        def _on_loaded(self, ok: bool):
            self._ready = ok
            if ok and self._pending_points is not None:
                self.set_points(self._pending_points)
                self._pending_points = None

        def _reload(self):
            self.view.setHtml(MAP_HTML, QUrl("https://localhost/"))

        def set_points(self, results: list):
            """results: 来自 query_batch 的列表，自动提取 lat/lng/risk/asn"""
            points = []
            for r in results or []:
                if not isinstance(r, dict):
                    continue
                if r.get("error"):
                    continue
                geo = r.get("geoip") or {}
                lat, lng = geo.get("latitude"), geo.get("longitude")
                if lat is None or lng is None:
                    continue
                asn = r.get("asn") or {}
                points.append({
                    "ip":           r.get("ip") or "",
                    "lat":          float(lat),
                    "lng":          float(lng),
                    "risk":         r.get("risk_level") or "clean",
                    "country_code": geo.get("country_code") or "",
                    "country_name": geo.get("country_name") or "",
                    "city":         geo.get("city") or "",
                    "asn":          asn.get("asn") or "",
                    "as_name":      asn.get("as_name") or asn.get("description") or "",
                    "threats":      len(r.get("threats") or []),
                })

            # 标题更新
            n_total = sum(1 for r in (results or []) if isinstance(r, dict) and not r.get("error"))
            self.info_label.setText(
                f"地图视图  ·  共 {n_total} 个结果，{len(points)} 个已定位  ·  "
                "需要联网加载 tile / 国旗"
            )

            payload = json.dumps(points, ensure_ascii=False)
            js = f"if(window.updateMarkers) window.updateMarkers({payload});"
            if self._ready:
                self.view.page().runJavaScript(js)
            else:
                # 还没就绪，先存起来
                self._pending_points = results

        def clear(self):
            self.set_points([])

else:

    # QtWebEngine 不可用时的兜底
    class MapWidget(QWidget):  # type: ignore[no-redef]
        def __init__(self, parent=None):
            super().__init__(parent)
            v = QVBoxLayout(self)
            v.addWidget(MapPlaceholder(WEBENGINE_ERR, self))

        def set_points(self, results: list):
            pass

        def clear(self):
            pass


def is_map_available() -> bool:
    return WEBENGINE_OK
