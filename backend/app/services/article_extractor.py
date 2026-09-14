"""网页正文提取：把外部资讯原文抓成纯文本，供详情页直接阅读。

背景：联网搜索（Tavily）采集的资讯此前只保存搜索摘要、且不设 source_url，
导致详情页既没有 iframe、也看不到完整内容。
更根本的问题是——多数新闻站会设置 `X-Frame-Options` / CSP `frame-ancestors`，
即使补上 source_url，iframe 同样会被浏览器拒绝而显示空白。

因此改为「后端抓正文 → 存库 → 详情页直接渲染」：
不依赖目标站点允许内嵌，阅读体验也更干净。
"""

from __future__ import annotations

import asyncio
import logging
import re
from html.parser import HTMLParser

import httpx

logger = logging.getLogger(__name__)

# 正文段落的最小长度（中文）：用于过滤导航、按钮、版权等短碎片
_MIN_LINE_LEN = 10

# 抓取结果的最小长度：低于该值视为「没抓到真正文」（多为页脚/导航碎片）
_MIN_TEXT_LEN = 250

# 页脚 / 导航特征词：命中多个且篇幅很短时判定为无效正文
_JUNK_MARKERS = (
    "ICP备", "公网安备", "网站标识码", "版权所有",
    "主办单位", "联系方式：", "网站地图", "免责声明",
)


def _looks_like_junk(text: str) -> bool:
    """判断抓到的内容是否只是页脚/导航碎片（而非文章正文）。"""
    if len(text) >= 600:  # 长文本基本是正文，不做特征词误伤
        return False
    return sum(1 for m in _JUNK_MARKERS if m in text) >= 2

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 这些标签内的文本不是正文
_SKIP_TAGS = {
    "script", "style", "noscript", "iframe", "svg", "canvas",
    "nav", "header", "footer", "form", "select", "option", "button",
}

# 块级标签：前后插入换行，保证段落边界
_BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "section", "article", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "pre",
}


class _ArticleParser(HTMLParser):
    """提取 HTML 中的可见文本。

    策略：优先只取 `<p>` 段落（新闻正文通常在 p 里，
    这样能自然滤掉标题栏、导航、时间戳等噪音）；
    若 p 段落过少（非典型新闻页），退化为全文提取。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._all: list[str] = []  # 全量文本
        self._p: list[str] = []  # 仅 <p> 内文本
        self._skip_depth = 0
        self._in_p = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "p":
            self._in_p = True
            self._p.append("\n")
            self._all.append("\n")
        elif tag in _BLOCK_TAGS:
            self._all.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag in _BLOCK_TAGS:
            self._all.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "p":
            self._in_p = False
            self._p.append("\n")
            self._all.append("\n")
        elif tag in _BLOCK_TAGS:
            self._all.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._all.append(data)
            if self._in_p:
                self._p.append(data)

    @staticmethod
    def _clean(raw: str) -> str:
        lines = [ln.strip() for ln in raw.split("\n")]
        lines = [ln for ln in lines if len(ln) >= _MIN_LINE_LEN]
        text = "\n".join(lines)
        text = re.sub(r"[ \t\u3000]{2,}", " ", text)  # 压缩连续空白
        text = re.sub(r"\n{3,}", "\n\n", text)  # 压缩多余空行
        return text.strip()

    def text(self) -> str:
        """整理为「一行一段」的纯文本，并过滤导航类碎片。"""
        p_text = self._clean("".join(self._p))
        if len(p_text) >= 150:
            return p_text
        return self._clean("".join(self._all))


def _decode(resp: httpx.Response) -> str:
    """解码响应体：优先响应头声明的编码，否则按 UTF-8 / GBK 兜底。"""
    if resp.charset_encoding:
        return resp.text
    for enc in ("utf-8", "gb18030"):
        try:
            return resp.content.decode(enc)
        except UnicodeDecodeError:
            continue
    return resp.content.decode("utf-8", errors="ignore")


async def fetch_article_text(
    url: str,
    max_chars: int = 3000,
    timeout: float = 12.0,
) -> str:
    """抓取网页并提取正文文本；失败返回空字符串（调用方走降级逻辑）。"""
    if not url:
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=timeout, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.info("正文抓取失败（%s）: %s", url[:60], exc)
        return ""

    if "html" not in resp.headers.get("content-type", "").lower() and "text" not in resp.headers.get(
        "content-type", ""
    ).lower():
        return ""

    parser = _ArticleParser()
    try:
        parser.feed(_decode(resp))
    except Exception as exc:  # noqa: BLE001
        logger.info("正文解析失败（%s）: %s", url[:60], exc)
        return ""

    text = parser.text()
    # 抓不到实质内容、或只抓到页脚版权，均视为失败（由调用方降级为原文链接）
    if len(text) < _MIN_TEXT_LEN or _looks_like_junk(text):
        return ""
    return text[:max_chars]


async def fetch_article_texts(
    urls: list[str],
    max_chars: int = 3000,
    concurrency: int = 5,
) -> dict[str, str]:
    """并发抓取多个 URL 的正文，返回 {url: text}。失败的 URL 不在结果中。"""
    if not urls:
        return {}

    semaphore = asyncio.Semaphore(concurrency)

    async def _one(u: str) -> tuple[str, str]:
        async with semaphore:
            return u, await fetch_article_text(u, max_chars=max_chars)

    pairs = await asyncio.gather(*(_one(u) for u in urls), return_exceptions=True)
    result: dict[str, str] = {}
    for item in pairs:
        if isinstance(item, BaseException):
            continue
        url, text = item
        if text:
            result[url] = text
    return result
