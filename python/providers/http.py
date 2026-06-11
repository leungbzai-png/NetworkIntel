"""
NetworkIntel - Provider HTTP 工具层（http）
==========================================
供所有 OnlineQueryProvider 复用的统一 HTTP GET 封装：
  * timeout / User-Agent
  * 429 与 5xx 简单重试（指数退避，尊重 Retry-After）
  * JSON 解析
  * 网络异常 / 超时 / HTTP 错误 → 统一失败对象 HttpResult（不向上抛异常）
  * 不记录任何请求头/密钥（无日志副作用）

导入惰性：requests 在函数内按需导入；本模块顶层仅依赖 stdlib。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional


DEFAULT_USER_AGENT = "NetworkIntel/1.0 (+https://github.com/local/networkintel)"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_TEXT = 2000  # 失败时保留的响应文本上限，避免膨胀


@dataclass
class HttpResult:
    """统一的 HTTP 结果对象。失败时 ok=False 且 error 非空。"""
    ok: bool
    status: Optional[int]
    json: Any
    text: Optional[str]
    error: Optional[str]
    url: str
    attempts: int
    elapsed: float


def _safe_text(resp) -> Optional[str]:
    try:
        return (resp.text or "")[:_MAX_TEXT]
    except Exception:
        return None


def _wait_seconds(backoff: float, attempt: int, retry_after: Optional[str]) -> float:
    """计算退避等待：优先 Retry-After，否则指数退避。"""
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except (TypeError, ValueError):
            pass
    return backoff * (2 ** (attempt - 1))


def http_get_json(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 15.0,
    max_retries: int = 3,
    backoff: float = 0.5,
    user_agent: str = DEFAULT_USER_AGENT,
    expect_json: bool = True,
) -> HttpResult:
    """
    执行 GET 请求并（可选）解析 JSON。任何异常都被吞掉并转为 HttpResult(ok=False)。
    headers 可包含鉴权头；本函数不会记录/打印它们。
    """
    start = time.time()

    try:
        import requests  # 惰性导入，保持模块导入轻量
    except Exception as e:  # 依赖缺失也不崩
        return HttpResult(False, None, None, None,
                          f"requests 不可用: {type(e).__name__}",
                          url, 0, time.time() - start)

    merged_headers = {"User-Agent": user_agent}
    if expect_json:
        merged_headers["Accept"] = "application/json"
    if headers:
        merged_headers.update(headers)

    last_err = None
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            resp = requests.get(url, params=params, headers=merged_headers, timeout=timeout)
            status = resp.status_code

            if status in _RETRYABLE_STATUS:
                last_err = f"HTTP {status}"
                if attempt < max_retries:
                    time.sleep(_wait_seconds(backoff, attempt, resp.headers.get("Retry-After")))
                    continue
                return HttpResult(False, status, None, _safe_text(resp),
                                  f"HTTP {status}（重试 {attempt} 次后仍失败）",
                                  url, attempt, time.time() - start)

            if not (200 <= status < 300):
                return HttpResult(False, status, None, _safe_text(resp),
                                  f"HTTP {status}", url, attempt, time.time() - start)

            if not expect_json:
                return HttpResult(True, status, None, _safe_text(resp),
                                  None, url, attempt, time.time() - start)

            try:
                data = resp.json()
            except Exception as e:
                return HttpResult(False, status, None, _safe_text(resp),
                                  f"JSON 解析失败: {type(e).__name__}",
                                  url, attempt, time.time() - start)
            return HttpResult(True, status, data, None, None, url, attempt, time.time() - start)

        except Exception as e:
            # 网络异常 / 超时 / DNS 等
            last_err = f"{type(e).__name__}: {e}"
            if attempt < max_retries:
                time.sleep(backoff * (2 ** (attempt - 1)))
                continue
            return HttpResult(False, None, None, None, last_err, url, attempt, time.time() - start)

    return HttpResult(False, None, None, None, last_err or "未知错误",
                      url, attempt, time.time() - start)
