"""
NetworkIntel - 统一 Provider 层（兼容脚手架）
=============================================
本包为「附加层」，当前**未接入**现有运行链路（scheduler / query.engine / do_update 仍用旧 plugin_registry）。
目的：为未来逐步纳管下载型与在线查询型数据源提供统一抽象。

导入本包是惰性的：不会读取配置、不联网、不实例化任何插件。
入口：providers.registry.get_provider_registry()

详见 docs/API_PROVIDER_SPEC.md
"""
