# -*- coding: utf-8 -*-
"""
NetworkIntel - 敏感值脱敏（v0.3.0）
=====================================
把可能出现在异常消息 / 日志 / GUI 文案里的密钥类值替换成 ``***``，
避免真实 key/token 通过错误信息泄露。典型场景：

  * MaxMind 下载 URL 形如 ``...&license_key=REALKEY&suffix=zip``，
    下载失败时 requests 异常消息里会带上整段 URL。
  * Authorization / X-Api-Key 请求头出现在异常里。

只做**保守**替换：命中已知敏感参数名/请求头才脱敏，绝不改动普通文本。
纯字符串处理，不联网、不读文件。
"""

import re

# URL query 参数：license_key / token / api_key / apikey / key / secret / password / access_key
_QUERY_PARAM_RE = re.compile(
    r"(?i)\b(license_key|api_key|apikey|access_key|auth_token|token|secret|password)"
    r"(=|%3D)([^&\s\"'<>]+)"
)

# HTTP 头：Authorization: Bearer xxx / X-Api-Key: xxx
# 头值可能带空格（如 "Bearer <token>"），整段（到行尾）脱敏，宁可多脱不漏。
_HEADER_RE = re.compile(
    r"(?i)\b(authorization|x-api-key|x-auth-token)\b(\s*[:=]\s*)(.+)"
)

_REDACTED = "***"


def redact_secrets(text) -> str:
    """返回脱敏后的字符串；输入非字符串时转成 str 再处理。"""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = _QUERY_PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", text)
    text = _HEADER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", text)
    return text
