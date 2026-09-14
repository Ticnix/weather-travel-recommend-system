"""对话历史服务测试：落库、上下文读取、会话列表、删除。

这套用例覆盖 Day 26 新增的"历史对话"能力，
其中**会话列表的分组逻辑**（标题取最早一条用户提问）最容易写错，是重点。

注意：`chat_messages.user_id` 有外键约束，测试必须先造用户。
"""

import pytest_asyncio

from app.models.user import User
from app.services import chat_history_service as chs


@pytest_asyncio.fixture
async def uid(db) -> int:
    """创建一个测试用户并返回其 id（满足 chat_messages 的外键约束）。"""
    user = User(username="chat_tester", password_hash="not-a-real-hash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


@pytest_asyncio.fixture
async def uid2(db) -> int:
    """第二个用户，用于验证数据隔离。"""
    user = User(username="chat_tester_2", password_hash="not-a-real-hash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


class TestAddMessage:
    async def test_匿名用户不落库(self, db):
        """匿名对话不持久化（user_id 为 None）。"""
        result = await chs.add_message(None, "conv-x", "user", "匿名提问", db=db)
        assert result["saved"] is False
        assert await chs.get_conversation_messages(1, "conv-x", db=db) == []

    async def test_登录用户落库(self, db, uid):
        result = await chs.add_message(uid, "conv-1", "user", "广州天气", db=db)
        assert result["saved"] is True
        assert result["id"] > 0

    async def test_多轮消息按序保存(self, db, uid):
        await chs.add_message(uid, "conv-2", "user", "问题一", db=db)
        await chs.add_message(uid, "conv-2", "assistant", "回答一", db=db)

        history = await chs.get_recent_history(uid, "conv-2", db=db)
        assert [h["role"] for h in history] == ["user", "assistant"]
        assert history[0]["content"] == "问题一"

    async def test_匿名读取历史返回空(self, db):
        assert await chs.get_recent_history(None, "conv-1", db=db) == []

    async def test_不同会话互不串扰(self, db, uid):
        await chs.add_message(uid, "conv-a", "user", "会话A的消息", db=db)
        await chs.add_message(uid, "conv-b", "user", "会话B的消息", db=db)

        a = await chs.get_recent_history(uid, "conv-a", db=db)
        assert len(a) == 1
        assert a[0]["content"] == "会话A的消息"


class TestConversationList:
    """会话列表：按最后活跃时间倒序，标题取**最早一条用户提问**。"""

    async def test_列出多个会话(self, db, uid):
        await chs.add_message(uid, "conv-1", "user", "第一个会话", db=db)
        await chs.add_message(uid, "conv-1", "assistant", "回复", db=db)
        await chs.add_message(uid, "conv-2", "user", "第二个会话", db=db)

        items = await chs.list_conversations(uid, db=db)
        assert len(items) == 2
        assert {i["conversation_id"] for i in items} == {"conv-1", "conv-2"}

    async def test_消息条数统计正确(self, db, uid):
        await chs.add_message(uid, "conv-1", "user", "问", db=db)
        await chs.add_message(uid, "conv-1", "assistant", "答", db=db)
        await chs.add_message(uid, "conv-1", "user", "再问", db=db)

        items = await chs.list_conversations(uid, db=db)
        assert items[0]["count"] == 3

    async def test_标题取最早一条用户提问(self, db, uid):
        """多轮对话中标题应该是**第一句**提问，而不是最后一句。"""
        await chs.add_message(uid, "conv-t", "user", "广州明天天气", db=db)
        await chs.add_message(uid, "conv-t", "assistant", "回复内容", db=db)
        await chs.add_message(uid, "conv-t", "user", "那穿搭呢", db=db)
        await chs.add_message(uid, "conv-t", "assistant", "回复内容2", db=db)

        items = await chs.list_conversations(uid, db=db)
        assert items[0]["title"] == "广州明天天气"

    async def test_标题去掉换行并截断(self, db, uid):
        await chs.add_message(uid, "conv-long", "user", "第一行\n第二行" + "长" * 100, db=db)
        items = await chs.list_conversations(uid, db=db)
        assert "\n" not in items[0]["title"]
        assert len(items[0]["title"]) <= 40

    async def test_按最后活跃时间倒序(self, db, uid):
        await chs.add_message(uid, "conv-old", "user", "旧会话", db=db)
        await chs.add_message(uid, "conv-new", "user", "新会话", db=db)

        items = await chs.list_conversations(uid, db=db)
        assert items[0]["conversation_id"] == "conv-new"

    async def test_只返回本人的会话(self, db, uid, uid2):
        await chs.add_message(uid, "conv-mine", "user", "我的", db=db)
        await chs.add_message(uid2, "conv-other", "user", "别人的", db=db)

        items = await chs.list_conversations(uid, db=db)
        assert [i["conversation_id"] for i in items] == ["conv-mine"]

    async def test_时间字段可序列化(self, db, uid):
        await chs.add_message(uid, "conv-1", "user", "内容", db=db)
        items = await chs.list_conversations(uid, db=db)
        # 必须是 ISO 字符串（能直接塞进 JSON 响应）
        assert isinstance(items[0]["last_at"], str)
        assert "T" in items[0]["last_at"]

    async def test_无会话返回空列表(self, db, uid):
        assert await chs.list_conversations(uid, db=db) == []

    async def test_匿名为空(self, db):
        assert await chs.list_conversations(None, db=db) == []


class TestConversationMessages:
    async def test_按时间正序返回(self, db, uid):
        await chs.add_message(uid, "conv-1", "user", "第一句", db=db)
        await chs.add_message(uid, "conv-1", "assistant", "第二句", db=db)
        await chs.add_message(uid, "conv-1", "user", "第三句", db=db)

        msgs = await chs.get_conversation_messages(uid, "conv-1", db=db)
        assert [m["content"] for m in msgs] == ["第一句", "第二句", "第三句"]

    async def test_字段完整(self, db, uid):
        await chs.add_message(uid, "conv-1", "user", "内容", db=db)
        msg = (await chs.get_conversation_messages(uid, "conv-1", db=db))[0]
        assert {"id", "role", "content", "created_at"} <= set(msg)

    async def test_他人会话查不到(self, db, uid, uid2):
        await chs.add_message(uid, "conv-1", "user", "私有内容", db=db)
        assert await chs.get_conversation_messages(uid2, "conv-1", db=db) == []

    async def test_匿名为空(self, db):
        assert await chs.get_conversation_messages(None, "conv-1", db=db) == []


class TestDeleteConversation:
    async def test_删除会话返回条数(self, db, uid):
        await chs.add_message(uid, "conv-del", "user", "a", db=db)
        await chs.add_message(uid, "conv-del", "assistant", "b", db=db)

        deleted = await chs.delete_conversation(uid, "conv-del", db=db)
        assert deleted == 2
        assert await chs.get_conversation_messages(uid, "conv-del", db=db) == []

    async def test_不能删除他人会话(self, db, uid, uid2):
        await chs.add_message(uid, "conv-1", "user", "我的", db=db)
        deleted = await chs.delete_conversation(uid2, "conv-1", db=db)
        assert deleted == 0
        assert await chs.get_conversation_messages(uid, "conv-1", db=db)

    async def test_匿名为0(self, db):
        assert await chs.delete_conversation(None, "conv-1", db=db) == 0
