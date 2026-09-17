"""结构化输出解析测试（Day 40）。

模型永远不会百分百按格式输出，所以「怎么把它的输出解析稳」
必须有测试守着——这些边界情况在真机上都会遇到。
"""

import pytest

from app.services.llm_client import extract_json


class TestExtractJson:
    def test_纯JSON(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_带代码围栏(self):
        text = '好的，结果如下：\n```json\n{"city": "广州"}\n```\n希望有帮助'
        assert extract_json(text) == {"city": "广州"}

    def test_围栏没标语言(self):
        assert extract_json('```\n{"a": 2}\n```') == {"a": 2}

    def test_前后有解释文字(self):
        # 模型爱写"好的，以下是行程："，不该因此让整个功能失败
        assert extract_json('好的，以下是行程：{"days": 2} 以上。') == {"days": 2}

    def test_前后空白(self):
        assert extract_json('   \n {"a": 3} \n  ') == {"a": 3}

    def test_嵌套对象(self):
        text = '{"plan": {"city": "广州", "items": [1, 2]}}'
        assert extract_json(text)["plan"]["items"] == [1, 2]

    def test_空内容报错(self):
        with pytest.raises(ValueError):
            extract_json("")

    def test_没有JSON时报错(self):
        with pytest.raises(ValueError):
            extract_json("抱歉，我无法完成这个请求。")

    def test_截断的JSON报错而不是返回半成品(self):
        # 宁可报错让上层兜底，也不要返回一个字段缺失的对象
        with pytest.raises(ValueError):
            extract_json('{"a": 1, "b": ')
