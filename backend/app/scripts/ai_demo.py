"""AI 演示脚本（Day 14）：一键演示 Agent 核心能力。

用法：
    cd backend
    venv\\Scripts\\python.exe -m app.scripts.ai_demo

演示内容：
    1. 天气查询（get_weather 工具）
    2. 穿搭推荐（recommend_outfit Skill）
    3. 出行规划（plan_travel_route Skill，高德真实路线）
    4. 复合场景（天气+穿搭+路线多工具协同）
    5. SSE 流式输出（chat_stream 逐 token）
    6. 多轮对话（省略主语仍理解上下文）

无需启动 FastAPI，直接调用 Agent 服务层，便于面试/演示快速跑通。
"""

from __future__ import annotations

import asyncio

from app.services import agent


def _hr(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


async def demo_single(question: str) -> None:
    result = await agent.chat(question)
    print(f"\n【用户】{question}")
    print(f"【意图】{result['intent']}")
    print(f"【回答】\n{result['answer']}")


async def demo_stream(question: str) -> None:
    print(f"\n【用户】{question}")
    print("【流式输出】", end=" ")
    async for evt in agent.chat_stream(question):
        if evt.get("type") == "intent":
            print(f"\n  (意图: {evt['intent']})", end=" ")
        elif evt.get("type") == "token":
            print(evt["content"], end="", flush=True)
        elif evt.get("type") == "done":
            print("\n  [流式结束]")


async def demo_multi_round() -> None:
    print("\n【多轮对话：第二轮省略主语】")
    history: list[dict] = []
    q1 = "我想去广州塔玩"
    r1 = await agent.chat(q1, history=history)
    print(f"\n  第1轮【用户】{q1}")
    print(f"  第1轮【回答】{r1['answer'][:80]}...")
    history += [{"role": "user", "content": q1}, {"role": "assistant", "content": r1["answer"]}]
    q2 = "那怎么过去比较方便"
    r2 = await agent.chat(q2, history=history)
    print(f"\n  第2轮【用户】{q2}（省略'广州塔'）")
    print(f"  第2轮【回答】{r2['answer'][:120]}...")


async def main() -> None:
    _hr("演示 1 · 天气查询")
    await demo_single("广州今天天气怎么样")

    _hr("演示 2 · 穿搭推荐")
    await demo_single("明天爬山穿什么")

    _hr("演示 3 · 出行规划")
    await demo_single("从广州南站去广州塔怎么走")

    _hr("演示 4 · 复合场景（多工具协同）")
    await demo_single("明天下午去广州塔玩，适合穿什么，怎么去最方便")

    _hr("演示 5 · SSE 流式输出")
    await demo_stream("广州今天天气怎么样")

    _hr("演示 6 · 多轮对话")
    await demo_multi_round()

    print("\n\n✅ 全部演示完成")


if __name__ == "__main__":
    asyncio.run(main())
