from __future__ import annotations

import html
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Any


logger = logging.getLogger("ai_interview.crawler")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT_SECONDS = 8
MAX_RESULTS = 4
MAX_CONTENT_LENGTH = 2 * 1024 * 1024

# 只允许访问常见文档/搜索站点，防止模型诱导后端访问任意 URL（执行手册 0.4 安全规则）。
ALLOWED_HOSTS = {
    "stackoverflow.com",
    "learn.microsoft.com",
    "docs.python.org",
    "developer.mozilla.org",
    "github.com",
    "juejin.cn",
    "cn.bing.com",
    "www.bing.com",
}

_ITEM_PATTERN = re.compile(
    r'<li class="b_algo".*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>(.*?)</li>',
    re.S,
)
_SNIPPET_PATTERN = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
_TAG_PATTERN = re.compile(r"<[^>]+>")


class CrawlerError(RuntimeError):
    """抓取失败时的统一错误；调用方静默降级，不阻塞面试流程。"""


def _strip_tags(fragment: str) -> str:
    return html.unescape(_TAG_PATTERN.sub("", fragment)).strip()


def _safe_host(url: str) -> str | None:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return None
    host = host.lower()
    for allowed in ALLOWED_HOSTS:
        if host == allowed or host.endswith("." + allowed):
            return allowed
    return None


def search_learning_resources(query: str, limit: int = MAX_RESULTS) -> list[dict[str, Any]]:
    """抓取 Bing 搜索结果页（静态 HTML），提取标题、链接与摘要。

    赛题三功能 6：Agent 通过 Function Call 调用爬虫获取外部学习资源。
    失败抛 CrawlerError，由工具执行层捕获后返回空列表降级。
    """
    keyword = str(query or "").strip()
    if not keyword:
        raise CrawlerError("检索关键词为空")
    limit = max(1, min(int(limit), MAX_RESULTS))
    search_url = (
        "https://cn.bing.com/search?"
        + urllib.parse.urlencode({"q": f"{keyword} 学习资源 教程", "count": "12", "setlang": "zh-hans"})
    )
    started = time.perf_counter()
    request = urllib.request.Request(search_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content = response.read(MAX_CONTENT_LENGTH).decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("crawler.search error=%s query_len=%d", type(exc).__name__, len(keyword))
        raise CrawlerError("学习资源抓取失败") from exc

    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for match in _ITEM_PATTERN.finditer(content):
        raw_url, title, body = match.groups()
        url = html.unescape(raw_url).strip()
        if not url.startswith("http") or url in seen_urls:
            continue
        if _safe_host(url) is None:
            continue
        snippet_match = _SNIPPET_PATTERN.search(body)
        snippet = _strip_tags(snippet_match.group(1)) if snippet_match else ""
        results.append(
            {
                "title": _strip_tags(title)[:80],
                "url": url,
                "snippet": snippet[:160],
                "source_host": _safe_host(url),
            }
        )
        seen_urls.add(url)
        if len(results) >= limit:
            break
    logger.info(
        "crawler.search elapsed_ms=%d results=%d query_len=%d",
        int((time.perf_counter() - started) * 1000),
        len(results),
        len(keyword),
    )
    return results
