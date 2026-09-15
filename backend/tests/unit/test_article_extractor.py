"""网页正文提取单元测试。

覆盖三类逻辑：
1. HTML 解析：优先取 <p> 段落、剔除 script/style、过滤导航碎片
2. 质量判定：页脚版权内容要能被识别为"无效正文"
3. 抓取流程：正常抓取 / 内容过短 / 网络异常 / 并发抓取
"""

import httpx
import pytest

from app.services import article_extractor as ae

# 一段"足够长"的正文（超过 _MIN_TEXT_LEN = 250 字）
LONG_TEXT = "广州今天有雷阵雨，出门记得带伞，尽量避免长时间户外活动。" * 20


class TestArticleParser:
    def test_优先取p段落并过滤短碎片(self):
        html = """
        <html><body>
          <nav><a href="/">首页</a></nav>
          <p>广州今天有雷阵雨，出门记得带伞，尽量避免长时间户外活动。</p>
          <p>明天降水减弱，气温回升到三十三度左右，注意防晒补水别中暑。</p>
        </body></html>
        """
        parser = ae._ArticleParser()
        parser.feed(html)
        text = parser.text()
        assert "雷阵雨" in text
        assert "首页" not in text  # 导航短文本应被过滤

    def test_script与style内容被忽略(self):
        html = (
            "<html><head><style>.a{color:red}</style></head><body>"
            "<script>var x=1;</script>"
            "<p>这是一段足够长的正文内容，用来通过最小长度校验，确保提取逻辑正常。</p>"
            "</body></html>"
        )
        parser = ae._ArticleParser()
        parser.feed(html)
        text = parser.text()
        assert "color:red" not in text
        assert "var x" not in text

    def test_p段落不足时退化为全文提取(self):
        """非典型新闻页（p 很少）应退化为全文提取，避免漏掉内容。"""
        html = (
            "<html><body><div>"
            "这是一段放在 div 里而不是 p 里的长文本内容，用于验证退化提取路径是否生效。"
            "</div></body></html>"
        )
        parser = ae._ArticleParser()
        parser.feed(html)
        assert "退化提取路径" in parser.text()


class TestJunkDetection:
    def test_页脚版权内容被判为无效(self):
        junk = (
            "主办单位：广州市气象局 联系方式：020-31166661 "
            "粤公网安备44010602000929号 网站标识码：4401000004"
        )
        assert ae._looks_like_junk(junk) is True

    def test_长正文不会被误伤(self):
        """篇幅够长时即使出现个别特征词，也不应判为垃圾。"""
        assert ae._looks_like_junk("广州天气很好适合出门走走。" * 100) is False

    def test_普通短文本不算垃圾(self):
        assert ae._looks_like_junk("今天多云转晴气温适宜") is False


class TestFetchArticleText:
    async def test_正常抓取正文(self, respx_mock):
        html = f"<html><body><p>{LONG_TEXT}</p></body></html>"
        respx_mock.get("https://example.com/a").mock(
            return_value=httpx.Response(
                200, headers={"content-type": "text/html; charset=utf-8"}, text=html
            )
        )
        text = await ae.fetch_article_text("https://example.com/a")
        assert "雷阵雨" in text

    async def test_内容过短视为失败(self, respx_mock):
        respx_mock.get("https://example.com/short").mock(
            return_value=httpx.Response(
                200, headers={"content-type": "text/html"}, text="<p>太短了</p>"
            )
        )
        assert await ae.fetch_article_text("https://example.com/short") == ""

    async def test_抓到页脚版权也判为失败(self, respx_mock):
        junk_html = (
            "<html><body><p>主办单位：广州市气象局 联系方式：020-31166661</p>"
            "<p>粤公网安备44010602000929号 网站标识码：4401000004 版权所有</p></body></html>"
        )
        respx_mock.get("https://example.com/junk").mock(
            return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=junk_html)
        )
        assert await ae.fetch_article_text("https://example.com/junk") == ""

    async def test_网络异常返回空字符串(self, respx_mock):
        respx_mock.get("https://example.com/err").mock(side_effect=httpx.ConnectError("boom"))
        assert await ae.fetch_article_text("https://example.com/err") == ""

    async def test_空URL直接返回空(self):
        assert await ae.fetch_article_text("") == ""

    async def test_并发抓取返回成功项(self, respx_mock):
        html = f"<html><body><p>{LONG_TEXT}</p></body></html>"
        respx_mock.get("https://example.com/0").mock(
            return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=html)
        )
        respx_mock.get("https://example.com/1").mock(side_effect=httpx.ConnectError("boom"))
        result = await ae.fetch_article_texts(["https://example.com/0", "https://example.com/1"])
        assert list(result.keys()) == ["https://example.com/0"]

    async def test_空列表返回空字典(self):
        assert await ae.fetch_article_texts([]) == {}


class TestDecode:
    """编码兜底：中文站点常见 UTF-8 / GBK，解错会满屏乱码。"""

    def test_优先使用响应头声明的编码(self):
        r = httpx.Response(
            200,
            headers={"content-type": "text/html; charset=gb18030"},
            content="<p>中文编码测试内容足够长通过校验。</p>".encode("gb18030"),
        )
        assert "中文编码测试" in ae._decode(r)

    def test_无编码声明时回退UTF8(self):
        r = httpx.Response(200, content="<p>中文内容测试</p>".encode())
        assert "中文内容测试" in ae._decode(r)

    def test_GBK字节在无声明时也能解出(self):
        """响应头没写编码、内容又是 GBK 时，应靠兜底解码救回来。"""
        r = httpx.Response(200, content="<p>广州天气</p>".encode("gb18030"))
        assert "广州天气" in ae._decode(r)


@pytest.mark.parametrize("raw", ["", "短", "not html at all"])
def test_解析异常输入不抛错(raw):
    """健壮性：任何字符串输入都不应让解析器崩溃。"""
    parser = ae._ArticleParser()
    parser.feed(raw)
    assert isinstance(parser.text(), str)
